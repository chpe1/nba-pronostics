from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ImportType(str, enum.Enum):
    TEAMS_HOME_AWAY = "teams_home_away"
    PLAYERS_ADVANCED = "players_advanced"
    DRAFT = "draft"
    SCHEDULE = "schedule"


class ImportStatus(str, enum.Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"


class SeasonType(str, enum.Enum):
    """La saison à laquelle appartiennent les données d'un import CSV.

    "previous" concerne uniquement teams_home_away/players_advanced (voir
    csv_import.py) ; sans objet pour "draft", toujours "current".
    """

    CURRENT = "current"
    PREVIOUS = "previous"


class ImportHistory(Base):
    __tablename__ = "import_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_type: Mapped[ImportType] = mapped_column(Enum(ImportType), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[ImportStatus] = mapped_column(Enum(ImportStatus), nullable=False)
    # Liste des erreurs par ligne : [{"row": 3, "message": "..."}]
    errors: Mapped[list] = mapped_column(JSON, default=list)

    season_type: Mapped[SeasonType] = mapped_column(
        Enum(SeasonType), default=SeasonType.CURRENT, nullable=False
    )
    # Libellé de la saison N-1 (ex: "2024-2025"), renseigné uniquement quand
    # season_type == PREVIOUS.
    season: Mapped[str | None] = mapped_column(String(9), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<ImportHistory {self.import_type} {self.filename} {self.status}>"
