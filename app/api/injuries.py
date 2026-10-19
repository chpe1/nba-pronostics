from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_current_admin
from app.database import get_db
from app.schemas.injury import InjuryUpdateReport
from app.services.injury_report_fetcher import InjuryReportFetchError
from app.services.injury_report_runner import InjuryReportReadError, run_injury_update

router = APIRouter(prefix="/api/injuries", tags=["injuries"], dependencies=[Depends(get_current_admin)])


@router.post("/refresh", response_model=InjuryUpdateReport)
def refresh_injuries(db: Session = Depends(get_db)):
    """Télécharge le rapport de blessures NBA le plus récent, le lit, le
    rapproche des joueurs et applique les statuts en base. Déclenché à la
    main depuis l'écran d'import (la tâche planifiée reste désactivée).
    Aucune écriture si le rapport n'est pas encore soumis (ou vide) : la
    transaction n'est validée que si quelque chose a été écrit."""
    try:
        report = run_injury_update(db)
    except InjuryReportFetchError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except InjuryReportReadError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if report.written:
        db.commit()
    else:
        db.rollback()
    return report
