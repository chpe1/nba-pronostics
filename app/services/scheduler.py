"""Tâches planifiées : rapport de blessures NBA + synchronisation des scores.

Rapport de blessures : toutes les 30 minutes, de 11h à 23h30 heure US
Eastern (la NBA republie en continu pendant cette plage).

Synchronisation des scores (balldontlie.io) : toutes les 2h de 12h à 2h du
matin heure US Eastern (couvre la plage des matchs + leur fin ; la borne
2h du matin couvre les matchs qui se terminent après minuit ET). Récupère à
chaque exécution hier ET aujourd'hui (couvre un match commencé la veille ET
mais terminé après minuit ET).

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
from app.services.injury_report_fetcher import fetch_latest_report_bytes
from app.services.injury_report_parser import parse_injury_report_pdf
from app.services.injury_report_updater import apply_injury_report
from app.services.nba_calendar import current_nba_date
from app.services.scores_fetcher import sync_scores_for_date

logger = logging.getLogger(__name__)

JOB_ID = "injury_report_refresh"
SCORES_JOB_ID = "scores_sync"


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
                    "Scores synchronisés pour %s : %d récupéré(s), %d mis à jour, %d ignoré(s)",
                    target_date,
                    result["fetched"],
                    result["updated"],
                    result["skipped"],
                )
            except Exception:
                logger.exception("Échec de la synchronisation des scores pour %s", target_date)
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    """Démarre le scheduler et n'y enregistre que les tâches dont le toggle
    dédié est actif (ENABLE_INJURY_SCHEDULER / ENABLE_SCORES_SCHEDULER),
    indépendamment l'une de l'autre -- voir app/main.py pour la condition de
    démarrage du scheduler lui-même (au moins un des deux toggles à true)."""
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
    scheduler.start()
    return scheduler
