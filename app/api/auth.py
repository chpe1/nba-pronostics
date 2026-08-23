from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.security import (
    create_access_token,
    get_admin_password_hash,
    get_admin_username,
    verify_password,
)
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Identifiants invalides"
        )

    token = create_access_token(admin_username)
    return TokenResponse(access_token=token)
