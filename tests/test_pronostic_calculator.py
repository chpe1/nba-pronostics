from datetime import date, datetime, timedelta

import pytest

from app.models import (
    Game,
    GameStatus,
    InjuryStatus,
    Player,
    PreviousSeasonPlayerStat,
    ReliabilityLevel,
    Settings,
    Team,
)
from app.services import pronostic_calculator as calc

SEASON = "2025-2026"


def _team(**overrides) -> Team:
    defaults = dict(
        name="Boston Celtics",
        abbreviation="BOS",
        win_pct_home=0.7,
        win_pct_away=0.5,
        win_pct_home_prev_season=0.6,
        win_pct_away_prev_season=0.4,
    )
    defaults.update(overrides)
    return Team(**defaults)


def _settings(**overrides) -> Settings:
    defaults = dict(
        base_note_multiplier=1.0,
        per_impact_multiplier=1.0,
        back_to_back_penalty=3.0,
        three_in_four_penalty=5.0,
        mpg_threshold=15.0,
        player_sample_size_threshold=5,
        draft_bonus_config={},
        reliability_threshold_low=5.0,
        reliability_threshold_high=10.0,
        transfer_impact_multiplier=1.0,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _finished_game(db_session, team: Team, opponent: Team, game_date: date) -> Game:
    game = Game(
        season=SEASON,
        game_date=datetime.combine(game_date, datetime.min.time()),
        home_team_id=team.id,
        away_team_id=opponent.id,
        status=GameStatus.FINISHED,
        home_score=100,
        away_score=90,
    )
    db_session.add(game)
    db_session.flush()
    return game


def _scheduled_game(db_session, team: Team, opponent: Team, game_date: date) -> Game:
    game = Game(
        season=SEASON,
        game_date=datetime.combine(game_date, datetime.min.time()),
        home_team_id=team.id,
        away_team_id=opponent.id,
        status=GameStatus.SCHEDULED,
    )
    db_session.add(game)
    db_session.flush()
    return game


# --- compute_note_de_base -------------------------------------------------


def test_note_de_base_uses_current_season_when_not_early_season():
    team = _team()
    assert calc.compute_note_de_base(team, is_home=True, in_early_season=False) == 0.7
    assert calc.compute_note_de_base(team, is_home=False, in_early_season=False) == 0.5


def test_note_de_base_uses_previous_season_when_early_season():
    team = _team()
    assert calc.compute_note_de_base(team, is_home=True, in_early_season=True) == 0.6
    assert calc.compute_note_de_base(team, is_home=False, in_early_season=True) == 0.4


# --- compute_injury_penalty / get_questionable_players --------------------

PREV_SEASON = "2024-2025"


def test_injury_penalty_counts_only_out_and_doubtful_above_mpg_threshold(db_session):
    team = _team()
    db_session.add(team)
    db_session.flush()
    settings = _settings()

    db_session.add_all(
        [
            Player(name="Out Star", team_id=team.id, per=25.0, mpg=32.0, games_played_this_season=20, injury_status=InjuryStatus.OUT),
            Player(name="Doubtful Starter", team_id=team.id, per=15.0, mpg=28.0, games_played_this_season=20, injury_status=InjuryStatus.DOUBTFUL),
            Player(name="Questionable Guy", team_id=team.id, per=20.0, mpg=30.0, games_played_this_season=20, injury_status=InjuryStatus.QUESTIONABLE, injury_reason="Ankle"),
            Player(name="Out Bench Player", team_id=team.id, per=10.0, mpg=8.0, games_played_this_season=20, injury_status=InjuryStatus.OUT),
            Player(name="Healthy Starter", team_id=team.id, per=18.0, mpg=30.0, games_played_this_season=20, injury_status=InjuryStatus.HEALTHY),
        ]
    )
    db_session.flush()

    penalty = calc.compute_injury_penalty(db_session, team, settings, PREV_SEASON)
    assert penalty == pytest.approx(40.0)  # 25.0 + 15.0, pas le joueur OUT sous le seuil MPG

    questionable = calc.get_questionable_players(db_session, team, settings, PREV_SEASON)
    assert len(questionable) == 1
    assert questionable[0].name == "Questionable Guy"
    assert questionable[0].reason == "Ankle"

    absent = calc.get_absent_players(db_session, team, settings, PREV_SEASON)
    assert {p.name for p in absent} == {"Out Star", "Doubtful Starter"}  # pas le joueur OUT sous le seuil MPG


def test_injury_penalty_zero_when_no_absent_players(db_session):
    team = _team()
    db_session.add(team)
    db_session.flush()
    db_session.add(Player(name="Healthy Starter", team_id=team.id, per=18.0, mpg=30.0, games_played_this_season=20, injury_status=InjuryStatus.HEALTHY))
    db_session.flush()

    assert calc.compute_injury_penalty(db_session, team, _settings(), PREV_SEASON) == 0.0


# --- garde-fou petit échantillon individuel (games_played_this_season) ----


def test_injury_penalty_player_absent_from_player_table_is_simply_not_evaluated(db_session):
    """Avant tout import courant, le joueur n'existe pas encore dans Player
    -- rien à évaluer pour lui, pas de crash (comportement déjà inhérent à la
    requête, testé ici explicitement)."""
    team = _team()
    db_session.add(team)
    db_session.flush()

    assert calc.compute_injury_penalty(db_session, team, _settings(), PREV_SEASON) == 0.0
    assert calc.get_questionable_players(db_session, team, _settings(), PREV_SEASON) == []


def test_injury_penalty_uses_prev_season_stat_when_games_played_below_threshold(db_session):
    """G courant sous le seuil + PreviousSeasonPlayerStat existant -> PER/MPG
    N-1 utilisés à la place des valeurs courantes, pour le calcul ET pour le
    filtre MPG."""
    team = _team()
    db_session.add(team)
    db_session.flush()
    settings = _settings(player_sample_size_threshold=5, mpg_threshold=15.0)

    db_session.add(
        Player(
            name="Comeback Star",
            team_id=team.id,
            per=99.0,  # valeur courante aberrante (petit échantillon), ne doit pas être utilisée
            mpg=5.0,  # sous le seuil MPG courant -- ne doit pas non plus être utilisé
            games_played_this_season=2,
            injury_status=InjuryStatus.OUT,
        )
    )
    db_session.add(
        PreviousSeasonPlayerStat(
            season=PREV_SEASON,
            player_name="Comeback Star",
            team_abbreviation=team.abbreviation,
            per=22.0,
            mpg=30.0,
        )
    )
    db_session.flush()

    penalty = calc.compute_injury_penalty(db_session, team, settings, PREV_SEASON)
    assert penalty == pytest.approx(22.0)


def test_injury_penalty_ignores_prev_season_stat_when_games_played_above_threshold(db_session):
    """G courant au-dessus du seuil -> valeur courante utilisée même si une
    ligne N-1 différente existe."""
    team = _team()
    db_session.add(team)
    db_session.flush()
    settings = _settings(player_sample_size_threshold=5, mpg_threshold=15.0)

    db_session.add(
        Player(
            name="Established Starter",
            team_id=team.id,
            per=18.0,
            mpg=30.0,
            games_played_this_season=6,
            injury_status=InjuryStatus.OUT,
        )
    )
    db_session.add(
        PreviousSeasonPlayerStat(
            season=PREV_SEASON,
            player_name="Established Starter",
            team_abbreviation=team.abbreviation,
            per=99.0,
            mpg=99.0,
        )
    )
    db_session.flush()

    penalty = calc.compute_injury_penalty(db_session, team, settings, PREV_SEASON)
    assert penalty == pytest.approx(18.0)


def test_injury_penalty_keeps_current_value_when_no_prev_season_stat_exists(db_session):
    """Cas 4 (limite acceptée) : G courant sous le seuil mais aucun
    PreviousSeasonPlayerStat (rookie/nouveau dans la ligue) -> valeur
    courante conservée telle quelle, pas de crash."""
    team = _team()
    db_session.add(team)
    db_session.flush()
    settings = _settings(player_sample_size_threshold=5, mpg_threshold=15.0)

    db_session.add(
        Player(
            name="Rookie No History",
            team_id=team.id,
            per=12.0,
            mpg=20.0,
            games_played_this_season=1,
            injury_status=InjuryStatus.OUT,
        )
    )
    db_session.flush()

    penalty = calc.compute_injury_penalty(db_session, team, settings, PREV_SEASON)
    assert penalty == pytest.approx(12.0)


# --- compute_calendar_penalty ----------------------------------------------


def test_calendar_penalty_back_to_back(db_session):
    team = _team()
    opponent = _team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add_all([team, opponent])
    db_session.flush()

    game_date = date(2026, 1, 10)
    _finished_game(db_session, team, opponent, game_date - timedelta(days=1))

    result = calc.compute_calendar_penalty(db_session, team, game_date, _settings())
    assert result["is_back_to_back"] is True
    assert result["is_three_in_four"] is False
    assert result["penalty"] == pytest.approx(3.0)


def test_calendar_penalty_three_in_four_takes_precedence_when_more_severe(db_session):
    team = _team()
    opponent = _team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add_all([team, opponent])
    db_session.flush()

    game_date = date(2026, 1, 10)
    # B2B la veille + un autre match il y a 3 jours -> B2B ET 3in4 vrais.
    _finished_game(db_session, team, opponent, game_date - timedelta(days=1))
    _finished_game(db_session, team, opponent, game_date - timedelta(days=3))

    result = calc.compute_calendar_penalty(db_session, team, game_date, _settings())
    assert result["is_back_to_back"] is True
    assert result["is_three_in_four"] is True
    # three_in_four_penalty (5.0) > back_to_back_penalty (3.0) -> le plus sévère.
    assert result["penalty"] == pytest.approx(5.0)


def test_calendar_penalty_none_when_well_rested(db_session):
    team = _team()
    db_session.add(team)
    db_session.flush()

    result = calc.compute_calendar_penalty(db_session, team, date(2026, 1, 10), _settings())
    assert result["is_back_to_back"] is False
    assert result["is_three_in_four"] is False
    assert result["penalty"] == 0.0


# --- compute_calendar_flags (statut B2B/3-en-4 pour l'affichage public) ----


def test_calendar_flags_back_to_back(db_session):
    team = _team()
    opponent = _team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add_all([team, opponent])
    db_session.flush()

    game_date = date(2026, 1, 10)
    _finished_game(db_session, team, opponent, game_date - timedelta(days=1))

    result = calc.compute_calendar_flags(db_session, team, game_date)
    assert result == {"is_back_to_back": True, "is_three_in_four": False}


def test_calendar_flags_both_true_simultaneously(db_session):
    """Un 3-en-4 inclut presque toujours un B2B la veille -- pas un choix
    binaire entre les deux, une équipe peut être vraie sur les deux à la fois."""
    team = _team()
    opponent = _team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add_all([team, opponent])
    db_session.flush()

    game_date = date(2026, 1, 10)
    _finished_game(db_session, team, opponent, game_date - timedelta(days=1))
    _finished_game(db_session, team, opponent, game_date - timedelta(days=3))

    result = calc.compute_calendar_flags(db_session, team, game_date)
    assert result == {"is_back_to_back": True, "is_three_in_four": True}


def test_calendar_flags_none_when_well_rested(db_session):
    team = _team()
    db_session.add(team)
    db_session.flush()

    result = calc.compute_calendar_flags(db_session, team, date(2026, 1, 10))
    assert result == {"is_back_to_back": False, "is_three_in_four": False}


def test_calendar_flags_work_for_scheduled_games_unlike_penalty(db_session):
    """Différence clé avec compute_calendar_penalty : le calendrier d'une
    saison est connu à l'avance, donc un match SCHEDULED (pas encore joué)
    compte quand même -- sinon un match futur montrerait toujours "aucun B2B"
    à tort, simplement parce que les matchs précédents n'ont pas encore eu
    lieu."""
    team = _team()
    opponent = _team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add_all([team, opponent])
    db_session.flush()

    game_date = date(2026, 1, 10)
    _scheduled_game(db_session, team, opponent, game_date - timedelta(days=1))

    flags_result = calc.compute_calendar_flags(db_session, team, game_date)
    assert flags_result["is_back_to_back"] is True

    # compute_calendar_penalty, lui, ne voit rien (filtre FINISHED) -- limite
    # connue et volontairement non corrigée dans le cadre de cette fonctionnalité.
    penalty_result = calc.compute_calendar_penalty(db_session, team, game_date, _settings())
    assert penalty_result["is_back_to_back"] is False


# --- compute_draft_bonus ----------------------------------------------------


def test_draft_bonus_sums_all_rookies(db_session):
    team = _team()
    db_session.add(team)
    db_session.flush()
    settings = _settings(draft_bonus_config={"1": 5.0, "2": 3.0})

    db_session.add_all(
        [
            Player(name="Pick 1", team_id=team.id, draft_pick=1),
            Player(name="Pick 2", team_id=team.id, draft_pick=2),
            Player(name="Undrafted Vet", team_id=team.id, draft_pick=None),
        ]
    )
    db_session.flush()

    assert calc.compute_draft_bonus(db_session, team, settings) == pytest.approx(8.0)


def test_draft_bonus_zero_without_config_entry(db_session):
    team = _team()
    db_session.add(team)
    db_session.flush()
    db_session.add(Player(name="Pick 30", team_id=team.id, draft_pick=30))
    db_session.flush()

    assert calc.compute_draft_bonus(db_session, team, _settings(draft_bonus_config={"1": 5.0})) == 0.0


# --- compute_team_note (assemblage) ----------------------------------------


def test_compute_team_note_early_season_applies_draft_bonus_and_prev_season_pct(db_session):
    team = _team()
    opponent = _team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add_all([team, opponent])
    db_session.flush()
    settings = _settings(draft_bonus_config={"1": 4.0})
    db_session.add(Player(name="Rookie", team_id=team.id, draft_pick=1))
    db_session.flush()

    game_date = date(2026, 10, 25)  # aucun match encore joué cette saison
    breakdown = calc.compute_team_note(db_session, team, game_date, SEASON, is_home=True, settings=settings)

    assert breakdown.games_played_this_season == 0
    assert breakdown.in_early_season is True
    assert breakdown.note_de_base == 0.6  # win_pct_home_prev_season
    assert breakdown.draft_bonus == pytest.approx(4.0)
    assert breakdown.final_note == pytest.approx(0.6 + 4.0)


def test_compute_team_note_after_early_season_uses_current_pct_and_no_draft_bonus(db_session):
    team = _team()
    opponent = _team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add_all([team, opponent])
    db_session.flush()
    settings = _settings(draft_bonus_config={"1": 4.0})
    db_session.add(Player(name="Rookie", team_id=team.id, draft_pick=1))
    db_session.flush()

    base_date = date(2025, 10, 22)
    for i in range(10):
        _finished_game(db_session, team, opponent, base_date + timedelta(days=i * 2))

    game_date = base_date + timedelta(days=30)
    breakdown = calc.compute_team_note(db_session, team, game_date, SEASON, is_home=True, settings=settings)

    assert breakdown.games_played_this_season == 10
    assert breakdown.in_early_season is False
    assert breakdown.note_de_base == 0.7  # win_pct_home (saison courante)
    assert breakdown.draft_bonus == 0.0


# --- compute_matchup / save_prediction --------------------------------------


def test_compute_matchup_end_to_end(db_session):
    home = _team(name="Boston Celtics", abbreviation="BOS", win_pct_home=0.8, win_pct_away=0.5)
    away = _team(name="Los Angeles Lakers", abbreviation="LAL", win_pct_home=0.6, win_pct_away=0.3)
    db_session.add_all([home, away])
    db_session.flush()
    settings = _settings()

    # Passé les 10 premiers matchs, pour utiliser win_pct_home/away de la
    # saison courante (plutôt que N-1) dans le calcul.
    base_date = date(2025, 10, 22)
    for i in range(10):
        _finished_game(db_session, home, away, base_date + timedelta(days=i * 2))

    game_date = base_date + timedelta(days=60)
    game = Game(
        season=SEASON,
        game_date=datetime.combine(game_date, datetime.min.time()).replace(hour=19),
        home_team_id=home.id,
        away_team_id=away.id,
        status=GameStatus.SCHEDULED,
    )
    db_session.add(game)
    db_session.flush()

    result = calc.compute_matchup(db_session, game, settings)

    assert result.predicted_winner_team_id == home.id
    assert result.spread == pytest.approx(0.8 - 0.3)
    # Écart de 0.5 < reliability_threshold_low (5.0) avec les seuils par
    # défaut : la calibration fine des seuils/multiplicateurs se fera à
    # l'Étape 6, ce test vérifie juste la logique d'assemblage.
    assert result.reliability == ReliabilityLevel.FAIBLE


def test_save_prediction_upserts_single_row_per_game(db_session):
    home = _team(name="Boston Celtics", abbreviation="BOS")
    away = _team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add_all([home, away])
    db_session.flush()
    settings = _settings()
    game = Game(
        season=SEASON,
        game_date=datetime(2026, 1, 15, 19, 0),
        home_team_id=home.id,
        away_team_id=away.id,
        status=GameStatus.SCHEDULED,
    )
    db_session.add(game)
    db_session.flush()

    first = calc.save_prediction(db_session, game, settings)
    first_id = first.id

    # Aucun match encore joué cette saison -> "début de saison" -> le calcul
    # utilise win_pct_away_prev_season (pas win_pct_away).
    away.win_pct_away_prev_season = 0.9
    db_session.flush()
    second = calc.save_prediction(db_session, game, settings)

    assert second.id == first_id  # même ligne, pas de doublon
    assert second.breakdown["away"]["note_de_base"] == pytest.approx(0.9)
    assert second.breakdown["home"]["absent_players"] == []
    assert second.breakdown["away"]["absent_players"] == []


# --- Bonus/Malus Transferts (Étape 6bis) ------------------------------------

PREV_SEASON = "2024-2025"


def test_previous_season_label():
    assert calc.previous_season_label("2025-2026") == "2024-2025"
    assert calc.previous_season_label("2024-2025") == "2023-2024"


def test_transfer_bonus_detects_incoming_player(db_session):
    team = _team()
    db_session.add(team)
    db_session.flush()
    db_session.add(Player(name="New Arrival", team_id=team.id, per=15.0, mpg=20.0))
    db_session.add(
        PreviousSeasonPlayerStat(
            season=PREV_SEASON, player_name="New Arrival", team_abbreviation="LAL", per=22.0, mpg=30.0
        )
    )
    db_session.flush()

    bonus = calc.compute_transfer_bonus(db_session, team, _settings(), PREV_SEASON)
    assert bonus == pytest.approx(22.0)  # PER N-1, pas le PER courant (15.0)


def test_transfer_bonus_detects_incoming_player_case_insensitive(db_session):
    """Point 1 (retour d'usage réel) : le rapprochement Player.name /
    PreviousSeasonPlayerStat.player_name doit ignorer la casse -- un joueur
    actuel "LEBRON JAMES" doit retrouver sa ligne N-1 "LeBron James"."""
    team = _team()
    db_session.add(team)
    db_session.flush()
    db_session.add(Player(name="LEBRON JAMES", team_id=team.id, per=15.0, mpg=20.0))
    db_session.add(
        PreviousSeasonPlayerStat(
            season=PREV_SEASON, player_name="LeBron James", team_abbreviation="LAL", per=22.0, mpg=30.0
        )
    )
    db_session.flush()

    bonus = calc.compute_transfer_bonus(db_session, team, _settings(), PREV_SEASON)
    assert bonus == pytest.approx(22.0)


def test_transfer_bonus_ignores_player_already_on_team_last_season(db_session):
    team = _team()
    db_session.add(team)
    db_session.flush()
    db_session.add(Player(name="Stayed Player", team_id=team.id, per=15.0, mpg=20.0))
    db_session.add(
        PreviousSeasonPlayerStat(
            season=PREV_SEASON,
            player_name="Stayed Player",
            team_abbreviation=team.abbreviation,
            per=22.0,
            mpg=30.0,
        )
    )
    db_session.flush()

    assert calc.compute_transfer_bonus(db_session, team, _settings(), PREV_SEASON) == 0.0


def test_transfer_bonus_filters_by_previous_season_mpg_not_current(db_session):
    team = _team()
    db_session.add(team)
    db_session.flush()
    # MPG courant élevé mais MPG N-1 sous le seuil -> pas pris en compte
    # (signal jugé plus fiable en tout début de saison, cf. docstring).
    db_session.add(Player(name="Bench Arrival", team_id=team.id, per=15.0, mpg=25.0))
    db_session.add(
        PreviousSeasonPlayerStat(
            season=PREV_SEASON, player_name="Bench Arrival", team_abbreviation="LAL", per=22.0, mpg=8.0
        )
    )
    db_session.flush()

    bonus = calc.compute_transfer_bonus(db_session, team, _settings(mpg_threshold=15.0), PREV_SEASON)
    assert bonus == 0.0


def test_transfer_bonus_ignores_rookie_without_previous_season_data(db_session):
    team = _team()
    db_session.add(team)
    db_session.flush()
    db_session.add(Player(name="Fresh Rookie", team_id=team.id, per=10.0, mpg=20.0, draft_pick=5))
    db_session.flush()

    assert calc.compute_transfer_bonus(db_session, team, _settings(), PREV_SEASON) == 0.0


def test_transfer_malus_detects_outgoing_player(db_session):
    old_team = _team(name="Boston Celtics", abbreviation="BOS")
    new_team = _team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add_all([old_team, new_team])
    db_session.flush()
    db_session.add(Player(name="Departed Player", team_id=new_team.id, per=18.0, mpg=25.0))
    db_session.add(
        PreviousSeasonPlayerStat(
            season=PREV_SEASON, player_name="Departed Player", team_abbreviation="BOS", per=21.0, mpg=28.0
        )
    )
    db_session.flush()

    malus = calc.compute_transfer_malus(db_session, old_team, _settings(), PREV_SEASON)
    assert malus == pytest.approx(21.0)


def test_transfer_malus_ignores_player_who_stayed(db_session):
    team = _team()
    db_session.add(team)
    db_session.flush()
    db_session.add(Player(name="Stayed Player", team_id=team.id, per=18.0, mpg=25.0))
    db_session.add(
        PreviousSeasonPlayerStat(
            season=PREV_SEASON,
            player_name="Stayed Player",
            team_abbreviation=team.abbreviation,
            per=21.0,
            mpg=28.0,
        )
    )
    db_session.flush()

    assert calc.compute_transfer_malus(db_session, team, _settings(), PREV_SEASON) == 0.0


def test_transfer_malus_ignores_player_not_found_in_current_league(db_session):
    """Joueur introuvable en base actuelle (retraite, non reconduit...) :
    pas de malus, ce n'est pas un transfert vérifiable."""
    team = _team()
    db_session.add(team)
    db_session.flush()
    db_session.add(
        PreviousSeasonPlayerStat(
            season=PREV_SEASON,
            player_name="Retired Player",
            team_abbreviation=team.abbreviation,
            per=21.0,
            mpg=28.0,
        )
    )
    db_session.flush()

    assert calc.compute_transfer_malus(db_session, team, _settings(), PREV_SEASON) == 0.0


def test_transfer_adjustment_only_applies_during_early_season(db_session):
    team = _team()
    opponent = _team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add_all([team, opponent])
    db_session.flush()
    db_session.add(Player(name="New Arrival", team_id=team.id, per=15.0, mpg=20.0))
    db_session.add(
        PreviousSeasonPlayerStat(
            season=PREV_SEASON, player_name="New Arrival", team_abbreviation="LAL", per=22.0, mpg=30.0
        )
    )
    db_session.flush()
    settings = _settings(transfer_impact_multiplier=1.0)

    early_breakdown = calc.compute_team_note(
        db_session, team, date(2025, 10, 25), SEASON, is_home=True, settings=settings
    )
    assert early_breakdown.transfer_adjustment == pytest.approx(22.0)
    assert early_breakdown.final_note == pytest.approx(
        early_breakdown.note_de_base * settings.base_note_multiplier + 22.0
    )

    base_date = date(2025, 10, 22)
    for i in range(10):
        _finished_game(db_session, team, opponent, base_date + timedelta(days=i * 2))

    later_breakdown = calc.compute_team_note(
        db_session, team, base_date + timedelta(days=30), SEASON, is_home=True, settings=settings
    )
    assert later_breakdown.in_early_season is False
    assert later_breakdown.transfer_adjustment == 0.0


def test_transfer_adjustment_combines_with_draft_bonus(db_session):
    """Un transfert entrant ET un rookie drafté sur la même équipe doivent
    s'additionner (deux effets distincts de la règle des 10 premiers matchs)."""
    team = _team()
    db_session.add(team)
    db_session.flush()
    db_session.add(Player(name="New Arrival", team_id=team.id, per=15.0, mpg=20.0))
    db_session.add(Player(name="Rookie", team_id=team.id, draft_pick=1, per=0.0, mpg=0.0))
    db_session.add(
        PreviousSeasonPlayerStat(
            season=PREV_SEASON, player_name="New Arrival", team_abbreviation="LAL", per=22.0, mpg=30.0
        )
    )
    db_session.flush()
    settings = _settings(transfer_impact_multiplier=1.0, draft_bonus_config={"1": 8.0})

    breakdown = calc.compute_team_note(
        db_session, team, date(2025, 10, 25), SEASON, is_home=True, settings=settings
    )
    assert breakdown.transfer_adjustment == pytest.approx(22.0)
    assert breakdown.draft_bonus == pytest.approx(8.0)
