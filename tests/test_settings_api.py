from app.models import Settings


def test_settings_requires_authentication(client):
    assert client.get("/api/settings").status_code == 401
    assert client.put("/api/settings", json={}).status_code == 401


def test_get_settings_creates_default_row_if_missing(client, db_session, auth_headers):
    assert db_session.query(Settings).count() == 0

    response = client.get("/api/settings", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["base_note_multiplier"] == 1.0
    assert body["mpg_threshold"] == 15.0
    assert body["reliability_threshold_low"] == 5.0
    assert body["reliability_threshold_high"] == 10.0
    assert db_session.query(Settings).count() == 1


def test_get_settings_returns_existing_row_without_duplicating(client, db_session, auth_headers):
    client.get("/api/settings", headers=auth_headers)
    client.get("/api/settings", headers=auth_headers)
    assert db_session.query(Settings).count() == 1


def test_update_settings_partial_update(client, db_session, auth_headers):
    client.get("/api/settings", headers=auth_headers)  # crée la ligne par défaut

    response = client.put(
        "/api/settings",
        json={"base_note_multiplier": 2.5, "draft_bonus_config": {"1": 6.0}},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["base_note_multiplier"] == 2.5
    assert body["draft_bonus_config"] == {"1": 6.0}
    # Les champs non fournis restent inchangés.
    assert body["per_impact_multiplier"] == 1.0

    db_session.expire_all()
    settings = db_session.query(Settings).one()
    assert settings.base_note_multiplier == 2.5
