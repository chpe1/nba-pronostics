import io
from pathlib import Path

import pytest

from app.models import ImportHistory, Player, Team

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _upload(client, filename: str, dry_run: bool, headers: dict, **params):
    with open(FIXTURES_DIR / filename, "rb") as f:
        return client.post(
            "/api/imports/stats",
            params={"dry_run": dry_run, **params},
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


# --- Étape 6bis : saison précédente + draft ---------------------------------


def test_previous_season_without_season_param_returns_400(client, auth_headers):
    response = _upload(
        client, "teams_home_away.csv", dry_run=True, headers=auth_headers, season_type="previous"
    )
    assert response.status_code == 400
    assert "season" in response.json()["detail"]


def test_previous_season_teams_import_writes_prev_season_columns(client, db_session, auth_headers):
    response = _upload(
        client,
        "teams_home_away.csv",
        dry_run=False,
        headers=auth_headers,
        season_type="previous",
        season="2024-2025",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["import_history"]["season_type"] == "previous"
    assert body["import_history"]["season"] == "2024-2025"

    celtics = db_session.query(Team).filter(Team.abbreviation == "BOS").one()
    assert celtics.win_pct_home_prev_season == pytest.approx(24 / 30)
    assert celtics.win_pct_home == 0.0  # saison courante non affectée


def test_draft_import_creates_rookie_with_draft_pick(client, db_session, auth_headers):
    csv_content = b"Pk,Tm,Player\n1,BOS,Rookie One\n2,LAL,Rookie Two\n"
    response = client.post(
        "/api/imports/stats",
        params={"dry_run": False},
        files={"file": ("draft.csv", io.BytesIO(csv_content), "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["import_history"]["import_type"] == "draft"
    assert body["import_history"]["season_type"] == "current"  # sans objet, toujours "current"

    rookie = db_session.query(Player).filter(Player.name == "Rookie One").one()
    assert rookie.draft_pick == 1
    assert rookie.team.abbreviation == "BOS"


def test_import_history_defaults_to_current_season(client, db_session, auth_headers):
    _upload(client, "teams_home_away.csv", dry_run=False, headers=auth_headers)
    history = db_session.query(ImportHistory).one()
    assert history.season_type.value == "current"
    assert history.season is None
