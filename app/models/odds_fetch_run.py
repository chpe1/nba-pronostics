from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OddsFetchTrigger(str, enum.Enum):
    SCHEDULED = "scheduled"  # tâche planifiée
    BUTTON = "button"  # bouton « Relever les cotes maintenant »


class OddsFetchRun(Base):
    """Journal des appels à the-odds-api.com : UNE ligne par appel, réussi ou non.

    C'est lui qui distingue « la cote n'a pas bougé » (un appel a eu lieu, il a relu la même valeur) de « on n'a
    pas regardé » (aucun appel à cette heure-là : PC éteint, serveur arrêté, crédits épuisés). Un appel en échec
    est journalisé lui aussi, avec son erreur, et n'écrit aucune cote.

    `report` : le compte-rendu complet de l'appel (matchs reconnus, non reconnus avec leur motif, sans cote encore
    ouverte, commencés et ignorés, écarts d'heure de coup d'envoi), tel que l'écran l'affiche. L'alerte « coup
    d'envoi annoncé plus tôt » est recalculée à l'affichage à partir des heures qu'il contient
    (`app/services/odds_fetcher.py::active_kickoff_alerts`), jamais stockée à part.
    """

    __tablename__ = "odds_fetch_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Instant de l'appel, naïf UTC -- c'est aussi le `recorded_at` des cotes écrites par cet appel.
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    trigger: Mapped[OddsFetchTrigger] = mapped_column(Enum(OddsFetchTrigger), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # En-têtes x-requests-last / x-requests-remaining de l'API (vides si l'appel n'a pas abouti).
    credits_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    credits_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    events_returned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<OddsFetchRun {self.fetched_at} {self.trigger.value} http={self.http_status} rows={self.rows_written}>"
