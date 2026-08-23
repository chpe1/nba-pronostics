from app.core.security import create_access_token
from tests.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME


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
