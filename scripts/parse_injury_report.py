"""Parse un rapport de blessures NBA (PDF) et applique les statuts aux
joueurs en base, sans attendre le job planifié APScheduler. Utile pour
tester manuellement le parsing sur une des fixtures réelles
(tests/fixtures/Injury-Report_*.pdf) ou un nouveau rapport téléchargé.

Usage :
    python scripts/parse_injury_report.py <chemin_vers_le_pdf>
    python scripts/parse_injury_report.py <chemin_vers_le_pdf> --dry-run
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pdfplumber  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.services.injury_report_parser import parse_injury_report_pdf  # noqa: E402
from app.services.injury_report_updater import apply_injury_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path", type=Path, help="Chemin vers le PDF du rapport de blessures")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse et affiche le résultat sans écrire en base.",
    )
    args = parser.parse_args()

    if not args.pdf_path.exists():
        print(f"Fichier introuvable : {args.pdf_path}")
        raise SystemExit(1)

    with pdfplumber.open(args.pdf_path) as pdf:
        entries = parse_injury_report_pdf(pdf)

    print(f"{len(entries)} entrée(s) parsée(s) depuis {args.pdf_path.name}\n")
    for entry in entries[:15]:
        status = entry.status.value if entry.status else "?"
        print(
            f"  {entry.game_date} {entry.matchup:10s} {entry.team_abbreviation or '???':4s} "
            f"{entry.player_name_raw:25s} {status:13s} {entry.reason}"
        )
    if len(entries) > 15:
        print(f"  ... et {len(entries) - 15} de plus")

    if args.dry_run:
        print("\n--dry-run : rien écrit en base.")
        return

    db = SessionLocal()
    try:
        result = apply_injury_report(db, entries)
        db.commit()
        print(f"\n{result.matched_count} joueur(s) mis à jour en base.")
        print(
            f"{len(result.unmatched_entries)} entrée(s) non rapprochée(s) "
            "(joueur absent de la base, ou statut non reconnu)."
        )
        if result.unmatched_entries:
            print("Non rapprochées (premières 10) :")
            for entry in result.unmatched_entries[:10]:
                print(f"  {entry.team_abbreviation or '???'} {entry.player_name_raw} ({entry.status_raw})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
