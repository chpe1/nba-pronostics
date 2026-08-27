from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.team import Team


# Minutes moyennes/match maximales réalistes sur une saison (48 min
# réglementaires + marge prolongations) : au-delà, une valeur de mpg est une
# erreur de saisie/donnée plutôt qu'un vrai record -- validée au formulaire
# admin manuel ET à l'import CSV (voir app/api/players.py, app/services/csv_import.py).
MAX_REALISTIC_MPG = 48.0


class InjuryStatus(str, enum.Enum):
    HEALTHY = "healthy"
    OUT = "out"
    QUESTIONABLE = "questionable"
    DOUBTFUL = "doubtful"
    PROBABLE = "probable"
    AVAILABLE = "available"


class Player(Base):
    __tablename__ = "players"
    # Filet de sécurité complémentaire, PAS un remplacement de la
    # déduplication insensible à la casse : cette contrainte bloque un
    # doublon EXACT (même chaîne, même team_id) qui contournerait
    # find_player_by_name suite à un bug futur non anticipé. Elle ne détecte
    # PAS "LeBron James" vs "LEBRON JAMES" -- SQLite ne replie que l'ASCII,
    # comme LOWER() -- cette casse-là reste protégée uniquement par
    # find_player_by_name (app/services/player_matching.py). Voir CLAUDE.md,
    # "Décisions d'architecture", point 4.
    __table_args__ = (UniqueConstraint("name", "team_id", name="uq_player_name_team"),)

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
    # Nombre de matchs joués cette saison (colonne G du fichier Advanced,
    # déjà extraite pour calculer mpg = mp/g -- voir csv_import.py). Sert de
    # garde-fou petit échantillon côté algorithme (Settings.player_sample_size_threshold,
    # voir pronostic_calculator.py) : PAS mis à jour en temps réel entre deux
    # imports CSV, donc temporairement figé après le dernier import -- limite
    # acceptée, voir CLAUDE.md ("Décisions d'architecture").
    games_played_this_season: Mapped[int] = mapped_column(Integer, default=0)

    injury_status: Mapped[InjuryStatus] = mapped_column(
        Enum(InjuryStatus), default=InjuryStatus.HEALTHY, nullable=False
    )
    injury_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Raison brute issue du rapport de blessures (ex: "Injury/Illness-RightAnkle;Sprain")
    injury_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

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
