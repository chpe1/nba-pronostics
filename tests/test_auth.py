from datetime import UTC, datetime, timedelta

import pytest

from app.core.security import MIN_JWT_SECRET_BYTES, create_access_token, decode_access_token
from app.models import LoginLockout
from app.services.login_lockout import MAX_FAILED_ATTEMPTS
from tests.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME


# --- Validation du secret JWT (audit sécurité 2026-08-29) -------------------


def test_create_access_token_rejects_secret_shorter_than_minimum(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "too-short")
    with pytest.raises(RuntimeError, match="trop court"):
        create_access_token("admin")


def test_decode_access_token_rejects_secret_shorter_than_minimum(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "too-short")
    with pytest.raises(RuntimeError, match="trop court"):
        decode_access_token("irrelevant-token")


def test_create_access_token_accepts_secret_at_exactly_the_minimum(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "a" * MIN_JWT_SECRET_BYTES)
    token = create_access_token("admin")
    assert len(token) > 0


def test_login_success_returns_jwt(client, admin_env):
    response = client.post(
        "/api/auth/login",
        json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 0


def test_login_wrong_password_rejected(client, admin_env):
    response = client.post(
        "/api/auth/login",
        json={"username": TEST_ADMIN_USERNAME, "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_login_wrong_username_rejected(client, admin_env):
    response = client.post(
        "/api/auth/login",
        json={"username": "not-the-admin", "password": TEST_ADMIN_PASSWORD},
    )
    assert response.status_code == 401


def test_login_without_admin_config_returns_500(client, monkeypatch):
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    response = client.post(
        "/api/auth/login", json={"username": "admin", "password": "whatever"}
    )
    assert response.status_code == 500


def test_protected_route_rejects_missing_token(client):
    response = client.get("/api/imports/history")
    assert response.status_code == 401


def test_protected_route_rejects_garbage_token(client, admin_env):
    response = client.get(
        "/api/imports/history", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401


def test_protected_route_rejects_token_for_different_username(client, admin_env):
    token = create_access_token("someone-else")
    response = client.get(
        "/api/imports/history", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


def test_protected_route_accepts_valid_token(client, admin_env, auth_headers):
    response = client.get("/api/imports/history", headers=auth_headers)
    assert response.status_code == 200


# --- Protection anti-brute-force (verrou global, voir login_lockout.py) ----


def _fail_login(client, times, password="wrong-password"):
    return [
        client.post("/api/auth/login", json={"username": TEST_ADMIN_USERNAME, "password": password})
        for _ in range(times)
    ]


def test_login_locks_out_after_max_failed_attempts(client, admin_env):
    responses = _fail_login(client, MAX_FAILED_ATTEMPTS)
    assert all(r.status_code == 401 for r in responses)  # même le dernier échec qui déclenche le verrou

    locked = client.post(
        "/api/auth/login", json={"username": TEST_ADMIN_USERNAME, "password": "wrong-password"}
    )
    assert locked.status_code == 429
    assert "Retry-After" in locked.headers


def test_login_rejects_correct_password_while_locked(client, admin_env):
    """Le verrou bloque aussi le bon mot de passe -- sinon il ne protège
    rien contre un attaquant qui finit par retomber dessus."""
    _fail_login(client, MAX_FAILED_ATTEMPTS)

    response = client.post(
        "/api/auth/login", json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD}
    )
    assert response.status_code == 429


def test_login_unlocks_after_lockout_expires(client, db_session, admin_env):
    _fail_login(client, MAX_FAILED_ATTEMPTS)

    lockout = db_session.query(LoginLockout).one()
    lockout.locked_until = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
    db_session.commit()

    response = client.post(
        "/api/auth/login", json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD}
    )
    assert response.status_code == 200


def test_successful_login_resets_failed_attempts(client, admin_env):
    _fail_login(client, MAX_FAILED_ATTEMPTS - 1)

    success = client.post(
        "/api/auth/login", json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD}
    )
    assert success.status_code == 200

    # Un seul nouvel échec après un succès ne doit pas re-verrouiller.
    response = client.post(
        "/api/auth/login", json={"username": TEST_ADMIN_USERNAME, "password": "wrong-password"}
    )
    assert response.status_code == 401


def test_failed_login_never_logs_the_password(client, admin_env, caplog):
    secret_password = "super-secret-guess"
    with caplog.at_level("WARNING"):
        client.post(
            "/api/auth/login", json={"username": TEST_ADMIN_USERNAME, "password": secret_password}
        )
    assert secret_password not in caplog.text
