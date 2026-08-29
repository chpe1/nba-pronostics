from datetime import datetime

from app.models import Game, GameStatus, InjuryStatus, Player, PreviousSeasonPlayerStat, Team

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


# --- DELETE ----------------------------------------------------------------


def test_delete_requires_authentication(client, db_session):
    stat = _stat()
    db_session.add(stat)
    db_session.commit()
    assert client.delete(f"/api/previous-season-stats/{stat.id}").status_code == 401


def test_delete_returns_404_for_unknown_id(client, auth_headers):
    response = client.delete("/api/previous-season-stats/999999", headers=auth_headers)
    assert response.status_code == 404


def test_delete_removes_it(client, db_session, auth_headers):
    stat = _stat()
    db_session.add(stat)
    db_session.commit()
    stat_id = stat.id

    response = client.delete(f"/api/previous-season-stats/{stat_id}", headers=auth_headers)

    assert response.status_code == 204
    assert db_session.get(PreviousSeasonPlayerStat, stat_id) is None


def test_deleting_stat_never_affects_an_already_saved_prediction_only_future_recalculations(
    client, db_session, auth_headers
):
    """Prediction.breakdown stocke un résultat figé au moment du calcul, pas
    une référence vivante vers PreviousSeasonPlayerStat -- supprimer la
    ligne ne doit jamais modifier une Prediction déjà sauvegardée, mais doit
    bien changer le résultat d'un futur recalcul (plus de fallback
    disponible pour ce joueur en petit échantillon)."""
    home = Team(
        name="Boston Celtics", abbreviation="BOS",
        win_pct_home=0.5, win_pct_away=0.5, win_pct_home_prev_season=0.5, win_pct_away_prev_season=0.5,
    )
    away = Team(
        name="Los Angeles Lakers", abbreviation="LAL",
        win_pct_home=0.5, win_pct_away=0.5, win_pct_home_prev_season=0.5, win_pct_away_prev_season=0.5,
    )
    db_session.add_all([home, away])
    db_session.flush()

    # Petit échantillon cette saison (2 < player_sample_size_threshold=5) --
    # doit retomber sur le PER/MPG N-1 (20.0), pas sur le PER courant (99.0,
    # volontairement aberrant pour rendre le fallback repérable sans ambiguïté).
    db_session.add(
        Player(
            name="Small Sample Star", team_id=home.id, per=99.0, mpg=30.0,
            games_played_this_season=2, injury_status=InjuryStatus.OUT,
        )
    )
    stat = PreviousSeasonPlayerStat(
        season="2024-2025", player_name="Small Sample Star", team_abbreviation="BOS", per=20.0, mpg=28.0,
    )
    db_session.add(stat)
    db_session.add(
        Game(
            season=SEASON,
            game_date=datetime(2026, 1, 15, 19, 0),
            home_team_id=home.id,
            away_team_id=away.id,
            status=GameStatus.SCHEDULED,
        )
    )
    db_session.flush()
    stat_id = stat.id

    client.post("/api/predictions/recalculate", params={"date": "2026-01-15"}, headers=auth_headers)

    before = client.get(f"/api/predictions/by-team/{home.id}", headers=auth_headers).json()[0]
    assert before["prediction"]["breakdown"]["home"]["injury_penalty"] == 20.0  # PER N-1, pas le PER courant

    delete_response = client.delete(f"/api/previous-season-stats/{stat_id}", headers=auth_headers)
    assert delete_response.status_code == 204

    # La Prediction déjà sauvegardée reste inchangée -- aucun recalcul déclenché.
    after_delete = client.get(f"/api/predictions/by-team/{home.id}", headers=auth_headers).json()[0]
    assert after_delete["prediction"]["breakdown"]["home"]["injury_penalty"] == 20.0

    # Un NOUVEAU recalcul, en revanche, ne trouve plus le fallback.
    client.post("/api/predictions/recalculate", params={"date": "2026-01-15"}, headers=auth_headers)
    after_recalculate = client.get(f"/api/predictions/by-team/{home.id}", headers=auth_headers).json()[0]
    assert after_recalculate["prediction"]["breakdown"]["home"]["injury_penalty"] == 99.0
