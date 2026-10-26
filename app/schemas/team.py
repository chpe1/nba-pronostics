from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# Écart de points moyen N-1 : bornes larges (aucune équipe n'approche ±20 sur une saison) mais assez
# serrées pour refuser une faute de frappe d'ordre de grandeur (ex. 1115 au lieu de 11.15).
POINT_DIFF_BOUND = 25.0


class TeamBase(BaseModel):
    name: str
    abbreviation: str
    win_pct_home: float = 0.0
    win_pct_away: float = 0.0
    win_pct_home_prev_season: float = 0.0
    win_pct_away_prev_season: float = 0.0
    # NULL = inconnu (jamais 0) : voir Team.point_diff_prev_season.
    point_diff_prev_season: float | None = None


class TeamCreate(TeamBase):
    pass


class TeamUpdate(BaseModel):
    name: str | None = None
    abbreviation: str | None = None
    win_pct_home: float | None = None
    win_pct_away: float | None = None
    win_pct_home_prev_season: float | None = None
    win_pct_away_prev_season: float | None = None
    # Envoyer null efface la valeur (redevient inconnue).
    point_diff_prev_season: float | None = Field(default=None, ge=-POINT_DIFF_BOUND, le=POINT_DIFF_BOUND)


class TeamRead(TeamBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
