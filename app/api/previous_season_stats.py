from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_admin
from app.database import get_db
from app.models import MAX_REALISTIC_MPG, PreviousSeasonPlayerStat
from app.schemas.previous_season_player_stat import (
    PreviousSeasonPlayerStatCreate,
    PreviousSeasonPlayerStatRead,
    PreviousSeasonPlayerStatUpdate,
)
from app.services.nba_teams import ABBREVIATION_TO_NAME, normalize_abbreviation
from app.services.player_matching import find_prev_season_stat_by_name

router = APIRouter(
    prefix="/api/previous-season-stats",
    tags=["previous-season-stats"],
    dependencies=[Depends(get_current_admin)],
)


def _validate_mpg(mpg: float | None) -> None:
    if mpg is None:
        return
    if not (0 <= mpg <= MAX_REALISTIC_MPG):
        raise HTTPException(
            status_code=422,
            detail=f"MPG invalide ({mpg}) : doit être compris entre 0 et {MAX_REALISTIC_MPG} minutes/match.",
        )


def _validate_and_normalize_abbreviation(abbreviation: str) -> str:
    normalized = normalize_abbreviation(abbreviation)
    if normalized not in ABBREVIATION_TO_NAME:
        raise HTTPException(status_code=422, detail=f"Équipe inconnue : {abbreviation!r}")
    return normalized


@router.get("", response_model=list[PreviousSeasonPlayerStatRead])
def list_previous_season_stats(
    season: str | None = Query(default=None),
    player_name: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(PreviousSeasonPlayerStat)
    if season is not None:
        query = query.filter(PreviousSeasonPlayerStat.season == season)
    if player_name is not None:
        query = query.filter(PreviousSeasonPlayerStat.player_name.ilike(f"%{player_name}%"))
    return query.order_by(PreviousSeasonPlayerStat.season.desc(), PreviousSeasonPlayerStat.player_name).all()


@router.post("", response_model=PreviousSeasonPlayerStatRead, status_code=201)
def create_previous_season_stat(payload: PreviousSeasonPlayerStatCreate, db: Session = Depends(get_db)):
    """Création stricte, pas un upsert : `(season, player_name)` doit être
    disponible (comparaison insensible à la casse, comme partout ailleurs
    dans le projet -- voir player_matching.py). Corriger une ligne
    existante se fait via PATCH, pas en la recréant ici."""
    existing = find_prev_season_stat_by_name(db, payload.season, payload.player_name)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Une ligne existe déjà pour ce joueur et cette saison -- utilisez plutôt la modification.",
        )
    _validate_mpg(payload.mpg)
    team_abbreviation = _validate_and_normalize_abbreviation(payload.team_abbreviation)

    stat = PreviousSeasonPlayerStat(
        season=payload.season,
        player_name=payload.player_name,
        team_abbreviation=team_abbreviation,
        per=payload.per,
        mpg=payload.mpg,
    )
    db.add(stat)
    db.commit()
    db.refresh(stat)
    return stat


@router.patch("/{stat_id}", response_model=PreviousSeasonPlayerStatRead)
def update_previous_season_stat(
    stat_id: int, payload: PreviousSeasonPlayerStatUpdate, db: Session = Depends(get_db)
):
    """Édition directe par id."""
    stat = db.get(PreviousSeasonPlayerStat, stat_id)
    if stat is None:
        raise HTTPException(status_code=404, detail="Ligne introuvable")

    fields = payload.model_dump(exclude_unset=True)
    if "mpg" in fields:
        _validate_mpg(fields["mpg"])
    if "team_abbreviation" in fields:
        fields["team_abbreviation"] = _validate_and_normalize_abbreviation(fields["team_abbreviation"])

    if "season" in fields or "player_name" in fields:
        target_season = fields.get("season", stat.season)
        target_name = fields.get("player_name", stat.player_name)
        conflict = find_prev_season_stat_by_name(db, target_season, target_name)
        if conflict is not None and conflict.id != stat.id:
            raise HTTPException(
                status_code=409,
                detail="Une autre ligne existe déjà pour ce joueur et cette saison",
            )

    for field, value in fields.items():
        setattr(stat, field, value)

    db.commit()
    db.refresh(stat)
    return stat


@router.delete("/{stat_id}", status_code=204)
def delete_previous_season_stat(stat_id: int, db: Session = Depends(get_db)):
    """Suppression directe par id -- symétrique de DELETE /api/players/{id}
    et DELETE /api/games/{id}. Contrairement à Game (référencée par
    Prediction.game_id), aucune table ne référence previous_season_player_stats.id
    par clé étrangère (vérifié) : tous les rapprochements se font par
    (season, player_name) via find_prev_season_stat_by_name, jamais par id --
    pas de cascade à gérer.

    N'affecte qu'un futur recalcul (le joueur concerné retombe sur le cas
    "pas de fallback disponible", déjà géré) : une Prediction déjà
    sauvegardée stocke un résultat figé au moment du calcul (des valeurs,
    jamais une référence vivante vers cette table), donc totalement
    inchangée par cette suppression."""
    stat = db.get(PreviousSeasonPlayerStat, stat_id)
    if stat is None:
        raise HTTPException(status_code=404, detail="Ligne introuvable")
    db.delete(stat)
    db.commit()
