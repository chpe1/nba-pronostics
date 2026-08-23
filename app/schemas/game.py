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
    created_at: datetime
    updated_at: datetime
