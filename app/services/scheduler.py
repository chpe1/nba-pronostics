"""Tâche planifiée : récupération + parsing + application du rapport de
blessures NBA le plus récent.

Fréquence : toutes les 30 minutes, de 11h à 23h30 heure US Eastern (la NBA
republie en continu pendant cette plage). L'utilisation du fuseau
"America/New_York" (plutôt qu'une conversion figée vers l'heure française)
fait gérer le changement d'heure automatiquement par APScheduler/zoneinfo,
côté US comme côté France.
"""
from __future__ import annotations

import io
import logging

import pdfplumber
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.database import SessionLocal
from app.services.injury_report_fetcher import fetch_latest_report_bytes
from app.services.injury_report_parser import parse_injury_report_pdf
from app.services.injury_report_updater import apply_injury_report

logger = logging.getLogger(__name__)

JOB_ID = "injury_report_refresh"


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


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="America/New_York")
    scheduler.add_job(
        run_injury_report_job,
        trigger=CronTrigger(hour="11-23", minute="0,30", timezone="America/New_York"),
        id=JOB_ID,
        replace_existing=True,
    )
    scheduler.start()
    return scheduler
