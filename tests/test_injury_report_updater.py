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


# ----------------------------------------------------------------------------- suffixes (2026-10-26)
# Les deux formes réelles observées le 2026-10-26 sur le même rapport : suffixe COLLÉ au nom
# ("LivelyII,Dereck", 2 champs) et suffixe en CHAMP SÉPARÉ ("Udeh,Jr.,Ernest", 3 champs).


def test_glued_suffix_form_already_worked_and_still_does_no_regression(db_session):
    (lively,) = _team_with(db_session, "Dereck Lively II")
    result = apply_injury_report(db_session, [_okc_entry("LivelyII,Dereck")])
    assert result.matched_count == 1
    db_session.refresh(lively)
    assert lively.injury_status == InjuryStatus.OUT


def test_separate_field_suffix_form_now_matches_the_real_udeh_case(db_session):
    """Le cas réel du 2026-10-24/26 : "Udeh,Jr.,Ernest" (3 champs) ne retrouvait pas
    "Ernest Udeh, Jr." en base -- un découpage à la première virgule fabriquait la clé
    "jrernestudeh" au lieu de "ernestudehjr"."""
    (udeh,) = _team_with(db_session, "Ernest Udeh, Jr.")
    result = apply_injury_report(db_session, [_okc_entry("Udeh,Jr.,Ernest")])
    assert result.matched_count == 1 and result.unmatched_entries == []
    db_session.refresh(udeh)
    assert udeh.injury_status == InjuryStatus.OUT


def test_build_match_key_handles_the_three_field_form():
    assert build_match_key("Udeh,Jr.,Ernest") == "ernestudehjr"


def test_report_suffix_missing_on_one_side_falls_back_to_tolerant(db_session):
    """Le rapport omet parfois un suffixe que la base porte (ou l'inverse) -- strict échoue,
    la clé tolérante (celle du moteur, suffixes repliés des deux côtés) retrouve le joueur."""
    (butler,) = _team_with(db_session, "Jimmy Butler III")
    result = apply_injury_report(db_session, [_okc_entry("Butler,Jimmy")])  # rapport SANS le "III"
    assert result.matched_count == 1
    db_session.refresh(butler)
    assert butler.injury_status == InjuryStatus.OUT


def test_two_players_distinguished_only_by_a_suffix_are_left_unmatched_not_guessed(db_session):
    """La garde contre la confusion, reprise de la clé tolérante du moteur : si elle désigne
    plusieurs joueurs (ex. Gary Payton et Gary Payton II dans la même équipe), on ne choisit pas
    au hasard. Le rapport écrit ici un suffixe ("Jr.") qu'aucun des deux ne porte réellement --
    0 correspondance stricte (ni "garypayton" ni "garypaytonii"), donc repli tolérant ; une fois
    le suffixe replié des DEUX côtés, père et fils deviennent indiscernables ("gary payton")."""
    father, son = _team_with(db_session, "Gary Payton", "Gary Payton II")
    result = apply_injury_report(db_session, [_okc_entry("PaytonJr.,Gary")])
    assert result.matched_count == 0 and len(result.unmatched_entries) == 1
    db_session.refresh(father); db_session.refresh(son)
    assert father.injury_status == InjuryStatus.HEALTHY and son.injury_status == InjuryStatus.HEALTHY


def test_two_players_distinguished_only_by_a_suffix_each_still_matches_their_own_exact_form(db_session):
    """Mais quand le rapport ÉCRIT le suffixe, le strict suffit à départager -- pas besoin du
    repli tolérant, donc pas d'ambiguïté : chacun retrouve SA ligne, jamais l'autre."""
    father, son = _team_with(db_session, "Gary Payton", "Gary Payton II")
    result = apply_injury_report(db_session, [_okc_entry("PaytonII,Gary")])
    assert result.matched_count == 1
    db_session.refresh(father); db_session.refresh(son)
    assert father.injury_status == InjuryStatus.HEALTHY
    assert son.injury_status == InjuryStatus.OUT
