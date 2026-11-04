"""app/services/odds_fetcher.py : relevé automatique des cotes (the-odds-api.com).

Données : la VRAIE réponse de l'API du 2026-11-03 à 20:40:34 UTC (tests/fixtures/odds_api_nba_2026-11-03.json, clé
absente du fichier, vérifié), 10 matchs : 6 le 4 novembre, 4 le 25 décembre. Aucun test n'appelle l'API.
"""
import copy
import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest

from app.models import Game, GameStatus, Odds, OddsCollection, OddsFetchRun, OddsFetchTrigger, OddsMarket, OddsSide, Team
from app.services import odds_fetcher
from app.services.odds import latest_odds_by_cell, record_odds
from app.services.odds_fetcher import (
    ODDS_API_TEAM_ABBREVIATIONS,
    active_kickoff_alerts,
    process_events,
    run_odds_fetch,
)

FIXTURE = Path(__file__).parent / "fixtures" / "odds_api_nba_2026-11-03.json"
FETCHED_AT = datetime(2026, 11, 3, 20, 40, 34)  # instant réel de l'appel, UTC naïf
SECRET = "cle-secrete-de-test-0123456789"

# Nos heures de coup d'envoi (heure murale de New York, comme le calendrier en base) pour les 6 matchs du
# 4 novembre présents dans la réponse. CHI@NYK : 19:30 chez nous, 19:40 pour l'API (écart réel constaté).
NOV4_IN_RESPONSE = [
    ("PHI", "DET", 19, 0), ("CHA", "BKN", 19, 30), ("CHI", "NYK", 19, 30),
    ("CLE", "OKC", 20, 0), ("MIN", "HOU", 20, 30), ("DAL", "SAS", 21, 30),
]


def load_events() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def db_name(api_label: str) -> str:
    return "LA Clippers" if api_label == "Los Angeles Clippers" else api_label


@pytest.fixture()
def teams(db_session):
    by_abbr = {}
    for label, abbr in ODDS_API_TEAM_ABBREVIATIONS.items():
        team = Team(name=db_name(label), abbreviation=abbr)
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
    return {f"{a}@{h}": add_game(db_session, teams, a, h, datetime(2026, 11, 4, hh, mm))
            for a, h, hh, mm in NOV4_IN_RESPONSE}


def expected_rows(event: dict) -> int:
    return sum(len(m["outcomes"]) for b in event["bookmakers"] for m in b["markets"] if m["key"] in ("h2h", "h2h_lay"))


def nov4_events():
    return [e for e in load_events() if e["commence_time"].startswith("2026-11-0")]


# --------------------------------------------------------------------------- données de test


def test_fixture_is_the_real_response_and_contains_no_key():
    raw = FIXTURE.read_text(encoding="utf-8")
    assert "apiKey" not in raw
    assert len(load_events()) == 10


def test_team_table_has_exactly_30_entries_and_maps_clippers():
    assert len(ODDS_API_TEAM_ABBREVIATIONS) == 30
    assert len(set(ODDS_API_TEAM_ABBREVIATIONS.values())) == 30
    assert ODDS_API_TEAM_ABBREVIATIONS["Los Angeles Clippers"] == "LAC"
    assert "Golden State Warriors Blue" not in ODDS_API_TEAM_ABBREVIATIONS


# --------------------------------------------------------------------------- écriture


def test_every_bookmaker_buy_and_lay_is_stored_with_exact_source(db_session, nov4):
    report = process_events(db_session, load_events(), FETCHED_AT, None)
    assert len(report["matched"]) == 6
    total = sum(expected_rows(e) for e in nov4_events())
    assert report["rows_written"] == total == db_session.query(Odds).count()
    sources = {s for (s,) in db_session.query(Odds.source).distinct()}
    assert {"winamax_fr", "unibet_fr", "betfair_ex_eu", "winamax_de", "unibet_se"} <= sources
    assert all(o.collection == OddsCollection.API and o.recorded_at == FETCHED_AT for o in db_session.query(Odds))


def test_values_compared_by_the_user_on_both_sites(db_session, nov4):
    process_events(db_session, load_events(), FETCHED_AT, None)
    game = nov4["PHI@DET"]

    def value(source, side):
        return db_session.query(Odds).filter_by(game_id=game.id, source=source, side=side,
                                                market=OddsMarket.WINNER).one().value
    assert (value("winamax_fr", OddsSide.HOME), value("winamax_fr", OddsSide.AWAY)) == (1.6, 1.84)
    assert (value("unibet_fr", OddsSide.HOME), value("unibet_fr", OddsSide.AWAY)) == (1.65, 1.91)


def test_bookmaker_update_time_is_kept_apart_from_the_call_time(db_session, nov4):
    process_events(db_session, load_events(), FETCHED_AT, None)
    row = db_session.query(Odds).filter_by(game_id=nov4["PHI@DET"].id, source="winamax_fr", side=OddsSide.HOME).one()
    assert row.bookmaker_updated_at == datetime(2026, 11, 3, 20, 40, 8)
    assert row.recorded_at == FETCHED_AT


def test_exchange_lay_is_stored_without_judgment_even_when_empty(db_session, nov4):
    process_events(db_session, load_events(), FETCHED_AT, None)
    lay = db_session.query(Odds).filter_by(game_id=nov4["DAL@SAS"].id, source="betfair_ex_eu",
                                           market=OddsMarket.WINNER_LAY).all()
    assert sorted(o.value for o in lay) == [1000.0, 1000.0]
    back = db_session.query(Odds).filter_by(game_id=nov4["PHI@DET"].id, source="betfair_ex_eu",
                                            market=OddsMarket.WINNER, side=OddsSide.HOME).one()
    assert back.value == 1.87


def test_a_second_identical_fetch_adds_every_row_again_and_overwrites_nothing(db_session, nov4):
    first = process_events(db_session, load_events(), FETCHED_AT, None)["rows_written"]
    later = datetime(2026, 11, 3, 21, 10, 34)
    second = process_events(db_session, load_events(), later, None)["rows_written"]
    assert first == second
    assert db_session.query(Odds).count() == 2 * first
    assert db_session.query(Odds).filter_by(recorded_at=FETCHED_AT).count() == first


def test_rows_are_linked_to_their_fetch_run(db_session, nov4):
    run = OddsFetchRun(fetched_at=FETCHED_AT, trigger=OddsFetchTrigger.BUTTON)
    db_session.add(run)
    process_events(db_session, load_events(), FETCHED_AT, run)
    assert db_session.query(Odds).filter(Odds.fetch_run_id == run.id).count() == db_session.query(Odds).count() > 0


# --------------------------------------------------------------------------- correspondance stricte


def test_games_not_in_database_are_reported_not_guessed(db_session, nov4):
    report = process_events(db_session, load_events(), FETCHED_AT, None)
    unmatched = [u for u in report["unmatched"] if u["reason"] == "not_in_database"]
    assert len(unmatched) == 4  # les 4 matchs du 25 décembre, absents de cette base de test
    assert all(u["nba_date"] == "2026-12-25" for u in unmatched)


def test_unknown_team_label_is_reported_and_nothing_is_written(db_session, nov4):
    events = nov4_events()[:1]
    events[0]["home_team"] = "Golden State Warriors Blue"
    report = process_events(db_session, events, FETCHED_AT, None)
    assert report["matched"] == [] and db_session.query(Odds).count() == 0
    assert report["unmatched"][0]["reason"] == "unknown_team"
    assert report["unmatched"][0]["unknown_labels"] == ["Golden State Warriors Blue"]


def test_clippers_api_label_matches_our_la_clippers(db_session, teams):
    game = add_game(db_session, teams, "MIA", "LAC", datetime(2026, 11, 4, 22, 30))
    event = copy.deepcopy(nov4_events()[0])
    event.update(home_team="Los Angeles Clippers", away_team="Miami Heat", commence_time="2026-11-05T03:30:00Z")
    for b in event["bookmakers"]:
        for m in b["markets"]:
            m["outcomes"] = [{"name": "Los Angeles Clippers", "price": 1.5}, {"name": "Miami Heat", "price": 2.6}]
    report = process_events(db_session, [event], FETCHED_AT, None)
    assert [m["game_id"] for m in report["matched"]] == [game.id]


def test_home_and_away_reversed_in_database_is_reported(db_session, teams):
    add_game(db_session, teams, "DET", "PHI", datetime(2026, 11, 4, 19, 0))  # inversé par rapport à l'API
    report = process_events(db_session, nov4_events()[:1], FETCHED_AT, None)
    assert report["unmatched"][0]["reason"] == "home_away_reversed"
    assert db_session.query(Odds).count() == 0


def test_outcome_name_not_matching_either_team_is_an_anomaly(db_session, nov4):
    events = copy.deepcopy(nov4_events()[:1])
    events[0]["bookmakers"][0]["markets"][0]["outcomes"][0]["name"] = "Detroit"
    report = process_events(db_session, events, FETCHED_AT, None)
    assert any(a["reason"] == "outcome_name" and a["outcome"] == "Detroit" for a in report["anomalies"])
    assert report["rows_written"] == expected_rows(events[0]) - 1


@pytest.mark.parametrize("price", [None, "1.8", 1.0, 0.5, True])
def test_unusable_price_is_an_anomaly(db_session, nov4, price):
    events = copy.deepcopy(nov4_events()[:1])
    events[0]["bookmakers"][0]["markets"][0]["outcomes"][0]["price"] = price
    report = process_events(db_session, events, FETCHED_AT, None)
    assert any(a["reason"] == "bad_price" for a in report["anomalies"])
    assert report["rows_written"] == expected_rows(events[0]) - 1


def test_duplicate_event_for_the_same_game_is_reported(db_session, nov4):
    event = nov4_events()[0]
    report = process_events(db_session, [event, copy.deepcopy(event)], FETCHED_AT, None)
    assert len(report["matched"]) == 1
    assert report["unmatched"][0]["reason"] == "duplicate_event"


def test_missing_screen_bookmaker_is_reported(db_session, nov4):
    report = process_events(db_session, load_events(), FETCHED_AT, None)
    by_label = {m["label"]: m for m in report["matched"]}
    assert by_label["CHI@NYK"]["missing_screen_bookmakers"] == ["winamax_fr"]
    assert by_label["PHI@DET"]["missing_screen_bookmakers"] == []


# --------------------------------------------------------------------------- matchs non relevés


@pytest.mark.parametrize("status, reason", [(GameStatus.FINISHED, "finished"), (GameStatus.POSTPONED, "postponed")])
def test_finished_or_postponed_games_are_not_recorded(db_session, nov4, status, reason):
    nov4["PHI@DET"].status = status
    report = process_events(db_session, nov4_events()[:1], FETCHED_AT, None)
    assert report["ignored"][0]["reason"] == reason and db_session.query(Odds).count() == 0


def test_started_game_by_our_time_is_not_recorded(db_session, nov4):
    after_our_start = datetime(2026, 11, 5, 0, 1)  # PHI@DET : 19:00 à New York = 00:00 UTC
    report = process_events(db_session, nov4_events()[:1], after_our_start, None)
    assert report["ignored"][0]["reason"] == "started" and db_session.query(Odds).count() == 0


def test_started_game_by_api_time_earlier_than_ours_is_not_recorded(db_session, nov4):
    nov4["PHI@DET"].game_date = datetime(2026, 11, 4, 19, 30)  # notre base dit 19:30, l'API 19:00
    db_session.flush()
    between = datetime(2026, 11, 5, 0, 10)  # après l'heure de l'API, avant la nôtre
    report = process_events(db_session, nov4_events()[:1], between, None)
    assert report["ignored"][0]["reason"] == "started" and db_session.query(Odds).count() == 0


def test_todays_games_absent_from_the_response_are_reported_as_no_odds_yet(db_session, teams, nov4):
    atl_was = add_game(db_session, teams, "ATL", "WAS", datetime(2026, 11, 4, 19, 0))
    morning_nov4 = datetime(2026, 11, 4, 14, 0)
    report = process_events(db_session, load_events(), morning_nov4, None)
    no_odds = {n["label"]: n["reason"] for n in report["no_odds_yet"]}
    assert no_odds == {"ATL@WAS": "not_in_response"}
    assert atl_was.id not in {m["game_id"] for m in report["matched"]}
    assert "ATL@WAS" not in {u.get("label") for u in report["unmatched"]}


def test_event_without_bookmaker_is_no_odds_yet_not_unmatched(db_session, nov4):
    events = copy.deepcopy(nov4_events()[:1])
    events[0]["bookmakers"] = []
    report = process_events(db_session, events, FETCHED_AT, None)
    assert report["no_odds_yet"][0]["reason"] == "no_bookmaker" and report["unmatched"] == []


# --------------------------------------------------------------------------- écart d'heure et alerte


def test_later_api_kickoff_is_reported_without_alert(db_session, nov4):
    report = process_events(db_session, load_events(), FETCHED_AT, None)
    gaps = {g["label"]: (g["gap_minutes"], g["alert"]) for g in report["time_gaps"]}
    assert gaps == {"CHI@NYK": (10, False)}


def test_earlier_api_kickoff_raises_an_alert_that_stays_until_corrected(db_session, nov4):
    nov4["PHI@DET"].game_date = datetime(2026, 11, 4, 19, 20)  # l'API dit 19:00 : 20 minutes PLUS TÔT
    db_session.flush()
    run = run_with_report(db_session, nov4_events()[:1], FETCHED_AT)
    assert run.report["time_gaps"][0]["alert"] is True and run.report["time_gaps"][0]["gap_minutes"] == -20

    later_that_day = datetime(2026, 11, 4, 18, 0)  # aucun nouveau relevé depuis : l'alerte reste
    alerts = active_kickoff_alerts(db_session, later_that_day)
    assert [(a.label, a.minutes_earlier) for a in alerts] == [("PHI@DET", 20)]

    nov4["PHI@DET"].game_date = datetime(2026, 11, 4, 19, 0)  # corrigé sur l'écran Matchs
    db_session.flush()
    assert active_kickoff_alerts(db_session, later_that_day) == []


def test_alert_disappears_once_the_game_has_started(db_session, nov4):
    nov4["PHI@DET"].game_date = datetime(2026, 11, 4, 19, 20)
    db_session.flush()
    run_with_report(db_session, nov4_events()[:1], FETCHED_AT)
    assert active_kickoff_alerts(db_session, datetime(2026, 11, 5, 0, 5)) == []  # 19:05 à New York


def test_no_alert_when_api_kickoff_is_later(db_session, nov4):
    run_with_report(db_session, load_events(), FETCHED_AT)  # CHI@NYK : API 10 minutes plus tard
    assert active_kickoff_alerts(db_session, datetime(2026, 11, 4, 18, 0)) == []


def run_with_report(db, events, fetched_at):
    run = OddsFetchRun(fetched_at=fetched_at, trigger=OddsFetchTrigger.SCHEDULED)
    db.add(run)
    run.report = process_events(db, events, fetched_at, run)
    db.flush()
    return run


# --------------------------------------------------------------------------- appel et journal


def mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_successful_call_is_journaled_with_credits(db_session, nov4):
    def handler(request):
        assert request.url.params["regions"] == "eu" and request.url.params["markets"] == "h2h"
        return httpx.Response(200, json=load_events(), headers={"x-requests-last": "1", "x-requests-remaining": "497"})
    run = run_odds_fetch(db_session, mock_client(handler), SECRET, OddsFetchTrigger.BUTTON, FETCHED_AT)
    assert (run.http_status, run.credits_used, run.credits_remaining, run.events_returned) == (200, 1, 497, 10)
    assert run.rows_written == db_session.query(Odds).count() > 0
    assert run.report["rows_written"] == run.rows_written and run.error is None


def test_refused_call_is_journaled_writes_nothing_and_hides_the_key(db_session, nov4):
    def handler(request):
        return httpx.Response(401, json={"message": f"Invalid key {SECRET}"})
    run = run_odds_fetch(db_session, mock_client(handler), SECRET, OddsFetchTrigger.SCHEDULED, FETCHED_AT)
    assert run.http_status == 401 and SECRET not in run.error and "***" in run.error
    assert db_session.query(Odds).count() == 0 and db_session.query(OddsFetchRun).count() == 1


def test_network_error_message_never_contains_the_key(db_session, nov4):
    def handler(request):
        raise httpx.ConnectError(f"connexion refusée pour {request.url}")
    run = run_odds_fetch(db_session, mock_client(handler), SECRET, OddsFetchTrigger.BUTTON, FETCHED_AT)
    assert run.http_status is None and run.error and SECRET not in run.error


@pytest.mark.parametrize("body", ["pas du json", '{"message": "objet"}'])
def test_unexpected_body_is_journaled_as_error(db_session, nov4, body):
    def handler(request):
        return httpx.Response(200, text=body)
    run = run_odds_fetch(db_session, mock_client(handler), SECRET, OddsFetchTrigger.BUTTON, FETCHED_AT)
    assert run.error and db_session.query(Odds).count() == 0


# --------------------------------------------------------------------------- cohabitation avec la saisie manuelle


def test_manual_duplicate_rule_ignores_api_rows(db_session, nov4):
    process_events(db_session, load_events(), FETCHED_AT, None)  # API : winamax_fr domicile PHI@DET = 1,6
    out = record_odds(db_session, nov4["PHI@DET"].id, OddsSide.HOME, "winamax_fr", 1.6, datetime(2026, 11, 3, 21))
    assert out.action == "created" and out.odds.collection == OddsCollection.MANUEL


def test_screen_reads_latest_of_either_origin_for_its_two_sources_only(db_session, nov4):
    game = nov4["PHI@DET"]
    record_odds(db_session, game.id, OddsSide.HOME, "winamax_fr", 1.55, datetime(2026, 11, 3, 19))
    process_events(db_session, load_events(), FETCHED_AT, None)  # plus récent
    latest = latest_odds_by_cell(db_session, [game.id], ("winamax_fr", "unibet_fr"))
    cell = latest[(game.id, OddsSide.HOME, "winamax_fr")]
    assert (cell.value, cell.collection) == (1.6, OddsCollection.API)
    assert {source for (_, _, source) in latest} == {"winamax_fr", "unibet_fr"}
    record_odds(db_session, game.id, OddsSide.HOME, "winamax_fr", 1.62, datetime(2026, 11, 3, 21))
    cell = latest_odds_by_cell(db_session, [game.id], ("winamax_fr", "unibet_fr"))[(game.id, OddsSide.HOME, "winamax_fr")]
    assert (cell.value, cell.collection) == (1.62, OddsCollection.MANUEL)


def test_odds_without_collection_cannot_be_written(db_session, nov4):
    db_session.add(Odds(game_id=nov4["PHI@DET"].id, side=OddsSide.HOME, source="winamax_fr", value=1.8,
                        recorded_at=FETCHED_AT))
    with pytest.raises(Exception):
        db_session.flush()


@pytest.fixture()
def live_loggers():
    """Un test de migration plus tôt dans la suite charge la configuration de journal d'Alembic, qui DÉSACTIVE les
    journaux déjà créés (disable_existing_loggers) : sans ceci, ces tests ne verraient rien et passeraient pour de
    mauvaises raisons, ou échoueraient selon l'ordre."""
    import logging
    names = ("httpx", odds_fetcher.__name__)
    before = {n: logging.getLogger(n).disabled for n in names}
    for n in names:
        logging.getLogger(n).disabled = False
    yield
    for n, disabled in before.items():
        logging.getLogger(n).disabled = disabled


def test_module_never_logs_or_stores_the_key(db_session, nov4, caplog, live_loggers):
    def handler(request):
        return httpx.Response(500, text=f"erreur interne {request.url}")
    with caplog.at_level("INFO", logger=odds_fetcher.__name__):
        run = run_odds_fetch(db_session, mock_client(handler), SECRET, OddsFetchTrigger.BUTTON, FETCHED_AT)
    assert SECRET not in caplog.text and SECRET not in (run.error or "")
    assert "apiKey=***" in caplog.text  # la ligne de httpx est bien là, clé masquée


def test_httpx_request_line_is_redacted_on_success_too(db_session, nov4, caplog, live_loggers):
    def handler(request):
        return httpx.Response(200, json=[], headers={"x-requests-last": "0", "x-requests-remaining": "497"})
    with caplog.at_level("INFO"):
        run_odds_fetch(db_session, mock_client(handler), SECRET, OddsFetchTrigger.BUTTON, FETCHED_AT)
    assert "HTTP Request" in caplog.text and SECRET not in caplog.text
