from datetime import date

from pydantic import BaseModel


class TableCountsRead(BaseModel):
    team_count: int
    player_count: int
    game_count: int
    previous_season_player_stat_count: int
    import_history_count: int
    prediction_count: int
    login_lockout_count: int


class TeamGameCountRead(BaseModel):
    team_id: int
    team_name: str
    abbreviation: str
    game_count: int
    # Écart de plus de 1 par rapport au nombre de matchs le plus fréquent
    # parmi les 30 équipes -- une finale NBA Cup peut légitimement donner un
    # écart de 1 à 2 équipes, pas plus (voir CLAUDE.md).
    is_outlier: bool


class DuplicateGameRead(BaseModel):
    """Même date, mêmes deux équipes -- indépendamment de qui reçoit (une
    contrainte UNIQUE existe déjà en base mais ne couvre pas le cas où
    domicile/extérieur seraient inversés entre les deux lignes)."""

    game_date: date
    team_a_abbreviation: str
    team_b_abbreviation: str
    count: int


class SameDayConflictRead(BaseModel):
    """Une équipe avec plusieurs matchs le même jour contre des adversaires
    DIFFÉRENTS -- distinct de DuplicateGameRead (mêmes deux équipes)."""

    team_id: int
    team_name: str
    game_date: date
    opponent_abbreviations: list[str]


class IntegrityAuditRead(BaseModel):
    team_game_counts: list[TeamGameCountRead]
    mode_game_count: int
    total_games: int
    games_count_consistent: bool
    missing_teams: list[str]
    unexpected_teams: list[str]
    duplicate_games: list[DuplicateGameRead]
    same_day_conflicts: list[SameDayConflictRead]
