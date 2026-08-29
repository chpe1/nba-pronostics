from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.game import GameStatus
from app.models.prediction import ReliabilityLevel
from app.schemas.settings import SettingsUpdate


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


class TodayPredictionRead(BaseModel):
    """Comme PredictionRead, mais pour GET /api/predictions/today (Dashboard
    public) uniquement -- les champs qui révéleraient le résultat sont mis à
    None quand `is_upcoming` est vrai (match à plus de
    PREDICTION_REVEAL_THRESHOLD_DAYS jours dans le futur, voir
    app/api/predictions.py). Schéma volontairement distinct de PredictionRead
    (utilisé tel quel par by-team/recalculate, jamais masqué) plutôt qu'un
    champ optionnel ajouté dessus -- le masquage est spécifique à cette seule
    route publique."""

    id: int
    game_id: int
    is_upcoming: bool
    home_team_note: float | None = None
    away_team_note: float | None = None
    predicted_winner_team_id: int | None = None
    spread: float | None = None
    reliability: ReliabilityLevel | None = None
    breakdown: dict | None = None
    computed_at: datetime


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
    prediction: TodayPredictionRead | None = None


class TeamGamePredictionRead(BaseModel):
    """Match + pronostic déjà calculé, pour la page de diagnostic par équipe
    (GET /api/predictions/by-team/{team_id}) -- contrairement à
    GameWithPredictionRead, `prediction` n'est jamais None ici : la requête
    ne renvoie que des matchs déjà pronostiqués. Pas de bilan V-D récent
    (spécifique au Dashboard), volontairement plus léger."""

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
    home_score: int | None
    away_score: int | None
    status: GameStatus
    prediction: PredictionRead


class MatchupSimulationRequest(BaseModel):
    """Réutilise SettingsUpdate tel quel plutôt que redéfinir les mêmes
    champs optionnels une 3e fois -- non renseigné = valeur réelle actuelle
    conservée (voir simulate_prediction, app/api/predictions.py)."""

    game_id: int
    overrides: SettingsUpdate = SettingsUpdate()


class MatchupSimulationRead(BaseModel):
    """Même forme que PredictionRead (moins id/game_id/computed_at, puisque
    rien n'est persisté) -- affichée par le même composant frontend que le
    vrai pronostic, pour comparaison directe."""

    predicted_winner_team_id: int
    spread: float
    reliability: ReliabilityLevel
    home: dict
    away: dict
