"""Crédit des joueurs présents sans ligne N-1 (2026-10-22) : composante distincte, symétrique de la pénalité des
absents, limitée à la fenêtre de début de saison."""
from datetime import date, datetime, timedelta

import pytest

from app.models import Game, GameStatus, InjuryStatus, Player, PreviousSeasonPlayerStat, Settings, Team
from app.services import pronostic_calculator as calc

SEASON = "2026-2027"
PREV = "2025-2026"
GAME_DAY = date(2026, 11, 20)


def _settings(**overrides) -> Settings:
    defaults = dict(
        base_note_multiplier=100.0, per_impact_multiplier=0.4, back_to_back_penalty=0.0, three_in_four_penalty=0.0,
        mpg_threshold=15.0, player_sample_size_threshold=5, draft_bonus_config={"1": 8.0},
        reliability_threshold_low=7.0, reliability_threshold_high=30.0, transfer_impact_multiplier=0.0,
        no_prev_season_impact_multiplier=0.4,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _team(db_session, abbr="IND") -> Team:
    team = Team(name=f"Team {abbr}", abbreviation=abbr, win_pct_home=0.5, win_pct_away=0.5,
                win_pct_home_prev_season=0.5, win_pct_away_prev_season=0.5)
    db_session.add(team)
    db_session.flush()
    return team


def _player(db_session, team, name="Tyrese Haliburton", **kw) -> Player:
    values = dict(per=19.5, mpg=33.0, games_played_this_season=0)
    values.update(kw)
    player = Player(name=name, team_id=team.id, **values)
    db_session.add(player)
    db_session.flush()
    return player


def _detail(db_session, team, **settings_kw):
    return calc.compute_no_prev_season_credit_detail(db_session, team, _settings(**settings_kw), PREV)


def test_player_without_prev_line_is_credited_per_times_multiplier(db_session):
    team = _team(db_session)
    _player(db_session, team)
    detail = _detail(db_session, team)
    assert [(e.name, e.per, e.mpg) for e in detail.players] == [("Tyrese Haliburton", 19.5, 33.0)]
    assert detail.players[0].points == pytest.approx(19.5 * 0.4)
    assert detail.total == pytest.approx(7.8)


def test_player_with_a_prev_season_line_is_not_credited(db_session):
    team = _team(db_session)
    _player(db_session, team)
    db_session.add(PreviousSeasonPlayerStat(season=PREV, player_name="Tyrese Haliburton", team_abbreviation="IND", per=19.0, mpg=32.0))
    db_session.flush()
    assert _detail(db_session, team).players == []


def test_player_below_mpg_threshold_is_not_credited(db_session):
    team = _team(db_session)
    _player(db_session, team, mpg=15.0)  # le seuil est strict : 15 n'est pas « au-dessus »
    assert _detail(db_session, team).players == []


@pytest.mark.parametrize("status", [InjuryStatus.OUT, InjuryStatus.DOUBTFUL])
def test_injured_player_is_not_credited(db_session, status):
    team = _team(db_session)
    _player(db_session, team, injury_status=status)
    assert _detail(db_session, team).players == []


def test_questionable_player_is_credited(db_session):
    team = _team(db_session)
    _player(db_session, team, injury_status=InjuryStatus.QUESTIONABLE)
    detail = _detail(db_session, team)
    assert [(e.name, e.injury_status) for e in detail.players] == [("Tyrese Haliburton", "questionable")]


def test_player_with_zero_per_is_not_credited(db_session):
    team = _team(db_session)
    _player(db_session, team, per=0.0)
    assert _detail(db_session, team).players == []


def test_drafted_player_is_not_credited_the_draft_bonus_stands_in(db_session):
    team = _team(db_session)
    _player(db_session, team, name="Rookie", draft_pick=3)
    assert _detail(db_session, team).players == []


def test_team_without_any_concerned_player(db_session):
    team = _team(db_session)
    detail = _detail(db_session, team)
    assert (detail.players, detail.total) == ([], 0.0)


def test_player_of_another_team_or_inactive_is_not_credited(db_session):
    team, other = _team(db_session), _team(db_session, "BOS")
    _player(db_session, other)
    _player(db_session, team, name="Retired", is_active=False)
    assert _detail(db_session, team).players == []


def test_multiplier_zero_cancels_everything(db_session):
    team = _team(db_session)
    _player(db_session, team)
    detail = _detail(db_session, team, no_prev_season_impact_multiplier=0.0)
    assert detail.total == 0.0
    note = calc.compute_team_note(db_session, team, GAME_DAY, SEASON, True, _settings(no_prev_season_impact_multiplier=0.0))
    assert note.no_prev_season_credit == 0.0


def _note(db_session, team, **settings_kw):
    return calc.compute_team_note(db_session, team, GAME_DAY, SEASON, True, _settings(**settings_kw))


def test_credit_enters_the_final_note_and_the_breakdown(db_session):
    team = _team(db_session)
    _player(db_session, team)
    without = _note(db_session, team, no_prev_season_impact_multiplier=0.0)
    with_credit = _note(db_session, team)
    assert with_credit.final_note - without.final_note == pytest.approx(7.8)
    assert with_credit.no_prev_season_credit == pytest.approx(7.8)
    as_dict = calc.breakdown_to_dict(with_credit)
    assert as_dict["no_prev_season_credit"] == pytest.approx(7.8)
    assert as_dict["no_prev_season_players"] == [
        {"name": "Tyrese Haliburton", "per": 19.5, "mpg": 33.0, "injury_status": "healthy", "points": pytest.approx(7.8)}
    ]


def test_credit_is_independent_of_the_transfer_multiplier(db_session):
    team = _team(db_session)
    _player(db_session, team)
    note = _note(db_session, team, transfer_impact_multiplier=0.0)
    assert note.transfer_adjustment == 0.0 and note.no_prev_season_credit == pytest.approx(7.8)


def test_outside_early_season_window_nothing_is_credited(db_session):
    team = _team(db_session)
    opponent = _team(db_session, "BOS")
    _player(db_session, team)
    for i in range(calc.EARLY_SEASON_GAME_THRESHOLD):
        db_session.add(Game(
            season=SEASON, game_date=datetime(2026, 10, 25) + timedelta(days=i), home_team_id=team.id,
            away_team_id=opponent.id, status=GameStatus.FINISHED, home_score=100, away_score=90,
        ))
    db_session.flush()
    note = _note(db_session, team)
    assert note.in_early_season is False
    assert (note.no_prev_season_credit, note.no_prev_season_players) == (0.0, [])
