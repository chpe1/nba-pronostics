from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.security import get_current_admin
from app.database import get_db
from app.models import Player, Team
from app.schemas import PlayerManualCreate, PlayerManualUpdate, PlayerWithTeamRead

router = APIRouter(prefix="/api/players", tags=["players"], dependencies=[Depends(get_current_admin)])


def _to_read(player: Player) -> PlayerWithTeamRead:
    return PlayerWithTeamRead(
        id=player.id,
        name=player.name,
        team_id=player.team_id,
        team_name=player.team.name,
        team_abbreviation=player.team.abbreviation,
        draft_pick=player.draft_pick,
        per=player.per,
        mpg=player.mpg,
        injury_status=player.injury_status,
        is_active=player.is_active,
    )


@router.get("", response_model=list[PlayerWithTeamRead])
def list_players(team_id: int | None = Query(default=None), db: Session = Depends(get_db)):
    query = db.query(Player)
    if team_id is not None:
        query = query.filter(Player.team_id == team_id)
    players = query.order_by(Player.name).all()
    return [_to_read(p) for p in players]


@router.post("", response_model=PlayerWithTeamRead)
def create_or_upsert_player(payload: PlayerManualCreate, response: Response, db: Session = Depends(get_db)):
    """Upsert par (name, team_id) -- même clé que les appliers CSV
    (apply_players_advanced/apply_players_per_game/apply_draft), pour qu'un
    joueur ajouté à la main soit retrouvé (et complété, pas dupliqué) par un
    futur import CSV du même joueur, et inversement.

    Décision volontaire (à l'inverse de Game.manually_overridden pour les
    matchs) : aucun verrou n'est posé ici. Un per/mpg saisi à la main reste
    un simple placeholder, écrasé sans protection par le prochain import CSV
    Advanced/Per Game du même joueur -- comportement déjà en place côté
    import, non modifié par cet endpoint."""
    team = db.get(Team, payload.team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Équipe introuvable")

    player = db.query(Player).filter(Player.name == payload.name, Player.team_id == team.id).one_or_none()
    if player is None:
        player = Player(name=payload.name, team_id=team.id)
        db.add(player)
        response.status_code = 201

    if payload.draft_pick is not None:
        player.draft_pick = payload.draft_pick
    if payload.per is not None:
        player.per = payload.per
    if payload.mpg is not None:
        player.mpg = payload.mpg

    db.commit()
    db.refresh(player)
    return _to_read(player)


@router.patch("/{player_id}", response_model=PlayerWithTeamRead)
def update_player(player_id: int, payload: PlayerManualUpdate, db: Session = Depends(get_db)):
    """Édition directe par id (liste/édition inline) : on connaît déjà la
    ligne exacte à corriger, pas besoin de repasser par la clé
    (name, team_id) -- permet aussi de corriger name/team_id eux-mêmes sans
    déclencher de logique d'upsert."""
    player = db.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=404, detail="Joueur introuvable")

    fields = payload.model_dump(exclude_unset=True)

    if "team_id" in fields:
        team = db.get(Team, fields["team_id"])
        if team is None:
            raise HTTPException(status_code=404, detail="Équipe introuvable")
        player.team_id = team.id
    if "name" in fields:
        player.name = fields["name"]
    if "draft_pick" in fields:
        player.draft_pick = fields["draft_pick"]
    if "per" in fields:
        player.per = fields["per"]
    if "mpg" in fields:
        player.mpg = fields["mpg"]

    db.commit()
    db.refresh(player)
    return _to_read(player)
