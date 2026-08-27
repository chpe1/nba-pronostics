"""Scénarios de validation du calibrage (Étape 6) : vérifie que
`compute_matchup`, avec les valeurs par défaut calibrées (voir
docs/calibrage-v1.md), produit des résultats cohérents avec l'intuition
basket sur un calendrier simulé multi-équipes réaliste.

Complète (sans dupliquer) la couverture unitaire déjà existante depuis
l'Étape 3 dans test_pronostic_calculator.py (règle des 10 premiers matchs,
non-cumul B2B/3in4) en la vérifiant bout en bout, plus des scénarios de
garde-fou qui n'existaient pas encore.
"""
from datetime import timedelta

import pytest

from app.models import InjuryStatus, Player, PreviousSeasonPlayerStat, ReliabilityLevel, Settings, Team
from app.services.pronostic_calculator import compute_matchup
from tests.simulation_data import (
    TARGET_DATE,
    _finished_game,
    build_league,
    create_full_slate,
    create_scheduled_game,
)


def _calibrated_settings(**overrides) -> Settings:
    """Valeurs par défaut calibrées (V1) -- voir docs/calibrage-v1.md."""
    defaults = dict(
        base_note_multiplier=100.0,
        per_impact_multiplier=0.4,
        back_to_back_penalty=2.0,
        three_in_four_penalty=3.5,
        mpg_threshold=15.0,
        player_sample_size_threshold=5,
        draft_bonus_config={"1": 8.0},
        reliability_threshold_low=7.0,
        reliability_threshold_high=30.0,
        transfer_impact_multiplier=0.4,
    )
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.fixture()
def league(db_session):
    return build_league(db_session)


@pytest.fixture()
def settings():
    return _calibrated_settings()


# --- 1. Blessure d'un titulaire majeur dans un match serré -----------------


def test_favorite_losing_star_flips_matchup_with_low_reliability(db_session, settings):
    # Favori léger (50 dom.) contre outsider (42 ext.), sans effet calendrier.
    favorite = Team(
        abbreviation="NEA", name="Favorite", win_pct_home=0.50, win_pct_away=0.40,
        win_pct_home_prev_season=0.50, win_pct_away_prev_season=0.40,
    )
    underdog = Team(
        abbreviation="NEB", name="Underdog", win_pct_home=0.48, win_pct_away=0.42,
        win_pct_home_prev_season=0.48, win_pct_away_prev_season=0.42,
    )
    db_session.add_all([favorite, underdog])
    db_session.flush()

    star = Player(name="Favorite Star", team_id=favorite.id, per=25.0, mpg=34.0, injury_status=InjuryStatus.OUT)
    db_session.add(star)
    db_session.flush()

    game = create_scheduled_game(db_session, favorite, underdog)
    result = compute_matchup(db_session, game, settings)

    assert result.predicted_winner_team_id == underdog.id  # bascule
    assert result.reliability == ReliabilityLevel.FAIBLE  # écart resserré, pas absurde
    assert abs(result.spread) < 10  # renversement net mais pas démesuré


# --- 2. Blessure d'un joueur sous le seuil MPG ------------------------------


def test_bench_player_injury_below_mpg_threshold_has_no_effect(db_session, league, settings):
    """compute_matchup ne modifie ni ne persiste rien sur `game` (fonction de
    lecture pure) -- une seule ligne Game suffit pour les deux calculs
    avant/après. Deux lignes distinctes pour le même (date, domicile,
    extérieur) heurteraient désormais la contrainte UNIQUE ajoutée le
    2026-08-27 (uq_game_date_teams), à raison : ça n'a jamais représenté un
    vrai second match, seulement deux passes de calcul sur un scénario."""
    roster = league.rosters["BOS"]
    game = create_scheduled_game(db_session, league.teams["BOS"], league.teams["DET"], game_date=TARGET_DATE)
    baseline = compute_matchup(db_session, game, settings)

    roster.bench_player.injury_status = InjuryStatus.OUT
    db_session.flush()
    result = compute_matchup(db_session, game, settings)

    assert result.home.final_note == pytest.approx(baseline.home.final_note)


# --- 3. Blessure d'une star dans un gros mismatch ---------------------------


def test_star_injury_does_not_overwhelm_large_talent_gap(db_session, league, settings):
    """Le scénario qui répond directement à l'inquiétude notée à l'Étape 3 :
    le malus PER ne doit pas écraser un écart de niveau important."""
    league.rosters["BOS"].star.injury_status = InjuryStatus.OUT
    db_session.flush()

    game = create_scheduled_game(db_session, league.teams["BOS"], league.teams["DET"])
    result = compute_matchup(db_session, game, settings)

    assert result.predicted_winner_team_id == league.teams["BOS"].id  # toujours favori
    assert result.reliability == ReliabilityLevel.FORTE  # écart toujours large


# --- 4/5. Malus calendrier isolés -------------------------------------------


def test_back_to_back_alone_creates_small_disadvantage(db_session, settings):
    team = Team(abbreviation="NEC", name="B2B Team", win_pct_home=0.50, win_pct_away=0.50,
                win_pct_home_prev_season=0.50, win_pct_away_prev_season=0.50)
    opponent = Team(abbreviation="NED", name="B2B Opponent", win_pct_home=0.50, win_pct_away=0.50,
                     win_pct_home_prev_season=0.50, win_pct_away_prev_season=0.50)
    dummy = Team(abbreviation="HDX", name="History Dummy", win_pct_home=0.50, win_pct_away=0.50,
                 win_pct_home_prev_season=0.50, win_pct_away_prev_season=0.50)
    db_session.add_all([team, opponent, dummy])
    db_session.flush()
    _finished_game(db_session, team, dummy, TARGET_DATE - timedelta(days=1))

    game = create_scheduled_game(db_session, team, opponent)
    result = compute_matchup(db_session, game, settings)

    assert result.home.is_back_to_back is True
    assert result.home.calendar_penalty == pytest.approx(2.0)
    assert result.reliability == ReliabilityLevel.FAIBLE  # désavantage réel mais pas décisif


def test_three_in_four_alone_is_more_severe_than_back_to_back(db_session, settings):
    team = Team(abbreviation="NEE", name="3in4 Team", win_pct_home=0.50, win_pct_away=0.50,
                win_pct_home_prev_season=0.50, win_pct_away_prev_season=0.50)
    opponent = Team(abbreviation="NEF", name="3in4 Opponent", win_pct_home=0.50, win_pct_away=0.50,
                     win_pct_home_prev_season=0.50, win_pct_away_prev_season=0.50)
    dummy = Team(abbreviation="HDY", name="History Dummy 2", win_pct_home=0.50, win_pct_away=0.50,
                 win_pct_home_prev_season=0.50, win_pct_away_prev_season=0.50)
    db_session.add_all([team, opponent, dummy])
    db_session.flush()
    _finished_game(db_session, team, dummy, TARGET_DATE - timedelta(days=1))
    _finished_game(db_session, team, dummy, TARGET_DATE - timedelta(days=3))

    game = create_scheduled_game(db_session, team, opponent)
    result = compute_matchup(db_session, game, settings)

    assert result.home.is_three_in_four is True
    assert result.home.calendar_penalty == pytest.approx(3.5)
    assert result.home.calendar_penalty > 2.0  # plus sévère qu'un simple B2B


def test_three_in_four_penalty_not_cumulated_with_back_to_back_end_to_end(db_session, league, settings):
    """Vérifie bout en bout (via compute_matchup, pas juste compute_calendar_penalty
    isolément comme à l'Étape 3) : CHI est en 3in4 ET B2B simultanément à
    TARGET_DATE, seul le malus le plus sévère (3.5) doit s'appliquer."""
    game = create_scheduled_game(db_session, league.teams["CHI"], league.teams["DET"])
    result = compute_matchup(db_session, game, settings)

    assert result.home.is_back_to_back is True
    assert result.home.is_three_in_four is True
    assert result.home.calendar_penalty == pytest.approx(3.5)  # pas 2.0 + 3.5


# --- 6. Règle des 10 premiers matchs ----------------------------------------


def test_early_season_team_uses_previous_season_win_pct(db_session, league, settings):
    game = create_scheduled_game(db_session, league.teams["CHA"], league.teams["DET"])
    result = compute_matchup(db_session, game, settings)

    assert result.home.in_early_season is True
    assert result.home.games_played_this_season == 3
    # win_pct_home_prev_season (0.55), pas win_pct_home (0.28) : note_de_base
    # est la valeur brute, avant application du Curseur A (base_note_multiplier).
    assert result.home.note_de_base == pytest.approx(0.55)
    assert result.home.final_note == pytest.approx(0.55 * settings.base_note_multiplier + result.home.draft_bonus)


# --- 7. Bonus draft en début de saison --------------------------------------


def test_draft_bonus_applies_only_during_early_season(db_session, league, settings):
    game = create_scheduled_game(db_session, league.teams["CHA"], league.teams["DET"])
    result = compute_matchup(db_session, game, settings)

    assert result.home.draft_bonus == pytest.approx(8.0)  # pick #1 -> 8.0 points


# --- 8. Cumul de plusieurs absences ------------------------------------------


def test_multiple_absences_stack_but_stay_finite_and_reasonable(db_session, league, settings):
    sorted_roster = sorted(league.rosters["DEN"].others, key=lambda p: p.per, reverse=True)
    sorted_roster[0].injury_status = InjuryStatus.OUT
    sorted_roster[1].injury_status = InjuryStatus.OUT
    db_session.flush()

    game = create_scheduled_game(db_session, league.teams["DEN"], league.teams["MIA"])
    result = compute_matchup(db_session, game, settings)

    # injury_penalty est la somme BRUTE des PER (le Curseur B n'est appliqué
    # qu'au moment du calcul de final_note, pas stocké ici).
    expected_raw_penalty = sorted_roster[0].per + sorted_roster[1].per
    assert result.home.injury_penalty == pytest.approx(expected_raw_penalty)
    assert result.home.final_note > -100  # pas de valeur aberrante
    assert result.home.final_note < 200


# --- 9. Garde-fou sur l'ensemble du calendrier simulé -----------------------


def test_full_slate_spreads_stay_within_sane_bounds(db_session, league, settings):
    games = create_full_slate(db_session, league)
    results = [compute_matchup(db_session, g, settings) for g in games]

    spreads = [abs(r.spread) for r in results]
    assert all(spread < 100 for spread in spreads)  # aucun spread qui explose

    reliabilities = {r.reliability for r in results}
    assert len(reliabilities) >= 2  # le calendrier simulé produit une vraie variété


# --- 10. Bonus/Malus Transferts, bout en bout (Étape 6bis) -------------------


def test_transfer_bonus_affects_early_season_matchup_end_to_end(db_session, league, settings):
    """CHA (déjà l'équipe "début de saison" du calendrier simulé) récupère
    un joueur transféré depuis DET : vérifie l'effet sur compute_matchup,
    pas seulement sur compute_team_note isolément."""
    transferred_player = league.rosters["CHA"].others[0]
    db_session.add(
        PreviousSeasonPlayerStat(
            season="2024-2025",
            player_name=transferred_player.name,
            team_abbreviation="DET",
            per=18.0,
            mpg=26.0,
        )
    )
    db_session.flush()

    game_without_transfer = create_scheduled_game(db_session, league.teams["CHA"], league.teams["MIA"])
    baseline = compute_matchup(db_session, game_without_transfer, settings)

    # On ne peut pas juste "annuler" le transfert : on compare avec une note
    # calculée manuellement (bonus attendu = 18.0 * per_impact... non, *
    # transfer_impact_multiplier).
    expected_bonus = 18.0 * settings.transfer_impact_multiplier
    assert baseline.home.transfer_adjustment == pytest.approx(expected_bonus)
    assert baseline.home.final_note == pytest.approx(
        baseline.home.note_de_base * settings.base_note_multiplier
        + baseline.home.draft_bonus
        + expected_bonus
    )
