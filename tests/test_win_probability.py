"""Probabilité de victoire (modèle d'écart de points), calculée à côté de la note.

Trois familles de garanties :
  1. la formule (réglages de l'étude, version dérivée des réglages) ;
  2. ANTI-FUITE : seuls les matchs TERMINÉS, avec score, de la même saison, d'un jour STRICTEMENT antérieur
     comptent ; rien de ce qui se passe le jour du match ou après ne change une probabilité ;
  3. la note n'est pas touchée, la protection « match commencé » vaut aussi pour la probabilité, et un écart
     N-1 inconnu n'est jamais remplacé par 0.
"""
import math
from datetime import date, datetime, timedelta

import pytest

from app.models import Game, GameStatus, Prediction, Settings, Team
from app.services import nba_calendar
from app.services import pronostic_calculator as calc
from app.services import win_probability as wp

SEASON = "2026-2027"
DAY = date(2026, 11, 10)


def _settings() -> Settings:
    return Settings(
        base_note_multiplier=1.0, per_impact_multiplier=1.0, back_to_back_penalty=3.0, three_in_four_penalty=5.0,
        mpg_threshold=15.0, player_sample_size_threshold=5, draft_bonus_config={},
        reliability_threshold_low=7.0, reliability_threshold_high=30.0, transfer_impact_multiplier=0.0,
        current_season=SEASON,
    )


@pytest.fixture()
def teams(db_session):
    made = {}
    for abbr, name, prev in (("BOS", "Boston Celtics", 7.70), ("DET", "Detroit Pistons", 8.16),
                             ("WAS", "Washington Wizards", -11.98), ("OKC", "Oklahoma City Thunder", 11.15)):
        t = Team(name=name, abbreviation=abbr, win_pct_home_prev_season=0.6, win_pct_away_prev_season=0.4,
                 point_diff_prev_season=prev)
        db_session.add(t)
        made[abbr] = t
    db_session.add(_settings())
    db_session.commit()
    return made


def _game(db, home, away, day, status=GameStatus.SCHEDULED, score=None, season=SEASON, hour=19):
    g = Game(season=season, game_date=datetime.combine(day, datetime.min.time()) + timedelta(hours=hour),
             home_team_id=home.id, away_team_id=away.id, status=status)
    if score:
        g.home_score, g.away_score = score
    db.add(g)
    db.commit()
    return g


# ---------- 1. formule et version ----------

def test_version_is_derived_from_the_settings():
    assert wp.MODEL_VERSION == "ecart1/w=8/c=0.7/hca=1.84/sigma=14.13"
    assert wp.model_version(w=6) != wp.MODEL_VERSION  # un réglage modifié = une autre version, sans y penser


def test_first_game_uses_the_reduced_previous_season_only(db_session, teams):
    g = _game(db_session, teams["DET"], teams["BOS"], DAY)
    r = wp.compute_win_probability(db_session, g)
    expected = 0.7 * 8.16 - 0.7 * 7.70 + 1.84  # n = 0 : force = c × écart N-1
    assert r.expected_margin == pytest.approx(expected)
    assert r.home_win_probability == pytest.approx(0.5 * (1 + math.erf(expected / 14.13 / math.sqrt(2))))
    assert (r.home.games_used, r.away.games_used) == (0, 0)


def test_season_games_enter_with_weight_one_each(db_session, teams):
    det, bos, was = teams["DET"], teams["BOS"], teams["WAS"]
    _game(db_session, det, was, DAY - timedelta(days=3), GameStatus.FINISHED, (120, 100))  # DET +20
    _game(db_session, was, det, DAY - timedelta(days=2), GameStatus.FINISHED, (110, 105))  # DET -5
    g = _game(db_session, det, bos, DAY)
    r = wp.compute_win_probability(db_session, g)
    assert r.home.games_used == 2 and r.home.margin_sum == 15
    assert r.home.force == pytest.approx((8 * 0.7 * 8.16 + 15) / (8 + 2))
    assert r.away.games_used == 0


# ---------- 2. anti-fuite ----------

def _probability(db, game):
    return wp.compute_win_probability(db, game).home_win_probability


def test_same_day_and_later_games_never_count(db_session, teams):
    det, bos, was, okc = teams["DET"], teams["BOS"], teams["WAS"], teams["OKC"]
    g = _game(db_session, det, bos, DAY, hour=19)
    before = _probability(db_session, g)
    # le même jour, plus tôt (même jour = exclu, quel que soit l'horaire) et plus tard, puis les jours suivants
    _game(db_session, det, was, DAY, GameStatus.FINISHED, (140, 80), hour=12)
    _game(db_session, okc, bos, DAY, GameStatus.FINISHED, (140, 80), hour=22)
    _game(db_session, was, det, DAY + timedelta(days=1), GameStatus.FINISHED, (150, 70))
    _game(db_session, bos, okc, DAY + timedelta(days=30), GameStatus.FINISHED, (60, 130))
    assert _probability(db_session, g) == before


def test_only_finished_games_with_a_score_of_the_same_season_count(db_session, teams):
    det, bos, was = teams["DET"], teams["BOS"], teams["WAS"]
    g = _game(db_session, det, bos, DAY)
    before = _probability(db_session, g)
    earlier = DAY - timedelta(days=5)
    _game(db_session, det, was, earlier, GameStatus.SCHEDULED, (130, 90))           # pas terminé (score saisi)
    _game(db_session, det, was, earlier - timedelta(days=1), GameStatus.POSTPONED)  # reporté
    _game(db_session, was, det, earlier - timedelta(days=2), GameStatus.FINISHED)   # terminé SANS score
    _game(db_session, det, was, earlier - timedelta(days=3), GameStatus.FINISHED, (130, 90), season="2025-2026")
    r = wp.compute_win_probability(db_session, g)
    assert r.home.games_used == 0 and r.home_win_probability == before


def test_rewriting_every_result_from_the_game_day_on_changes_nothing(db_session, teams):
    """Le test de l'étude, transposé : tous les résultats du jour du match et après sont réécrits au hasard ;
    aucune probabilité d'un match de ce jour ou d'avant ne bouge -- et celles d'après, si (le test vit)."""
    import random

    rng = random.Random(7)
    t = list(teams.values())
    games = []
    for k in range(40):
        day = DAY - timedelta(days=20) + timedelta(days=k)
        home, away = rng.sample(t, 2)
        status = GameStatus.FINISHED if day < DAY + timedelta(days=10) else GameStatus.SCHEDULED
        score = (rng.randint(80, 140), rng.randint(80, 140)) if status == GameStatus.FINISHED else None
        games.append(_game(db_session, home, away, day, status, score))
    base = {g.id: _probability(db_session, g) for g in games}
    for g in games:
        if g.game_date_only >= DAY and g.status == GameStatus.FINISHED:
            g.home_score, g.away_score = rng.randint(60, 160), rng.randint(60, 160)
    db_session.commit()
    after = {g.id: _probability(db_session, g) for g in games}
    assert all(after[g.id] == base[g.id] for g in games if g.game_date_only <= DAY)
    assert any(after[g.id] != base[g.id] for g in games if g.game_date_only > DAY)


# ---------- 3. vide n'est jamais 0, note intacte, protection ----------

def test_unknown_previous_season_point_diff_gives_no_probability(db_session, teams):
    teams["BOS"].point_diff_prev_season = None
    db_session.commit()
    g = _game(db_session, teams["DET"], teams["BOS"], DAY)
    r = wp.compute_win_probability(db_session, g)
    assert r.home_win_probability is None and r.expected_margin is None
    assert r.missing_prev_point_diff == [teams["BOS"].id]
    assert r.away.force is None and r.home.force is not None


def test_saved_prediction_stores_probability_version_and_inputs(db_session, teams):
    g = _game(db_session, teams["DET"], teams["BOS"], DAY)
    p = calc.save_prediction(db_session, g, db_session.query(Settings).one())
    assert p.probability_model_version == wp.MODEL_VERSION
    assert p.home_win_probability == pytest.approx(_probability(db_session, g))
    assert p.probability_inputs["params"] == {"w": 8.0, "c": 0.7, "home_advantage": 1.84, "sigma": 14.13}
    assert p.probability_inputs["home"]["games_used"] == 0
    assert p.probability_inputs["away"]["prev_point_diff"] == 7.70


def test_the_note_is_identical_with_or_without_the_probability_inputs(db_session, teams):
    """Règle absolue : la note ne dépend ni de l'écart N-1 ni de la probabilité."""
    g = _game(db_session, teams["DET"], teams["BOS"], DAY)
    s = db_session.query(Settings).one()
    with_diff = calc.compute_matchup(db_session, g, s)
    teams["DET"].point_diff_prev_season = -30.0
    teams["BOS"].point_diff_prev_season = None
    db_session.commit()
    without = calc.compute_matchup(db_session, g, s)
    assert (with_diff.home.final_note, with_diff.away.final_note, with_diff.spread, with_diff.reliability) == (
        without.home.final_note, without.away.final_note, without.spread, without.reliability)


def test_a_started_game_keeps_its_pre_game_probability(db_session, teams, monkeypatch):
    g = _game(db_session, teams["DET"], teams["BOS"], DAY)
    s = db_session.query(Settings).one()
    p = calc.save_prediction(db_session, g, s)
    db_session.commit()
    frozen = (p.home_win_probability, p.expected_margin, p.probability_inputs)
    teams["DET"].point_diff_prev_season = -10.0
    db_session.commit()
    monkeypatch.setattr(nba_calendar, "utc_now", lambda: nba_calendar.game_start_utc(g.game_date))
    with pytest.raises(calc.GameAlreadyStartedError):
        calc.save_prediction(db_session, g, s)
    db_session.rollback()
    stored = db_session.query(Prediction).filter_by(game_id=g.id).one()
    assert (stored.home_win_probability, stored.expected_margin, stored.probability_inputs) == frozen


# ---------- API ----------

def test_today_route_masks_the_probability_of_a_far_future_game(client, db_session, teams, monkeypatch):
    from app.api import predictions as api

    far = date(2026, 12, 25)
    g = _game(db_session, teams["DET"], teams["BOS"], far)
    calc.save_prediction(db_session, g, db_session.query(Settings).one())
    db_session.commit()
    monkeypatch.setattr(api, "current_nba_date", lambda: far - timedelta(days=10))
    body = client.get("/api/predictions/today", params={"date": far.isoformat()}).json()
    pred = body[0]["prediction"]
    assert pred["is_upcoming"] is True
    assert pred["home_win_probability"] is None and pred["probability_inputs"] is None
    monkeypatch.setattr(api, "current_nba_date", lambda: far)
    pred = client.get("/api/predictions/today", params={"date": far.isoformat()}).json()[0]["prediction"]
    assert pred["home_win_probability"] == pytest.approx(_probability(db_session, g))
    assert pred["probability_model_version"] == wp.MODEL_VERSION


def test_admin_can_set_clear_and_is_refused_an_absurd_point_diff(client, db_session, teams, auth_headers):
    tid = teams["BOS"].id
    r = client.patch(f"/api/teams/{tid}", json={"point_diff_prev_season": -4.5}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["point_diff_prev_season"] == -4.5
    r = client.patch(f"/api/teams/{tid}", json={"point_diff_prev_season": 1115}, headers=auth_headers)
    assert r.status_code == 422
    r = client.patch(f"/api/teams/{tid}", json={"point_diff_prev_season": None}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["point_diff_prev_season"] is None
    r = client.patch(f"/api/teams/{tid}", json={"win_pct_home": 0.5}, headers=auth_headers)
    assert r.json()["point_diff_prev_season"] is None  # un autre champ modifié ne la remplit pas
