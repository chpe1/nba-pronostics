from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.game import Game
    from app.models.odds_fetch_run import OddsFetchRun


class OddsSide(str, enum.Enum):
    HOME = "home"
    AWAY = "away"


class OddsMarket(str, enum.Enum):
    # Seul marché pour l'instant (victoire, pas de nul au basket). Le handicap viendra plus tard sans
    # migration structurelle de cette table -- seulement une colonne de plus (la valeur de la ligne,
    # ex. "+5.5", absente pour WINNER) et un nouveau membre d'énumération. Voir CLAUDE.md.
    WINNER = "winner"
    # Cote de VENTE d'une bourse d'échange (Betfair, marché `h2h_lay` de the-odds-api) : parier CONTRE l'équipe.
    # L'achat va dans WINNER. Stockée sans jugement : c'est l'écart achat/vente qui dit si la bourse a de la
    # liquidité (un 1,50 / 2,50 paraît normal et ne vaut rien), et on ne peut le voir qu'avec les deux côtés.
    WINNER_LAY = "winner_lay"


class OddsCollection(str, enum.Enum):
    """Façon dont la cote a été relevée : saisie à la main sur l'écran Cotes, ou relevé automatique
    the-odds-api.com. Distingue deux séries d'un MÊME bookmaker, prises à des heures différentes."""

    MANUEL = "manuel"
    API = "api"


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

    `source` est une chaîne libre (PAS un type énuméré SQL) : l'identifiant EXACT du bookmaker chez
    the-odds-api.com (`winamax_fr`, `unibet_fr`, `betfair_ex_eu`, `winamax_de`...), y compris pour une saisie
    manuelle (validée contre `app/services/odds.py::KNOWN_ODDS_SOURCES`). Les 240 cotes saisies avant le
    2026-11-03 sous « winamax »/« unibet » ont été renommées `winamax_fr`/`unibet_fr` par la migration
    a7b8c9d0e1f2, après comparaison des cotes de l'API aux deux sites par l'utilisateur.

    `collection` dit COMMENT la cote a été relevée (saisie à la main ou relevé automatique) : deux séries d'un
    même bookmaker restent distinctes. La règle de doublon ci-dessus ne vaut que pour la saisie manuelle ; un
    relevé automatique écrit CHAQUE cote lue, même inchangée (`app/services/odds_fetcher.py`), et c'est le
    journal des appels (`OddsFetchRun`) qui distingue « la cote n'a pas bougé » de « on n'a pas regardé ».
    """

    __tablename__ = "odds"
    __table_args__ = (
        UniqueConstraint(
            "game_id", "market", "side", "source", "collection", "recorded_at", name="uq_odds_snapshot"
        ),
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
    # Pas de défaut : toute écriture dit d'où vient la cote (un oubli serait une erreur, jamais un « manuel »
    # implicite qui mélangerait les deux séries).
    collection: Mapped[OddsCollection] = mapped_column(Enum(OddsCollection), nullable=False)
    # Relevé automatique seulement : l'instant où le BOOKMAKER a changé sa cote pour la dernière fois
    # (`last_update` du marché chez the-odds-api, naïf UTC). Distinct de `recorded_at` (instant de l'appel) :
    # une cote relevée à 19 h mais inchangée depuis 14 h n'est pas la même information. Vide pour une saisie.
    bookmaker_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Relevé automatique seulement : l'appel qui a produit la ligne (journal des appels). Vide pour une saisie.
    fetch_run_id: Mapped[int | None] = mapped_column(ForeignKey("odds_fetch_runs.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    game: Mapped["Game"] = relationship("Game")
    fetch_run: Mapped["OddsFetchRun | None"] = relationship("OddsFetchRun")

    def __repr__(self) -> str:
        return f"<Odds game_id={self.game_id} {self.source}/{self.side.value}={self.value} @ {self.recorded_at}>"
