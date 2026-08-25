from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TeamBase(BaseModel):
    name: str
    abbreviation: str
    conference: str | None = None
    division: str | None = None
    win_pct_home: float = 0.0
    win_pct_away: float = 0.0
    win_pct_home_prev_season: float = 0.0
    win_pct_away_prev_season: float = 0.0
    current_streak: int = 0


class TeamCreate(TeamBase):
    pass


class TeamUpdate(BaseModel):
    name: str | None = None
    abbreviation: str | None = None
    conference: str | None = None
    division: str | None = None
    win_pct_home: float | None = None
    win_pct_away: float | None = None
    win_pct_home_prev_season: float | None = None
    win_pct_away_prev_season: float | None = None
    current_streak: int | None = None


class TeamRead(TeamBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class TeamSummaryRead(BaseModel):
    """Vue allégée utilisée pour peupler un sélecteur d'équipe côté frontend
    (ex: AdminPlayersView.vue) -- pas besoin des win_pct/created_at."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    abbreviation: str
