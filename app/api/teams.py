from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Team
from app.schemas import TeamSummaryRead

router = APIRouter(prefix="/api/teams", tags=["teams"])


@router.get("", response_model=list[TeamSummaryRead])
def list_teams(db: Session = Depends(get_db)):
    """Route publique : les noms/abréviations d'équipe sont déjà exposés
    publiquement ailleurs (ex: /api/predictions/today), donc rien de nouveau
    côté confidentialité. Sert notamment à peupler le sélecteur d'équipe
    d'AdminPlayersView.vue."""
    return db.query(Team).order_by(Team.name).all()
