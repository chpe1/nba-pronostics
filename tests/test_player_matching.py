import pytest

from app.models import Player, PreviousSeasonPlayerStat, Team
from app.services.player_matching import (
    find_active_player_by_name,
    find_player_by_name,
    find_prev_season_stat_by_name,
    normalize_player_name,
)


def test_normalize_player_name_ignores_case():
    assert normalize_player_name("LEBRON JAMES") == normalize_player_name("LeBron James")


def test_normalize_player_name_ignores_case_on_accented_letters():
    """casefold() (pas lower()) : SQLite LOWER() ne replie que l'ASCII, donc
    ce comportement doit être garanti côté Python, pas délégué à la DB."""
    assert normalize_player_name("GARCÍA") == normalize_player_name("García")


def test_normalize_player_name_strips_surrounding_whitespace():
    assert normalize_player_name("  LeBron James  ") == normalize_player_name("LeBron James")


def test_find_player_by_name_matches_regardless_of_case(db_session):
    team = Team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add(team)
    db_session.flush()
    player = Player(name="LeBron James", team_id=team.id)
    db_session.add(player)
    db_session.flush()

    found = find_player_by_name(db_session, "LEBRON JAMES", team.id)
    assert found is not None
    assert found.id == player.id


def test_find_player_by_name_scoped_to_team(db_session):
    lal = Team(name="Los Angeles Lakers", abbreviation="LAL")
    bos = Team(name="Boston Celtics", abbreviation="BOS")
    db_session.add_all([lal, bos])
    db_session.flush()
    db_session.add(Player(name="LeBron James", team_id=lal.id))
    db_session.flush()

    assert find_player_by_name(db_session, "LeBron James", bos.id) is None


def test_find_player_by_name_returns_none_when_not_found(db_session):
    team = Team(name="Boston Celtics", abbreviation="BOS")
    db_session.add(team)
    db_session.flush()

    assert find_player_by_name(db_session, "Nobody", team.id) is None


def test_find_active_player_by_name_ignores_inactive(db_session):
    team = Team(name="Boston Celtics", abbreviation="BOS")
    db_session.add(team)
    db_session.flush()
    db_session.add(Player(name="Retired Guy", team_id=team.id, is_active=False))
    db_session.flush()

    assert find_active_player_by_name(db_session, "RETIRED GUY") is None


def test_find_active_player_by_name_matches_across_teams(db_session):
    lal = Team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add(lal)
    db_session.flush()
    player = Player(name="LeBron James", team_id=lal.id, is_active=True)
    db_session.add(player)
    db_session.flush()

    found = find_active_player_by_name(db_session, "lebron james")
    assert found is not None
    assert found.id == player.id


def test_find_prev_season_stat_by_name_matches_regardless_of_case(db_session):
    stat = PreviousSeasonPlayerStat(
        season="2024-2025", player_name="LeBron James", team_abbreviation="LAL", per=25.0, mpg=35.0
    )
    db_session.add(stat)
    db_session.flush()

    found = find_prev_season_stat_by_name(db_session, "2024-2025", "LEBRON JAMES")
    assert found is not None
    assert found.id == stat.id


def test_find_prev_season_stat_by_name_scoped_to_season(db_session):
    db_session.add(
        PreviousSeasonPlayerStat(
            season="2023-2024", player_name="LeBron James", team_abbreviation="LAL", per=25.0, mpg=35.0
        )
    )
    db_session.flush()

    assert find_prev_season_stat_by_name(db_session, "2024-2025", "LeBron James") is None
