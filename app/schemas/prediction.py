from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.game import GameStatus
from app.models.prediction import ReliabilityLevel


class PredictionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    game_id: int
    home_team_note: float
    away_team_note: float
    predicted_winner_team_id: int
    spread: float
    reliability: ReliabilityLevel
    breakdown: dict
    computed_at: datetime


class RecentRecordRead(BaseModel):
    wins: int
    losses: int
    games_considered: int


class GameWithPredictionRead(BaseModel):
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
    status: GameStatus
    home_team_recent_record: RecentRecordRead
    away_team_recent_record: RecentRecordRead
    prediction: PredictionRead | None = None
