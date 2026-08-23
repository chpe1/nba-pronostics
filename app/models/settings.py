from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Settings(Base):
    """Réglages de l'algorithme (curseurs du back-office).

    Table à ligne unique : une seule ligne de configuration active
    (convention appliquée au niveau du service, pas d'une contrainte SQL).
    """

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Curseur A : multiplicateur de la note de base (% de victoires)
    base_note_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    # Curseur B : multiplicateur d'impact du PER des absents
    per_impact_multiplier: Mapped[float] = mapped_column(Float, default=1.0)

    back_to_back_penalty: Mapped[float] = mapped_column(Float, default=0.0)
    three_in_four_penalty: Mapped[float] = mapped_column(Float, default=0.0)

    # Seuil de temps de jeu (MPG) minimum pour la prise en compte du PER
    mpg_threshold: Mapped[float] = mapped_column(Float, default=15.0)

    # Bonus Draft par pick, ex: {"1": 5.0, "2": 4.0, ...}
    draft_bonus_config: Mapped[dict] = mapped_column(JSON, default=dict)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Settings id={self.id}>"
