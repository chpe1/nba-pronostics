from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    get_admin_password_hash,
    get_admin_username,
    verify_password,
)
from app.database import get_db
from app.schemas.auth import LoginRequest, TokenResponse
from app.services.login_lockout import (
    check_not_locked,
    register_failed_attempt,
    register_successful_login,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    check_not_locked(db)

    admin_username = get_admin_username()
    admin_password_hash = get_admin_password_hash()

    if not admin_username or not admin_password_hash:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuration admin manquante (.env) : ADMIN_USERNAME/ADMIN_PASSWORD_HASH",
        )

    if payload.username != admin_username or not verify_password(
        payload.password, admin_password_hash
    ):
        register_failed_attempt(db)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Identifiants invalides"
        )

    register_successful_login(db)
    token = create_access_token(admin_username)
    return TokenResponse(access_token=token)
