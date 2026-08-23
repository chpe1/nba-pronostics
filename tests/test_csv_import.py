from pathlib import Path

import pytest

from app.models import ImportType
from app.services import csv_import

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _read(filename: str):
    return csv_import.read_csv((FIXTURES_DIR / filename).read_bytes())


def test_detect_teams_home_away():
    df = _read("teams_home_away.csv")
    assert csv_import.detect_import_type(df) == ImportType.TEAMS_HOME_AWAY
    assert csv_import.validate_columns(df, ImportType.TEAMS_HOME_AWAY) == []


def test_detect_players_advanced():
    df = _read("players_advanced.csv")
    assert csv_import.detect_import_type(df) == ImportType.PLAYERS_ADVANCED


def test_detect_players_per_game():
    df = _read("players_per_game.csv")
    assert csv_import.detect_import_type(df) == ImportType.PLAYERS_PER_GAME


def test_players_advanced_drops_br_blank_columns():
    df = _read("players_advanced.csv")
    assert not any(str(c).startswith("Unnamed") for c in df.columns)


def test_parse_teams_home_away_computes_win_pct():
    df = _read("teams_home_away.csv")
    parsed, errors = csv_import.parse_teams_home_away(df)
    assert errors == []
    celtics = next(item for item in parsed if item["abbreviation"] == "BOS")
    assert celtics["name"] == "Boston Celtics"
    assert celtics["win_pct_home"] == pytest.approx(24 / 30)
    assert celtics["win_pct_away"] == pytest.approx(18 / 30)


def test_parse_teams_home_away_unknown_team_reports_error():
    df = _read("teams_home_away.csv")
    df.loc[0, "Team"] = "Not A Real Team"
    parsed, errors = csv_import.parse_teams_home_away(df)
    assert len(errors) == 1
    assert errors[0]["row"] == 2
    assert "inconnue" in errors[0]["message"]
    assert len(parsed) == len(df) - 1


def test_parse_players_advanced_extracts_per():
    df = _read("players_advanced.csv")
    parsed, errors = csv_import.parse_players_advanced(df)
    assert errors == []
    player_a = next(item for item in parsed if item["name"] == "Player A")
    assert player_a["team_abbreviation"] == "BOS"
    assert player_a["per"] == pytest.approx(24.3)


def test_parse_players_per_game_extracts_mpg():
    df = _read("players_per_game.csv")
    parsed, errors = csv_import.parse_players_per_game(df)
    assert errors == []
    player_a = next(item for item in parsed if item["name"] == "Player A")
    assert player_a["mpg"] == pytest.approx(34.1)


def test_parse_players_unknown_team_reports_error():
    df = _read("players_advanced.csv")
    df.loc[0, "Team"] = "ZZZ"
    parsed, errors = csv_import.parse_players_advanced(df)
    assert len(errors) == 1
    assert "inconnue" in errors[0]["message"]
