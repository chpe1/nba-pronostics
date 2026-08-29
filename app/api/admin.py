from __future__ import annotations

from collections import Counter, defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_admin
from app.database import get_db
from app.models import (
    Game,
    ImportHistory,
    LoginLockout,
    Player,
    Prediction,
    PreviousSeasonPlayerStat,
    Team,
)
from app.schemas.admin import (
    DuplicateGameRead,
    IntegrityAuditRead,
    SameDayConflictRead,
    TableCountsRead,
    TeamGameCountRead,
)
from app.services.nba_teams import NBA_TEAMS

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(get_current_admin)])

# Tolérance avant de signaler un écart de calendrier comme un vrai problème
# plutôt qu'une variation normale (typiquement, la finale NBA Cup qui ajoute
# 1 match aux deux finalistes -- confirmé sur les vraies données importées le
# 2026-08-29 : aucun seuil fixe à 82 codé en dur, voir CLAUDE.md).
OUTLIER_TOLERANCE = 1


@router.get("/table-counts", response_model=TableCountsRead)
def get_table_counts(db: Session = Depends(get_db)) -> TableCountsRead:
    return TableCountsRead(
        team_count=db.query(Team).count(),
        player_count=db.query(Player).count(),
        game_count=db.query(Game).count(),
        previous_season_player_stat_count=db.query(PreviousSeasonPlayerStat).count(),
        import_history_count=db.query(ImportHistory).count(),
        prediction_count=db.query(Prediction).count(),
        login_lockout_count=db.query(LoginLockout).count(),
    )


@router.get("/integrity-audit", response_model=IntegrityAuditRead)
def get_integrity_audit(db: Session = Depends(get_db)) -> IntegrityAuditRead:
    """Reprend les contrôles jusqu'ici faits ponctuellement à la main
    (jamais formalisés en outil) : décompte de matchs par équipe, cohérence
    du total, présence exacte des 30 équipes NBA, et deux formes de conflit
    de calendrier (doublon même paire d'équipes, équipe sur deux matchs le
    même jour contre des adversaires différents)."""
    teams = db.query(Team).all()
    games = db.query(Game).all()
    team_by_id = {team.id: team for team in teams}

    # --- décompte de matchs par équipe (domicile + extérieur) -------------
    counts_by_team_id: dict[int, int] = {team.id: 0 for team in teams}
    for game in games:
        counts_by_team_id[game.home_team_id] = counts_by_team_id.get(game.home_team_id, 0) + 1
        counts_by_team_id[game.away_team_id] = counts_by_team_id.get(game.away_team_id, 0) + 1

    counts = list(counts_by_team_id.values())
    mode_count = Counter(counts).most_common(1)[0][0] if counts else 0

    team_game_counts = [
        TeamGameCountRead(
            team_id=team.id,
            team_name=team.name,
            abbreviation=team.abbreviation,
            game_count=counts_by_team_id[team.id],
            is_outlier=abs(counts_by_team_id[team.id] - mode_count) > OUTLIER_TOLERANCE,
        )
        for team in sorted(teams, key=lambda t: t.name)
    ]

    total_games = len(games)
    games_count_consistent = sum(counts) == 2 * total_games

    # --- équipes canoniques -------------------------------------------------
    db_abbreviations = {team.abbreviation for team in teams}
    canonical_abbreviations = set(NBA_TEAMS.values())
    missing_teams = sorted(canonical_abbreviations - db_abbreviations)
    unexpected_teams = sorted(db_abbreviations - canonical_abbreviations)

    # --- doublons : même date, mêmes deux équipes (peu importe qui reçoit) --
    games_by_date_pair: dict[tuple, list[Game]] = defaultdict(list)
    for game in games:
        pair_key = frozenset((game.home_team_id, game.away_team_id))
        games_by_date_pair[(game.game_date_only, pair_key)].append(game)

    duplicate_games = []
    for (game_date, pair_key), matching_games in games_by_date_pair.items():
        if len(matching_games) > 1:
            team_ids = list(pair_key)
            team_b_id = team_ids[1] if len(team_ids) > 1 else team_ids[0]
            duplicate_games.append(
                DuplicateGameRead(
                    game_date=game_date,
                    team_a_abbreviation=team_by_id[team_ids[0]].abbreviation,
                    team_b_abbreviation=team_by_id[team_b_id].abbreviation,
                    count=len(matching_games),
                )
            )

    # --- conflits : une équipe avec 2 matchs le même jour, adversaires ------
    # différents (distinct des doublons ci-dessus, qui portent sur la MÊME
    # paire d'équipes).
    games_by_team_date: dict[tuple, list[Game]] = defaultdict(list)
    for game in games:
        games_by_team_date[(game.home_team_id, game.game_date_only)].append(game)
        games_by_team_date[(game.away_team_id, game.game_date_only)].append(game)

    same_day_conflicts = []
    for (team_id, game_date), matching_games in games_by_team_date.items():
        if len(matching_games) <= 1:
            continue
        opponent_ids = {
            g.away_team_id if g.home_team_id == team_id else g.home_team_id for g in matching_games
        }
        if len(opponent_ids) > 1:
            same_day_conflicts.append(
                SameDayConflictRead(
                    team_id=team_id,
                    team_name=team_by_id[team_id].name,
                    game_date=game_date,
                    opponent_abbreviations=sorted(team_by_id[o].abbreviation for o in opponent_ids),
                )
            )

    return IntegrityAuditRead(
        team_game_counts=team_game_counts,
        mode_game_count=mode_count,
        total_games=total_games,
        games_count_consistent=games_count_consistent,
        missing_teams=missing_teams,
        unexpected_teams=unexpected_teams,
        duplicate_games=duplicate_games,
        same_day_conflicts=same_day_conflicts,
    )
