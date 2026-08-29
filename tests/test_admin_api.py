from datetime import datetime

from app.models import Game, GameStatus, Team

SEASON = "2026-2027"


def _team(abbreviation: str, name: str) -> Team:
    return Team(name=name, abbreviation=abbreviation, win_pct_home=0.5, win_pct_away=0.5)


def _game(home: Team, away: Team, game_date: datetime) -> Game:
    return Game(
        season=SEASON,
        game_date=game_date,
        home_team_id=home.id,
        away_team_id=away.id,
        status=GameStatus.SCHEDULED,
    )


# --- GET /api/admin/table-counts -------------------------------------------


def test_table_counts_requires_authentication(client):
    assert client.get("/api/admin/table-counts").status_code == 401


def test_table_counts_reflects_real_row_counts(client, db_session, auth_headers):
    home = _team("BOS", "Boston Celtics")
    away = _team("LAL", "Los Angeles Lakers")
    db_session.add_all([home, away])
    db_session.flush()
    db_session.add(_game(home, away, datetime(2026, 11, 1, 19, 0)))
    db_session.commit()

    response = client.get("/api/admin/table-counts", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["team_count"] == 2
    assert body["game_count"] == 1
    assert body["player_count"] == 0
    assert body["previous_season_player_stat_count"] == 0
    assert body["import_history_count"] == 0
    assert body["prediction_count"] == 0
    assert body["login_lockout_count"] == 0


# --- GET /api/admin/integrity-audit -----------------------------------------


def test_integrity_audit_requires_authentication(client):
    assert client.get("/api/admin/integrity-audit").status_code == 401


def test_integrity_audit_no_outliers_when_counts_are_uniform(client, db_session, auth_headers):
    a, b, c = _team("AAA", "Team A"), _team("BBB", "Team B"), _team("CCC", "Team C")
    db_session.add_all([a, b, c])
    db_session.flush()
    db_session.add_all(
        [
            _game(a, b, datetime(2026, 11, 1, 19, 0)),
            _game(b, c, datetime(2026, 11, 2, 19, 0)),
            _game(c, a, datetime(2026, 11, 3, 19, 0)),
        ]
    )
    db_session.commit()

    body = client.get("/api/admin/integrity-audit", headers=auth_headers).json()

    assert all(not t["is_outlier"] for t in body["team_game_counts"])
    assert body["mode_game_count"] == 2
    assert body["total_games"] == 3
    assert body["games_count_consistent"] is True


def test_integrity_audit_tolerates_one_game_difference(client, db_session, auth_headers):
    """Écart de 1 par rapport au mode (ex: finale NBA Cup) -- pas signalé."""
    a, b, c, d, e, f = (
        _team("AAA", "Team A"),
        _team("BBB", "Team B"),
        _team("CCC", "Team C"),
        _team("DDD", "Team D"),
        _team("EEE", "Team E"),
        _team("FFF", "Team F"),
    )
    db_session.add_all([a, b, c, d, e, f])
    db_session.flush()
    # a/b et e/f jouent 2 matchs chacune (mode, sans ambiguïté : 4 équipes à 2
    # contre seulement 2 à 1) ; c et d n'en jouent qu'un.
    db_session.add_all(
        [
            _game(a, b, datetime(2026, 11, 1, 19, 0)),
            _game(a, b, datetime(2026, 11, 5, 19, 0)),
            _game(e, f, datetime(2026, 11, 1, 19, 0)),
            _game(e, f, datetime(2026, 11, 5, 19, 0)),
            _game(c, d, datetime(2026, 11, 2, 19, 0)),
        ]
    )
    db_session.commit()

    body = client.get("/api/admin/integrity-audit", headers=auth_headers).json()
    by_abbr = {t["abbreviation"]: t for t in body["team_game_counts"]}

    assert body["mode_game_count"] == 2
    assert by_abbr["AAA"]["is_outlier"] is False
    assert by_abbr["CCC"]["game_count"] == 1
    assert by_abbr["CCC"]["is_outlier"] is False  # écart de 1 seulement -> toléré


def test_integrity_audit_flags_team_far_from_mode(client, db_session, auth_headers):
    a, b, c, d = (
        _team("AAA", "Team A"),
        _team("BBB", "Team B"),
        _team("CCC", "Team C"),
        _team("DDD", "Team D"),
    )
    db_session.add_all([a, b, c, d])
    db_session.flush()
    db_session.add_all(
        [
            _game(a, b, datetime(2026, 11, 1, 19, 0)),
            _game(a, b, datetime(2026, 11, 3, 19, 0)),
            _game(a, b, datetime(2026, 11, 5, 19, 0)),
            _game(c, d, datetime(2026, 11, 2, 19, 0)),
            _game(c, d, datetime(2026, 11, 4, 19, 0)),
            _game(c, d, datetime(2026, 11, 6, 19, 0)),
        ]
    )
    db_session.commit()

    body = client.get("/api/admin/integrity-audit", headers=auth_headers).json()
    by_abbr = {t["abbreviation"]: t for t in body["team_game_counts"]}
    # a et c ont joué 3 matchs, b et d aussi (chacun apparaît 2 fois en domicile/extérieur + ...)
    # recompte: a joue 3 fois (toujours domicile), b joue 3 fois (toujours extérieur), idem c/d.
    assert by_abbr["AAA"]["game_count"] == 3
    assert by_abbr["AAA"]["is_outlier"] is False

    # Ajoute un match isolé pour une 5e équipe, largement sous le mode (3).
    e = _team("EEE", "Team E")
    f = _team("FFF", "Team F")
    db_session.add_all([e, f])
    db_session.flush()
    db_session.add(_game(e, f, datetime(2026, 11, 7, 19, 0)))
    db_session.commit()

    body = client.get("/api/admin/integrity-audit", headers=auth_headers).json()
    by_abbr = {t["abbreviation"]: t for t in body["team_game_counts"]}
    assert by_abbr["EEE"]["game_count"] == 1
    assert by_abbr["EEE"]["is_outlier"] is True  # écart de 2 par rapport au mode (3)


def test_integrity_audit_detects_missing_and_unexpected_teams(client, db_session, auth_headers):
    db_session.add(_team("XXX", "Fictional Team"))
    db_session.commit()

    body = client.get("/api/admin/integrity-audit", headers=auth_headers).json()

    assert "XXX" in body["unexpected_teams"]
    assert len(body["missing_teams"]) == 30  # aucune des 30 vraies équipes n'est en base


def test_integrity_audit_detects_duplicate_with_swapped_home_away(client, db_session, auth_headers):
    """Même date, mêmes deux équipes, domicile/extérieur inversés -- la
    contrainte UNIQUE en base ne bloque pas ce cas (tuple différent)."""
    a, b = _team("AAA", "Team A"), _team("BBB", "Team B")
    db_session.add_all([a, b])
    db_session.flush()
    db_session.add_all(
        [
            _game(a, b, datetime(2026, 11, 1, 19, 0)),
            _game(b, a, datetime(2026, 11, 1, 21, 0)),
        ]
    )
    db_session.commit()

    body = client.get("/api/admin/integrity-audit", headers=auth_headers).json()

    assert len(body["duplicate_games"]) == 1
    dup = body["duplicate_games"][0]
    assert {dup["team_a_abbreviation"], dup["team_b_abbreviation"]} == {"AAA", "BBB"}
    assert dup["count"] == 2


def test_integrity_audit_detects_same_day_conflict(client, db_session, auth_headers):
    """Une équipe avec deux matchs le même jour contre des adversaires
    différents -- distinct d'un doublon (mêmes deux équipes)."""
    a, b, c = _team("AAA", "Team A"), _team("BBB", "Team B"), _team("CCC", "Team C")
    db_session.add_all([a, b, c])
    db_session.flush()
    db_session.add_all(
        [
            _game(a, b, datetime(2026, 11, 1, 19, 0)),
            _game(a, c, datetime(2026, 11, 1, 21, 0)),
        ]
    )
    db_session.commit()

    body = client.get("/api/admin/integrity-audit", headers=auth_headers).json()

    assert len(body["same_day_conflicts"]) == 1
    conflict = body["same_day_conflicts"][0]
    assert conflict["team_name"] == "Team A"
    assert conflict["opponent_abbreviations"] == ["BBB", "CCC"]
    assert body["duplicate_games"] == []  # pas la même paire d'équipes -- pas un doublon
