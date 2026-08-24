from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.game import GameStatus


class GameBase(BaseModel):
    season: str
    game_date: datetime
    home_team_id: int
    away_team_id: int
    home_score: int | None = None
    away_score: int | None = None
    status: GameStatus = GameStatus.SCHEDULED


class GameCreate(GameBase):
    pass


class GameUpdate(BaseModel):
    season: str | None = None
    game_date: datetime | None = None
    home_team_id: int | None = None
    away_team_id: int | None = None
    home_score: int | None = None
    away_score: int | None = None
    status: GameStatus | None = None


class GameRead(GameBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    manually_overridden: bool
    created_at: datetime
    updated_at: datetime


class GameWithTeamsRead(BaseModel):
    """Vue enrichie (noms d'équipes) utilisée par le formulaire admin
    AdminGamesView.vue -- évite un aller-retour supplémentaire côté
    frontend pour résoudre home_team_id/away_team_id en noms affichables."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    season: str
    game_date: datetime
    home_team_id: int
    home_team_name: str
    home_team_abbreviation: str
    away_team_id: int
    away_team_name: str
    away_team_abbreviation: str
    home_score: int | None = None
    away_score: int | None = None
    status: GameStatus
    manually_overridden: bool


class GameManualUpdate(BaseModel):
    """Corps du PATCH /api/games/{id} (formulaire admin : report de date,
    correction de score). `manually_overridden` n'a pas de défaut implicite
    ici : si le champ est fourni, il est appliqué tel quel ; s'il est absent,
    la valeur existante en base n'est pas modifiée. C'est au frontend de le
    fournir explicitement à chaque enregistrement (voir AdminGamesView.vue)."""

    game_date: datetime | None = None
    home_score: int | None = None
    away_score: int | None = None
    status: GameStatus | None = None
    manually_overridden: bool | None = None
