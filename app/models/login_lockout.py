from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LoginLockout(Base):
    """État de la protection anti-brute-force sur /api/auth/login.

    Table à ligne unique (même convention que Settings), mais volontairement
    séparée de Settings : état de sécurité, pas un curseur de l'algorithme.
    Verrou global, pas par compte/IP -- cohérent avec l'authentification
    admin unique (pas un système multi-utilisateurs).

    Persisté (pas un compteur en mémoire) : un redémarrage du serveur en
    usage normal (mise à jour Windows, veille, simple relance) ne doit pas
    remettre le compteur à zéro et annuler la protection.
    """

    __tablename__ = "login_lockouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<LoginLockout failed_attempts={self.failed_attempts} locked_until={self.locked_until}>"
