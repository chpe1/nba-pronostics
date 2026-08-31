"""Peuple la base SQLite de dev avec le calendrier simulé de l'Étape 6
(équipes, joueurs, quelques blessures, matchs du jour), pour tester
l'application de bout en bout sans attendre de vraies données de saison.

Réutilise les factories de tests/simulation_data.py, en générant le
calendrier sur la date du jour (plutôt que la date fixe utilisée pour les
tests de calibrage) pour que le Dashboard affiche directement les matchs.

Usage :
    DATABASE_URL=sqlite:///./nba_pronostics_dev.db python scripts/seed_dev_data.py
    DATABASE_URL=sqlite:///./nba_pronostics_dev.db python scripts/seed_dev_data.py --reset

DATABASE_URL est OBLIGATOIRE et doit pointer vers une base autre que la vraie
(nba_pronostics.db) -- voir ensure_not_real_database() ci-dessous. Ce script
REMPLACE Team/Player/Game/Prediction : jamais contre la vraie base.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.engine import make_url  # noqa: E402

from app.database import SQLALCHEMY_DATABASE_URL, SessionLocal  # noqa: E402
from app.models import Game, InjuryStatus, Player, Prediction, Team  # noqa: E402
from app.services.nba_calendar import current_nba_date  # noqa: E402
from tests.simulation_data import build_league, create_scheduled_game  # noqa: E402

# Dupliqué du fallback de app/database.py (SQLALCHEMY_DATABASE_URL) -- on ne peut
# pas l'importer de là puisque cette variable reflète déjà la config EFFECTIVE
# (DATABASE_URL appliquée ou non), pas la valeur par défaut en soi. À
# resynchroniser si ce fallback change un jour dans app/database.py.
REAL_DATABASE_URL = "sqlite:///./nba_pronostics.db"


def resolve_sqlite_path(url: str) -> Path | None:
    """Chemin de fichier RÉSOLU d'une URL sqlite, ou None si elle ne désigne
    pas un fichier réel (:memory:, backend non-sqlite). Passe par
    sqlalchemy.engine.make_url plutôt qu'un découpage de chaîne à la main --
    gère nativement les variantes relatives/absolues, slashes Windows compris."""
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or not parsed.database or parsed.database == ":memory:":
        return None
    return Path(parsed.database).resolve()


def ensure_not_real_database(configured_url: str) -> None:
    """Refuse l'exécution si `configured_url` (DATABASE_URL appliquée, ou son
    absence) résout vers le MÊME FICHIER que la vraie base -- comparaison sur
    les chemins résolus, pas les chaînes brutes : 'sqlite:///./nba_pronostics.db'
    et un chemin absolu vers ce même fichier doivent être reconnus comme
    identiques. os.path.normcase() en plus de resolve() : Windows est
    insensible à la casse, .resolve() seul ne la normalise pas."""
    configured = resolve_sqlite_path(configured_url)
    real = resolve_sqlite_path(REAL_DATABASE_URL)
    if configured is None or real is None:
        return  # pas de fichier réel identifiable (:memory:...) -- rien à protéger ici
    if os.path.normcase(str(configured)) == os.path.normcase(str(real)):
        raise SystemExit(
            "Refus d'exécution : la base ciblée est la VRAIE base "
            f"({real}).\n"
            "Elle contient le calendrier 2026-2027, le classement N-1, 582 joueurs "
            "et la draft 2026 -- ce script REMPLACE Team/Player/Game/Prediction, "
            "jamais contre cette base.\n\n"
            "Relancez avec une base de développement séparée, par exemple :\n"
            "  DATABASE_URL=sqlite:///./nba_pronostics_dev.db python scripts/seed_dev_data.py"
        )


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


def create_dashboard_demo_slate(db, league) -> list[Game]:
    """Programme du jour pensé pour rendre le Dashboard observable dans ses trois
    niveaux de fiabilité ET avec un match totalement neutre -- contrairement à
    tests.simulation_data.create_full_slate (6 confrontations, chaque équipe
    jouant deux fois, pensées pour un garde-fou "aucun spread aberrant", pas pour
    la variété visuelle). Ne touche pas à create_full_slate ni au reste de
    tests/simulation_data.py -- réutilise juste create_scheduled_game.

    Vérifié empiriquement (pas seulement calculé à la main) avant d'écrire ces
    commentaires -- voir le compte-rendu de cette étape :
    - DET @ CHA  : les deux SEULES équipes sans aucune blessure ni drapeau
      calendaire à TARGET_DATE (apply_sample_injuries ne les touche pas,
      setup_calendar_history ne place leur dernier match antérieur qu'hors de la
      fenêtre des 3 jours) -- AUCUNE pastille de contexte des deux côtés.
    - CHI @ MIA  : les deux équipes les plus proches en niveau (note de base à
      quelques points l'une de l'autre) -- écart final sous le seuil bas
      (fiabilité "faible"), la bande jamais couverte par create_full_slate.
    - BOS @ DEN  : deux équipes fortes proches l'une de l'autre -- écart
      "moyenne", chacune avec sa propre pastille d'absence (star Out / titulaire
      Doubtful, posées par apply_sample_injuries).
    - BOS @ DET  : BOS (fort) contre DET (faible) -- écart "forte", la bande la
      plus simple à obtenir mais qui aurait disparu sans ce 4e match une fois les
      confrontations en double de create_full_slate abandonnées. BOS et DET sont
      donc les deux seules équipes du programme à jouer deux fois -- un artefact
      assumé de données simulées, jamais un vrai calendrier."""
    pairings = [
        ("DET", "CHA"),
        ("CHI", "MIA"),
        ("BOS", "DEN"),
        ("BOS", "DET"),
    ]
    return [
        create_scheduled_game(db, league.teams[home], league.teams[away], game_date=league.target_date)
        for home, away in pairings
    ]


def main() -> None:
    ensure_not_real_database(SQLALCHEMY_DATABASE_URL)

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
        games = create_dashboard_demo_slate(db, league)
        db.commit()

        player_count = sum(len(r.others) + (1 if r.rookie else 0) for r in league.rosters.values())
        print(f"Calendrier simulé créé pour le {league.target_date.isoformat()} :")
        print(f"  - {len(league.teams)} équipes, {player_count} joueurs")
        print(f"  - {len(games)} matchs programmés")
        print("    DET @ CHA (fiabilité moyenne, AUCUNE pastille de contexte des deux côtés)")
        print("    CHI @ MIA (fiabilité faible -- écart serré)")
        print("    BOS @ DEN (fiabilité moyenne, pastilles d'absence des deux côtés)")
        print("    BOS @ DET (fiabilité forte -- BOS et DET jouent deux fois aujourd'hui,")
        print("               artefact assumé des données simulées)")
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
