from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.import_history import ImportStatus, ImportType


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
    created_at: datetime


class ImportPreviewResponse(BaseModel):
    import_type: ImportType
    filename: str
    row_count: int
    error_count: int
    sample_rows: list[dict]
    errors: list[ImportErrorDetail]


class ImportResultResponse(BaseModel):
    import_history: ImportHistoryRead
