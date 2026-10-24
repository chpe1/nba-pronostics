"""GET/POST /api/odds."""
from datetime import datetime, timedelta, timezone

from app.models import Game, Odds, OddsSide, Team
from app.services import nba_calendar


def _teams(db_session):
    home = Team(name="Boston Celtics", abbreviation="BOS")
    away = Team(name="Miami Heat", abbreviation="MIA")
    db_session.add_all([home, away])
    db_session.flush()
    return home, away


def _game(db_session, home, away, game_date=datetime(2026, 10, 24, 19)):
    g = Game(season="2026-2027", game_date=game_date, home_team_id=home.id, away_team_id=away.id)
    db_session.add(g)
    db_session.flush()
    return g


def test_requires_authentication(client):
    response = client.get("/api/odds", params={"date": "2026-10-24"})
    assert response.status_code == 401


def test_get_returns_the_day_s_games_with_empty_cells(client, db_session, auth_headers):
    home, away = _teams(db_session)
    _game(db_session, home, away)

    response = client.get("/api/odds", params={"date": "2026-10-24"}, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["games"]) == 1
    g = body["games"][0]
    assert g["home_team_abbreviation"] == "BOS" and g["away_team_abbreviation"] == "MIA"
    assert g["started"] is False
    for cell in ("winamax_home", "winamax_away", "unibet_home", "unibet_away"):
        assert g[cell] == {"value": None, "recorded_at": None}


def test_get_shows_the_latest_known_value_per_cell(client, db_session, auth_headers):
    home, away = _teams(db_session)
    game = _game(db_session, home, away)
    db_session.add_all([
        Odds(game_id=game.id, side=OddsSide.HOME, source="winamax", value=1.80, recorded_at=datetime(2026, 10, 24, 10)),
        Odds(game_id=game.id, side=OddsSide.HOME, source="winamax", value=1.85, recorded_at=datetime(2026, 10, 24, 16)),
    ])
    db_session.commit()

    body = client.get("/api/odds", params={"date": "2026-10-24"}, headers=auth_headers).json()
    cell = body["games"][0]["winamax_home"]
    assert cell["value"] == 1.85  # le plus récent, pas le premier
    assert cell["recorded_at"] == "2026-10-24T16:00:00Z"  # Z explicite : UTC, pas une heure locale ambiguë


def test_post_partial_submission_writes_only_the_filled_cells(client, db_session, auth_headers):
    home, away = _teams(db_session)
    game = _game(db_session, home, away)

    response = client.post(
        "/api/odds",
        json={"recorded_at": "2026-10-24T14:30:00Z", "entries": [
            {"game_id": game.id, "side": "home", "source": "winamax", "value": "1,85"},
        ]},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["created_count"], body["updated_count"], body["rejected_count"]) == (1, 0, 0)
    assert db_session.query(Odds).count() == 1
    row = db_session.query(Odds).one()
    assert row.value == 1.85 and row.source == "winamax" and row.side == OddsSide.HOME
    assert row.recorded_at == datetime(2026, 10, 24, 14, 30, 0)  # converti en UTC naïf


def test_post_accepts_french_comma_and_dot_decimals(client, db_session, auth_headers):
    home, away = _teams(db_session)
    game = _game(db_session, home, away)
    response = client.post(
        "/api/odds",
        json={"recorded_at": "2026-10-24T14:30:00Z", "entries": [
            {"game_id": game.id, "side": "home", "source": "winamax", "value": "1,85"},
            {"game_id": game.id, "side": "away", "source": "winamax", "value": "2.10"},
        ]},
        headers=auth_headers,
    )
    assert response.json()["created_count"] == 2
    values = {o.side.value: o.value for o in db_session.query(Odds).all()}
    assert values == {"home": 1.85, "away": 2.10}


def test_post_resubmitting_the_exact_same_batch_is_a_no_op_pressing_twice_is_safe(client, db_session, auth_headers):
    home, away = _teams(db_session)
    game = _game(db_session, home, away)
    payload = {"recorded_at": "2026-10-24T14:30:00Z", "entries": [
        {"game_id": game.id, "side": "home", "source": "winamax", "value": "1,85"},
    ]}
    client.post("/api/odds", json=payload, headers=auth_headers)
    second = client.post("/api/odds", json=payload, headers=auth_headers)
    assert second.json()["unchanged_count"] == 1
    assert db_session.query(Odds).count() == 1


def test_post_rejects_an_absurd_value_without_losing_the_rest_of_the_batch(client, db_session, auth_headers):
    home, away = _teams(db_session)
    game = _game(db_session, home, away)
    response = client.post(
        "/api/odds",
        json={"recorded_at": "2026-10-24T14:30:00Z", "entries": [
            {"game_id": game.id, "side": "home", "source": "winamax", "value": "1,85"},
            {"game_id": game.id, "side": "away", "source": "winamax", "value": "0,80"},  # sous 1,01
        ]},
        headers=auth_headers,
    )
    body = response.json()
    assert response.status_code == 200  # le lot entier n'échoue jamais pour une seule cellule invalide
    assert (body["created_count"], body["rejected_count"]) == (1, 1)
    rejected = next(e for e in body["entries"] if e["outcome"] == "rejected")
    assert "0.8" in rejected["detail"] or "0,8" in rejected["detail"]
    assert db_session.query(Odds).count() == 1


def test_post_rejects_an_unknown_source(client, db_session, auth_headers):
    home, away = _teams(db_session)
    game = _game(db_session, home, away)
    response = client.post(
        "/api/odds",
        json={"recorded_at": "2026-10-24T14:30:00Z", "entries": [
            {"game_id": game.id, "side": "home", "source": "betclic", "value": "1,85"},
        ]},
        headers=auth_headers,
    )
    assert response.json()["entries"][0]["outcome"] == "rejected"
    assert db_session.query(Odds).count() == 0


def test_post_normalizes_source_case_on_write(client, db_session, auth_headers):
    home, away = _teams(db_session)
    game = _game(db_session, home, away)
    client.post(
        "/api/odds",
        json={"recorded_at": "2026-10-24T14:30:00Z", "entries": [
            {"game_id": game.id, "side": "home", "source": "Winamax", "value": "1,85"},
        ]},
        headers=auth_headers,
    )
    assert db_session.query(Odds).one().source == "winamax"


def test_post_refuses_a_game_already_started(client, db_session, auth_headers, monkeypatch):
    home, away = _teams(db_session)
    game = _game(db_session, home, away, game_date=datetime(2026, 10, 24, 19))
    monkeypatch.setattr(nba_calendar, "utc_now", lambda: nba_calendar.game_start_utc(game.game_date) + timedelta(minutes=1))

    response = client.post(
        "/api/odds",
        json={"recorded_at": "2026-10-24T23:50:00Z", "entries": [
            {"game_id": game.id, "side": "home", "source": "winamax", "value": "1,85"},
        ]},
        headers=auth_headers,
    )
    assert response.json()["entries"][0]["outcome"] == "skipped_started"
    assert db_session.query(Odds).count() == 0


def test_get_marks_an_already_started_game(client, db_session, auth_headers, monkeypatch):
    home, away = _teams(db_session)
    game = _game(db_session, home, away, game_date=datetime(2026, 10, 24, 19))
    monkeypatch.setattr(nba_calendar, "utc_now", lambda: nba_calendar.game_start_utc(game.game_date) + timedelta(minutes=1))

    body = client.get("/api/odds", params={"date": "2026-10-24"}, headers=auth_headers).json()
    assert body["games"][0]["started"] is True
