from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.game import Game


class OddsSide(str, enum.Enum):
    HOME = "home"
    AWAY = "away"


class OddsMarket(str, enum.Enum):
    # Seul marché pour l'instant (victoire, pas de nul au basket). Le handicap viendra plus tard sans
    # migration structurelle de cette table -- seulement une colonne de plus (la valeur de la ligne,
    # ex. "+5.5", absente pour WINNER) et un nouveau membre d'énumération. Voir CLAUDE.md.
    WINNER = "winner"


class Odds(Base):
    """Un relevé de cote, à un instant donné, pour un match/marché/côté/bookmaker.

    HISTORIQUE COMPLET, jamais écrasé en place (décision explicite, 2026-10-24) : les cotes bougent dans
    la journée, la cote de clôture n'est pas celle du matin -- à l'inverse de `Prediction` (Décision
    n°24), qui ne garde qu'une seule ligne par match. `recorded_at` distingue les relevés successifs d'un
    même (match, marché, côté, source).

    Règle de doublon (service `app/services/odds.py::record_odds`, PAS ici) : même valeur que le dernier
    relevé connu -> rien n'est écrit ; valeur différente au même `recorded_at` qu'un relevé déjà en base ->
    ce relevé est corrigé en place (un bookmaker n'a qu'une seule vraie cote à un instant donné) ; valeur
    différente à un instant différent -> nouvelle ligne d'historique. La contrainte UNIQUE ci-dessous est
    le filet de sécurité qui rend ce choix possible sans jamais laisser deux lignes contradictoires au
    même instant -- complémentaire à cette logique de service, pas un remplacement (même principe que
    UNIQUE(name, team_id) sur Player, Décision d'architecture n°7).

    `source` est une chaîne libre (PAS un type énuméré SQL), validée à l'écriture contre une liste connue
    (`app/services/odds.py::KNOWN_ODDS_SOURCES`) et normalisée en casse avant stockage -- décision
    explicite du 2026-10-24 : un type énuméré SQL demanderait une migration pour chaque nouveau
    bookmaker, une simple liste Python n'en demande aucune.
    """

    __tablename__ = "odds"
    __table_args__ = (
        UniqueConstraint("game_id", "market", "side", "source", "recorded_at", name="uq_odds_snapshot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), nullable=False)
    market: Mapped[OddsMarket] = mapped_column(Enum(OddsMarket), default=OddsMarket.WINNER, nullable=False)
    side: Mapped[OddsSide] = mapped_column(Enum(OddsSide), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    # Instant du RELEVÉ (naïf UTC, comme LoginLockout.locked_until -- ce n'est pas une date de calendrier
    # de match comme Game.game_date, qui lui est en heure murale US/ET, Décision n°3 : c'est un instant
    # d'observation quelconque). Par défaut l'instant de la saisie, mais CORRIGIBLE par l'admin -- distinct
    # de created_at ci-dessous, qui lui ne l'est jamais.
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    game: Mapped["Game"] = relationship("Game")

    def __repr__(self) -> str:
        return f"<Odds game_id={self.game_id} {self.source}/{self.side.value}={self.value} @ {self.recorded_at}>"
