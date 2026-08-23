from datetime import date
from pathlib import Path

import pdfplumber
import pytest

from app.models import InjuryStatus
from app.services.injury_report_parser import parse_injury_report_pdf

FIXTURES_DIR = Path(__file__).parent / "fixtures"

FIXTURES = [
    "Injury-Report_2026-01-01_05_00PM.pdf",
    "Injury-Report_2026-04-08_03_45PM.pdf",
    "Injury-Report_2026-04-12_01_00PM.pdf",
]


def _parse(filename: str):
    with pdfplumber.open(FIXTURES_DIR / filename) as pdf:
        return parse_injury_report_pdf(pdf)


@pytest.mark.parametrize("filename", FIXTURES)
def test_all_entries_fully_resolved(filename):
    """Sur un rapport officiel réel, chaque ligne doit être rattachée à une
    équipe et un statut reconnus, avec une date de match et une raison non
    vides (aucune ligne orpheline / mal classée)."""
    entries = _parse(filename)
    assert len(entries) > 0
    assert all(e.team_full_name is not None for e in entries)
    assert all(e.status is not None for e in entries)
    assert all(e.game_date is not None for e in entries)
    assert all(e.reason for e in entries)


def test_row_counts_match_known_fixtures():
    assert len(_parse(FIXTURES[0])) == 122
    assert len(_parse(FIXTURES[1])) == 78
    assert len(_parse(FIXTURES[2])) == 229


def test_simple_single_line_reason():
    entries = _parse(FIXTURES[0])
    adams = next(e for e in entries if e.player_name_raw == "Adams,Steven")
    assert adams.game_date == date(2026, 1, 1)
    assert adams.matchup == "HOU@BKN"
    assert adams.team_full_name == "Houston Rockets"
    assert adams.team_abbreviation == "HOU"
    assert adams.status == InjuryStatus.OUT
    assert adams.reason == "Injury/Illness-RightAnkle;Sprain"


def test_reason_wrapping_before_and_after_player_row_is_merged_in_order():
    """Cas réel où le champ Reason est écrit sur 2 lignes qui encadrent la
    ligne du joueur (bloc centré verticalement) : la 1ère ligne apparaît
    AVANT la ligne joueur, la 2e APRÈS."""
    entries = _parse(FIXTURES[0])
    highsmith = next(e for e in entries if e.player_name_raw == "Highsmith,Haywood")
    assert highsmith.reason == "Injury/Illness-RightKnee;Surgery, InjuryRecovery"


def test_reason_continuation_across_page_break():
    """Cas réel où la 2e ligne du Reason est rejetée sur la page suivante,
    en tout début de page (avant la prochaine ligne joueur de cette page)."""
    entries = _parse(FIXTURES[0])
    fontecchio = next(e for e in entries if e.player_name_raw == "Fontecchio,Simone")
    assert fontecchio.matchup == "MIA@DET"
    assert fontecchio.team_full_name == "Miami Heat"
    assert fontecchio.status == InjuryStatus.AVAILABLE
    assert fontecchio.reason == "Injury/Illness-LeftAnkle; Inflammation"

    # Le joueur suivant (1ère ligne "ancre" de la page 2) ne doit pas avoir
    # récupéré ce fragment de raison par erreur.
    goldin = next(e for e in entries if e.player_name_raw == "Goldin,Vladislav")
    assert goldin.reason == "GLeague-Two-Way"


def test_game_time_and_matchup_update_independently_from_game_date():
    """Un nouveau match (même jour) ne répète pas la date, seulement l'heure
    et le matchup : ces deux champs doivent être reportés même sans nouvelle
    ligne GameDate."""
    entries = _parse(FIXTURES[0])
    matchups = {e.matchup for e in entries}
    assert "HOU@BKN" in matchups
    assert "MIA@DET" in matchups
    assert all(e.game_date == date(2026, 1, 1) for e in entries if e.matchup in ("HOU@BKN", "MIA@DET"))


@pytest.mark.parametrize("filename", FIXTURES)
def test_all_known_status_values_map_correctly(filename):
    entries = _parse(filename)
    seen = {e.status for e in entries}
    assert seen.issubset(set(InjuryStatus))
