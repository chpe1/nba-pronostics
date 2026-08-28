"""Protection anti-brute-force sur /api/auth/login (compte admin unique).

Verrou global (pas par IP/compte) : cohérent avec une authentification à un
seul compte admin, pas un système multi-utilisateurs. État persisté en base
(LoginLockout, ligne unique) plutôt qu'un compteur en mémoire -- un
redémarrage du serveur en usage normal (mise à jour Windows, veille, simple
relance) ne doit pas remettre le compteur à zéro et annuler la protection.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import LoginLockout

logger = logging.getLogger(__name__)

# Constantes en dur (pas un curseur Settings) : paramètre de sécurité, pas un
# réglage de l'algorithme de pronostic.
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=5)


def _now() -> datetime:
    """UTC naïf : `locked_until` est stocké en DateTime naïf (comme toutes
    les colonnes DateTime de ce projet, ex: Game.game_date) -- un datetime
    conscient du fuseau (`datetime.now(UTC)`) ne serait plus comparable à la
    valeur relue depuis la base après un aller-retour SQLite."""
    return datetime.now(UTC).replace(tzinfo=None)


def _get_or_create_lockout(db: Session) -> LoginLockout:
    lockout = db.query(LoginLockout).first()
    if lockout is None:
        lockout = LoginLockout()
        db.add(lockout)
        db.commit()
        db.refresh(lockout)
    return lockout


def _reset_if_expired(lockout: LoginLockout, now: datetime) -> None:
    if lockout.locked_until is not None and lockout.locked_until <= now:
        lockout.failed_attempts = 0
        lockout.locked_until = None


def check_not_locked(db: Session) -> None:
    """Lève 429 si un verrou actif existe -- appelée AVANT toute vérification
    du mot de passe, pour bloquer aussi bien une tentative avec le bon mot de
    passe qu'une tentative incorrecte pendant le verrou (sinon la protection
    ne protège rien : un attaquant qui retombe sur le bon mot de passe
    pendant le verrou s'y connecterait quand même)."""
    lockout = _get_or_create_lockout(db)
    now = _now()
    _reset_if_expired(lockout, now)
    if lockout.locked_until is not None:
        remaining = max(1, int((lockout.locked_until - now).total_seconds()))
        logger.warning("Tentative de connexion refusée : compte verrouillé encore %ds", remaining)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Trop de tentatives échouées. Réessayez dans {remaining} secondes.",
            headers={"Retry-After": str(remaining)},
        )
    db.commit()


def register_failed_attempt(db: Session) -> None:
    lockout = _get_or_create_lockout(db)
    now = _now()
    _reset_if_expired(lockout, now)

    lockout.failed_attempts += 1
    logger.warning(
        "Tentative de connexion échouée (%d/%d)", lockout.failed_attempts, MAX_FAILED_ATTEMPTS
    )
    if lockout.failed_attempts >= MAX_FAILED_ATTEMPTS:
        lockout.locked_until = now + LOCKOUT_DURATION
        logger.warning(
            "Compte verrouillé %d minutes après %d échecs consécutifs",
            LOCKOUT_DURATION.total_seconds() // 60,
            lockout.failed_attempts,
        )
    db.commit()


def register_successful_login(db: Session) -> None:
    lockout = _get_or_create_lockout(db)
    if lockout.failed_attempts or lockout.locked_until is not None:
        lockout.failed_attempts = 0
        lockout.locked_until = None
        db.commit()
