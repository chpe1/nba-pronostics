from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.game import Game
    from app.models.team import Team


class ReliabilityLevel(str, enum.Enum):
    FAIBLE = "faible"
    MOYENNE = "moyenne"
    FORTE = "forte"


class Prediction(Base):
    """Pronostic calculé pour un match. Une ligne par Game, recalculée en
    place à chaque exécution du moteur (pas d'historique de versions pour
    le MVP)."""

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), unique=True, nullable=False)

    home_team_note: Mapped[float] = mapped_column(Float, nullable=False)
    away_team_note: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_winner_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)
    # home_team_note - away_team_note (positif = domicile favori)
    spread: Mapped[float] = mapped_column(Float, nullable=False)
    reliability: Mapped[ReliabilityLevel] = mapped_column(Enum(ReliabilityLevel), nullable=False)

    # Détail par composant (note de base, malus PER, malus calendrier, bonus
    # draft, joueurs Questionable...) pour chaque équipe : transparence/debug,
    # base pour l'affichage frontend (badges "incertain" par joueur, etc.).
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    game: Mapped["Game"] = relationship("Game")
    predicted_winner: Mapped["Team"] = relationship("Team", foreign_keys=[predicted_winner_team_id])

    def __repr__(self) -> str:
        return f"<Prediction game_id={self.game_id}>"
