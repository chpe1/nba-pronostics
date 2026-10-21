"""POST /api/scores/sync -- aucun appel réseau : l'API balldontlie est simulée par un MockTransport."""
from datetime import date, datetime, timedelta

import httpx
import pytest

from app.api import scores as scores_api
from app.models import Game, GameStatus, Team
from app.services.nba_calendar import current_nba_date
from app.services.scores_fetcher import sync_scores_for_range as real_sync

D1, D2, D3 = date(2026, 10, 19), date(2026, 10, 20), date(2026, 10, 21)


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("BALLDONTLIE_API_KEY", "test-key")


@pytest.fixture()
def teams(db_session):
    home = Team(name="Detroit Pistons", abbreviation="DET")
    away = Team(name="Boston Celtics", abbreviation="BOS")
    db_session.add_all([home, away])
    db_session.flush()
    return home, away


def _game(db_session, teams, day, status=GameStatus.SCHEDULED, scores=(None, None)):
    home, away = teams
    game = Game(season="2026-2027", game_date=datetime.combine(day, datetime.min.time()).replace(hour=19),
                home_team_id=home.id, away_team_id=away.id, status=status, home_score=scores[0], away_score=scores[1])
    db_session.add(game)
    db_session.commit()
    return game


def _raw(day, state="final", home_score=98, away_score=100):
    return {"date": day.isoformat(), "status_state": state, "postponed": False,
            "home_team": {"abbreviation": "DET"}, "visitor_team": {"abbreviation": "BOS"},
            "home_team_score": home_score, "visitor_team_score": away_score}


def _serve(monkeypatch, handler):
    """Fait passer la route par un client httpx simulé."""
    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(scores_api, "sync_scores_for_range",
                        lambda db, key, start, end, client_=None: real_sync(db, key, start, end, client=client))


def _json_handler(payload):
    return lambda request: httpx.Response(200, json=payload)


def _post(client, headers, **params):
    return client.post("/api/scores/sync", params=params, headers=headers)


def test_requires_authentication(client):
    assert client.post("/api/scores/sync").status_code == 401


def test_missing_api_key_gives_a_clear_503(client, auth_headers, monkeypatch):
    monkeypatch.delenv("BALLDONTLIE_API_KEY")
    response = _post(client, auth_headers)
    assert response.status_code == 503 and "BALLDONTLIE_API_KEY" in response.json()["detail"]


def test_one_day_range_records_the_game_and_reports_it_by_name(client, db_session, auth_headers, teams, monkeypatch):
    game = _game(db_session, teams, D3)
    _serve(monkeypatch, _json_handler({"data": [_raw(D3)]}))

    response = _post(client, auth_headers, date_from=D3.isoformat(), date_to=D3.isoformat())

    assert response.status_code == 200
    body = response.json()
    assert (body["days_count"], body["found"], body["recorded_count"], body["written"]) == (1, 1, 1, True)
    recorded = body["days"][0]["recorded"][0]
    assert (recorded["away_team_name"], recorded["away_score"], recorded["home_team_name"], recorded["home_score"]) == (
        "Boston Celtics", 100, "Detroit Pistons", 98)
    db_session.refresh(game)
    assert game.status == GameStatus.FINISHED and (game.home_score, game.away_score) == (98, 100)


def test_multi_day_range_reports_each_day_and_a_day_without_games(client, db_session, auth_headers, teams, monkeypatch):
    _game(db_session, teams, D1)
    _game(db_session, teams, D3)
    seen = []

    def handler(request):
        seen.append(request.url.params.get_list("dates[]"))
        return httpx.Response(200, json={"data": [_raw(D1), _raw(D3, state="scheduled", home_score=0, away_score=0)]})

    _serve(monkeypatch, handler)
    body = _post(client, auth_headers, date_from=D1.isoformat(), date_to=D3.isoformat()).json()

    assert seen == [["2026-10-19", "2026-10-20", "2026-10-21"]]  # un seul appel à l'API
    assert [d["found"] for d in body["days"]] == [1, 0, 1]
    assert (body["recorded_count"], body["not_finished_count"], body["found"]) == (1, 1, 2)


def test_date_without_games_writes_nothing_and_says_so(client, db_session, auth_headers, teams, monkeypatch):
    _serve(monkeypatch, _json_handler({"data": []}))
    body = _post(client, auth_headers, date_from=D2.isoformat(), date_to=D2.isoformat()).json()
    assert (body["found"], body["recorded_count"], body["written"]) == (0, 0, False)
    assert body["days"][0]["found"] == 0


def test_already_finished_game_is_counted_apart_and_not_rewritten(client, db_session, auth_headers, teams, monkeypatch):
    game = _game(db_session, teams, D3, GameStatus.FINISHED, (98, 100))
    game.updated_at = datetime(2026, 10, 1, 12, 0, 0)
    db_session.commit()
    _serve(monkeypatch, _json_handler({"data": [_raw(D3)]}))

    body = _post(client, auth_headers, date_from=D3.isoformat(), date_to=D3.isoformat()).json()

    # Le décompte corrigé (limitation n°36) : trouvé, mais NI enregistré NI écrit.
    assert (body["found"], body["recorded_count"], body["already_final_count"], body["written"]) == (1, 0, 1, False)
    db_session.refresh(game)
    assert game.updated_at == datetime(2026, 10, 1, 12, 0, 0)


def test_manually_locked_game_is_skipped_and_named_with_its_reason(client, db_session, auth_headers, teams, monkeypatch):
    game = _game(db_session, teams, D3)
    game.manually_overridden = True
    db_session.commit()
    _serve(monkeypatch, _json_handler({"data": [_raw(D3)]}))

    body = _post(client, auth_headers, date_from=D3.isoformat(), date_to=D3.isoformat()).json()

    assert (body["skipped_count"], body["recorded_count"], body["written"]) == (1, 0, False)
    skipped = body["days"][0]["skipped"][0]
    assert skipped["reason"] == "manually_overridden" and "verrouillé" in skipped["reason_label"]
    db_session.refresh(game)
    assert game.status == GameStatus.SCHEDULED


@pytest.mark.parametrize("status,expected", [(429, "429"), (500, "500"), (401, "401")])
def test_api_http_failure_returns_502_with_the_real_status(client, db_session, auth_headers, teams, monkeypatch, status, expected):
    game = _game(db_session, teams, D3)
    _serve(monkeypatch, lambda request: httpx.Response(status, text="Too Many Requests" if status == 429 else "boom"))

    response = _post(client, auth_headers, date_from=D3.isoformat(), date_to=D3.isoformat())

    assert response.status_code == 502
    assert f"balldontlie a répondu {expected}" in response.json()["detail"]
    if status == 429:
        assert "Too Many Requests" in response.json()["detail"] and "réessayez" in response.json()["detail"]
    db_session.refresh(game)
    assert game.status == GameStatus.SCHEDULED  # rien d'écrit


def test_network_failure_returns_502_with_the_real_message(client, db_session, auth_headers, teams, monkeypatch):
    def handler(request):
        raise httpx.ConnectError("Name or service not known")

    _serve(monkeypatch, handler)
    response = _post(client, auth_headers, date_from=D3.isoformat(), date_to=D3.isoformat())
    assert response.status_code == 502
    assert "Name or service not known" in response.json()["detail"]


def test_inverted_range_is_refused(client, auth_headers):
    response = _post(client, auth_headers, date_from=D3.isoformat(), date_to=D1.isoformat())
    assert response.status_code == 422 and "précéder" in response.json()["detail"]


def test_range_longer_than_the_limit_is_refused(client, auth_headers):
    response = _post(client, auth_headers, date_from=D1.isoformat(), date_to=(D1 + timedelta(days=40)).isoformat())
    assert response.status_code == 422 and "31" in response.json()["detail"]


def test_default_range_is_the_last_three_days_up_to_the_nba_today(client, auth_headers, monkeypatch):
    seen = []

    def handler(request):
        seen.append(request.url.params.get_list("dates[]"))
        return httpx.Response(200, json={"data": []})

    _serve(monkeypatch, handler)
    body = _post(client, auth_headers).json()
    today = current_nba_date()
    assert (body["date_to"], body["date_from"], body["days_count"]) == (
        today.isoformat(), (today - timedelta(days=3)).isoformat(), 4)
    assert len(seen[0]) == 4
