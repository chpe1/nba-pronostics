from __future__ import annotations

import os
from datetime import date, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_admin
from app.database import get_db
from app.schemas.scores import (
    ScoreSyncDay,
    ScoreSyncRecordedGame,
    ScoreSyncReport,
    ScoreSyncSkipped,
    ScoreSyncStatusChange,
)
from app.services.nba_calendar import current_nba_date
from app.services.scores_fetcher import (
    SKIP_MANUALLY_OVERRIDDEN,
    SKIP_NOT_IN_DATABASE,
    SKIP_UNKNOWN_DATE,
    SKIP_UNKNOWN_TEAM,
    DaySyncResult,
    sync_scores_for_range,
)

router = APIRouter(prefix="/api/scores", tags=["scores"], dependencies=[Depends(get_current_admin)])

# Plage la plus longue acceptée (jours inclus). Une plage entière tient en un seul appel API ; la limite
# évite surtout une saisie absurde (année entière) qui ramènerait des milliers de matchs.
MAX_RANGE_DAYS = 31
# Par défaut : les 3 derniers jours et aujourd'hui (dates NBA, US/ET) -- couvre une absence de trois jours
# ET la fenêtre habituelle de la tâche planifiée (hier + aujourd'hui), pour un seul appel à l'API.
DEFAULT_LOOKBACK_DAYS = 3

REASON_LABELS = {
    SKIP_UNKNOWN_TEAM: "équipe inconnue de la base",
    SKIP_NOT_IN_DATABASE: "aucun match correspondant en base (date, domicile, extérieur)",
    SKIP_MANUALLY_OVERRIDDEN: "match verrouillé à la main : jamais modifié par la synchro",
    SKIP_UNKNOWN_DATE: "date absente ou hors de la plage demandée dans la réponse de l'API",
}


def _day_read(day: DaySyncResult) -> ScoreSyncDay:
    return ScoreSyncDay(
        date=day.date,
        found=day.found,
        recorded_count=len(day.recorded),
        already_final_count=day.already_final,
        not_finished_count=day.not_finished,
        status_change_count=len(day.status_changes),
        skipped_count=day.skipped_count,
        recorded=[ScoreSyncRecordedGame(**vars(g)) for g in day.recorded],
        status_changes=[ScoreSyncStatusChange(**vars(c)) for c in day.status_changes],
        skipped=[
            ScoreSyncSkipped(label=s.label, reason=s.reason, reason_label=REASON_LABELS.get(s.reason, s.reason))
            for s in day.skipped
        ],
    )


@router.post("/sync", response_model=ScoreSyncReport)
def sync_scores(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Synchronise à la main les scores balldontlie.io sur une plage de dates NBA (US/ET), en un seul appel
    API. Complète la tâche planifiée (qui ne rattrape aucun créneau manqué et ne lit que la veille et le jour) ;
    ne la remplace ni ne la modifie. Le compte-rendu ne compte comme « enregistré » que les matchs dont une
    valeur a réellement changé ; la transaction n'est validée que si quelque chose a changé."""
    today = current_nba_date()
    end = date_to or today
    start = date_from or (end - timedelta(days=DEFAULT_LOOKBACK_DAYS))
    if start > end:
        raise HTTPException(status_code=422, detail="La date de début doit précéder ou égaler la date de fin.")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(status_code=422, detail=f"Plage trop longue : {MAX_RANGE_DAYS} jours au maximum.")

    api_key = os.getenv("BALLDONTLIE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="BALLDONTLIE_API_KEY absente de la configuration du serveur.")

    try:
        days = sync_scores_for_range(db, api_key, start, end)
    except httpx.HTTPStatusError as exc:
        db.rollback()
        body = (exc.response.text or "").strip()[:200]
        detail = f"balldontlie a répondu {exc.response.status_code}" + (f" : {body}" if body else "")
        if exc.response.status_code == 429:
            detail += " (limite de requêtes atteinte, réessayez dans une minute)"
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.RequestError as exc:
        db.rollback()
        raise HTTPException(
            status_code=502, detail=f"Impossible de joindre balldontlie : {str(exc) or type(exc).__name__}"
        ) from exc

    written = any(day.updated > 0 for day in days)
    if written:
        db.commit()
    else:
        db.rollback()

    return ScoreSyncReport(
        date_from=start,
        date_to=end,
        days_count=len(days),
        found=sum(d.found for d in days),
        recorded_count=sum(len(d.recorded) for d in days),
        already_final_count=sum(d.already_final for d in days),
        not_finished_count=sum(d.not_finished for d in days),
        status_change_count=sum(len(d.status_changes) for d in days),
        skipped_count=sum(d.skipped_count for d in days),
        written=written,
        days=[_day_read(d) for d in days],
    )
