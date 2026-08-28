"""Authentification admin unique (pas de système multi-utilisateurs).

Les identifiants/secrets sont lus depuis les variables d'environnement à
chaque appel (pas de constantes figées à l'import), pour rester facilement
surchargeables en test via `monkeypatch.setenv`.

Protection anti-brute-force sur /api/auth/login : voir
app/services/login_lockout.py (verrou global persisté en base, appliqué par
app/api/auth.py -- pas dans ce module, qui reste des utilitaires JWT/bcrypt
sans état).
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

JWT_ALGORITHM = "HS256"
DEFAULT_TOKEN_EXPIRE_MINUTES = 480

_bearer_scheme = HTTPBearer(auto_error=False)


def get_admin_username() -> str | None:
    return os.getenv("ADMIN_USERNAME")


def get_admin_password_hash() -> str | None:
    return os.getenv("ADMIN_PASSWORD_HASH")


def get_jwt_secret() -> str | None:
    return os.getenv("JWT_SECRET_KEY")


def get_token_expire_minutes() -> int:
    return int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", DEFAULT_TOKEN_EXPIRE_MINUTES))


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(username: str) -> str:
    secret = get_jwt_secret()
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY n'est pas configuré (.env)")
    expire = datetime.now(UTC) + timedelta(minutes=get_token_expire_minutes())
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str:
    """Retourne le username (sub) si le token est valide ; lève JWTError sinon."""
    secret = get_jwt_secret()
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY n'est pas configuré (.env)")
    payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
    return payload["sub"]


def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    """Dépendance FastAPI à appliquer sur toutes les routes back-office."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        username = decode_access_token(credentials.credentials)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    admin_username = get_admin_username()
    if admin_username is None or username != admin_username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username
