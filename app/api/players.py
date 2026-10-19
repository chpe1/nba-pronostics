from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.security import get_current_admin
from app.database import get_db
from app.models import MAX_REALISTIC_MPG, Player, Team
from app.schemas import PlayerManualCreate, PlayerManualUpdate, PlayerWithTeamRead
from app.services.csv_import import build_active_player_index, find_or_create_player_league_wide
from app.services.player_matching import find_player_by_name

router = APIRouter(prefix="/api/players", tags=["players"], dependencies=[Depends(get_current_admin)])


def _validate_mpg(mpg: float | None) -> None:
    """Rejette une valeur aberrante plutôt que de l'accepter silencieusement
    (retour d'usage réel, point 2) -- HTTPException avec un `detail` texte
    simple, pas une erreur de validation Pydantic (422 par défaut) : son
    format `detail` en liste d'objets s'afficherait mal dans apiClient.js/
    AdminPlayersView.vue, qui attend une chaîne."""
    if mpg is None:
        return
    if not (0 <= mpg <= MAX_REALISTIC_MPG):
        raise HTTPException(
            status_code=422,
            detail=f"MPG invalide ({mpg}) : doit être compris entre 0 et {MAX_REALISTIC_MPG} minutes/match.",
        )


def _to_read(player: Player) -> PlayerWithTeamRead:
    # Un agent libre (team_id NULL, Décision n°39) n'a pas d'équipe : player.team vaut None.
    team = player.team
    return PlayerWithTeamRead(
        id=player.id,
        name=player.name,
        team_id=player.team_id,
        team_name=team.name if team is not None else None,
        team_abbreviation=team.abbreviation if team is not None else None,
        draft_pick=player.draft_pick,
        per=player.per,
        mpg=player.mpg,
        injury_status=player.injury_status,
        is_active=player.is_active,
    )


@router.get("", response_model=list[PlayerWithTeamRead])
def list_players(
    team_id: int | None = Query(default=None),
    free_agent: bool = Query(default=False, description="true : uniquement les agents libres (team_id NULL)"),
    db: Session = Depends(get_db),
):
    if free_agent and team_id is not None:
        raise HTTPException(status_code=400, detail="'team_id' et 'free_agent' sont exclusifs.")
    query = db.query(Player)
    if free_agent:
        query = query.filter(Player.team_id.is_(None))
    elif team_id is not None:
        query = query.filter(Player.team_id == team_id)
    players = query.order_by(Player.name).all()
    return [_to_read(p) for p in players]


@router.post("", response_model=PlayerWithTeamRead)
def create_or_upsert_player(payload: PlayerManualCreate, response: Response, db: Session = Depends(get_db)):
    """Upsert league-wide -- même mécanisme que les appliers CSV
    (apply_players_advanced/apply_draft/apply_roster, voir
    csv_import.py::find_or_create_player_league_wide), pour qu'un joueur
    ajouté à la main soit retrouvé (et complété, pas dupliqué) par un futur
    import CSV du même joueur, et inversement. Recherché dans TOUTE la ligue
    active, pas restreint à l'équipe choisie : si le nom retrouvé appartient
    à une autre équipe, la ligne est DÉPLACÉE vers `payload.team_id` plutôt
    que dupliquée -- un admin qui choisit une équipe pour un joueur qui
    appartient à une autre veut très probablement le transférer (chantier
    fermeture du doublon, 2026-09-12). Rapprochement insensible à la casse,
    aux diacritiques, à la ponctuation et aux suffixes Jr./Sr./II/III (voir
    _roster_match_key) : "LEBRON JAMES" et "LeBron James" désignent le même
    joueur, comme avant.

    Décision volontaire (à l'inverse de Game.manually_overridden pour les
    matchs) : aucun verrou n'est posé ici. Un per/mpg saisi à la main reste
    un simple placeholder, écrasé sans protection par le prochain import CSV
    Advanced du même joueur -- comportement déjà en place côté
    import, non modifié par cet endpoint."""
    team = db.get(Team, payload.team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Équipe introuvable")
    _validate_mpg(payload.mpg)

    player_by_key = build_active_player_index(db)
    player, was_created = find_or_create_player_league_wide(db, player_by_key, payload.name, team)
    if was_created:
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


@router.delete("/{player_id}", status_code=204)
def delete_player(player_id: int, db: Session = Depends(get_db)):
    """Suppression directe par id -- capacité manquante depuis l'Étape 7,
    symétrique de POST/PATCH. Aucune table ne référence `players.id` par
    clé étrangère (vérifié), donc pas de cascade à gérer."""
    player = db.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=404, detail="Joueur introuvable")
    db.delete(player)
    db.commit()


@router.patch("/{player_id}", response_model=PlayerWithTeamRead)
def update_player(player_id: int, payload: PlayerManualUpdate, db: Session = Depends(get_db)):
    """Édition directe par id (liste/édition inline) : on connaît déjà la
    ligne exacte à corriger, pas besoin de repasser par la clé
    (name, team_id) -- permet aussi de corriger name/team_id eux-mêmes sans
    déclencher de logique d'upsert.

    Garde-fou : refuse (409) toute modification qui ferait converger
    name/team_id vers une combinaison déjà utilisée par un AUTRE joueur (casse
    ignorée, find_player_by_name -- un contrôle DÉLIBÉRÉMENT resté strict et
    borné à une équipe, distinct du rapprochement league-wide de l'upsert CSV
    depuis le chantier fermeture du doublon, 2026-09-12 : cette vérification
    protège la contrainte UNIQUE(name, team_id) en base, pas la recherche
    d'un import, donc pas concernée par ce chantier). Sans ce contrôle, deux
    lignes pourraient finir par partager la même clé (name, team_id) -- et un
    futur import ne retrouverait alors qu'une seule des deux lignes de façon
    imprévisible, cassant silencieusement le matching pour l'autre."""
    player = db.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=404, detail="Joueur introuvable")

    fields = payload.model_dump(exclude_unset=True)
    if "mpg" in fields:
        _validate_mpg(fields["mpg"])

    if "team_id" in fields:
        if fields["team_id"] is None:
            # Décision n°39 : un seul chemin pour détacher un joueur (l'aperçu d'import),
            # jamais cette route -- et db.get(Team, None) émettrait un SAWarning.
            raise HTTPException(
                status_code=400,
                detail="Détacher un joueur de son équipe n'est pas possible ici (agent libre : seulement via l'aperçu d'import).",
            )
        team = db.get(Team, fields["team_id"])
        if team is None:
            raise HTTPException(status_code=404, detail="Équipe introuvable")

    if "name" in fields or "team_id" in fields:
        target_name = fields.get("name", player.name)
        target_team_id = fields.get("team_id", player.team_id)
        conflict = find_player_by_name(db, target_name, target_team_id)
        if conflict is not None and conflict.id != player.id:
            raise HTTPException(
                status_code=409,
                detail="Un autre joueur existe déjà avec ce nom dans cette équipe",
            )

    if "team_id" in fields:
        player.team_id = fields["team_id"]
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
