"""Peuple la base SQLite de dev avec le calendrier simulé de l'Étape 6
(équipes, joueurs, quelques blessures, matchs du jour), pour tester
l'application de bout en bout sans attendre de vraies données de saison.

Réutilise les factories de tests/simulation_data.py, en générant le
calendrier sur la date du jour (plutôt que la date fixe utilisée pour les
tests de calibrage) pour que le Dashboard affiche directement les matchs.

Usage :
    python scripts/seed_dev_data.py
    python scripts/seed_dev_data.py --reset   # si déjà lancé une fois
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.models import Game, InjuryStatus, Player, Prediction, Team  # noqa: E402
from app.services.nba_calendar import current_nba_date  # noqa: E402
from tests.simulation_data import build_league, create_full_slate  # noqa: E402


def reset_existing_data(db) -> None:
    db.query(Prediction).delete()
    db.query(Game).delete()
    db.query(Player).delete()
    db.query(Team).delete()
    db.commit()


def apply_sample_injuries(league) -> None:
    """Quelques blessures représentatives (l'effectif est entièrement sain
    par défaut dans build_league) : une star Out, un titulaire Doubtful, un
    joueur Questionable, et un joueur de banc Out sous le seuil MPG (pour
    vérifier visuellement que ce dernier n'affecte pas la note)."""
    league.rosters["BOS"].star.injury_status = InjuryStatus.OUT
    league.rosters["BOS"].star.injury_reason = "Injury/Illness-Ankle;Sprain"

    league.rosters["DEN"].others[1].injury_status = InjuryStatus.DOUBTFUL
    league.rosters["DEN"].others[1].injury_reason = "Injury/Illness-Knee;Soreness"

    league.rosters["MIA"].others[2].injury_status = InjuryStatus.QUESTIONABLE
    league.rosters["MIA"].others[2].injury_reason = "Injury/Illness-Back;Stiffness"

    league.rosters["CHI"].bench_player.injury_status = InjuryStatus.OUT
    league.rosters["CHI"].bench_player.injury_reason = "GLeague-Two-Way"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Supprime les Team/Player/Game/Prediction existants avant de re-semer.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        existing_teams = db.query(Team).count()
        if existing_teams and not args.reset:
            print(
                f"{existing_teams} équipe(s) déjà en base. Relancez avec --reset pour "
                "vider Team/Player/Game/Prediction avant de re-semer."
            )
            raise SystemExit(1)
        if args.reset:
            reset_existing_data(db)

        league = build_league(db, target_date=current_nba_date())
        apply_sample_injuries(league)
        games = create_full_slate(db, league)
        db.commit()

        player_count = sum(len(r.others) + (1 if r.rookie else 0) for r in league.rosters.values())
        print(f"Calendrier simulé créé pour le {league.target_date.isoformat()} :")
        print(f"  - {len(league.teams)} équipes, {player_count} joueurs")
        print(f"  - {len(games)} matchs programmés")
        print(f"  - équipe en back-to-back : {league.back_to_back_team}")
        print(f"  - équipe en 3-matchs-en-4-nuits : {league.three_in_four_team}")
        print(f"  - équipe reposée : {league.rested_team}")
        print(f"  - équipe en début de saison (règle des 10 premiers matchs) : {league.early_season_team}")
        print("  - blessures : BOS (star, Out), DEN (titulaire, Doubtful),")
        print("    MIA (Questionable), CHI (banc sous le seuil MPG, Out)")
        print()
        print("Pour calculer les pronostics : bouton 'Recalculer les pronostics du")
        print("jour' dans le Dashboard (une fois connecté), ou :")
        print("  POST /api/predictions/recalculate")
    finally:
        db.close()


if __name__ == "__main__":
    main()
