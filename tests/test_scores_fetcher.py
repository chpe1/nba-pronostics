from datetime import date, datetime

import httpx
import pytest

from app.models import Game, GameStatus, Team
from app.services.scores_fetcher import fetch_games_for_date, sync_scores_for_date

TARGET_DATE = date(2026, 10, 21)


def _teams(db_session) -> tuple[Team, Team]:
    home = Team(name="Detroit Pistons", abbreviation="DET")
    away = Team(name="Boston Celtics", abbreviation="BOS")
    db_session.add_all([home, away])
    db_session.flush()
    return home, away


def _game(db_session, home: Team, away: Team, hour: int = 19) -> Game:
    game = Game(
        season="2026-2027",
        game_date=datetime.combine(TARGET_DATE, datetime.min.time()).replace(hour=hour),
        home_team_id=home.id,
        away_team_id=away.id,
        status=GameStatus.SCHEDULED,
    )
    db_session.add(game)
    db_session.flush()
    return game


def _raw_game(*, status_state="final", postponed=False, home_score=98, away_score=100):
    return {
        "id": 1,
        "date": TARGET_DATE.isoformat(),
        "status_state": status_state,
        "postponed": postponed,
        "home_team": {"abbreviation": "DET"},
        "visitor_team": {"abbreviation": "BOS"},
        "home_team_score": home_score,
        "visitor_team_score": away_score,
    }


def _client_returning(payload: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") == "test-key"
        assert request.url.params.get("dates[]") == TARGET_DATE.isoformat()
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_games_for_date_sends_auth_header_and_date_filter():
    client = _client_returning({"data": [_raw_game()]})
    games = fetch_games_for_date(client, "test-key", TARGET_DATE)
    assert len(games) == 1
    assert games[0]["home_team"]["abbreviation"] == "DET"


def test_sync_updates_finished_game_with_scores(db_session):
    home, away = _teams(db_session)
    game = _game(db_session, home, away)
    client = _client_returning({"data": [_raw_game(status_state="final", home_score=98, away_score=100)]})

    result = sync_scores_for_date(db_session, "test-key", TARGET_DATE, client=client)

    db_session.refresh(game)
    assert result == {"fetched": 1, "updated": 1, "skipped": 0}
    assert game.status == GameStatus.FINISHED
    assert game.home_score == 98
    assert game.away_score == 100


def test_sync_sets_postponed_status(db_session):
    home, away = _teams(db_session)
    game = _game(db_session, home, away)
    client = _client_returning({"data": [_raw_game(postponed=True, status_state="scheduled")]})

    sync_scores_for_date(db_session, "test-key", TARGET_DATE, client=client)

    db_session.refresh(game)
    assert game.status == GameStatus.POSTPONED
    assert game.home_score is None and game.away_score is None


def test_sync_skips_manually_overridden_game(db_session):
    home, away = _teams(db_session)
    game = _game(db_session, home, away)
    game.manually_overridden = True
    db_session.flush()
    client = _client_returning({"data": [_raw_game(status_state="final")]})

    result = sync_scores_for_date(db_session, "test-key", TARGET_DATE, client=client)

    db_session.refresh(game)
    assert result["skipped"] == 1
    assert result["updated"] == 0
    assert game.status == GameStatus.SCHEDULED
    assert game.home_score is None and game.away_score is None


def test_sync_skips_game_not_found_in_db(db_session):
    client = _client_returning({"data": [_raw_game(status_state="final")]})

    result = sync_scores_for_date(db_session, "test-key", TARGET_DATE, client=client)

    assert result == {"fetched": 1, "updated": 0, "skipped": 1}


def test_sync_skips_unrecognized_team(db_session):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "status_state": "final",
                        "postponed": False,
                        "home_team": {"abbreviation": "ZZZ"},
                        "visitor_team": {"abbreviation": "BOS"},
                        "home_team_score": 100,
                        "visitor_team_score": 90,
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = sync_scores_for_date(db_session, "test-key", TARGET_DATE, client=client)
    assert result == {"fetched": 1, "updated": 0, "skipped": 1}


def test_sync_propagates_http_errors(db_session):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        sync_scores_for_date(db_session, "test-key", TARGET_DATE, client=client)
