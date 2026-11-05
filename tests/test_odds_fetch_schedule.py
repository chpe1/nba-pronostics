"""Relevé des cotes : règle de rythme de la tâche planifiée, tâche elle-même, routes du bouton et de l'état.

Règle (validée par l'utilisateur le 2026-11-03) : « un relevé par heure tant qu'un match commence dans les 3 heures
qui suivent, jusqu'au dernier coup d'envoi du jour », sans aucune heure d'arrêt écrite ; sous 20 crédits restants,
la tâche planifiée n'appelle plus. Aucun test n'appelle l'API : le client HTTP est remplacé (`make_client`).
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest

from app.models import Game, GameStatus, Odds, OddsFetchRun, OddsFetchTrigger, Team
from app.services import nba_calendar, odds_fetcher, scheduler
from app.services.odds_fetcher import (
    DECISION_CALL,
    DECISION_CREDITS_LOW,
    DECISION_NO_GAME_SOON,
    MIN_CREDITS_FOR_SCHEDULED,
    ODDS_API_TEAM_ABBREVIATIONS,
    scheduled_fetch_decision,
)

FIXTURE = Path(__file__).parent / "fixtures" / "odds_api_nba_2026-11-03.json"
SECRET = "cle-secrete-de-test-0123456789"

# Les 6 matchs du 4 novembre 2026 (heure de New York, UTC-5 ce jour-là) : coups d'envoi de 00:00 à 02:30 UTC le 5.
NOV4 = [("PHI", "DET", 19, 0), ("CHA", "BKN", 19, 30), ("CHI", "NYK", 19, 30),
        ("CLE", "OKC", 20, 0), ("MIN", "HOU", 20, 30), ("DAL", "SAS", 21, 30)]


@pytest.fixture()
def teams(db_session):
    by_abbr = {}
    for label, abbr in ODDS_API_TEAM_ABBREVIATIONS.items():
        team = Team(name="LA Clippers" if abbr == "LAC" else label, abbreviation=abbr)
        db_session.add(team)
        by_abbr[abbr] = team
    db_session.flush()
    return by_abbr


def add_game(db, teams, away, home, when, status=GameStatus.SCHEDULED):
    game = Game(season="2026-2027", game_date=when, home_team_id=teams[home].id, away_team_id=teams[away].id,
                status=status)
    db.add(game)
    db.flush()
    return game


@pytest.fixture()
def nov4(db_session, teams):
    return {f"{a}@{h}": add_game(db_session, teams, a, h, datetime(2026, 11, 4, hh, mm)) for a, h, hh, mm in NOV4}


def add_run(db, fetched_at, credits_remaining, trigger=OddsFetchTrigger.SCHEDULED):
    run = OddsFetchRun(fetched_at=fetched_at, trigger=trigger, http_status=200, credits_used=1,
                       credits_remaining=credits_remaining, events_returned=0, rows_written=0, report={})
    db.add(run)
    db.flush()
    return run


def utc(day, hour, minute=0):
    return datetime(2026, 11, day, hour, minute)


# --------------------------------------------------------------------------- la règle de rythme


def test_the_hourly_rule_on_a_real_evening_calls_from_three_hours_before_until_the_last_kickoff(db_session, nov4):
    """Réveils de 12:00 UTC le 4 à 12:00 UTC le 5 : appel à 21, 22, 23, 0, 1 et 2 h UTC (16 h à 21 h à New York), soit
    6 appels. Le dernier précède DAL@SAS (02:30 UTC) de 30 minutes ; à 3 h UTC, plus aucun match à venir."""
    wakeups = [utc(4, 12) + timedelta(hours=h) for h in range(25)]
    called = [w for w in wakeups if scheduled_fetch_decision(db_session, w).action == DECISION_CALL]
    assert called == [utc(4, 21), utc(4, 22), utc(4, 23), utc(5, 0), utc(5, 1), utc(5, 2)]


def test_every_game_gets_a_relevé_within_the_hour_before_its_kickoff(db_session, nov4):
    wakeups = [utc(4, 12) + timedelta(hours=h) for h in range(25)]
    called = [w for w in wakeups if scheduled_fetch_decision(db_session, w).action == DECISION_CALL]
    for game in nov4.values():
        start = nba_calendar.game_start_utc(game.game_date)
        last_before = max(w for w in called if w < start)
        assert start - last_before <= timedelta(hours=1)


@pytest.mark.parametrize("minutes_ahead, expected", [
    (180, DECISION_CALL),  # exactement 3 heures : dans la fenêtre
    (181, DECISION_NO_GAME_SOON),
    (1, DECISION_CALL),
    (0, DECISION_NO_GAME_SOON),  # coup d'envoi à l'instant même : commencé, plus rien à relever
    (-30, DECISION_NO_GAME_SOON),
])
def test_window_bounds(db_session, teams, minutes_ahead, expected):
    game = add_game(db_session, teams, "BOS", "MIA", datetime(2026, 11, 10, 19, 0))
    now = nba_calendar.game_start_utc(game.game_date) - timedelta(minutes=minutes_ahead)
    assert scheduled_fetch_decision(db_session, now).action == expected


@pytest.mark.parametrize("status", [GameStatus.FINISHED, GameStatus.POSTPONED])
def test_finished_or_postponed_games_never_trigger_a_call(db_session, teams, status):
    game = add_game(db_session, teams, "BOS", "MIA", datetime(2026, 11, 10, 19, 0), status=status)
    now = nba_calendar.game_start_utc(game.game_date) - timedelta(hours=1)
    assert scheduled_fetch_decision(db_session, now).action == DECISION_NO_GAME_SOON


def test_a_late_game_after_midnight_utc_and_paris_is_handled_without_any_stop_hour(db_session, teams):
    """22:30 à New York le 10 novembre = 03:30 UTC le 11 = 04:30 à Paris. Réveil à 01:00 UTC le 11 (dans les 3 heures) :
    appel, alors que la date de New York (10) et la date UTC (11) diffèrent."""
    add_game(db_session, teams, "LAL", "GSW", datetime(2026, 11, 10, 22, 30))
    assert scheduled_fetch_decision(db_session, utc(11, 1)).action == DECISION_CALL
    assert scheduled_fetch_decision(db_session, utc(11, 0)).action == DECISION_NO_GAME_SOON


def test_decision_names_the_next_game_in_the_window(db_session, nov4):
    decision = scheduled_fetch_decision(db_session, utc(4, 23))
    assert decision.next_game == "PHI@DET 2026-11-05T00:00:00Z"


# --------------------------------------------------------------------------- seuil de crédits


@pytest.mark.parametrize("credits, expected", [
    (None, DECISION_CALL),  # aucun solde connu (premier appel) : on appelle
    (MIN_CREDITS_FOR_SCHEDULED, DECISION_CALL),
    (MIN_CREDITS_FOR_SCHEDULED - 1, DECISION_CREDITS_LOW),
    (0, DECISION_CREDITS_LOW),
])
def test_credit_threshold_is_20(db_session, nov4, credits, expected):
    if credits is not None:
        add_run(db_session, utc(4, 20), credits)
    decision = scheduled_fetch_decision(db_session, utc(4, 22))
    assert decision.action == expected and decision.credits_remaining == credits


def test_credits_low_is_only_reported_when_a_game_is_coming(db_session, nov4):
    add_run(db_session, utc(4, 20), 3)
    assert scheduled_fetch_decision(db_session, utc(4, 12)).action == DECISION_NO_GAME_SOON


def test_a_button_call_with_a_fresh_balance_resumes_the_scheduled_task(db_session, nov4):
    add_run(db_session, utc(4, 18), 5)
    add_run(db_session, utc(4, 21, 30), 499, trigger=OddsFetchTrigger.BUTTON)  # ex. après la remise à zéro mensuelle
    assert scheduled_fetch_decision(db_session, utc(4, 22)).action == DECISION_CALL


def test_a_failed_call_without_balance_does_not_hide_the_last_known_balance(db_session, nov4):
    add_run(db_session, utc(4, 20), 7)
    db_session.add(OddsFetchRun(fetched_at=utc(4, 21), trigger=OddsFetchTrigger.SCHEDULED, http_status=500,
                                error="panne", events_returned=0, rows_written=0))
    db_session.flush()
    assert scheduled_fetch_decision(db_session, utc(4, 22)).action == DECISION_CREDITS_LOW


# --------------------------------------------------------------------------- la tâche planifiée


@pytest.fixture()
def job_env(db_session, monkeypatch):
    """La tâche ouvre sa propre session (SessionLocal) : on lui donne celle du test, sans la fermer."""
    monkeypatch.setattr(scheduler, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    monkeypatch.setenv("ODDS_API_KEY", SECRET)
    calls = []

    def install(handler):
        def counted(request):
            calls.append(request)
            return handler(request)
        monkeypatch.setattr(odds_fetcher, "make_client", lambda: httpx.Client(transport=httpx.MockTransport(counted)))
    return install, calls


def real_response(request):
    events = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return httpx.Response(200, json=events, headers={"x-requests-last": "1", "x-requests-remaining": "480"})


def test_job_calls_and_journals_when_a_game_is_coming(db_session, nov4, job_env, monkeypatch):
    install, calls = job_env
    install(real_response)
    monkeypatch.setattr(nba_calendar, "utc_now", lambda: utc(4, 22))
    scheduler.run_odds_fetch_job()
    run = db_session.query(OddsFetchRun).one()
    assert len(calls) == 1 and run.trigger == OddsFetchTrigger.SCHEDULED
    assert run.fetched_at == utc(4, 22) and run.credits_remaining == 480
    assert db_session.query(Odds).count() == run.rows_written > 0


def test_job_does_not_call_when_no_game_is_within_three_hours(db_session, nov4, job_env, monkeypatch):
    install, calls = job_env
    install(real_response)
    monkeypatch.setattr(nba_calendar, "utc_now", lambda: utc(4, 15))
    scheduler.run_odds_fetch_job()
    assert calls == [] and db_session.query(OddsFetchRun).count() == 0


@pytest.fixture()
def scheduler_logger_live():
    """Même précaution que `live_loggers` (test_odds_fetcher.py) : la configuration de journal d'Alembic, chargée par
    un test de migration plus tôt dans la suite, désactive les journaux déjà créés."""
    import logging
    logger = logging.getLogger(scheduler.__name__)
    before = logger.disabled
    logger.disabled = False
    yield
    logger.disabled = before


def balance_response(remaining):
    def handler(request):
        if request.url.path.endswith("/v4/sports"):
            return httpx.Response(200, json=[], headers={"x-requests-last": "0", "x-requests-remaining": str(remaining)})
        return real_response(request)
    return handler


def test_job_under_the_threshold_rereads_the_balance_for_free_and_stays_suspended_if_still_low(
        db_session, nov4, job_env, monkeypatch, caplog, scheduler_logger_live):
    install, calls = job_env
    install(balance_response(12))
    add_run(db_session, utc(4, 20), 12)
    monkeypatch.setattr(nba_calendar, "utc_now", lambda: utc(4, 22))
    with caplog.at_level("WARNING", logger="app.services.scheduler"):
        scheduler.run_odds_fetch_job()
    assert [c.url.path for c in calls] == ["/v4/sports"]  # jamais l'appel payant
    assert db_session.query(OddsFetchRun).count() == 2 and db_session.query(Odds).count() == 0
    assert "12 crédit(s) restant(s), sous le seuil de 20" in caplog.text


def test_job_resumes_by_itself_when_the_free_call_shows_the_monthly_reset(db_session, nov4, job_env, monkeypatch):
    install, calls = job_env
    install(balance_response(500))
    add_run(db_session, utc(4, 20), 3)
    monkeypatch.setattr(nba_calendar, "utc_now", lambda: utc(4, 22))
    scheduler.run_odds_fetch_job()
    assert [c.url.path for c in calls] == ["/v4/sports", "/v4/sports/basketball_nba/odds"]
    check = db_session.query(OddsFetchRun).filter(OddsFetchRun.report == {"balance_check_only": True}).one()
    assert check.credits_used == 0 and check.credits_remaining == 500 and check.rows_written == 0
    assert db_session.query(Odds).count() > 0


def test_job_stays_suspended_and_says_so_when_the_free_call_fails(db_session, nov4, job_env, monkeypatch, caplog,
                                                                    scheduler_logger_live):
    install, calls = job_env
    install(lambda request: httpx.Response(500, text="panne"))
    add_run(db_session, utc(4, 20), 12)
    monkeypatch.setattr(nba_calendar, "utc_now", lambda: utc(4, 22))
    with caplog.at_level("WARNING", logger="app.services.scheduler"):
        scheduler.run_odds_fetch_job()
    assert len(calls) == 1 and db_session.query(Odds).count() == 0
    assert "solde non relu" in caplog.text
    failed = db_session.query(OddsFetchRun).order_by(OddsFetchRun.id.desc()).first()
    assert failed.http_status == 500 and failed.error and failed.credits_remaining is None


def test_job_does_not_reread_the_balance_when_no_game_is_coming(db_session, nov4, job_env, monkeypatch):
    install, calls = job_env
    install(balance_response(500))
    add_run(db_session, utc(4, 10), 3)
    monkeypatch.setattr(nba_calendar, "utc_now", lambda: utc(4, 15))
    scheduler.run_odds_fetch_job()
    assert calls == []


def test_job_journals_a_failed_call_without_writing_odds(db_session, nov4, job_env, monkeypatch):
    install, calls = job_env
    install(lambda request: httpx.Response(500, text="erreur interne"))
    monkeypatch.setattr(nba_calendar, "utc_now", lambda: utc(4, 22))
    scheduler.run_odds_fetch_job()
    run = db_session.query(OddsFetchRun).one()
    assert run.http_status == 500 and run.error and db_session.query(Odds).count() == 0


def test_job_without_api_key_does_not_raise_nor_call(db_session, nov4, job_env, monkeypatch):
    install, calls = job_env
    install(real_response)
    monkeypatch.delenv("ODDS_API_KEY")
    monkeypatch.setattr(nba_calendar, "utc_now", lambda: utc(4, 22))
    scheduler.run_odds_fetch_job()
    assert calls == []


def test_odds_toggle_registers_an_hourly_job_without_any_hour_range(monkeypatch):
    for name in ("ENABLE_INJURY_SCHEDULER", "ENABLE_SCORES_SCHEDULER"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ENABLE_ODDS_SCHEDULER", "true")
    sched = scheduler.start_scheduler()
    try:
        (job,) = sched.get_jobs()
        fields = {f.name: str(f) for f in job.trigger.fields}
        assert job.id == scheduler.ODDS_JOB_ID
        assert (fields["minute"], fields["hour"]) == ("0", "*")
    finally:
        sched.shutdown()


# --------------------------------------------------------------------------- routes


@pytest.fixture()
def api_mock(monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY", SECRET)

    def install(handler):
        monkeypatch.setattr(odds_fetcher, "make_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    return install


def test_fetch_requires_authentication(client):
    assert client.post("/api/odds/fetch").status_code == 401
    assert client.get("/api/odds/fetch-status").status_code == 401


def test_fetch_without_key_is_503_and_journals_nothing(client, db_session, auth_headers, monkeypatch):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    response = client.post("/api/odds/fetch", headers=auth_headers)
    assert response.status_code == 503 and db_session.query(OddsFetchRun).count() == 0


def test_button_fetch_returns_the_full_report_and_ignores_the_credit_threshold(
        client, db_session, nov4, auth_headers, api_mock, monkeypatch):
    add_run(db_session, utc(3, 12), 2)  # sous le seuil : la tâche planifiée s'arrêterait, pas le bouton
    api_mock(real_response)
    monkeypatch.setattr(nba_calendar, "utc_now", lambda: utc(3, 20, 40))
    response = client.post("/api/odds/fetch", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["trigger"] == "button" and body["fetched_at"] == "2026-11-03T20:40:00Z"
    assert body["credits_remaining"] == 480 and body["matched_count"] == 6 and body["unmatched_count"] == 4
    assert body["rows_written"] == db_session.query(Odds).count() > 0
    assert {e["label"] for e in body["report"]["matched"]} >= {"PHI@DET", "CHI@NYK"}


def test_button_failure_is_502_with_the_api_message_key_hidden_and_still_journaled(
        client, db_session, nov4, auth_headers, api_mock):
    api_mock(lambda request: httpx.Response(401, json={"message": f"Invalid key {SECRET}"}))
    response = client.post("/api/odds/fetch", headers=auth_headers)
    assert response.status_code == 502
    assert SECRET not in response.text and "401" in response.json()["detail"]
    # La vraie session (get_db) annule tout ce qui n'est pas validé quand la route lève : seul un journal VALIDÉ
    # avant l'erreur survit.
    db_session.rollback()
    run = db_session.query(OddsFetchRun).one()
    assert run.trigger == OddsFetchTrigger.BUTTON and run.http_status == 401


def test_status_when_nothing_was_ever_fetched(client, auth_headers, monkeypatch):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    monkeypatch.delenv("ENABLE_ODDS_SCHEDULER", raising=False)
    body = client.get("/api/odds/fetch-status", headers=auth_headers).json()
    assert body == {
        "scheduler_enabled": False, "api_key_configured": False, "credits_threshold": 20,
        "last_known_credits": None, "last_known_credits_at": None, "scheduled_suspended": False,
        "latest_run": None, "recent_runs": [], "alerts": [],
    }


def test_status_shows_journal_balance_suspension_and_kickoff_alerts(
        client, db_session, nov4, auth_headers, api_mock, monkeypatch):
    # L'API annonce PHI@DET à 18:30 (New York) alors que la base dit 19:00 : alerte.
    events = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for event in events:
        if event["home_team"] == "Detroit Pistons":
            event["commence_time"] = "2026-11-04T23:30:00Z"
    api_mock(lambda request: httpx.Response(200, json=events, headers={"x-requests-remaining": "15"}))
    monkeypatch.setattr(nba_calendar, "utc_now", lambda: utc(4, 22))
    assert client.post("/api/odds/fetch", headers=auth_headers).status_code == 200

    body = client.get("/api/odds/fetch-status", headers=auth_headers).json()
    assert body["last_known_credits"] == 15 and body["scheduled_suspended"] is True
    assert body["latest_run"]["report"] is not None
    assert len(body["recent_runs"]) == 1 and body["recent_runs"][0]["report"] is None
    (alert,) = body["alerts"]
    assert alert["label"] == "PHI@DET" and alert["minutes_earlier"] == 30
    assert alert["api_start"] == "2026-11-04T23:30:00Z" and alert["our_start"] == "2026-11-05T00:00:00Z"


def test_status_raises_no_alert_when_the_api_announces_a_LATER_kickoff_or_the_same_one(
        client, db_session, nov4, auth_headers, api_mock, monkeypatch):
    """L'alerte ne vaut que dans le sens dangereux (l'API annonce PLUS TÔT que notre calendrier : le match peut être
    commencé quand on le croit à venir). Plus tard ou identique : rien à signaler à l'écran."""
    events = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for event in events:
        if event["home_team"] == "Detroit Pistons":
            event["commence_time"] = "2026-11-05T00:30:00Z"  # 30 minutes PLUS TARD que notre 00:00Z
    api_mock(lambda request: httpx.Response(200, json=events, headers={"x-requests-remaining": "400"}))
    monkeypatch.setattr(nba_calendar, "utc_now", lambda: utc(4, 22))
    assert client.post("/api/odds/fetch", headers=auth_headers).status_code == 200
    body = client.get("/api/odds/fetch-status", headers=auth_headers).json()
    assert body["alerts"] == []
    # le compte-rendu le dit sans alerte : l'écart existe mais n'est pas dangereux
    gaps = [g for g in body["latest_run"]["report"]["time_gaps"] if g["label"] == "PHI@DET"]
    assert gaps and gaps[0]["gap_minutes"] == 30 and gaps[0]["alert"] is False
