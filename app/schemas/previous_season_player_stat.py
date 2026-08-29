from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PreviousSeasonPlayerStatCreate(BaseModel):
    season: str
    player_name: str
    team_abbreviation: str
    per: float | None = None
    mpg: float | None = None


class PreviousSeasonPlayerStatUpdate(BaseModel):
    """Aucun champ n'a de valeur par défaut implicite : seul un champ fourni
    est modifié (même convention que PlayerManualUpdate)."""

    season: str | None = None
    player_name: str | None = None
    team_abbreviation: str | None = None
    per: float | None = None
    mpg: float | None = None


class PreviousSeasonPlayerStatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    season: str
    player_name: str
    team_abbreviation: str
    per: float | None
    mpg: float | None
    created_at: datetime
    updated_at: datetime
