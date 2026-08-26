from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.import_history import ImportStatus, ImportType, SeasonType


class ImportErrorDetail(BaseModel):
    row: int
    message: str


class ImportHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    import_type: ImportType
    filename: str
    row_count: int
    error_count: int
    status: ImportStatus
    errors: list[ImportErrorDetail]
    season_type: SeasonType
    season: str | None
    created_at: datetime


class ImportPreviewResponse(BaseModel):
    import_type: ImportType
    filename: str
    row_count: int
    error_count: int
    sample_rows: list[dict]
    errors: list[ImportErrorDetail]
    season_type: SeasonType
    season: str | None = None
    # Renseigné uniquement pour un roster Advanced d'une seule équipe (pas de
    # colonne Team dans le fichier) : seule protection visible contre une
    # erreur de sélection dans le menu déroulant équipe, le fichier lui-même
    # ne contenant aucune info d'équipe à croiser. Scope volontairement
    # limité à l'aperçu dry-run -- pas dans l'historique des imports.
    resolved_team_name: str | None = None
    resolved_team_abbreviation: str | None = None


class ImportResultResponse(BaseModel):
    import_history: ImportHistoryRead
