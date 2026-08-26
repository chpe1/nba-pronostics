from datetime import date, time
from pathlib import Path

import pandas as pd
import pytest

from app.models import Game, GameStatus, ImportType, Player, PreviousSeasonPlayerStat, Team
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


def test_parse_players_advanced_extracts_per_and_raw_mp_g():
    df = _read("players_advanced.csv")
    parsed, errors = csv_import.parse_players_advanced(df)
    assert errors == []
    player_a = next(item for item in parsed if item["name"] == "Player A")
    assert player_a["team_abbreviation"] == "BOS"
    assert player_a["per"] == pytest.approx(24.3)
    assert player_a["g"] == pytest.approx(58)
    assert player_a["mp"] == pytest.approx(1980)


def test_apply_players_advanced_derives_mpg_from_mp_and_g(db_session):
    df = _read("players_advanced.csv")
    parsed, errors = csv_import.parse_players_advanced(df)
    assert errors == []

    csv_import.apply_players_advanced(parsed, db_session)

    player_a = db_session.query(Player).filter(Player.name == "Player A").one()
    assert player_a.per == pytest.approx(24.3)
    assert player_a.mpg == pytest.approx(1980 / 58)


def test_apply_players_advanced_g_zero_gives_mpg_zero(db_session):
    df = pd.DataFrame([{"Player": "Bench Warmer", "Team": "BOS", "PER": 5.0, "G": 0, "MP": 0}])
    parsed, errors = csv_import.parse_players_advanced(df)
    assert errors == []

    csv_import.apply_players_advanced(parsed, db_session)

    player = db_session.query(Player).filter(Player.name == "Bench Warmer").one()
    assert player.mpg == 0.0


def test_parse_players_unknown_team_reports_error():
    df = _read("players_advanced.csv")
    df.loc[0, "Team"] = "ZZZ"
    parsed, errors = csv_import.parse_players_advanced(df)
    assert len(errors) == 1
    assert "inconnue" in errors[0]["message"]


# --- Roster par équipe (pas de colonne Team, fichier réel) ------------------


def test_detect_roster_by_team_advanced_as_players_advanced():
    """Le vrai fichier n'a pas de colonne Team (une seule équipe) -- doit
    quand même être détecté comme PLAYERS_ADVANCED (Player+PER suffisent)."""
    df = _read("roster_exemple_equipe_advanced.csv")
    assert csv_import.detect_import_type(df) == ImportType.PLAYERS_ADVANCED
    assert "Team" not in df.columns


def test_parse_players_advanced_without_team_column_uses_provided_abbreviation():
    df = _read("roster_exemple_equipe_advanced.csv")
    parsed, errors = csv_import.parse_players_advanced(df, team_abbreviation="DET")
    assert errors == []
    assert all(item["team_abbreviation"] == "DET" for item in parsed)
    cade = next(item for item in parsed if item["name"] == "Cade Cunningham")
    assert cade["per"] == pytest.approx(21.6)


def test_parse_players_advanced_without_team_column_skips_team_totals_row():
    df = _read("roster_exemple_equipe_advanced.csv")
    parsed, errors = csv_import.parse_players_advanced(df, team_abbreviation="DET")
    assert errors == []
    assert all(item["name"] != "Team Totals" for item in parsed)


def test_apply_players_advanced_without_team_column_creates_players_on_given_team(db_session):
    df = _read("roster_exemple_equipe_advanced.csv")
    parsed, errors = csv_import.parse_players_advanced(df, team_abbreviation="DET")
    assert errors == []

    count = csv_import.apply_players_advanced(parsed, db_session)

    assert count == len(parsed)
    cade = db_session.query(Player).filter(Player.name == "Cade Cunningham").one()
    assert cade.team.abbreviation == "DET"
    assert cade.per == pytest.approx(21.6)
    assert db_session.query(Player).filter(Player.name == "Team Totals").count() == 0


# --- Draft (nouveau 4e type CSV) --------------------------------------------


def _draft_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_detect_draft():
    df = _draft_df([{"Pk": 1, "Tm": "BOS", "Player": "Rookie One"}])
    assert csv_import.detect_import_type(df) == ImportType.DRAFT


def test_real_draft_file_with_grouped_header_row_is_detected_and_parsed():
    """Vrai fichier Basketball-Reference : 2 lignes d'en-tête (ligne de
    regroupement "Round 1"/"Totals"/"Per Game"/"Advanced", puis la vraie
    ligne d'en-tête). Sans _promote_grouped_header_if_needed, Pk/Tm/Rk sont
    supprimés comme colonnes "Unnamed" et la détection échoue -- verrouille
    le comportement corrigé bout en bout (read_csv + detect + parse)."""
    df = _read("draft.csv")
    assert csv_import.detect_import_type(df) == ImportType.DRAFT
    assert csv_import.validate_columns(df, ImportType.DRAFT) == []

    parsed, errors = csv_import.parse_draft(df)
    assert errors == []
    assert len(parsed) == 60

    first = next(item for item in parsed if item["name"] == "AJ Dybantsa")
    assert first == {"name": "AJ Dybantsa", "team_abbreviation": "WAS", "draft_pick": 1}

    # College vide pour un international : ignoré par parse_draft, pas une erreur.
    international = next(item for item in parsed if item["name"] == "Karim López")
    assert international["team_abbreviation"] == "DET"
    assert international["draft_pick"] == 21


def test_parse_draft_extracts_pick_and_team():
    df = _draft_df(
        [
            {"Pk": 1, "Tm": "BOS", "Player": "Rookie One"},
            {"Pk": 2, "Tm": "LAL", "Player": "Rookie Two"},
        ]
    )
    parsed, errors = csv_import.parse_draft(df)
    assert errors == []
    assert parsed[0] == {"name": "Rookie One", "team_abbreviation": "BOS", "draft_pick": 1}
    assert parsed[1] == {"name": "Rookie Two", "team_abbreviation": "LAL", "draft_pick": 2}


def test_parse_draft_unknown_team_reports_error():
    df = _draft_df([{"Pk": 1, "Tm": "ZZZ", "Player": "Rookie One"}])
    parsed, errors = csv_import.parse_draft(df)
    assert parsed == []
    assert "inconnue" in errors[0]["message"]


def test_apply_draft_creates_new_rookie_player(db_session):
    df = _draft_df([{"Pk": 1, "Tm": "BOS", "Player": "Rookie One"}])
    parsed, _ = csv_import.parse_draft(df)

    count = csv_import.apply_draft(parsed, db_session)

    assert count == 1
    player = db_session.query(Player).filter(Player.name == "Rookie One").one()
    assert player.draft_pick == 1
    assert player.team.abbreviation == "BOS"
    assert player.per == 0.0  # pas encore de vraies stats


def test_apply_draft_then_stats_import_updates_same_player_not_duplicate(db_session):
    """Compatibilité upsert : les vraies stats arrivant plus tard (même nom,
    même équipe) doivent retrouver la ligne créée par la draft, pas en créer
    une deuxième."""
    draft_df = _draft_df([{"Pk": 1, "Tm": "BOS", "Player": "Rookie One"}])
    parsed, _ = csv_import.parse_draft(draft_df)
    csv_import.apply_draft(parsed, db_session)

    stats_df = pd.DataFrame([{"Player": "Rookie One", "Team": "BOS", "PER": 14.2, "G": 20, "MP": 300}])
    parsed_stats, errors = csv_import.parse_players_advanced(stats_df)
    assert errors == []
    csv_import.apply_players_advanced(parsed_stats, db_session)

    assert db_session.query(Player).filter(Player.name == "Rookie One").count() == 1
    player = db_session.query(Player).filter(Player.name == "Rookie One").one()
    assert player.draft_pick == 1  # conservé
    assert player.per == pytest.approx(14.2)  # mis à jour


# --- Import saison précédente (Étape 6bis) ----------------------------------


def test_apply_teams_home_away_prev_season_writes_prev_season_columns(db_session):
    df = _read("teams_home_away.csv")
    parsed, errors = csv_import.parse_teams_home_away(df)
    assert errors == []

    csv_import.apply_teams_home_away_prev_season(parsed, db_session)

    celtics = db_session.query(Team).filter(Team.abbreviation == "BOS").one()
    assert celtics.win_pct_home_prev_season == pytest.approx(24 / 30)
    assert celtics.win_pct_away_prev_season == pytest.approx(18 / 30)
    # Les colonnes de la saison courante ne doivent pas être touchées.
    assert celtics.win_pct_home == 0.0
    assert celtics.win_pct_away == 0.0


def test_prev_season_players_advanced_ignores_tot_and_keeps_last_team(db_session):
    """Cas réel Basketball-Reference : un joueur échangé en cours de saison
    N-1 a une ligne TOT agrégée + une ligne par équipe jouée. La ligne TOT
    doit être ignorée (pas une erreur), et seule la DERNIÈRE ligne d'équipe
    (l'équipe de fin de saison) doit être conservée."""
    df = pd.DataFrame(
        [
            {"Player": "Traded Player", "Team": "TOT", "PER": 18.5, "G": 60, "MP": 1500},
            {"Player": "Traded Player", "Team": "BOS", "PER": 17.0, "G": 30, "MP": 700},
            {"Player": "Traded Player", "Team": "LAL", "PER": 19.8, "G": 30, "MP": 800},
            {"Player": "Stable Player", "Team": "MIA", "PER": 20.0, "G": 40, "MP": 1000},
        ]
    )
    parsed, errors = csv_import.parse_players_advanced_prev_season(df)
    assert errors == []  # TOT n'est pas une erreur
    assert [p["team_abbreviation"] for p in parsed] == ["BOS", "LAL", "MIA"]

    csv_import.apply_players_advanced_prev_season(parsed, db_session, season="2024-2025")

    traded = (
        db_session.query(PreviousSeasonPlayerStat)
        .filter(PreviousSeasonPlayerStat.player_name == "Traded Player")
        .one()
    )
    assert traded.team_abbreviation == "LAL"  # dernière équipe, pas TOT ni BOS
    assert traded.per == pytest.approx(19.8)  # valeur de la ligne LAL, pas TOT (18.5)
    assert traded.mpg == pytest.approx(800 / 30)

    stable = (
        db_session.query(PreviousSeasonPlayerStat)
        .filter(PreviousSeasonPlayerStat.player_name == "Stable Player")
        .one()
    )
    assert stable.team_abbreviation == "MIA"
    assert stable.per == pytest.approx(20.0)
    assert stable.mpg == pytest.approx(1000 / 40)


def test_prev_season_advanced_alone_sets_both_per_and_mpg(db_session):
    """Depuis la suppression de players_per_game : un seul import Advanced
    (N-1) renseigne à la fois per et mpg (dérivé de MP/G), plus besoin d'un
    second fichier."""
    df = pd.DataFrame([{"Player": "Stable Player", "Team": "MIA", "PER": 20.0, "G": 40, "MP": 1240}])

    parsed, errors = csv_import.parse_players_advanced_prev_season(df)
    assert errors == []
    csv_import.apply_players_advanced_prev_season(parsed, db_session, season="2024-2025")

    stat = db_session.query(PreviousSeasonPlayerStat).filter(
        PreviousSeasonPlayerStat.player_name == "Stable Player"
    ).one()
    assert stat.per == pytest.approx(20.0)
    assert stat.mpg == pytest.approx(31.0)


def test_prev_season_advanced_without_team_column_uses_provided_abbreviation(db_session):
    """Impact sur les rosters N-1 par équipe (Étape 6bis) : même mécanisme
    que la saison courante -- pas de colonne Team, team_abbreviation fourni
    explicitement, ligne "Team Totals" ignorée."""
    df = _read("roster_exemple_equipe_advanced.csv")
    parsed, errors = csv_import.parse_players_advanced_prev_season(df, team_abbreviation="DET")
    assert errors == []
    assert all(item["team_abbreviation"] == "DET" for item in parsed)
    assert all(item["name"] != "Team Totals" for item in parsed)

    csv_import.apply_players_advanced_prev_season(parsed, db_session, season="2024-2025")

    cade = db_session.query(PreviousSeasonPlayerStat).filter(
        PreviousSeasonPlayerStat.player_name == "Cade Cunningham"
    ).one()
    assert cade.team_abbreviation == "DET"
    assert cade.per == pytest.approx(21.6)


def test_prev_season_stat_does_not_pollute_current_player_queries(db_session):
    """Garde-fou explicite : une donnée N-1 pour un joueur qui existe aussi
    dans l'effectif actuel (nom identique) ne doit jamais apparaître dans une
    requête Player courante."""
    team = Team(name="Boston Celtics", abbreviation="BOS")
    db_session.add(team)
    db_session.flush()
    current_player = Player(name="Stable Player", team_id=team.id, per=99.0)
    db_session.add(current_player)
    db_session.flush()

    df = pd.DataFrame([{"Player": "Stable Player", "Team": "MIA", "PER": 20.0, "G": 40, "MP": 1000}])
    parsed, _ = csv_import.parse_players_advanced_prev_season(df)
    csv_import.apply_players_advanced_prev_season(parsed, db_session, season="2024-2025")

    # La donnée N-1 (équipe MIA, PER 20.0) ne doit pas avoir modifié le
    # Player courant (toujours BOS, PER 99.0).
    db_session.refresh(current_player)
    assert current_player.team_id == team.id
    assert current_player.per == pytest.approx(99.0)
    assert db_session.query(Player).filter(Player.name == "Stable Player").count() == 1


# --- Calendrier de saison (Étape 6ter) ---------------------------------------


def _schedule_df(rows: list[dict]) -> pd.DataFrame:
    columns = ["Date", "Start (ET)", "Visitor/Neutral", "PTS", "Home/Neutral", "PTS.1"]
    return pd.DataFrame(rows, columns=columns)


def test_detect_schedule():
    df = _read("calendrier_saison_26_27.csv")
    assert csv_import.detect_import_type(df) == ImportType.SCHEDULE
    assert csv_import.validate_columns(df, ImportType.SCHEDULE) == []


def test_schedule_real_fixture_reports_malformed_rows_as_explicit_errors_by_line_number():
    """Le fichier réel contient 6 en-têtes répétées + 1 ligne vide, dues à un
    assemblage manuel fautif (plusieurs exports mensuels collés sans retirer
    les en-têtes intermédiaires) -- PAS un artefact légitime et garanti comme
    les lignes Tm="TOT" de l'Étape 6bis. Elles doivent remonter comme erreurs
    explicites, identifiées par leur numéro de ligne exact, pas être
    ignorées silencieusement ni comptées dans l'import réussi."""
    df = _read("calendrier_saison_26_27.csv")
    parsed, errors = csv_import.parse_schedule(df)

    assert len(parsed) == 1200
    assert len(errors) == 7

    error_rows = {e["row"]: e["message"] for e in errors}
    for expected_row in [90, 306, 479, 717, 887, 1120]:
        assert expected_row in error_rows
        assert "en-tête" in error_rows[expected_row].lower() or "en-t" in error_rows[expected_row].lower()
    assert 480 in error_rows
    assert "vide" in error_rows[480].lower()


def test_schedule_real_fixture_parsed_rows_have_no_score_yet():
    df = _read("calendrier_saison_26_27.csv")
    parsed, _ = csv_import.parse_schedule(df)
    assert all(item["home_score"] is None and item["away_score"] is None for item in parsed)
    first = parsed[0]
    assert first["game_date"] == date(2026, 10, 20)
    assert first["game_time"] == time(15, 0)
    assert first["away_team_abbreviation"] == "BOS"
    assert first["home_team_abbreviation"] == "DET"


@pytest.mark.parametrize(
    "raw_time, expected",
    [
        ("3:00p", time(15, 0)),
        ("10:30a", time(10, 30)),
        ("12:00p", time(12, 0)),  # midi
        ("12:00a", time(0, 0)),  # minuit
        ("9:00a", time(9, 0)),
    ],
)
def test_parse_schedule_time_edge_cases(raw_time, expected):
    df = _schedule_df(
        [{"Date": "Tue Oct 20 2026", "Start (ET)": raw_time, "Visitor/Neutral": "Boston Celtics",
          "PTS": None, "Home/Neutral": "Detroit Pistons", "PTS.1": None}]
    )
    parsed, errors = csv_import.parse_schedule(df)
    assert errors == []
    assert parsed[0]["game_time"] == expected


def test_parse_schedule_unknown_team_reports_error():
    df = _schedule_df(
        [{"Date": "Tue Oct 20 2026", "Start (ET)": "7:00p", "Visitor/Neutral": "Not A Real Team",
          "PTS": None, "Home/Neutral": "Detroit Pistons", "PTS.1": None}]
    )
    parsed, errors = csv_import.parse_schedule(df)
    assert parsed == []
    assert "inconnue" in errors[0]["message"]


def test_parse_schedule_invalid_date_reports_error():
    df = _schedule_df(
        [{"Date": "Not A Date", "Start (ET)": "7:00p", "Visitor/Neutral": "Boston Celtics",
          "PTS": None, "Home/Neutral": "Detroit Pistons", "PTS.1": None}]
    )
    parsed, errors = csv_import.parse_schedule(df)
    assert parsed == []
    assert "invalide" in errors[0]["message"].lower()


def test_parse_schedule_partial_score_reports_error():
    df = _schedule_df(
        [{"Date": "Tue Oct 20 2026", "Start (ET)": "7:00p", "Visitor/Neutral": "Boston Celtics",
          "PTS": 100, "Home/Neutral": "Detroit Pistons", "PTS.1": None}]
    )
    parsed, errors = csv_import.parse_schedule(df)
    assert parsed == []
    assert "partiel" in errors[0]["message"].lower()


def test_parse_schedule_full_score_marks_finished():
    df = _schedule_df(
        [{"Date": "Tue Oct 20 2026", "Start (ET)": "7:00p", "Visitor/Neutral": "Boston Celtics",
          "PTS": 100, "Home/Neutral": "Detroit Pistons", "PTS.1": 98}]
    )
    parsed, errors = csv_import.parse_schedule(df)
    assert errors == []
    assert parsed[0]["away_score"] == 100
    assert parsed[0]["home_score"] == 98


def test_apply_schedule_creates_scheduled_game_without_score(db_session):
    df = _schedule_df(
        [{"Date": "Tue Oct 20 2026", "Start (ET)": "7:00p", "Visitor/Neutral": "Boston Celtics",
          "PTS": None, "Home/Neutral": "Detroit Pistons", "PTS.1": None}]
    )
    parsed, _ = csv_import.parse_schedule(df)
    count = csv_import.apply_schedule(parsed, db_session, season="2026-2027")

    assert count == 1
    game = db_session.query(Game).one()
    assert game.status == GameStatus.SCHEDULED
    assert game.season == "2026-2027"
    assert game.home_score is None and game.away_score is None
    assert game.game_date.hour == 19


def test_apply_schedule_creates_finished_game_with_score(db_session):
    df = _schedule_df(
        [{"Date": "Tue Oct 20 2026", "Start (ET)": "7:00p", "Visitor/Neutral": "Boston Celtics",
          "PTS": 100, "Home/Neutral": "Detroit Pistons", "PTS.1": 98}]
    )
    parsed, _ = csv_import.parse_schedule(df)
    csv_import.apply_schedule(parsed, db_session, season="2026-2027")

    game = db_session.query(Game).one()
    assert game.status == GameStatus.FINISHED
    assert game.home_score == 98
    assert game.away_score == 100


def test_apply_schedule_upsert_by_date_and_teams_updates_time_without_duplicating(db_session):
    df = _schedule_df(
        [{"Date": "Tue Oct 20 2026", "Start (ET)": "7:00p", "Visitor/Neutral": "Boston Celtics",
          "PTS": None, "Home/Neutral": "Detroit Pistons", "PTS.1": None}]
    )
    parsed, _ = csv_import.parse_schedule(df)
    csv_import.apply_schedule(parsed, db_session, season="2026-2027")

    df2 = _schedule_df(
        [{"Date": "Tue Oct 20 2026", "Start (ET)": "9:30p", "Visitor/Neutral": "Boston Celtics",
          "PTS": None, "Home/Neutral": "Detroit Pistons", "PTS.1": None}]
    )
    parsed2, _ = csv_import.parse_schedule(df2)
    csv_import.apply_schedule(parsed2, db_session, season="2026-2027")

    assert db_session.query(Game).count() == 1
    game = db_session.query(Game).one()
    assert game.game_date.hour == 21 and game.game_date.minute == 30


def test_apply_schedule_never_downgrades_finished_game_on_stale_reimport(db_session):
    scored_df = _schedule_df(
        [{"Date": "Tue Oct 20 2026", "Start (ET)": "7:00p", "Visitor/Neutral": "Boston Celtics",
          "PTS": 100, "Home/Neutral": "Detroit Pistons", "PTS.1": 98}]
    )
    parsed, _ = csv_import.parse_schedule(scored_df)
    csv_import.apply_schedule(parsed, db_session, season="2026-2027")

    stale_df = _schedule_df(
        [{"Date": "Tue Oct 20 2026", "Start (ET)": "7:00p", "Visitor/Neutral": "Boston Celtics",
          "PTS": None, "Home/Neutral": "Detroit Pistons", "PTS.1": None}]
    )
    parsed_stale, _ = csv_import.parse_schedule(stale_df)
    csv_import.apply_schedule(parsed_stale, db_session, season="2026-2027")

    assert db_session.query(Game).count() == 1
    game = db_session.query(Game).one()
    assert game.status == GameStatus.FINISHED
    assert game.home_score == 98
    assert game.away_score == 100


def test_apply_schedule_never_touches_manually_overridden_game(db_session):
    df = _schedule_df(
        [{"Date": "Tue Oct 20 2026", "Start (ET)": "7:00p", "Visitor/Neutral": "Boston Celtics",
          "PTS": None, "Home/Neutral": "Detroit Pistons", "PTS.1": None}]
    )
    parsed, _ = csv_import.parse_schedule(df)
    csv_import.apply_schedule(parsed, db_session, season="2026-2027")

    game = db_session.query(Game).one()
    game.manually_overridden = True
    game.game_date = game.game_date.replace(hour=22, minute=15)
    db_session.flush()

    df2 = _schedule_df(
        [{"Date": "Tue Oct 20 2026", "Start (ET)": "8:00p", "Visitor/Neutral": "Boston Celtics",
          "PTS": 100, "Home/Neutral": "Detroit Pistons", "PTS.1": 98}]
    )
    parsed2, _ = csv_import.parse_schedule(df2)
    csv_import.apply_schedule(parsed2, db_session, season="2026-2027")

    db_session.refresh(game)
    assert game.status == GameStatus.SCHEDULED
    assert game.home_score is None and game.away_score is None
    assert game.game_date.hour == 22 and game.game_date.minute == 15
