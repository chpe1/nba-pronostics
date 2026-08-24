from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_admin
from app.database import get_db
from app.models import Game, GameStatus
from app.schemas import GameManualUpdate, GameWithTeamsRead
from app.services.nba_calendar import current_nba_date

router = APIRouter(prefix="/api/games", tags=["games"])


@router.get("", response_model=list[GameWithTeamsRead])
def list_games(
    date_param: date = Query(default_factory=current_nba_date, alias="date"),
    db: Session = Depends(get_db),
):
    """Route publique : liste les matchs d'une date donnée (aujourd'hui par
    défaut, fuseau US/ET). Sert de base au formulaire admin de correction
    manuelle (report de date, saisie de score)."""
    start = datetime.combine(date_param, datetime.min.time())
    end = start + timedelta(days=1)
    games = (
        db.query(Game)
        .filter(Game.game_date >= start, Game.game_date < end)
        .order_by(Game.game_date)
        .all()
    )
    return [
        GameWithTeamsRead(
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
            manually_overridden=game.manually_overridden,
        )
        for game in games
    ]


@router.patch("/{game_id}", response_model=GameWithTeamsRead, dependencies=[Depends(get_current_admin)])
def update_game(game_id: int, payload: GameManualUpdate, db: Session = Depends(get_db)):
    """Correction manuelle admin d'un match : report de date et/ou score.

    `manually_overridden` n'a jamais de valeur implicite ici -- il n'est
    appliqué que si le frontend l'envoie explicitement dans le corps (voir
    GameManualUpdate). Un `PATCH` qui ne le fournit pas laisse la valeur
    existante en base inchangée."""
    game = db.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Match introuvable")

    fields = payload.model_dump(exclude_unset=True)

    if "game_date" in fields:
        game.game_date = fields["game_date"]
    if "home_score" in fields:
        game.home_score = fields["home_score"]
    if "away_score" in fields:
        game.away_score = fields["away_score"]

    if "status" in fields:
        game.status = fields["status"]
    elif "home_score" in fields and "away_score" in fields and game.home_score is not None and game.away_score is not None:
        game.status = GameStatus.FINISHED

    if "manually_overridden" in fields:
        game.manually_overridden = fields["manually_overridden"]

    db.commit()
    db.refresh(game)
    return GameWithTeamsRead(
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
        manually_overridden=game.manually_overridden,
    )
