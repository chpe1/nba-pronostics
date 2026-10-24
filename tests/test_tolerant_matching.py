"""Rapprochement TOLÉRANT des noms dans le moteur de calcul (2026-10-24) : accents, ponctuation et suffixes repliés
pour LIRE ; le rapprochement strict reste en place pour ÉCRIRE et pour les contrôles d'unicité."""
from datetime import date

import pytest

from app.models import InjuryStatus, Player, PreviousSeasonPlayerStat, Settings, Team
from app.services import csv_import, injury_report_updater, player_matching as pm
from app.services import pronostic_calculator as calc

PREV = "2025-2026"

# Les 11 cas réels mesurés le 2026-10-23 : (nom en base, nom de la ligne N-1)
REAL_CASES = [
    ("Jimmy Butler III", "Jimmy Butler"),
    ("Alperen Sengun", "Alperen Şengün"),
    ("Robert Williams III", "Robert Williams"),
    ("David Jones Garcia", "David Jones García"),
    ("Bobby Portis Jr.", "Bobby Portis"),
    ("GG Jackson", "GG Jackson II"),
    ("DaRon Holmes II", "DaRon Holmes"),
    ("Walter Clayton Jr.", "Walter Clayton"),
    ("AJ Green", "A.J. Green"),
    ("Terrence Shannon Jr", "Terrence Shannon Jr."),
    ("Nolan Traore", "Nolan Traoré"),
]


def _stat(db, name, per=15.0, mpg=30.0, team="GSW"):
    stat = PreviousSeasonPlayerStat(season=PREV, player_name=name, team_abbreviation=team, per=per, mpg=mpg)
    db.add(stat)
    db.flush()
    return stat


@pytest.mark.parametrize("base_name, n1_name", REAL_CASES)
def test_the_eleven_real_cases_find_their_n1_line(db_session, base_name, n1_name):
    stat = _stat(db_session, n1_name)
    assert pm.find_prev_season_stat_by_name(db_session, PREV, base_name) is None  # le strict échoue : c'est le défaut
    assert pm.find_prev_season_stat_by_name_tolerant(db_session, PREV, base_name) is stat


def test_accent_in_either_direction(db_session):
    stat = _stat(db_session, "Nikola Topić")
    assert pm.find_prev_season_stat_by_name_tolerant(db_session, PREV, "Nikola Topic") is stat
    assert pm.find_prev_season_stat_by_name_tolerant(db_session, PREV, "NIKOLA TOPIĆ") is stat


def test_suffix_in_either_direction(db_session):
    stat = _stat(db_session, "Jimmy Butler")
    assert pm.find_prev_season_stat_by_name_tolerant(db_session, PREV, "Jimmy Butler III") is stat
    stat2 = _stat(db_session, "Gary Trent Jr.")
    assert pm.find_prev_season_stat_by_name_tolerant(db_session, PREV, "Gary Trent") is stat2


def test_two_players_differing_only_by_suffix_stay_distinct(db_session):
    father = _stat(db_session, "Gary Payton", per=10.0)
    son = _stat(db_session, "Gary Payton II", per=14.0)
    # l'égalité stricte passe d'abord : chacun retrouve SA ligne
    assert pm.find_prev_season_stat_by_name_tolerant(db_session, PREV, "Gary Payton") is father
    assert pm.find_prev_season_stat_by_name_tolerant(db_session, PREV, "Gary Payton II") is son
    # une graphie qui ne coïncide strictement avec aucun des deux est ambiguë : aucun résultat, jamais au hasard
    assert pm.find_prev_season_stat_by_name_tolerant(db_session, PREV, "Gary Payton Jr.") is None
    assert pm.find_prev_season_stat_by_name_tolerant(db_session, PREV, "gary  payton, ii") is None


def test_ambiguous_active_players_give_no_match(db_session):
    team = Team(name="T", abbreviation="TTT")
    db_session.add(team)
    db_session.flush()
    db_session.add_all([Player(name="Gary Payton", team_id=team.id), Player(name="Gary Payton II", team_id=team.id)])
    db_session.flush()
    assert pm.find_active_player_by_name_tolerant(db_session, "Gary Payton Jr.") is None
    assert pm.find_active_player_by_name_tolerant(db_session, "gary payton ii").name == "Gary Payton II"


def test_active_lookup_ignores_inactive_players_and_finds_tolerantly(db_session):
    team = Team(name="T", abbreviation="TTT")
    db_session.add(team)
    db_session.flush()
    db_session.add_all([Player(name="Alperen Sengun", team_id=team.id), Player(name="Old Guy", team_id=team.id, is_active=False)])
    db_session.flush()
    assert pm.find_active_player_by_name_tolerant(db_session, "Alperen Şengün").name == "Alperen Sengun"
    assert pm.find_active_player_by_name_tolerant(db_session, "Old Guy") is None


def test_strict_variants_are_unchanged_they_still_guard_uniqueness(db_session):
    """Tolérant pour lire, strict pour écrire : les find_* d'origine ne replient toujours rien."""
    _stat(db_session, "Alperen Şengün")
    assert pm.find_prev_season_stat_by_name(db_session, PREV, "Alperen Sengun") is None
    assert pm.find_prev_season_stat_by_name(db_session, PREV, "ALPEREN ŞENGÜN") is not None  # la casse seule, comme avant


def test_unrelated_players_with_close_spelling_are_not_matched(db_session):
    _stat(db_session, "Jalen Wilson")
    assert pm.find_prev_season_stat_by_name_tolerant(db_session, PREV, "Caleb Wilson") is None
    _stat(db_session, "Ron Holland")
    assert pm.find_prev_season_stat_by_name_tolerant(db_session, PREV, "Ronald Holland II") is None  # diminutifs : non traités


def test_folding_helpers_live_in_the_low_level_module_and_are_reexported():
    assert csv_import.fold_diacritics is pm.fold_diacritics
    assert csv_import._roster_match_key is pm.tolerant_name_key
    assert injury_report_updater.fold_diacritics is pm.fold_diacritics


# ----------------------------------------------------------------------------- dans le moteur


def _settings(**kw):
    values = dict(
        base_note_multiplier=100.0, per_impact_multiplier=0.4, back_to_back_penalty=0.0, three_in_four_penalty=0.0,
        mpg_threshold=15.0, player_sample_size_threshold=5, draft_bonus_config={}, reliability_threshold_low=7.0,
        reliability_threshold_high=30.0, transfer_impact_multiplier=0.0, no_prev_season_impact_multiplier=0.4,
    )
    values.update(kw)
    return Settings(**values)


def test_engine_subtracts_an_absent_player_whose_n1_name_differs_by_suffix(db_session):
    """Le cas Butler : OUT, PER courant à 0, ligne N-1 « Jimmy Butler » ; la base dit « Jimmy Butler III »."""
    team = Team(name="Golden State", abbreviation="GSW")
    db_session.add(team)
    db_session.flush()
    db_session.add(Player(name="Jimmy Butler III", team_id=team.id, per=0.0, mpg=0.0, injury_status=InjuryStatus.OUT))
    _stat(db_session, "Jimmy Butler", per=23.5, mpg=31.1)
    assert calc.compute_injury_penalty(db_session, team, _settings(), PREV) == pytest.approx(23.5)


def test_engine_no_credit_for_a_player_who_finds_his_line_tolerantly(db_session):
    team = Team(name="Houston", abbreviation="HOU")
    db_session.add(team)
    db_session.flush()
    db_session.add(Player(name="Alperen Sengun", team_id=team.id, per=21.0, mpg=33.0))
    _stat(db_session, "Alperen Şengün", per=21.4, mpg=33.3, team="HOU")
    assert calc.compute_no_prev_season_credit_detail(db_session, team, _settings(), PREV).players == []


def test_engine_transfer_malus_finds_the_departed_player_tolerantly(db_session):
    old, new = Team(name="Old", abbreviation="OLD"), Team(name="New", abbreviation="NEW")
    db_session.add_all([old, new])
    db_session.flush()
    db_session.add(Player(name="Bobby Portis Jr.", team_id=new.id))
    _stat(db_session, "Bobby Portis", per=17.1, mpg=24.2, team="OLD")
    assert calc.compute_transfer_malus(db_session, old, _settings(), PREV) == pytest.approx(17.1)
    assert calc.compute_transfer_bonus(db_session, new, _settings(), PREV) == pytest.approx(17.1)


def test_engine_strict_matches_keep_working(db_session):
    team = Team(name="Boston", abbreviation="BOS")
    db_session.add(team)
    db_session.flush()
    db_session.add(Player(name="Jayson Tatum", team_id=team.id, per=0.0, mpg=0.0, injury_status=InjuryStatus.OUT))
    _stat(db_session, "jayson tatum", per=24.0, mpg=36.0, team="BOS")
    assert calc.compute_injury_penalty(db_session, team, _settings(), PREV) == pytest.approx(24.0)
