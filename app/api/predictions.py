from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.security import get_current_admin
from app.database import get_db
from app.models import Game, Prediction, Settings
from app.schemas.prediction import (
    CalendarStatusRead,
    GameWithPredictionRead,
    MatchupSimulationRead,
    MatchupSimulationRequest,
    PredictionRead,
    RecentRecordRead,
    TeamGamePredictionRead,
    TodayPredictionRead,
)
from app.services.nba_calendar import current_nba_date
from app.services.pronostic_calculator import (
    breakdown_to_dict,
    compute_calendar_flags,
    compute_matchup,
    compute_recent_record,
    save_prediction,
)

router = APIRouter(prefix="/api/predictions", tags=["predictions"])

# Un match à plus de ce nombre de jours dans le futur (par rapport à la vraie
# date du jour, current_nba_date() -- jamais la date consultée) voit son
# résultat masqué sur le Dashboard public, même si un pronostic a déjà été
# calculé pour lui. Constante en dur, pas un curseur Settings : c'est une
# politique d'affichage sur une route publique, pas un paramètre qui change
# le calcul d'un pronostic -- voir CLAUDE.md.
PREDICTION_REVEAL_THRESHOLD_DAYS = 2


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


def _to_today_prediction_read(prediction: Prediction, game: Game) -> TodayPredictionRead:
    """Masque le résultat d'un pronostic déjà calculé pour un match trop
    anticipé -- comparaison TOUJOURS contre la vraie date du jour
    (current_nba_date()), jamais contre la date consultée (`date_param`),
    et ne s'applique qu'au futur : pour une date passée, `days_ahead` est
    négatif, donc jamais > PREDICTION_REVEAL_THRESHOLD_DAYS."""
    days_ahead = (game.game_date_only - current_nba_date()).days
    is_upcoming = days_ahead > PREDICTION_REVEAL_THRESHOLD_DAYS

    if is_upcoming:
        return TodayPredictionRead(
            id=prediction.id,
            game_id=prediction.game_id,
            is_upcoming=True,
            computed_at=prediction.computed_at,
        )
    return TodayPredictionRead(
        id=prediction.id,
        game_id=prediction.game_id,
        is_upcoming=False,
        home_team_note=prediction.home_team_note,
        away_team_note=prediction.away_team_note,
        predicted_winner_team_id=prediction.predicted_winner_team_id,
        spread=prediction.spread,
        reliability=prediction.reliability,
        breakdown=prediction.breakdown,
        computed_at=prediction.computed_at,
    )


@router.get("/today", response_model=list[GameWithPredictionRead])
def get_today_predictions(
    date_param: date = Query(default_factory=current_nba_date, alias="date"),
    db: Session = Depends(get_db),
):
    """Route publique (dashboard) : liste les matchs de la date donnée
    (aujourd'hui par défaut) avec leur pronostic déjà calculé, s'il existe.
    Ne déclenche aucun calcul (voir POST /recalculate pour ça)."""
    settings = _get_or_create_settings(db)
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
        home_calendar = compute_calendar_flags(db, game.home_team, game_date)
        away_calendar = compute_calendar_flags(db, game.away_team, game_date)
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
                home_score=game.home_score,
                away_score=game.away_score,
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
                home_calendar_status=CalendarStatusRead(**home_calendar),
                away_calendar_status=CalendarStatusRead(**away_calendar),
                reliability_threshold_low=settings.reliability_threshold_low,
                reliability_threshold_high=settings.reliability_threshold_high,
                prediction=(
                    _to_today_prediction_read(predictions_by_game_id[game.id], game)
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


@router.get(
    "/by-team/{team_id}",
    response_model=list[TeamGamePredictionRead],
    dependencies=[Depends(get_current_admin)],
)
def list_predictions_for_team(team_id: int, db: Session = Depends(get_db)):
    """Page de diagnostic par équipe (back-office) : tous les matchs de
    `team_id` (passés et à venir) ayant déjà une Prediction calculée --
    jointure interne sur Prediction, donc liste vide si le roster courant de
    l'équipe n'a pas encore été importé (aucun calcul possible pour l'instant,
    pas une erreur)."""
    rows = (
        db.query(Game, Prediction)
        .join(Prediction, Prediction.game_id == Game.id)
        .filter(or_(Game.home_team_id == team_id, Game.away_team_id == team_id))
        .order_by(Game.game_date)
        .all()
    )
    return [
        TeamGamePredictionRead(
            id=game.id,
            season=game.season,
            game_date=game.game_date,
            home_team_id=game.home_team_id,
            home_team_name=game.home_team.name,
            home_team_abbreviation=game.home_team.abbreviation,
            away_team_id=game.away_team_id,
            away_team_name=game.away_team.name,
            away_team_abbreviation=game.away_team.abbreviation,
            home_score=game.home_score,
            away_score=game.away_score,
            status=game.status,
            prediction=PredictionRead.model_validate(prediction),
        )
        for game, prediction in rows
    ]


@router.post(
    "/simulate",
    response_model=MatchupSimulationRead,
    dependencies=[Depends(get_current_admin)],
)
def simulate_prediction(payload: MatchupSimulationRequest, db: Session = Depends(get_db)):
    """Simulateur ponctuel (page de diagnostic par équipe) : recalcule un
    match avec un mélange de réglages réels + overrides, SANS jamais écrire
    en base -- ni sur la vraie ligne Settings, ni en créant une Prediction.

    L'objet Settings construit ici est transitoire (jamais db.add()) :
    compute_matchup/compute_team_note ne font que LIRE des attributs sur
    l'objet settings qu'on leur passe (settings.mpg_threshold,
    settings.draft_bonus_config.get(...), etc.), jamais de requête ni
    d'écriture basée dessus -- un objet non attaché à la session fonctionne
    donc à l'identique d'un vrai, sans dupliquer la moindre logique de calcul."""
    game = db.get(Game, payload.game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Match introuvable")

    real_settings = _get_or_create_settings(db)
    transient_settings = Settings(
        base_note_multiplier=real_settings.base_note_multiplier,
        per_impact_multiplier=real_settings.per_impact_multiplier,
        back_to_back_penalty=real_settings.back_to_back_penalty,
        three_in_four_penalty=real_settings.three_in_four_penalty,
        mpg_threshold=real_settings.mpg_threshold,
        player_sample_size_threshold=real_settings.player_sample_size_threshold,
        draft_bonus_config=dict(real_settings.draft_bonus_config),
        reliability_threshold_low=real_settings.reliability_threshold_low,
        reliability_threshold_high=real_settings.reliability_threshold_high,
        transfer_impact_multiplier=real_settings.transfer_impact_multiplier,
        current_season=real_settings.current_season,
    )
    for field, value in payload.overrides.model_dump(exclude_unset=True).items():
        setattr(transient_settings, field, value)

    result = compute_matchup(db, game, transient_settings)
    return MatchupSimulationRead(
        predicted_winner_team_id=result.predicted_winner_team_id,
        spread=result.spread,
        reliability=result.reliability,
        home=breakdown_to_dict(result.home),
        away=breakdown_to_dict(result.away),
    )
