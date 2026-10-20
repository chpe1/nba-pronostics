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


def test_build_match_key_folds_diacritics_of_the_database_side():
    from app.services.injury_report_updater import _normalize

    assert build_match_key("Topic,Nikola") == "nikolatopic"
    assert _normalize("Nikola Topić") == "nikolatopic"


def _team_with(db_session, *names):
    team = Team(name="Oklahoma City Thunder", abbreviation="OKC")
    db_session.add(team)
    db_session.flush()
    players = [Player(name=n, team_id=team.id, injury_status=InjuryStatus.HEALTHY) for n in names]
    db_session.add_all(players)
    db_session.flush()
    return players


def _okc_entry(raw):
    return _entry(team_raw="OklahomaCityThunder", team_full_name="Oklahoma City Thunder", team_abbreviation="OKC", player_name_raw=raw)


def test_accentless_report_name_finds_accented_database_player(db_session):
    (topic,) = _team_with(db_session, "Nikola Topić")
    result = apply_injury_report(db_session, [_okc_entry("Topic,Nikola")])
    assert result.matched_count == 1 and result.unmatched_entries == []
    db_session.refresh(topic)
    assert topic.injury_status == InjuryStatus.OUT


def test_accentless_names_on_both_sides_still_match(db_session):
    (adams,) = _team_with(db_session, "Steven Adams")
    result = apply_injury_report(db_session, [_okc_entry("Adams,Steven")])
    assert result.matched_count == 1
    db_session.refresh(adams)
    assert adams.injury_status == InjuryStatus.OUT


def test_two_players_differing_only_by_an_accent_are_left_unmatched_not_guessed(db_session):
    a, b = _team_with(db_session, "Nikola Topić", "Nikola Topic")
    result = apply_injury_report(db_session, [_okc_entry("Topic,Nikola")])
    assert result.matched_count == 0 and len(result.unmatched_entries) == 1
    db_session.refresh(a); db_session.refresh(b)
    assert a.injury_status == InjuryStatus.HEALTHY and b.injury_status == InjuryStatus.HEALTHY
