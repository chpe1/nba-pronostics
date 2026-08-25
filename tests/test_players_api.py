from app.models import Player, Team
from app.services.csv_import import apply_players_advanced


def _teams(db_session) -> tuple[Team, Team]:
    bos = Team(name="Boston Celtics", abbreviation="BOS")
    lal = Team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add_all([bos, lal])
    db_session.flush()
    return bos, lal


def test_list_players_requires_authentication(client):
    assert client.get("/api/players").status_code == 401


def test_list_players_filters_by_team(client, db_session, auth_headers):
    bos, lal = _teams(db_session)
    db_session.add_all(
        [
            Player(name="Jayson Tatum", team_id=bos.id),
            Player(name="LeBron James", team_id=lal.id),
        ]
    )
    db_session.commit()

    response = client.get("/api/players", params={"team_id": bos.id}, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "Jayson Tatum"
    assert body[0]["team_abbreviation"] == "BOS"


def test_list_players_without_filter_returns_all(client, db_session, auth_headers):
    bos, lal = _teams(db_session)
    db_session.add_all(
        [
            Player(name="Jayson Tatum", team_id=bos.id),
            Player(name="LeBron James", team_id=lal.id),
        ]
    )
    db_session.commit()

    response = client.get("/api/players", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_create_player_requires_authentication(client, db_session):
    bos, _ = _teams(db_session)
    db_session.commit()
    response = client.post("/api/players", json={"name": "Rookie", "team_id": bos.id})
    assert response.status_code == 401


def test_create_player_unknown_team_returns_404(client, auth_headers):
    response = client.post(
        "/api/players", json={"name": "Rookie", "team_id": 999999}, headers=auth_headers
    )
    assert response.status_code == 404


def test_create_player_new_returns_201(client, db_session, auth_headers):
    bos, _ = _teams(db_session)
    db_session.commit()

    response = client.post(
        "/api/players",
        json={"name": "Joe Rookie", "team_id": bos.id, "draft_pick": 14, "per": 12.5, "mpg": 18.0},
        headers=auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Joe Rookie"
    assert body["draft_pick"] == 14
    assert body["per"] == 12.5
    assert body["mpg"] == 18.0
    assert db_session.query(Player).count() == 1


def test_create_player_upserts_existing_by_name_and_team_without_duplicating(client, db_session, auth_headers):
    """Scénario clé (point 2bis) : POST avec un (name, team_id) déjà
    existant met à jour la ligne existante -- ne crée jamais de doublon."""
    bos, _ = _teams(db_session)
    existing = Player(name="Jayson Tatum", team_id=bos.id, per=20.0, mpg=35.0, draft_pick=3)
    db_session.add(existing)
    db_session.commit()

    response = client.post(
        "/api/players",
        json={"name": "Jayson Tatum", "team_id": bos.id, "per": 22.0},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == existing.id
    assert body["per"] == 22.0
    assert body["mpg"] == 35.0  # non fourni -> inchangé
    assert body["draft_pick"] == 3  # non fourni -> inchangé
    assert db_session.query(Player).count() == 1


def test_manual_placeholder_is_overwritten_by_next_csv_import_without_protection(client, db_session, auth_headers):
    """Décision explicite (point 2bis) : contrairement à Game.manually_overridden,
    aucun verrou n'existe côté Player -- un placeholder manuel est écrasé
    sans protection par le prochain import CSV du même joueur."""
    bos, _ = _teams(db_session)
    db_session.commit()

    response = client.post(
        "/api/players",
        json={"name": "Joe Rookie", "team_id": bos.id, "per": 10.0},
        headers=auth_headers,
    )
    assert response.status_code == 201
    player_id = response.json()["id"]

    apply_players_advanced(
        [{"name": "Joe Rookie", "team_abbreviation": "BOS", "per": 25.0}], db_session
    )
    db_session.commit()

    updated = db_session.get(Player, player_id)
    assert updated.per == 25.0
    assert db_session.query(Player).count() == 1


def test_update_player_requires_authentication(client, db_session):
    bos, _ = _teams(db_session)
    player = Player(name="Jayson Tatum", team_id=bos.id)
    db_session.add(player)
    db_session.commit()

    response = client.patch(f"/api/players/{player.id}", json={"per": 20.0})
    assert response.status_code == 401


def test_update_player_unknown_id_returns_404(client, auth_headers):
    response = client.patch("/api/players/999999", json={"per": 20.0}, headers=auth_headers)
    assert response.status_code == 404


def test_update_player_unknown_team_returns_404(client, db_session, auth_headers):
    bos, _ = _teams(db_session)
    player = Player(name="Jayson Tatum", team_id=bos.id)
    db_session.add(player)
    db_session.commit()

    response = client.patch(
        f"/api/players/{player.id}", json={"team_id": 999999}, headers=auth_headers
    )
    assert response.status_code == 404


def test_update_player_partial_edit_leaves_other_fields_untouched(client, db_session, auth_headers):
    bos, _ = _teams(db_session)
    player = Player(name="Jayson Tatum", team_id=bos.id, per=20.0, mpg=35.0, draft_pick=3)
    db_session.add(player)
    db_session.commit()

    response = client.patch(f"/api/players/{player.id}", json={"per": 21.5}, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["per"] == 21.5
    assert body["mpg"] == 35.0
    assert body["draft_pick"] == 3
    assert body["name"] == "Jayson Tatum"


def test_update_player_rename_and_reassign_team(client, db_session, auth_headers):
    bos, lal = _teams(db_session)
    player = Player(name="Typo Namee", team_id=bos.id)
    db_session.add(player)
    db_session.commit()

    response = client.patch(
        f"/api/players/{player.id}",
        json={"name": "Correct Name", "team_id": lal.id},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Correct Name"
    assert body["team_id"] == lal.id
    assert body["team_abbreviation"] == "LAL"
