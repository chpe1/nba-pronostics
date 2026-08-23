from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.team import Team


class InjuryStatus(str, enum.Enum):
    HEALTHY = "healthy"
    OUT = "out"
    QUESTIONABLE = "questionable"
    DOUBTFUL = "doubtful"
    PROBABLE = "probable"
    AVAILABLE = "available"


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)
    # Équipe précédente (transfert estival) : sert au report du PER lors des
    # 10 premiers matchs de saison.
    previous_team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id"), nullable=True
    )

    per: Mapped[float] = mapped_column(Float, default=0.0)
    # Temps de jeu moyen (minutes) : filtre de pertinence à 15 min appliqué
    # côté algorithme, pas ici.
    mpg: Mapped[float] = mapped_column(Float, default=0.0)

    injury_status: Mapped[InjuryStatus] = mapped_column(
        Enum(InjuryStatus), default=InjuryStatus.HEALTHY, nullable=False
    )
    injury_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Numéro de pick à la draft (nullable si non-rookie), pour le bonus draft
    draft_pick: Mapped[int | None] = mapped_column(Integer, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    team: Mapped["Team"] = relationship(
        "Team", back_populates="players", foreign_keys=[team_id]
    )
    previous_team: Mapped["Team | None"] = relationship(
        "Team", foreign_keys=[previous_team_id]
    )

    def __repr__(self) -> str:
        return f"<Player {self.name}>"
