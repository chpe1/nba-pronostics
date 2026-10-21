from datetime import date, datetime

import httpx
import pytest

from app.models import Game, GameStatus, Team
from app.services import scores_fetcher
from app.services.scores_fetcher import (
    SKIP_MANUALLY_OVERRIDDEN,
    SKIP_NOT_IN_DATABASE,
    SKIP_UNKNOWN_DATE,
    SKIP_UNKNOWN_TEAM,
    fetch_games_for_date,
    fetch_games_for_dates,
    sync_scores_for_date,
    sync_scores_for_range,
)

TARGET_DATE = date(2026, 10, 21)


def _teams(db_session) -> tuple[Team, Team]:
    home = Team(name="Detroit Pistons", abbreviation="DET")
    away = Team(name="Boston Celtics", abbreviation="BOS")
    db_session.add_all([home, away])
    db_session.flush()
    return home, away


def _game(db_session, home: Team, away: Team, hour: int = 19, day: date = TARGET_DATE) -> Game:
    game = Game(
        season="2026-2027",
        game_date=datetime.combine(day, datetime.min.time()).replace(hour=hour),
        home_team_id=home.id,
        away_team_id=away.id,
        status=GameStatus.SCHEDULED,
    )
    db_session.add(game)
    db_session.flush()
    return game


def _raw_game(*, status_state="final", postponed=False, home_score=98, away_score=100, day: date = TARGET_DATE,
              home="DET", away="BOS"):
    return {
        "id": 1,
        "date": day.isoformat(),
        "status_state": status_state,
        "postponed": postponed,
        "home_team": {"abbreviation": home},
        "visitor_team": {"abbreviation": away},
        "home_team_score": home_score,
        "visitor_team_score": away_score,
    }


def _client_returning(payload: dict, expected_dates: list[date] | None = None) -> httpx.Client:
    expected = [d.isoformat() for d in (expected_dates or [TARGET_DATE])]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") == "test-key"
        assert request.url.params.get_list("dates[]") == expected
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_games_for_date_sends_auth_header_and_date_filter():
    client = _client_returning({"data": [_raw_game()]})
    games = fetch_games_for_date(client, "test-key", TARGET_DATE)
    assert len(games) == 1
    assert games[0]["home_team"]["abbreviation"] == "DET"


def test_fetch_games_for_dates_uses_one_request_for_several_dates():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.params.get_list("dates[]"))
        return httpx.Response(200, json={"data": [_raw_game()], "meta": {"per_page": 100}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    days = [date(2026, 10, 19), date(2026, 10, 20), date(2026, 10, 21)]
    games = fetch_games_for_dates(client, "test-key", days)
    assert len(games) == 1
    assert calls == [["2026-10-19", "2026-10-20", "2026-10-21"]]  # UN seul appel, trois dates


def test_fetch_games_for_dates_follows_the_pagination_cursor():
    pages = {None: {"data": [_raw_game(), _raw_game()], "meta": {"next_cursor": 7}}, "7": {"data": [_raw_game()], "meta": {}}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=pages[request.url.params.get("cursor")])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert len(fetch_games_for_dates(client, "test-key", [TARGET_DATE])) == 3


def test_sync_records_a_finished_game_with_its_scores(db_session):
    home, away = _teams(db_session)
    game = _game(db_session, home, away)
    client = _client_returning({"data": [_raw_game(status_state="final", home_score=98, away_score=100)]})

    result = sync_scores_for_date(db_session, "test-key", TARGET_DATE, client=client)

    db_session.refresh(game)
    assert (result.found, result.updated, result.skipped_count, result.already_final, result.not_finished) == (1, 1, 0, 0, 0)
    assert len(result.recorded) == 1
    recorded = result.recorded[0]
    assert (recorded.away_team_name, recorded.home_team_name, recorded.away_score, recorded.home_score) == (
        "Boston Celtics", "Detroit Pistons", 100, 98)
    assert recorded.correction is False
    assert (game.status, game.home_score, game.away_score) == (GameStatus.FINISHED, 98, 100)


def test_already_finished_game_with_same_scores_is_counted_apart_and_never_touched(db_session):
    home, away = _teams(db_session)
    game = _game(db_session, home, away)
    game.status, game.home_score, game.away_score = GameStatus.FINISHED, 98, 100
    game.updated_at = datetime(2026, 10, 1, 12, 0, 0)
    db_session.commit()
    client = _client_returning({"data": [_raw_game(status_state="final", home_score=98, away_score=100)]})

    result = sync_scores_for_date(db_session, "test-key", TARGET_DATE, client=client)

    db_session.refresh(game)
    # LIMITATION N°36 CORRIGÉE : retrouvé, mais rien n'a changé -> pas « mis à jour », et updated_at intact.
    assert (result.found, result.updated, result.already_final) == (1, 0, 1)
    assert result.recorded == []
    assert game.updated_at == datetime(2026, 10, 1, 12, 0, 0)


def test_scheduled_game_not_finished_yet_is_not_counted_as_updated(db_session):
    home, away = _teams(db_session)
    game = _game(db_session, home, away)
    game.updated_at = datetime(2026, 10, 1, 12, 0, 0)
    db_session.commit()
    client = _client_returning({"data": [_raw_game(status_state="in_progress", home_score=40, away_score=38)]})

    result = sync_scores_for_date(db_session, "test-key", TARGET_DATE, client=client)

    db_session.refresh(game)
    assert (result.found, result.updated, result.not_finished) == (1, 0, 1)
    assert game.status == GameStatus.SCHEDULED and game.home_score is None
    assert game.updated_at == datetime(2026, 10, 1, 12, 0, 0)  # le cas du journal du 2026-10-20 à 06:00


def test_finished_game_with_a_different_score_is_recorded_as_a_correction(db_session):
    home, away = _teams(db_session)
    game = _game(db_session, home, away)
    game.status, game.home_score, game.away_score = GameStatus.FINISHED, 90, 90
    db_session.commit()
    client = _client_returning({"data": [_raw_game(status_state="final", home_score=98, away_score=100)]})

    result = sync_scores_for_date(db_session, "test-key", TARGET_DATE, client=client)

    db_session.refresh(game)
    assert result.updated == 1 and result.recorded[0].correction is True
    assert (game.home_score, game.away_score) == (98, 100)


def test_postponed_status_is_a_status_change_not_a_recorded_score(db_session):
    home, away = _teams(db_session)
    game = _game(db_session, home, away)
    client = _client_returning({"data": [_raw_game(postponed=True, status_state="scheduled")]})

    result = sync_scores_for_date(db_session, "test-key", TARGET_DATE, client=client)

    db_session.refresh(game)
    assert game.status == GameStatus.POSTPONED
    assert game.home_score is None and game.away_score is None
    assert result.recorded == [] and result.updated == 1
    assert (result.status_changes[0].previous_status, result.status_changes[0].new_status) == ("scheduled", "postponed")


def test_manually_overridden_game_is_skipped_with_its_reason(db_session):
    home, away = _teams(db_session)
    game = _game(db_session, home, away)
    game.manually_overridden = True
    db_session.flush()
    client = _client_returning({"data": [_raw_game(status_state="final")]})

    result = sync_scores_for_date(db_session, "test-key", TARGET_DATE, client=client)

    db_session.refresh(game)
    assert (result.found, result.updated, result.skipped_count) == (1, 0, 1)
    assert result.skipped[0].reason == SKIP_MANUALLY_OVERRIDDEN and result.skipped[0].label == "BOS @ DET"
    assert game.status == GameStatus.SCHEDULED
    assert game.home_score is None and game.away_score is None


def test_game_not_found_in_database_is_skipped_with_its_reason(db_session):
    _teams(db_session)  # les deux équipes existent, mais aucun match (date, domicile, extérieur) en base
    client = _client_returning({"data": [_raw_game(status_state="final")]})

    result = sync_scores_for_date(db_session, "test-key", TARGET_DATE, client=client)

    assert (result.found, result.updated, result.skipped_count) == (1, 0, 1)
    assert result.skipped[0].reason == SKIP_NOT_IN_DATABASE


def test_unrecognized_team_is_skipped_with_its_reason(db_session):
    client = _client_returning({"data": [_raw_game(home="ZZZ")]})
    result = sync_scores_for_date(db_session, "test-key", TARGET_DATE, client=client)
    assert (result.found, result.updated, result.skipped_count) == (1, 0, 1)
    assert result.skipped[0].reason == SKIP_UNKNOWN_TEAM


def test_range_gives_one_result_per_date_including_a_date_without_games(db_session):
    home, away = _teams(db_session)
    d1, d2, d3 = date(2026, 10, 19), date(2026, 10, 20), date(2026, 10, 21)
    g1 = _game(db_session, home, away, day=d1)
    g3 = _game(db_session, home, away, day=d3)
    payload = {"data": [
        _raw_game(day=d1, home_score=101, away_score=99),
        _raw_game(day=d3, status_state="scheduled", home_score=0, away_score=0),
    ]}
    client = _client_returning(payload, expected_dates=[d1, d2, d3])

    results = sync_scores_for_range(db_session, "test-key", d1, d3, client=client)

    assert [r.date for r in results] == [d1, d2, d3]
    assert [r.found for r in results] == [1, 0, 1]  # d2 : aucun match, mais un résultat quand même
    assert [r.updated for r in results] == [1, 0, 0]
    assert results[2].not_finished == 1
    db_session.refresh(g1)
    db_session.refresh(g3)
    assert g1.status == GameStatus.FINISHED and g3.status == GameStatus.SCHEDULED


def test_game_with_an_unusable_date_is_counted_as_skipped_never_applied(db_session):
    home, away = _teams(db_session)
    game = _game(db_session, home, away)
    raw = _raw_game()
    raw["date"] = None
    client = _client_returning({"data": [raw]})

    result = sync_scores_for_date(db_session, "test-key", TARGET_DATE, client=client)

    db_session.refresh(game)
    assert (result.found, result.updated) == (1, 0)
    assert result.skipped[0].reason == SKIP_UNKNOWN_DATE
    assert game.status == GameStatus.SCHEDULED


def test_range_does_not_commit_but_single_date_does(db_session, monkeypatch):
    home, away = _teams(db_session)
    _game(db_session, home, away)
    commits = []
    monkeypatch.setattr(db_session, "commit", lambda: commits.append(1))
    client = _client_returning({"data": [_raw_game()]})
    sync_scores_for_range(db_session, "test-key", TARGET_DATE, TARGET_DATE, client=client)
    assert commits == []
    sync_scores_for_date(db_session, "test-key", TARGET_DATE, client=client)
    assert commits == [1]


def test_sync_propagates_http_errors(db_session):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        sync_scores_for_date(db_session, "test-key", TARGET_DATE, client=client)


def test_module_exposes_no_leftover_dict_style_result():
    # Le décompte n'est plus un dict {fetched, updated, skipped} : c'est un objet par date.
    assert hasattr(scores_fetcher, "DaySyncResult")
