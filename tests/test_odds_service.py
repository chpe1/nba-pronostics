"""app/services/odds.py : parsing, normalisation de source, et les trois règles de doublon."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Game, Odds, OddsSide, Team
from app.services.odds import (
    InvalidOddsSourceError,
    InvalidOddsValueError,
    normalize_odds_source,
    parse_odds_value,
    record_odds,
    to_naive_utc,
)

# --------------------------------------------------------------------------- parse_odds_value


@pytest.mark.parametrize("raw, expected", [("1,85", 1.85), ("1.85", 1.85), (" 2,50 ", 2.5), ("1.01", 1.01), ("100", 100.0)])
def test_parse_accepts_french_comma_and_dot(raw, expected):
    assert parse_odds_value(raw) == expected


@pytest.mark.parametrize("raw", ["1", "1,00", "0,99", "100,01", "500", "-1,5"])
def test_parse_rejects_out_of_bounds(raw):
    with pytest.raises(InvalidOddsValueError):
        parse_odds_value(raw)


@pytest.mark.parametrize("raw", ["", "abc", "1,8,5", "--"])
def test_parse_rejects_unparseable_text(raw):
    with pytest.raises(InvalidOddsValueError):
        parse_odds_value(raw)


# --------------------------------------------------------------------------- normalize_odds_source


@pytest.mark.parametrize("raw", ["winamax", "Winamax", "WINAMAX", " winamax "])
def test_normalize_source_folds_case(raw):
    assert normalize_odds_source(raw) == "winamax"


def test_normalize_source_rejects_unknown():
    with pytest.raises(InvalidOddsSourceError):
        normalize_odds_source("betclic")


def test_winamax_and_winamax_capitalized_never_produce_two_distinct_rows(db_session):
    home, away = Team(name="H", abbreviation="HHH"), Team(name="A", abbreviation="AAA")
    db_session.add_all([home, away])
    db_session.flush()
    game = Game(season="2026-2027", game_date=datetime(2026, 1, 1, 19), home_team_id=home.id, away_team_id=away.id)
    db_session.add(game)
    db_session.flush()
    now = datetime(2026, 1, 1, 10)
    record_odds(db_session, game.id, OddsSide.HOME, normalize_odds_source("Winamax"), 1.85, now)
    record_odds(db_session, game.id, OddsSide.HOME, normalize_odds_source("WINAMAX"), 1.90, now + timedelta(minutes=5))
    assert db_session.query(Odds).filter(Odds.source == "winamax").count() == 2
    assert db_session.query(Odds).filter(Odds.source == "Winamax").count() == 0


# --------------------------------------------------------------------------- to_naive_utc


def test_to_naive_utc_converts_an_aware_datetime():
    paris_like = datetime(2026, 10, 24, 16, 32, tzinfo=timezone.utc)
    assert to_naive_utc(paris_like) == datetime(2026, 10, 24, 16, 32)


def test_to_naive_utc_leaves_a_naive_datetime_untouched():
    naive = datetime(2026, 10, 24, 16, 32)
    assert to_naive_utc(naive) == naive


# --------------------------------------------------------------------------- record_odds : les 3 règles


@pytest.fixture()
def game(db_session):
    home, away = Team(name="Boston Celtics", abbreviation="BOS"), Team(name="Miami Heat", abbreviation="MIA")
    db_session.add_all([home, away])
    db_session.flush()
    g = Game(season="2026-2027", game_date=datetime(2026, 10, 24, 19), home_team_id=home.id, away_team_id=away.id)
    db_session.add(g)
    db_session.flush()
    return g


T1 = datetime(2026, 10, 24, 10, 0)
T2 = datetime(2026, 10, 24, 16, 0)


def test_first_record_is_created(db_session, game):
    out = record_odds(db_session, game.id, OddsSide.HOME, "winamax", 1.85, T1)
    assert out.action == "created"
    assert db_session.query(Odds).count() == 1


def test_same_value_again_is_a_no_op(db_session, game):
    record_odds(db_session, game.id, OddsSide.HOME, "winamax", 1.85, T1)
    out = record_odds(db_session, game.id, OddsSide.HOME, "winamax", 1.85, T2)
    assert out.action == "unchanged"
    assert db_session.query(Odds).count() == 1  # aucune deuxième ligne, même à un instant différent


def test_different_value_at_a_new_instant_adds_a_history_row(db_session, game):
    record_odds(db_session, game.id, OddsSide.HOME, "winamax", 1.85, T1)
    out = record_odds(db_session, game.id, OddsSide.HOME, "winamax", 1.90, T2)
    assert out.action == "created"
    assert db_session.query(Odds).count() == 2
    values = sorted(o.value for o in db_session.query(Odds).all())
    assert values == [1.85, 1.90]


def test_different_value_at_the_same_instant_corrects_in_place(db_session, game):
    record_odds(db_session, game.id, OddsSide.HOME, "winamax", 1.85, T1)
    out = record_odds(db_session, game.id, OddsSide.HOME, "winamax", 1.95, T1)  # même T1 : faute de frappe corrigée
    assert out.action == "updated"
    assert db_session.query(Odds).count() == 1
    assert db_session.query(Odds).one().value == 1.95


def test_each_side_source_market_combination_has_its_own_history(db_session, game):
    record_odds(db_session, game.id, OddsSide.HOME, "winamax", 1.85, T1)
    record_odds(db_session, game.id, OddsSide.AWAY, "winamax", 2.10, T1)
    record_odds(db_session, game.id, OddsSide.HOME, "unibet", 1.80, T1)
    assert db_session.query(Odds).count() == 3


def test_the_unique_constraint_is_a_backstop_not_the_mechanism(db_session, game):
    """record_odds gère déjà les 3 cas sans jamais violer la contrainte -- elle protège contre un bug
    futur qui écrirait directement sans passer par le service (même principe que UNIQUE(name, team_id),
    Décision d'architecture n°7)."""
    db_session.add(Odds(game_id=game.id, side=OddsSide.HOME, source="winamax", value=1.85, recorded_at=T1))
    db_session.flush()
    db_session.add(Odds(game_id=game.id, side=OddsSide.HOME, source="winamax", value=1.90, recorded_at=T1))
    with pytest.raises(Exception):
        db_session.flush()
