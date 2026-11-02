from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

# Écart de points moyen N-1 : bornes larges (aucune équipe n'approche ±20 sur une saison) mais assez
# serrées pour refuser une faute de frappe d'ordre de grandeur (ex. 1115 au lieu de 11.15).
POINT_DIFF_BOUND = 25.0


class TeamBase(BaseModel):
    name: str
    abbreviation: str
    # Saison en cours : calculés par le moteur (services/team_win_pct.py). None = aucun match compté, jamais 0.
    win_pct_home: float | None = None
    win_pct_away: float | None = None
    win_pct_home_prev_season: float = 0.0
    win_pct_away_prev_season: float = 0.0
    # NULL = inconnu (jamais 0) : voir Team.point_diff_prev_season.
    point_diff_prev_season: float | None = None


class TeamCreate(TeamBase):
    pass


class TeamUpdate(BaseModel):
    name: str | None = None
    abbreviation: str | None = None
    # LECTURE SEULE depuis le chantier (b2) : calculés depuis les matchs terminés. Déclarés ici uniquement pour que
    # la route les REFUSE explicitement (422) au lieu de les ignorer en silence.
    win_pct_home: float | None = None
    win_pct_away: float | None = None
    win_pct_home_prev_season: float | None = None
    win_pct_away_prev_season: float | None = None
    # Envoyer null efface la valeur (redevient inconnue).
    point_diff_prev_season: float | None = Field(default=None, ge=-POINT_DIFF_BOUND, le=POINT_DIFF_BOUND)


class SideRecordRead(BaseModel):
    wins: int
    losses: int
    games: int
    # Recompté depuis les matchs : None si aucun match compté de ce côté.
    pct: float | None


class ExcludedGameRead(BaseModel):
    game_id: int
    game_date: date
    reason: str


class CurrentSeasonRecordRead(BaseModel):
    """Bilan recompté À L'AFFICHAGE depuis les matchs terminés de la saison en cours (rien n'est stocké)."""

    season: str
    home: SideRecordRead
    away: SideRecordRead
    # Date (NBA, heure de New York) du dernier match compté pour l'équipe ; None si aucun.
    last_game_date: date | None
    # Faux si la valeur STOCKÉE (lue par la note) diffère du recomptage : à signaler visiblement.
    stored_matches_recount: bool
    # Matchs terminés de l'équipe NON comptés (sans score, égalité).
    excluded_games: list[ExcludedGameRead] = []


class TeamRead(TeamBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    # Rempli par les routes /api/teams ; None si la saison en cours est inconnue (aucune ligne Settings).
    current_season_record: CurrentSeasonRecordRead | None = None
