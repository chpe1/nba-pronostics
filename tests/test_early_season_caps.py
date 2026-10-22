"""Deux plafonds de début de saison (2026-10-21) :
1. le bonus draft d'une équipe est plafonné à la valeur du rang 1 du barème (lue dans la config, jamais codée en dur) ;
2. tant que la note de base d'au moins une équipe vient de la saison précédente, l'étiquette de fiabilité ne dépasse
   pas « moyenne » (l'écart, lui, ne change pas)."""
from datetime import date, datetime, timedelta

import pytest

from app.models import Game, GameStatus, Player, ReliabilityLevel, Settings, Team
from app.services import pronostic_calculator as calc

SEASON = "2026-2027"
GAME_DAY = date(2026, 11, 20)


def _team(abbr: str, **pct) -> Team:
    defaults = dict(win_pct_home=0.5, win_pct_away=0.5, win_pct_home_prev_season=0.5, win_pct_away_prev_season=0.5)
    defaults.update(pct)
    return Team(name=f"Team {abbr}", abbreviation=abbr, **defaults)


def _settings(**overrides) -> Settings:
    defaults = dict(
        base_note_multiplier=100.0, per_impact_multiplier=0.0, back_to_back_penalty=0.0, three_in_four_penalty=0.0,
        mpg_threshold=15.0, player_sample_size_threshold=5, draft_bonus_config={"1": 8.0, "2": 7.0, "8": 7.0, "23": 5.0, "52": 1.0},
        reliability_threshold_low=7.0, reliability_threshold_high=30.0, transfer_impact_multiplier=0.0,
        no_prev_season_impact_multiplier=0.0,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _picks(db_session, team, *ranks):
    db_session.add_all([Player(name=f"Rookie {r} {team.abbreviation}", team_id=team.id, draft_pick=r) for r in ranks])
    db_session.flush()


# ----------------------------------------------------------------------------- 1) plafond du bonus draft


def test_single_pick_is_unchanged(db_session):
    team = _team("ATL")
    db_session.add(team)
    db_session.flush()
    _picks(db_session, team, 8)
    detail = calc.compute_draft_bonus_detail(db_session, team, _settings())
    assert (detail.raw_total, detail.total, detail.capped, detail.cap) == (7.0, 7.0, False, 8.0)
    assert [(e.rank, e.points) for e in detail.players] == [(8, 7.0)]


def test_sum_above_the_cap_is_capped_and_the_detail_shows_it(db_session):
    team = _team("ATL")
    db_session.add(team)
    db_session.flush()
    _picks(db_session, team, 8, 23, 52)  # 7 + 5 + 1 = 13 > 8 : le cas d'Atlanta
    detail = calc.compute_draft_bonus_detail(db_session, team, _settings())
    assert detail.raw_total == pytest.approx(13.0)  # le total AVANT plafonnement reste visible
    assert detail.cap == 8.0 and detail.capped is True
    assert detail.total == 8.0
    assert [(e.rank, e.points) for e in detail.players] == [(8, 7.0), (23, 5.0), (52, 1.0)]
    assert calc.compute_draft_bonus(db_session, team, _settings()) == 8.0


def test_sum_exactly_on_the_cap_is_not_reported_as_capped(db_session):
    team = _team("ATL")
    db_session.add(team)
    db_session.flush()
    _picks(db_session, team, 8, 52)  # 7 + 1 = 8 pile
    detail = calc.compute_draft_bonus_detail(db_session, team, _settings())
    assert (detail.raw_total, detail.total, detail.capped) == (8.0, 8.0, False)  # le plafond n'a rien retranché


def test_team_without_pick_gets_zero(db_session):
    team = _team("ATL")
    db_session.add(team)
    db_session.flush()
    detail = calc.compute_draft_bonus_detail(db_session, team, _settings())
    assert (detail.raw_total, detail.total, detail.capped, detail.players) == (0.0, 0.0, False, [])


def test_the_cap_follows_the_scale_and_is_never_hardcoded(db_session):
    team = _team("ATL")
    db_session.add(team)
    db_session.flush()
    _picks(db_session, team, 8, 23)
    low = _settings(draft_bonus_config={"1": 4.0, "8": 3.0, "23": 2.5})  # plafond 4
    high = _settings(draft_bonus_config={"1": 20.0, "8": 7.0, "23": 5.0})  # plafond 20 : 12 passe tel quel
    assert calc.compute_draft_bonus_detail(db_session, team, low).total == 4.0
    assert calc.compute_draft_bonus_detail(db_session, team, low).cap == 4.0
    detail = calc.compute_draft_bonus_detail(db_session, team, high)
    assert (detail.cap, detail.total, detail.capped) == (20.0, 12.0, False)


def test_without_a_rank_one_entry_there_is_no_cap(db_session):
    team = _team("ATL")
    db_session.add(team)
    db_session.flush()
    _picks(db_session, team, 8, 23)
    detail = calc.compute_draft_bonus_detail(db_session, team, _settings(draft_bonus_config={"8": 7.0, "23": 5.0}))
    assert (detail.cap, detail.total, detail.capped) == (None, 12.0, False)


def test_team_note_breakdown_exposes_the_detail_for_the_diagnostic(db_session):
    team = _team("ATL")
    db_session.add(team)
    db_session.flush()
    _picks(db_session, team, 8, 23, 52)
    breakdown = calc.compute_team_note(db_session, team, GAME_DAY, SEASON, is_home=True, settings=_settings())
    assert breakdown.draft_bonus == 8.0  # ce qui entre dans la note
    as_dict = calc.breakdown_to_dict(breakdown)
    assert as_dict["draft_bonus"] == 8.0
    assert as_dict["draft_bonus_raw"] == pytest.approx(13.0)
    assert as_dict["draft_bonus_cap"] == 8.0 and as_dict["draft_bonus_capped"] is True
    assert [(p["rank"], p["points"]) for p in as_dict["draft_players"]] == [(8, 7.0), (23, 5.0), (52, 1.0)]


def test_detail_is_empty_once_the_team_is_out_of_early_season(db_session):
    team, other = _team("ATL"), _team("ORL")
    db_session.add_all([team, other])
    db_session.flush()
    _picks(db_session, team, 8, 23)
    _play_ten_games(db_session, team, other)
    breakdown = calc.compute_team_note(db_session, team, GAME_DAY, SEASON, is_home=True, settings=_settings())
    assert breakdown.in_early_season is False
    assert (breakdown.draft_bonus, breakdown.draft_bonus_raw, breakdown.draft_players, breakdown.draft_bonus_capped) == (0.0, 0.0, [], False)


# ----------------------------------------------------------------------------- 2) fiabilité plafonnée en début de saison


def _play_ten_games(db_session, team, opponent):
    for i in range(10):
        db_session.add(Game(
            season=SEASON, game_date=datetime(2026, 10, 22) + timedelta(days=i), home_team_id=team.id,
            away_team_id=opponent.id, status=GameStatus.FINISHED, home_score=100, away_score=90))
    db_session.flush()


def _matchup(db_session, home, away):
    game = Game(season=SEASON, game_date=datetime.combine(GAME_DAY, datetime.min.time()).replace(hour=19),
                home_team_id=home.id, away_team_id=away.id, status=GameStatus.SCHEDULED)
    db_session.add(game)
    db_session.flush()
    return calc.compute_matchup(db_session, game, _settings())


def _teams(db_session, home_pct, away_pct):
    """Écart de notes = (home_pct - away_pct) x 100, à la saison précédente comme à la saison en cours."""
    home = _team("HOM", win_pct_home=home_pct, win_pct_home_prev_season=home_pct)
    away = _team("AWY", win_pct_away=away_pct, win_pct_away_prev_season=away_pct)
    third = _team("OTH")
    db_session.add_all([home, away, third])
    db_session.flush()
    return home, away, third


def test_gap_above_30_in_early_season_is_capped_to_moyenne_but_the_gap_is_untouched(db_session):
    home, away, _ = _teams(db_session, 0.9, 0.2)  # écart 70
    result = _matchup(db_session, home, away)
    assert result.spread == pytest.approx(70.0)  # l'écart affiché ne change pas
    assert result.reliability_uncapped == ReliabilityLevel.FORTE
    assert result.reliability == ReliabilityLevel.MOYENNE and result.reliability_capped is True
    assert calc.reliability_cap_to_dict(result) == {"capped": True, "uncapped": "forte", "reason": "early_season"}


def test_same_gap_outside_early_season_keeps_forte(db_session):
    home, away, third = _teams(db_session, 0.9, 0.2)
    _play_ten_games(db_session, home, third)
    _play_ten_games(db_session, away, third)
    result = _matchup(db_session, home, away)
    assert result.spread == pytest.approx(70.0)
    assert result.reliability == ReliabilityLevel.FORTE and result.reliability_capped is False
    assert calc.reliability_cap_to_dict(result) == {"capped": False, "uncapped": "forte", "reason": None}


def test_small_and_middle_gaps_are_never_touched_in_early_season(db_session):
    home, away, _ = _teams(db_session, 0.55, 0.5)  # écart 5 : faible
    assert _matchup(db_session, home, away).reliability == ReliabilityLevel.FAIBLE
    home2, away2 = _team("HO2", win_pct_home_prev_season=0.7), _team("AW2", win_pct_away_prev_season=0.5)
    db_session.add_all([home2, away2])
    db_session.flush()
    result = _matchup(db_session, home2, away2)  # écart 20 : moyenne
    assert result.reliability == ReliabilityLevel.MOYENNE and result.reliability_capped is False


def test_when_only_one_team_is_past_the_threshold_the_label_is_still_capped(db_session):
    # Le domicile a joué 10 matchs (note de base de la saison en cours), l'extérieur aucun (saison précédente) :
    # l'écart compare une note de cette saison à une note de l'an dernier -> étiquette plafonnée.
    home, away, third = _teams(db_session, 0.9, 0.2)
    _play_ten_games(db_session, home, third)
    result = _matchup(db_session, home, away)
    assert (result.home.in_early_season, result.away.in_early_season) == (False, True)
    assert result.reliability_uncapped == ReliabilityLevel.FORTE
    assert result.reliability == ReliabilityLevel.MOYENNE and result.reliability_capped is True


def test_save_prediction_stores_the_label_and_the_reason(db_session):
    from app.models import Prediction

    home, away, _ = _teams(db_session, 0.9, 0.2)
    game = Game(season=SEASON, game_date=datetime(2026, 12, 25, 19), home_team_id=home.id, away_team_id=away.id,
                status=GameStatus.SCHEDULED)
    db_session.add(game)
    db_session.flush()
    calc.save_prediction(db_session, game, _settings())
    stored = db_session.query(Prediction).filter(Prediction.game_id == game.id).one()
    assert stored.reliability == ReliabilityLevel.MOYENNE
    assert stored.breakdown["reliability_cap"] == {"capped": True, "uncapped": "forte", "reason": "early_season"}
    assert stored.spread == pytest.approx(70.0)
