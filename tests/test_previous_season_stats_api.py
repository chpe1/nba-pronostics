from app.models import PreviousSeasonPlayerStat

SEASON = "2025-2026"


def _stat(**overrides) -> PreviousSeasonPlayerStat:
    defaults = dict(season=SEASON, player_name="LeBron James", team_abbreviation="LAL", per=25.0, mpg=35.0)
    defaults.update(overrides)
    return PreviousSeasonPlayerStat(**defaults)


# --- GET ---------------------------------------------------------------


def test_list_requires_authentication(client):
    assert client.get("/api/previous-season-stats").status_code == 401


def test_list_filters_by_season_and_player_name(client, db_session, auth_headers):
    db_session.add_all(
        [
            _stat(player_name="LeBron James", season="2025-2026"),
            _stat(player_name="Stephen Curry", season="2025-2026", team_abbreviation="GSW"),
            _stat(player_name="LeBron James", season="2024-2025"),
        ]
    )
    db_session.commit()

    response = client.get(
        "/api/previous-season-stats", params={"season": "2025-2026", "player_name": "lebron"}, headers=auth_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["player_name"] == "LeBron James"
    assert body[0]["season"] == "2025-2026"


# --- POST --------------------------------------------------------------


def test_create_requires_authentication(client):
    response = client.post(
        "/api/previous-season-stats",
        json={"season": SEASON, "player_name": "LeBron James", "team_abbreviation": "LAL"},
    )
    assert response.status_code == 401


def test_create_stat_succeeds(client, db_session, auth_headers):
    response = client.post(
        "/api/previous-season-stats",
        json={"season": SEASON, "player_name": "LeBron James", "team_abbreviation": "LAL", "per": 25.0, "mpg": 35.0},
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["player_name"] == "LeBron James"
    assert db_session.query(PreviousSeasonPlayerStat).count() == 1


def test_create_normalizes_non_canonical_abbreviation(client, db_session, auth_headers):
    """Comme à l'import CSV : "BRK" -> "BKN" avant écriture."""
    response = client.post(
        "/api/previous-season-stats",
        json={"season": SEASON, "player_name": "Some Player", "team_abbreviation": "BRK"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["team_abbreviation"] == "BKN"


def test_create_rejects_unknown_team_abbreviation(client, auth_headers):
    response = client.post(
        "/api/previous-season-stats",
        json={"season": SEASON, "player_name": "Some Player", "team_abbreviation": "ZZZ"},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_create_rejects_unrealistic_mpg(client, auth_headers):
    response = client.post(
        "/api/previous-season-stats",
        json={"season": SEASON, "player_name": "Some Player", "team_abbreviation": "LAL", "mpg": 99.0},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_create_rejects_duplicate_case_insensitive(client, db_session, auth_headers):
    db_session.add(_stat(player_name="LeBron James"))
    db_session.commit()

    response = client.post(
        "/api/previous-season-stats",
        json={"season": SEASON, "player_name": "LEBRON JAMES", "team_abbreviation": "LAL"},
        headers=auth_headers,
    )
    assert response.status_code == 409


# --- PATCH ---------------------------------------------------------------


def test_update_requires_authentication(client, db_session):
    stat = _stat()
    db_session.add(stat)
    db_session.commit()
    assert client.patch(f"/api/previous-season-stats/{stat.id}", json={"per": 20.0}).status_code == 401


def test_update_returns_404_for_unknown_id(client, auth_headers):
    response = client.patch("/api/previous-season-stats/999999", json={"per": 20.0}, headers=auth_headers)
    assert response.status_code == 404


def test_update_applies_partial_changes(client, db_session, auth_headers):
    stat = _stat()
    db_session.add(stat)
    db_session.commit()

    response = client.patch(
        f"/api/previous-season-stats/{stat.id}", json={"per": 27.5}, headers=auth_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["per"] == 27.5
    assert body["mpg"] == 35.0  # inchangé

    db_session.expire_all()
    assert db_session.get(PreviousSeasonPlayerStat, stat.id).per == 27.5


def test_update_rejects_unrealistic_mpg(client, db_session, auth_headers):
    stat = _stat()
    db_session.add(stat)
    db_session.commit()

    response = client.patch(f"/api/previous-season-stats/{stat.id}", json={"mpg": 99.0}, headers=auth_headers)
    assert response.status_code == 422


def test_update_normalizes_non_canonical_abbreviation(client, db_session, auth_headers):
    stat = _stat()
    db_session.add(stat)
    db_session.commit()

    response = client.patch(
        f"/api/previous-season-stats/{stat.id}", json={"team_abbreviation": "PHO"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["team_abbreviation"] == "PHX"


def test_update_rejects_collision_with_another_row(client, db_session, auth_headers):
    db_session.add(_stat(player_name="LeBron James", season=SEASON))
    other = _stat(player_name="Stephen Curry", season=SEASON, team_abbreviation="GSW")
    db_session.add(other)
    db_session.commit()

    response = client.patch(
        f"/api/previous-season-stats/{other.id}", json={"player_name": "LeBron James"}, headers=auth_headers
    )
    assert response.status_code == 409


def test_update_allows_keeping_its_own_name_and_season(client, db_session, auth_headers):
    stat = _stat()
    db_session.add(stat)
    db_session.commit()

    response = client.patch(
        f"/api/previous-season-stats/{stat.id}",
        json={"player_name": "LeBron James", "season": SEASON, "per": 30.0},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["per"] == 30.0
