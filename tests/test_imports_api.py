import io
from pathlib import Path

import pytest

from app.models import Game, GameStatus, ImportHistory, Player, Team

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


def test_confirmed_import_accepts_semicolon_separated_file(client, db_session, auth_headers):
    """Excel en localisation française réenregistre systématiquement les CSV
    en point-virgule -- vérifié bout en bout via l'API (pas seulement
    csv_import.read_csv), sur le même type de fichier que le point 1."""
    content = b"Team;Home;Road\nBoston Celtics;24-6;18-16\n"
    response = client.post(
        "/api/imports/stats",
        params={"dry_run": False},
        files={"file": ("classement.csv", io.BytesIO(content), "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["import_history"]["import_type"] == "teams_home_away"
    assert body["import_history"]["row_count"] == 1
    assert db_session.query(Team).filter(Team.abbreviation == "BOS").count() == 1


def test_player_import_creates_team_on_the_fly(client, db_session, auth_headers):
    response = _upload(client, "players_advanced.csv", dry_run=False, headers=auth_headers)
    assert response.status_code == 200
    assert db_session.query(Player).count() == 5
    # Les équipes référencées par les joueurs doivent avoir été créées.
    assert db_session.query(Team).filter(Team.abbreviation == "BOS").count() == 1


def test_players_advanced_import_sets_both_per_and_mpg(client, db_session, auth_headers):
    """Depuis la suppression de players_per_game : un seul import Advanced
    renseigne à la fois per et mpg (dérivé de MP/G du même fichier)."""
    _upload(client, "players_advanced.csv", dry_run=False, headers=auth_headers)

    player_a = db_session.query(Player).filter(Player.name == "Player A").one()
    assert player_a.per > 0
    assert player_a.mpg > 0


# --- Roster par équipe (Advanced, pas de colonne Team) ----------------------


def test_roster_by_team_import_without_team_id_returns_400(client, auth_headers):
    response = _upload(
        client, "roster_exemple_equipe_advanced.csv", dry_run=True, headers=auth_headers
    )
    assert response.status_code == 400
    assert "team_id" in response.json()["detail"]


def test_roster_by_team_import_unknown_team_id_returns_404(client, auth_headers):
    response = _upload(
        client, "roster_exemple_equipe_advanced.csv", dry_run=True, headers=auth_headers, team_id=999999
    )
    assert response.status_code == 404


def test_roster_by_team_dry_run_shows_resolved_team(client, db_session, auth_headers):
    """Seule protection visible contre une erreur de sélection dans le menu
    déroulant, le fichier ne contenant lui-même aucune info d'équipe."""
    pistons = Team(name="Detroit Pistons", abbreviation="DET")
    db_session.add(pistons)
    db_session.commit()

    response = _upload(
        client,
        "roster_exemple_equipe_advanced.csv",
        dry_run=True,
        headers=auth_headers,
        team_id=pistons.id,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["resolved_team_name"] == "Detroit Pistons"
    assert body["resolved_team_abbreviation"] == "DET"
    assert body["row_count"] == 20  # 20 joueurs, "Team Totals" exclue
    assert body["error_count"] == 0


def test_roster_by_team_confirmed_import_creates_players_on_given_team(client, db_session, auth_headers):
    pistons = Team(name="Detroit Pistons", abbreviation="DET")
    db_session.add(pistons)
    db_session.commit()

    response = _upload(
        client,
        "roster_exemple_equipe_advanced.csv",
        dry_run=False,
        headers=auth_headers,
        team_id=pistons.id,
    )
    assert response.status_code == 200
    assert db_session.query(Player).filter(Player.team_id == pistons.id).count() == 20
    assert db_session.query(Player).filter(Player.name == "Team Totals").count() == 0
    cade = db_session.query(Player).filter(Player.name == "Cade Cunningham").one()
    assert cade.mpg == pytest.approx(2172 / 64)


def test_players_advanced_with_team_column_ignores_team_id_param(client, db_session, auth_headers):
    """La variante ligue entière (colonne Team présente) doit continuer à
    fonctionner sans changement, team_id n'étant pas requis dans ce cas."""
    response = _upload(client, "players_advanced.csv", dry_run=True, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["resolved_team_name"] is None
    assert body["resolved_team_abbreviation"] is None


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


# --- Étape 6ter : calendrier de saison --------------------------------------


def test_schedule_import_without_season_returns_400(client, auth_headers):
    response = _upload(client, "calendrier_saison_26_27.csv", dry_run=True, headers=auth_headers)
    assert response.status_code == 400
    assert "season" in response.json()["detail"]


def test_schedule_dry_run_reports_malformed_rows_as_errors(client, auth_headers):
    response = _upload(
        client, "calendrier_saison_26_27.csv", dry_run=True, headers=auth_headers, season="2026-2027"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["import_type"] == "schedule"
    assert body["row_count"] == 1200
    assert body["error_count"] == 7
    assert body["season"] == "2026-2027"


def test_schedule_confirmed_import_creates_games(client, db_session, auth_headers):
    response = _upload(
        client, "calendrier_saison_26_27.csv", dry_run=False, headers=auth_headers, season="2026-2027"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["import_history"]["import_type"] == "schedule"
    assert body["import_history"]["row_count"] == 1200
    assert body["import_history"]["error_count"] == 7
    assert body["import_history"]["status"] == "partial"  # des lignes valides ET des erreurs

    assert db_session.query(Game).count() == 1200
    assert db_session.query(Game).filter(Game.status == GameStatus.SCHEDULED).count() == 1200
    assert db_session.query(Game).filter(Game.season == "2026-2027").count() == 1200


# --- Modèles CSV téléchargeables ---------------------------------------------


def test_download_template_requires_authentication(client):
    response = client.get("/api/imports/template", params={"type": "draft"})
    assert response.status_code == 401


def test_download_template_unknown_key_returns_400(client, auth_headers):
    response = client.get(
        "/api/imports/template", params={"type": "not_a_real_key"}, headers=auth_headers
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "key",
    ["teams_home_away", "players_advanced_league", "players_advanced_team", "draft", "schedule"],
)
def test_download_template_returns_csv_with_content_disposition(client, auth_headers, key):
    response = client.get("/api/imports/template", params={"type": key}, headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert f'modele_{key}.csv' in response.headers["content-disposition"]
    lines = response.text.strip().splitlines()
    assert len(lines) == 2
