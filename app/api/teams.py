from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_current_admin
from app.database import get_db
from app.models import Team
from app.schemas import TeamRead, TeamUpdate

router = APIRouter(prefix="/api/teams", tags=["teams"])


@router.get("", response_model=list[TeamRead])
def list_teams(db: Session = Depends(get_db)):
    """Route publique : les win_pct/nom/abréviation d'équipe sont déjà
    exposés publiquement ailleurs (ex: /api/predictions/today), donc rien de
    nouveau côté confidentialité. Réponse complète (TeamRead, pas un résumé)
    depuis la correction manuelle d'équipe (Admin > Équipes) : sert aussi au
    sélecteur d'équipe d'AdminPlayersView.vue, qui ignore simplement les
    champs en plus."""
    return db.query(Team).order_by(Team.name).all()


@router.patch("/{team_id}", response_model=TeamRead, dependencies=[Depends(get_current_admin)])
def update_team(team_id: int, payload: TeamUpdate, db: Session = Depends(get_db)):
    """Correction manuelle admin d'une équipe -- même esprit que le
    formulaire joueurs (Étape 7) : un ajustement ponctuel, pas verrouillé
    contre un futur réimport CSV (upsert existant inchangé, la dernière
    valeur importée l'emporte). Pas de création : les 30 équipes NBA
    existent déjà via les imports, aucun besoin identifié d'en créer une de
    plus à la main."""
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Équipe introuvable")

    fields = payload.model_dump(exclude_unset=True)

    if "name" in fields or "abbreviation" in fields:
        target_name = fields.get("name", team.name)
        target_abbreviation = fields.get("abbreviation", team.abbreviation)
        conflict = (
            db.query(Team)
            .filter(
                Team.id != team.id,
                (Team.name == target_name) | (Team.abbreviation == target_abbreviation),
            )
            .first()
        )
        if conflict is not None:
            raise HTTPException(
                status_code=409,
                detail="Une autre équipe existe déjà avec ce nom ou cette abréviation",
            )

    for field, value in fields.items():
        setattr(team, field, value)

    db.commit()
    db.refresh(team)
    return team
