"""Synchronise les scores balldontlie.io pour une date donnée, sans attendre
le prochain passage planifié du scheduler (voir app/services/scheduler.py::
run_scores_sync_job pour l'exécution automatique).

Usage :
    python scripts/sync_scores.py                # aujourd'hui (fuseau US/ET)
    python scripts/sync_scores.py 2026-10-21      # date précise
"""
import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

import os  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.services.nba_calendar import current_nba_date  # noqa: E402
from app.services.scores_fetcher import sync_scores_for_date  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target_date",
        type=date.fromisoformat,
        nargs="?",
        default=None,
        help="Date au format AAAA-MM-JJ (défaut : aujourd'hui, fuseau America/New_York)",
    )
    args = parser.parse_args()
    target_date = args.target_date or current_nba_date()

    api_key = os.getenv("BALLDONTLIE_API_KEY")
    if not api_key:
        print("BALLDONTLIE_API_KEY absente de l'environnement (.env) -- synchronisation impossible.")
        raise SystemExit(1)

    db = SessionLocal()
    try:
        result = sync_scores_for_date(db, api_key, target_date)
        print(
            f"Scores synchronisés pour {target_date} : "
            f"{result['fetched']} récupéré(s), {result['updated']} mis à jour, {result['skipped']} ignoré(s)."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
