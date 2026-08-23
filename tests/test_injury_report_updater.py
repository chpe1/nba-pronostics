from datetime import date

from app.models import InjuryStatus, Player, Team
from app.services.injury_report_parser import InjuryReportEntry
from app.services.injury_report_updater import apply_injury_report, build_match_key


def _entry(**overrides) -> InjuryReportEntry:
    defaults = dict(
        game_date=date(2026, 1, 1),
        game_time_raw="06:00(ET)",
        matchup="HOU@BKN",
        team_raw="HoustonRockets",
        team_full_name="Houston Rockets",
        team_abbreviation="HOU",
        player_name_raw="Adams,Steven",
        status=InjuryStatus.OUT,
        status_raw="Out",
        reason="Injury/Illness-RightAnkle;Sprain",
    )
    defaults.update(overrides)
    return InjuryReportEntry(**defaults)


def test_build_match_key_matches_first_last_order():
    assert build_match_key("Adams,Steven") == "stevenadams"
    assert build_match_key("PorterJr.,Michael") == "michaelporterjr"


def test_apply_injury_report_updates_matched_player(db_session):
    team = Team(name="Houston Rockets", abbreviation="HOU")
    db_session.add(team)
    db_session.flush()
    player = Player(name="Steven Adams", team_id=team.id, injury_status=InjuryStatus.HEALTHY)
    db_session.add(player)
    db_session.flush()

    result = apply_injury_report(db_session, [_entry()])

    assert result.matched_count == 1
    assert result.unmatched_entries == []
    db_session.refresh(player)
    assert player.injury_status == InjuryStatus.OUT
    assert player.injury_updated_at is not None


def test_apply_injury_report_reports_unmatched_player(db_session):
    team = Team(name="Houston Rockets", abbreviation="HOU")
    db_session.add(team)
    db_session.flush()
    # Aucun joueur "Steven Adams" créé en base.

    result = apply_injury_report(db_session, [_entry()])

    assert result.matched_count == 0
    assert len(result.unmatched_entries) == 1


def test_apply_injury_report_skips_unknown_status(db_session):
    team = Team(name="Houston Rockets", abbreviation="HOU")
    db_session.add(team)
    db_session.flush()
    player = Player(name="Steven Adams", team_id=team.id)
    db_session.add(player)
    db_session.flush()

    result = apply_injury_report(db_session, [_entry(status=None, status_raw="Unknown")])

    assert result.matched_count == 0
    assert len(result.unmatched_entries) == 1
