from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ImportType(str, enum.Enum):
    TEAMS_HOME_AWAY = "teams_home_away"
    PLAYERS_ADVANCED = "players_advanced"
    PLAYERS_PER_GAME = "players_per_game"


class ImportStatus(str, enum.Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"


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

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<ImportHistory {self.import_type} {self.filename} {self.status}>"
