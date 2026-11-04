"""Tâches planifiées : rapport de blessures NBA, synchronisation des scores, relevé des cotes.

Rapport de blessures : toutes les 30 minutes, de 11h à 23h30 heure US
Eastern (la NBA republie en continu pendant cette plage).

Synchronisation des scores (balldontlie.io) : toutes les 2h de 12h à 2h du
matin heure US Eastern (couvre la plage des matchs + leur fin ; la borne
2h du matin couvre les matchs qui se terminent après minuit ET). Récupère à
chaque exécution hier ET aujourd'hui (couvre un match commencé la veille ET
mais terminé après minuit ET).

Relevé des cotes (the-odds-api.com) : réveil à chaque heure pile ; un appel seulement si un match commence dans
les 3 heures qui suivent (règle écrite une seule fois, sans heure d'arrêt :
app/services/odds_fetcher.py::scheduled_fetch_decision).

L'utilisation du fuseau "America/New_York" (plutôt qu'une conversion figée
vers l'heure française) fait gérer le changement d'heure automatiquement par
APScheduler/zoneinfo, côté US comme côté France.
"""
from __future__ import annotations

import io
import logging
import os
from datetime import timedelta

import pdfplumber
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.database import SessionLocal
from app.models import OddsFetchTrigger
from app.services import nba_calendar, odds_fetcher
from app.services.injury_report_fetcher import fetch_latest_report_bytes
from app.services.injury_report_parser import parse_injury_report_pdf
from app.services.injury_report_updater import apply_injury_report
from app.services.nba_calendar import current_nba_date
from app.services.odds_fetcher import (
    DECISION_CREDITS_LOW,
    DECISION_NO_GAME_SOON,
    MIN_CREDITS_FOR_SCHEDULED,
    run_odds_fetch,
    scheduled_fetch_decision,
)
from app.services.scores_fetcher import sync_scores_for_date

logger = logging.getLogger(__name__)

JOB_ID = "injury_report_refresh"
SCORES_JOB_ID = "scores_sync"
ODDS_JOB_ID = "odds_fetch"


def run_injury_report_job() -> None:
    try:
        pdf_bytes = fetch_latest_report_bytes()
    except Exception:
        logger.exception("Échec de récupération du rapport de blessures")
        return

    if pdf_bytes is None:
        logger.warning("Aucun rapport de blessures trouvé sur la page officielle NBA")
        return

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            entries = parse_injury_report_pdf(pdf)
    except Exception:
        logger.exception("Échec du parsing du rapport de blessures")
        return

    db = SessionLocal()
    try:
        result = apply_injury_report(db, entries)
        db.commit()
        logger.info(
            "Rapport de blessures appliqué : %d joueur(s) mis à jour, %d entrée(s) non rapprochée(s)",
            result.matched_count,
            len(result.unmatched_entries),
        )
    finally:
        db.close()


def run_scores_sync_job() -> None:
    api_key = os.getenv("BALLDONTLIE_API_KEY")
    if not api_key:
        logger.warning("BALLDONTLIE_API_KEY absente : synchronisation des scores ignorée")
        return

    today = current_nba_date()
    db = SessionLocal()
    try:
        for target_date in (today - timedelta(days=1), today):
            try:
                result = sync_scores_for_date(db, api_key, target_date)
                logger.info(
                    "Scores synchronisés pour %s : %d récupéré(s), %d mis à jour, %d ignoré(s), "
                    "%d équipe(s) aux %% de victoires recalculés",
                    target_date,
                    result.found,
                    result.updated,  # uniquement les matchs dont une valeur a changé (limitation n°36)
                    result.skipped_count,
                    result.win_pct_teams_updated,
                )
            except Exception:
                logger.exception("Échec de la synchronisation des scores pour %s", target_date)
    finally:
        db.close()


def run_odds_fetch_job() -> None:
    """Réveil horaire du relevé des cotes : décide (aucun appel s'il n'y a pas de match dans les 3 heures, ou si le
    solde de crédits est sous le seuil), puis relève et journalise. Un appel en échec est journalisé lui aussi."""
    api_key = os.getenv("ODDS_API_KEY")
    if not api_key:
        logger.warning("ODDS_API_KEY absente : relevé des cotes ignoré")
        return

    now = nba_calendar.utc_now()
    db = SessionLocal()
    try:
        decision = scheduled_fetch_decision(db, now)
        if decision.action == DECISION_NO_GAME_SOON:
            logger.debug("Relevé des cotes : aucun match dans les 3 heures, pas d'appel")
            return
        if decision.action == DECISION_CREDITS_LOW:
            # Le solde connu est peut-être celui d'AVANT la remise à zéro mensuelle : on le relit par un appel
            # gratuit avant de renoncer, pour que la tâche reprenne toute seule.
            with odds_fetcher.make_client() as client:
                refreshed = odds_fetcher.refresh_credits(db, client, api_key, OddsFetchTrigger.SCHEDULED, now)
            db.commit()
            decision = scheduled_fetch_decision(db, now)
            if decision.action == DECISION_CREDITS_LOW:
                logger.warning(
                    "Relevé des cotes NON fait : %s crédit(s) restant(s)%s, sous le seuil de %s (prochain match : %s). "
                    "Le bouton reste utilisable.",
                    decision.credits_remaining,
                    "" if refreshed.credits_remaining is not None else " (solde non relu : appel gratuit en échec)",
                    MIN_CREDITS_FOR_SCHEDULED, decision.next_game,
                )
                return
            logger.info("Solde relu : %s crédit(s), le relevé reprend.", decision.credits_remaining)
        with odds_fetcher.make_client() as client:
            run_odds_fetch(db, client, api_key, OddsFetchTrigger.SCHEDULED, now)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Échec du relevé planifié des cotes")
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    """Démarre le scheduler et n'y enregistre que les tâches dont le toggle
    dédié est actif (ENABLE_INJURY_SCHEDULER / ENABLE_SCORES_SCHEDULER /
    ENABLE_ODDS_SCHEDULER), indépendamment les unes des autres -- voir app/main.py
    pour la condition de démarrage du scheduler lui-même (au moins un toggle à true)."""
    scheduler = BackgroundScheduler(timezone="America/New_York")
    if os.getenv("ENABLE_INJURY_SCHEDULER", "false").lower() == "true":
        scheduler.add_job(
            run_injury_report_job,
            trigger=CronTrigger(hour="11-23", minute="0,30", timezone="America/New_York"),
            id=JOB_ID,
            replace_existing=True,
        )
    if os.getenv("ENABLE_SCORES_SCHEDULER", "false").lower() == "true":
        scheduler.add_job(
            run_scores_sync_job,
            trigger=CronTrigger(hour="0,12,14,16,18,20,22", minute="0", timezone="America/New_York"),
            id=SCORES_JOB_ID,
            replace_existing=True,
        )
    if os.getenv("ENABLE_ODDS_SCHEDULER", "false").lower() == "true":
        # Chaque heure pile, sans plage horaire : c'est la décision (match dans les 3 heures ?) qui filtre.
        scheduler.add_job(
            run_odds_fetch_job,
            trigger=CronTrigger(minute="0", timezone="America/New_York"),
            id=ODDS_JOB_ID,
            replace_existing=True,
        )
    scheduler.start()
    return scheduler
