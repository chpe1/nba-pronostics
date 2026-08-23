from pathlib import Path

from app.models import Player, Team

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _upload(client, filename: str, dry_run: bool, headers: dict):
    with open(FIXTURES_DIR / filename, "rb") as f:
        return client.post(
            "/api/imports/stats",
            params={"dry_run": dry_run},
            files={"file": (filename, f, "text/csv")},
            headers=headers,
        )


def test_import_requires_authentication(client):
    response = _upload(client, "teams_home_away.csv", dry_run=True, headers={})
    assert response.status_code == 401


def test_history_requires_authentication(client):
    assert client.get("/api/imports/history").status_code == 401


def test_dry_run_does_not_write_to_db(client, db_session, auth_headers):
    response = _upload(client, "teams_home_away.csv", dry_run=True, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["row_count"] == 5
    assert body["error_count"] == 0
    assert db_session.query(Team).count() == 0


def test_confirmed_import_writes_teams_and_history(client, db_session, auth_headers):
    response = _upload(client, "teams_home_away.csv", dry_run=False, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["import_history"]["status"] == "success"
    assert body["import_history"]["row_count"] == 5
    assert db_session.query(Team).count() == 5

    history_response = client.get("/api/imports/history", headers=auth_headers)
    assert history_response.status_code == 200
    assert len(history_response.json()) == 1


def test_player_import_creates_team_on_the_fly(client, db_session, auth_headers):
    response = _upload(client, "players_advanced.csv", dry_run=False, headers=auth_headers)
    assert response.status_code == 200
    assert db_session.query(Player).count() == 5
    # Les équipes référencées par les joueurs doivent avoir été créées.
    assert db_session.query(Team).filter(Team.abbreviation == "BOS").count() == 1


def test_per_and_mpg_imports_merge_on_same_player(client, db_session, auth_headers):
    _upload(client, "players_advanced.csv", dry_run=False, headers=auth_headers)
    _upload(client, "players_per_game.csv", dry_run=False, headers=auth_headers)

    player_a = db_session.query(Player).filter(Player.name == "Player A").one()
    assert player_a.per > 0
    assert player_a.mpg > 0
