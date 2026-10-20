from datetime import date, datetime, timedelta

import pytest

from app.models import Game, GameStatus, Prediction, ReliabilityLevel, Team
from app.services import prediction_accuracy as acc
from app.services.nba_calendar import game_start_utc

# Coup d'envoi 19:00 heure de New York le 2026-10-20 = 23:00 UTC (EDT, UTC-4).
TIPOFF_ET = datetime(2026, 10, 20, 19, 0)
TIPOFF_UTC = datetime(2026, 10, 20, 23, 0)

_counter = {"n": 0}


@pytest.fixture
def teams(db_session):
    home = Team(name="Boston Celtics", abbreviation="BOS")
    away = Team(name="Miami Heat", abbreviation="MIA")
    db_session.add_all([home, away])
    db_session.flush()
    _counter["n"] = 0
    return home, away


def make(db_session, teams, *, scores=(110, 100), status=GameStatus.FINISHED, predicted="home",
         reliability=ReliabilityLevel.MOYENNE, spread=10.0, computed_before_kickoff=timedelta(hours=3),
         with_prediction=True):
    """Chaque appel crée un match le jour suivant (contrainte UNIQUE date/équipes) ; `computed_before_kickoff`
    est l'avance du calcul sur le coup d'envoi (négative = calculé APRÈS)."""
    home, away = teams
    _counter["n"] += 1
    shift = timedelta(days=_counter["n"])
    game = Game(season="2026-2027", game_date=TIPOFF_ET + shift, home_team_id=home.id, away_team_id=away.id,
                status=status, home_score=scores[0] if scores else None, away_score=scores[1] if scores else None)
    db_session.add(game)
    db_session.flush()
    if with_prediction:
        db_session.add(Prediction(
            game_id=game.id, home_team_note=60.0, away_team_note=50.0,
            predicted_winner_team_id=home.id if predicted == "home" else away.id,
            spread=spread, reliability=reliability, breakdown={},
            computed_at=TIPOFF_UTC + shift - computed_before_kickoff,
        ))
        db_session.flush()
    return game


def test_kickoff_is_converted_from_new_york_wall_clock_to_utc():
    assert game_start_utc(TIPOFF_ET) == TIPOFF_UTC
    assert game_start_utc(datetime(2026, 12, 1, 19, 0)) == datetime(2026, 12, 2, 0, 0)  # hiver : UTC-5


def test_measurable_match_counts_and_favorite_win(db_session, teams):
    make(db_session, teams)
    r = acc.compute_prediction_accuracy(db_session)
    assert (r.measured, r.excluded_total, r.favorite_wins, r.favorite_win_rate) == (1, 0, 1, 1.0)


def test_finished_game_without_prediction_is_excluded_with_its_reason(db_session, teams):
    make(db_session, teams, with_prediction=False)
    r = acc.compute_prediction_accuracy(db_session)
    assert r.measured == 0 and r.excluded == {acc.NO_PREDICTION: 1} and r.excluded_total == 1


def test_prediction_without_result_is_excluded(db_session, teams):
    make(db_session, teams, status=GameStatus.SCHEDULED, scores=None)
    make(db_session, teams, status=GameStatus.POSTPONED, scores=None)
    make(db_session, teams, status=GameStatus.FINISHED, scores=None)  # terminé sans score
    r = acc.compute_prediction_accuracy(db_session)
    assert r.measured == 0
    assert r.excluded == {acc.NOT_FINISHED: 2, acc.FINISHED_WITHOUT_SCORE: 1}


def test_scheduled_game_without_prediction_does_not_exist_for_the_measure(db_session, teams):
    make(db_session, teams, status=GameStatus.SCHEDULED, scores=None, with_prediction=False)
    r = acc.compute_prediction_accuracy(db_session)
    assert r.measured == 0 and r.excluded_total == 0


def test_prediction_computed_after_kickoff_is_excluded_and_counted(db_session, teams):
    make(db_session, teams, computed_before_kickoff=timedelta(minutes=-1))  # 1 min APRÈS
    make(db_session, teams, computed_before_kickoff=timedelta(0))  # pile à l'heure : pas strictement avant
    make(db_session, teams, computed_before_kickoff=timedelta(minutes=1))  # 1 min avant : mesuré
    r = acc.compute_prediction_accuracy(db_session)
    assert r.measured == 1 and r.excluded == {acc.PREDICTED_AFTER_KICKOFF: 2}


def test_kickoff_comparison_uses_new_york_time_not_the_naive_wall_clock(db_session, teams):
    # Calculé 3 h avant : 20:00 UTC, soit APRÈS « 19:00 » lu comme un UTC naïf, mais AVANT 23:00 UTC (19:00 ET).
    make(db_session, teams)
    assert acc.compute_prediction_accuracy(db_session).measured == 1


def test_equal_scores_are_excluded_never_counted_as_a_win(db_session, teams):
    make(db_session, teams, scores=(100, 100))
    r = acc.compute_prediction_accuracy(db_session)
    assert r.measured == 0 and r.excluded == {acc.TIED_SCORES: 1}


def test_away_favorite_and_margin_from_the_favorites_point_of_view(db_session, teams):
    make(db_session, teams, scores=(100, 110), predicted="away", spread=-8.0)  # favori visiteur, gagne de 10
    make(db_session, teams, scores=(105, 100), predicted="away", spread=-8.0)  # favori visiteur, perd de 5
    r = acc.compute_prediction_accuracy(db_session)
    level = r.by_reliability[ReliabilityLevel.MOYENNE]
    assert (r.favorite_wins, r.measured) == (1, 2)
    assert level.mean_margin_for_favorite == pytest.approx((10 - 5) / 2)
    assert level.mean_absolute_margin == pytest.approx(7.5)


def test_breakdown_by_reliability_with_counts_and_independent_flags(db_session, teams):
    for _ in range(3):
        make(db_session, teams, reliability=ReliabilityLevel.FORTE, scores=(120, 100))
    for i in range(5):
        make(db_session, teams, reliability=ReliabilityLevel.FAIBLE, scores=(100, 105) if i < 2 else (105, 100))
    r = acc.compute_prediction_accuracy(db_session, min_sample_size=4)
    forte = r.by_reliability[ReliabilityLevel.FORTE]
    faible = r.by_reliability[ReliabilityLevel.FAIBLE]
    moyenne = r.by_reliability[ReliabilityLevel.MOYENNE]
    assert (forte.measured, forte.favorite_wins, forte.favorite_win_rate) == (3, 3, 1.0)
    assert (faible.measured, faible.favorite_wins) == (5, 3)
    assert (moyenne.measured, moyenne.favorite_win_rate, moyenne.mean_margin_for_favorite) == (0, None, None)
    # même total, drapeaux différents : 8 au total >= 4, mais 3 en forte confiance < 4
    assert r.measured == 8 and r.insufficient_sample is False
    assert forte.insufficient_sample is True and faible.insufficient_sample is False and moyenne.insufficient_sample is True


def test_sample_below_threshold_is_flagged_on_the_total(db_session, teams):
    for _ in range(3):
        make(db_session, teams)
    assert acc.compute_prediction_accuracy(db_session).insufficient_sample is True
    assert acc.compute_prediction_accuracy(db_session, min_sample_size=3).insufficient_sample is False
    assert acc.MIN_SAMPLE_SIZE == 30


def test_period_filter_is_inclusive_on_the_game_date(db_session, teams):
    for _ in range(3):
        make(db_session, teams)  # 21, 22, 23 octobre
    r = acc.compute_prediction_accuracy(db_session, date_from=date(2026, 10, 22), date_to=date(2026, 10, 22))
    assert r.measured == 1 and (r.date_from, r.date_to) == (date(2026, 10, 22), date(2026, 10, 22))
    assert acc.compute_prediction_accuracy(db_session, date_from=date(2026, 10, 24)).measured == 0


def test_rank_correlation_perfect_inverse_and_undefined(db_session, teams):
    for spread, margin in ((2.0, 3), (8.0, 9), (15.0, 20), (25.0, 30)):
        make(db_session, teams, spread=spread, scores=(100 + margin, 100))
    assert acc.compute_prediction_accuracy(db_session).rank_correlation == pytest.approx(1.0)
    assert acc.spearman([1.0, 2.0, 3.0], [3.0, 2.0, 1.0]) == pytest.approx(-1.0)
    assert acc.spearman([1.0, 2.0], [5.0, 5.0]) is None  # série constante
    assert acc.spearman([1.0], [1.0]) is None
    assert acc.spearman([1.0, 2.0, 2.0, 4.0], [1.0, 3.0, 2.0, 9.0]) == pytest.approx(0.948683, abs=1e-5)  # ex æquo


def test_it_never_writes(db_session, teams):
    game = make(db_session, teams)
    pred = db_session.query(Prediction).filter_by(game_id=game.id).one()
    before = (pred.computed_at, pred.spread, game.status, game.home_score)
    acc.compute_prediction_accuracy(db_session)
    db_session.refresh(pred)
    db_session.refresh(game)
    assert (pred.computed_at, pred.spread, game.status, game.home_score) == before
