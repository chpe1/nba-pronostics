from datetime import date, datetime, timedelta

import pytest

from app.models import Game, GameStatus, Team
from app.services.pronostic_calculator import compute_recent_record

SEASON = "2025-2026"


def _team(**overrides) -> Team:
    defaults = dict(name="Boston Celtics", abbreviation="BOS")
    defaults.update(overrides)
    return Team(**defaults)


def _game(db_session, home, away, game_date, home_score, away_score):
    game = Game(
        season=SEASON,
        game_date=datetime.combine(game_date, datetime.min.time()),
        home_team_id=home.id,
        away_team_id=away.id,
        status=GameStatus.FINISHED,
        home_score=home_score,
        away_score=away_score,
    )
    db_session.add(game)
    db_session.flush()
    return game


def test_recent_record_counts_wins_and_losses(db_session):
    team = _team()
    opponent = _team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add_all([team, opponent])
    db_session.flush()

    base_date = date(2026, 1, 1)
    # team gagne à domicile (100-90), perd à l'extérieur (80-95)
    _game(db_session, team, opponent, base_date, 100, 90)
    _game(db_session, opponent, team, base_date + timedelta(days=2), 95, 80)

    record = compute_recent_record(db_session, team, before_date=base_date + timedelta(days=5))
    assert record.wins == 1
    assert record.losses == 1
    assert record.games_considered == 2


def test_recent_record_limited_to_window(db_session):
    team = _team()
    opponent = _team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add_all([team, opponent])
    db_session.flush()

    base_date = date(2026, 1, 1)
    for i in range(10):
        _game(db_session, team, opponent, base_date + timedelta(days=i), 100, 90)

    record = compute_recent_record(
        db_session, team, before_date=base_date + timedelta(days=20), window=7
    )
    assert record.games_considered == 7
    assert record.wins == 7


def test_recent_record_ignores_future_and_unfinished_games(db_session):
    team = _team()
    opponent = _team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add_all([team, opponent])
    db_session.flush()

    game_date = date(2026, 1, 10)
    _game(db_session, team, opponent, game_date, 100, 90)  # avant, compte
    # Match futur (après before_date) : ne doit pas compter.
    future_game = Game(
        season=SEASON,
        game_date=datetime.combine(date(2026, 1, 20), datetime.min.time()),
        home_team_id=team.id,
        away_team_id=opponent.id,
        status=GameStatus.FINISHED,
        home_score=100,
        away_score=90,
    )
    db_session.add(future_game)
    db_session.flush()

    record = compute_recent_record(db_session, team, before_date=date(2026, 1, 15))
    assert record.games_considered == 1


def test_recent_record_zero_when_no_games(db_session):
    team = _team()
    db_session.add(team)
    db_session.flush()

    record = compute_recent_record(db_session, team, before_date=date(2026, 1, 1))
    assert record.wins == 0
    assert record.losses == 0
    assert record.games_considered == 0
