from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ImportHistory, ImportStatus, ImportType
from app.schemas import ImportHistoryRead, ImportPreviewResponse, ImportResultResponse
from app.services import csv_import

router = APIRouter(prefix="/api/imports", tags=["imports"])


@router.post("/stats", response_model=ImportPreviewResponse | ImportResultResponse)
async def import_stats(
    file: UploadFile = File(...),
    dry_run: bool = Query(True, description="Aperçu sans écriture en base si true"),
    import_type: ImportType | None = Query(
        None, description="Force le type de fichier au lieu de la détection auto"
    ),
    db: Session = Depends(get_db),
):
    file_bytes = await file.read()
    try:
        df = csv_import.read_csv(file_bytes)
    except csv_import.CsvImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    detected_type = import_type or csv_import.detect_import_type(df)
    if detected_type is None:
        raise HTTPException(
            status_code=400,
            detail="Impossible de déterminer le type de fichier (colonnes attendues non trouvées).",
        )

    missing = csv_import.validate_columns(df, detected_type)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Colonnes manquantes pour {detected_type.value} : {', '.join(missing)}",
        )

    parsed, errors = csv_import.PARSERS[detected_type](df)
    filename = file.filename or "fichier.csv"

    if dry_run:
        return ImportPreviewResponse(
            import_type=detected_type,
            filename=filename,
            row_count=len(parsed),
            error_count=len(errors),
            sample_rows=parsed[:10],
            errors=errors,
        )

    row_count = csv_import.APPLIERS[detected_type](parsed, db)

    if errors and parsed:
        status = ImportStatus.PARTIAL
    elif errors and not parsed:
        status = ImportStatus.ERROR
    else:
        status = ImportStatus.SUCCESS

    history = ImportHistory(
        import_type=detected_type,
        filename=filename,
        row_count=row_count,
        error_count=len(errors),
        status=status,
        errors=errors,
    )
    db.add(history)
    db.commit()
    db.refresh(history)

    return ImportResultResponse(import_history=history)


@router.get("/history", response_model=list[ImportHistoryRead])
def get_import_history(db: Session = Depends(get_db)):
    return (
        db.query(ImportHistory)
        .order_by(ImportHistory.created_at.desc())
        .all()
    )
