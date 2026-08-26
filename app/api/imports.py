from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.security import get_current_admin
from app.database import get_db
from app.models import ImportHistory, ImportStatus, ImportType, SeasonType, Team
from app.schemas import ImportHistoryRead, ImportPreviewResponse, ImportResultResponse
from app.services import csv_import

router = APIRouter(prefix="/api/imports", tags=["imports"], dependencies=[Depends(get_current_admin)])


@router.post("/stats", response_model=ImportPreviewResponse | ImportResultResponse)
async def import_stats(
    file: UploadFile = File(...),
    dry_run: bool = Query(True, description="Aperçu sans écriture en base si true"),
    import_type: ImportType | None = Query(
        None, description="Force le type de fichier au lieu de la détection auto"
    ),
    season_type: SeasonType = Query(
        SeasonType.CURRENT,
        description="Saison courante ou précédente (sans objet pour le type draft)",
    ),
    season: str | None = Query(
        None, description="Libellé de la saison N-1, ex: '2024-2025' (requis si season_type=previous)"
    ),
    team_id: int | None = Query(
        None,
        description=(
            "ID de l'équipe -- requis uniquement pour un roster Advanced "
            "d'une seule équipe (fichier sans colonne Team), quelle que soit la saison."
        ),
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

    # players_advanced accepte un roster d'une seule équipe (pas de colonne
    # Team, l'équipe est alors implicite au fichier) : team_id devient
    # obligatoire dans ce cas précis. resolved_team_* est renvoyé dans
    # l'aperçu dry-run -- seule protection contre une erreur de sélection
    # dans le menu déroulant, puisque le fichier ne contient aucune info
    # d'équipe à croiser.
    team_abbreviation_param: str | None = None
    resolved_team_name: str | None = None
    resolved_team_abbreviation: str | None = None
    if detected_type == ImportType.PLAYERS_ADVANCED and "Team" not in df.columns:
        if team_id is None:
            raise HTTPException(
                status_code=400,
                detail="Le paramètre 'team_id' est requis pour un roster par équipe (fichier sans colonne Team).",
            )
        team = db.get(Team, team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="Équipe introuvable")
        team_abbreviation_param = team.abbreviation
        resolved_team_name = team.name
        resolved_team_abbreviation = team.abbreviation

    # La draft n'a pas de notion de saison précédente (toujours l'effectif
    # actuel). Le calendrier n'a pas cette notion non plus, mais pour la
    # raison inverse : `season` y est TOUJOURS requis (pas de "courant" par
    # défaut déductible des dates, cf. plan-etape6ter.md).
    if detected_type == ImportType.SCHEDULE:
        effective_season_type = SeasonType.CURRENT
        if not season:
            raise HTTPException(
                status_code=400,
                detail="Le paramètre 'season' (ex: '2026-2027') est requis pour importer un calendrier.",
            )
    elif detected_type == ImportType.DRAFT:
        effective_season_type = SeasonType.CURRENT
    else:
        effective_season_type = season_type
        if effective_season_type == SeasonType.PREVIOUS and not season:
            raise HTTPException(
                status_code=400,
                detail="Le paramètre 'season' (ex: '2024-2025') est requis pour un import de saison précédente.",
            )

    if detected_type == ImportType.SCHEDULE:
        parser = csv_import.PARSERS[detected_type]
        applier = None  # apply_schedule appelé directement plus bas (signature dédiée)
    elif effective_season_type == SeasonType.PREVIOUS:
        parser = csv_import.PREV_SEASON_PARSERS[detected_type]
        applier = csv_import.PREV_SEASON_APPLIERS[detected_type]
    else:
        parser = csv_import.PARSERS[detected_type]
        applier = csv_import.APPLIERS[detected_type]

    if detected_type == ImportType.PLAYERS_ADVANCED:
        parsed, errors = parser(df, team_abbreviation=team_abbreviation_param)
    else:
        parsed, errors = parser(df)
    filename = file.filename or "fichier.csv"

    if dry_run:
        return ImportPreviewResponse(
            import_type=detected_type,
            filename=filename,
            row_count=len(parsed),
            error_count=len(errors),
            sample_rows=parsed[:10],
            errors=errors,
            season_type=effective_season_type,
            season=season if detected_type == ImportType.SCHEDULE or effective_season_type == SeasonType.PREVIOUS else None,
            resolved_team_name=resolved_team_name,
            resolved_team_abbreviation=resolved_team_abbreviation,
        )

    if detected_type == ImportType.SCHEDULE:
        row_count = csv_import.apply_schedule(parsed, db, season)
    elif effective_season_type == SeasonType.PREVIOUS:
        row_count = applier(parsed, db, season)
    else:
        row_count = applier(parsed, db)

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
        season_type=effective_season_type,
        season=season if detected_type == ImportType.SCHEDULE or effective_season_type == SeasonType.PREVIOUS else None,
    )
    db.add(history)
    db.commit()
    db.refresh(history)

    return ImportResultResponse(import_history=history)


@router.get("/template")
def download_template(
    type: str = Query(..., description="Un de : " + ", ".join(csv_import.TEMPLATE_KEYS)),
):
    """Aide-mémoire rapide du format actuellement attendu par chaque type de
    fichier -- généré depuis REQUIRED_COLUMNS (même source de vérité que la
    validation à l'import), pas une liste recopiée à la main."""
    try:
        content = csv_import.generate_template_csv(type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="modele_{type}.csv"'},
    )


@router.get("/history", response_model=list[ImportHistoryRead])
def get_import_history(db: Session = Depends(get_db)):
    return (
        db.query(ImportHistory)
        .order_by(ImportHistory.created_at.desc())
        .all()
    )
