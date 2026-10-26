from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, func
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

    # Probabilité de victoire (modèle d'écart de points), calculée À CÔTÉ de la note -- jamais utilisée par
    # elle. Toutes vides (NULL) pour un pronostic calculé avant son introduction, et pour un match dont un écart
    # N-1 manque (probabilité incalculable : la version et les valeurs d'entrée sont alors quand même notées).
    # `probability_model_version` identifie formule + réglages (services/win_probability.py) : deux
    # probabilités ne sont comparables que si elles portent la même version.
    probability_model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Marge attendue en points, du point de vue de l'équipe à domicile (positif = domicile favori).
    expected_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    home_win_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Valeurs ayant servi au calcul (réglages, écart N-1, matchs terminés utilisés, somme des marges, force)
    # -- figées comme le reste du pronostic (Décision n°24).
    probability_inputs: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    game: Mapped["Game"] = relationship("Game")
    predicted_winner: Mapped["Team"] = relationship("Team", foreign_keys=[predicted_winner_team_id])

    def __repr__(self) -> str:
        return f"<Prediction game_id={self.game_id}>"
