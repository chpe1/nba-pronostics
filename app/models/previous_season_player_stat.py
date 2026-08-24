from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PreviousSeasonPlayerStat(Base):
    """Instantané du roster N-1 (équipe, PER, MPG), utilisé uniquement pour
    la détection des transferts (Étape 6bis).

    Volontairement séparée de `Player` (qui représente l'effectif ACTUEL) :
    aucune requête de `pronostic_calculator.py` ne touche cette table en
    dehors du calcul du bonus/malus transfert, ce qui rend impossible toute
    pollution accidentelle des calculs courants (injury_penalty, filtres de
    roster actif, etc.) par des données de la saison précédente.
    """

    __tablename__ = "previous_season_player_stats"
    __table_args__ = (UniqueConstraint("season", "player_name", name="uq_prev_season_player"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Libellé de la saison N-1 représentée, ex: "2024-2025".
    season: Mapped[str] = mapped_column(String(9), nullable=False)
    # Tel qu'il apparaît dans le CSV N-1 -- sert au rapprochement par nom
    # avec Player.name (même logique pragmatique que le reste de l'app).
    player_name: Mapped[str] = mapped_column(String(100), nullable=False)
    team_abbreviation: Mapped[str] = mapped_column(String(5), nullable=False)

    per: Mapped[float | None] = mapped_column(Float, nullable=True)
    mpg: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<PreviousSeasonPlayerStat {self.player_name} {self.season} {self.team_abbreviation}>"
