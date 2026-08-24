from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.team import Team


class GameStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    FINISHED = "finished"
    POSTPONED = "postponed"


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Saison au format "2025-2026", utile pour filtrer les stats par saison
    # et calculer la règle des 10 premiers matchs.
    season: Mapped[str] = mapped_column(String(9), nullable=False)
    game_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)

    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[GameStatus] = mapped_column(
        Enum(GameStatus), default=GameStatus.SCHEDULED, nullable=False
    )

    # Verrouille ce match hors des mises à jour automatiques (réimport CSV du
    # calendrier, synchro balldontlie.io) : posé explicitement par l'admin
    # depuis le formulaire de correction manuelle (date reportée, score saisi
    # à la main). Ne doit jamais être mis à True implicitement par le backend.
    manually_overridden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    home_team: Mapped["Team"] = relationship(
        "Team", back_populates="home_games", foreign_keys=[home_team_id]
    )
    away_team: Mapped["Team"] = relationship(
        "Team", back_populates="away_games", foreign_keys=[away_team_id]
    )

    def __repr__(self) -> str:
        return f"<Game {self.away_team_id}@{self.home_team_id} {self.game_date:%Y-%m-%d}>"
