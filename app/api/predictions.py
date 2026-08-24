from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_admin
from app.database import get_db
from app.models import Game, Prediction, Settings
from app.schemas.prediction import GameWithPredictionRead, PredictionRead, RecentRecordRead
from app.services.nba_calendar import current_nba_date
from app.services.pronostic_calculator import compute_recent_record, save_prediction

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


def _games_for_date(db: Session, target_date: date) -> list[Game]:
    start = datetime.combine(target_date, datetime.min.time())
    end = start + timedelta(days=1)
    return (
        db.query(Game)
        .filter(Game.game_date >= start, Game.game_date < end)
        .order_by(Game.game_date)
        .all()
    )


def _get_or_create_settings(db: Session) -> Settings:
    settings = db.query(Settings).first()
    if settings is None:
        settings = Settings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.get("/today", response_model=list[GameWithPredictionRead])
def get_today_predictions(
    date_param: date = Query(default_factory=current_nba_date, alias="date"),
    db: Session = Depends(get_db),
):
    """Route publique (dashboard) : liste les matchs de la date donnée
    (aujourd'hui par défaut) avec leur pronostic déjà calculé, s'il existe.
    Ne déclenche aucun calcul (voir POST /recalculate pour ça)."""
    games = _games_for_date(db, date_param)
    game_ids = [g.id for g in games]
    predictions_by_game_id = (
        {p.game_id: p for p in db.query(Prediction).filter(Prediction.game_id.in_(game_ids)).all()}
        if game_ids
        else {}
    )

    results = []
    for game in games:
        game_date = game.game_date.date() if hasattr(game.game_date, "date") else game.game_date
        home_record = compute_recent_record(db, game.home_team, before_date=game_date)
        away_record = compute_recent_record(db, game.away_team, before_date=game_date)
        results.append(
            GameWithPredictionRead(
                id=game.id,
                season=game.season,
                game_date=game.game_date,
                home_team_id=game.home_team_id,
                home_team_name=game.home_team.name,
                home_team_abbreviation=game.home_team.abbreviation,
                away_team_id=game.away_team_id,
                away_team_name=game.away_team.name,
                away_team_abbreviation=game.away_team.abbreviation,
                status=game.status,
                home_team_recent_record=RecentRecordRead(
                    wins=home_record.wins,
                    losses=home_record.losses,
                    games_considered=home_record.games_considered,
                ),
                away_team_recent_record=RecentRecordRead(
                    wins=away_record.wins,
                    losses=away_record.losses,
                    games_considered=away_record.games_considered,
                ),
                prediction=(
                    PredictionRead.model_validate(predictions_by_game_id[game.id])
                    if game.id in predictions_by_game_id
                    else None
                ),
            )
        )
    return results


@router.post(
    "/recalculate",
    response_model=list[PredictionRead],
    dependencies=[Depends(get_current_admin)],
)
def recalculate_predictions(
    date_param: date = Query(default_factory=current_nba_date, alias="date"),
    db: Session = Depends(get_db),
):
    """Route back-office (protégée) : recalcule et sauvegarde le pronostic de
    tous les matchs de la date donnée (aujourd'hui par défaut)."""
    settings = _get_or_create_settings(db)
    games = _games_for_date(db, date_param)
    predictions = [save_prediction(db, game, settings) for game in games]
    db.commit()
    for prediction in predictions:
        db.refresh(prediction)
    return predictions
