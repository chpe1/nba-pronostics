from pathlib import Path

import pandas as pd
import pytest

from app.models import ImportType, Player, PreviousSeasonPlayerStat, Team
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


# --- Draft (nouveau 4e type CSV) --------------------------------------------


def _draft_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_detect_draft():
    df = _draft_df([{"Pk": 1, "Tm": "BOS", "Player": "Rookie One"}])
    assert csv_import.detect_import_type(df) == ImportType.DRAFT


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

    stats_df = pd.DataFrame([{"Player": "Rookie One", "Team": "BOS", "PER": 14.2}])
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
            {"Player": "Traded Player", "Team": "TOT", "PER": 18.5},
            {"Player": "Traded Player", "Team": "BOS", "PER": 17.0},
            {"Player": "Traded Player", "Team": "LAL", "PER": 19.8},
            {"Player": "Stable Player", "Team": "MIA", "PER": 20.0},
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

    stable = (
        db_session.query(PreviousSeasonPlayerStat)
        .filter(PreviousSeasonPlayerStat.player_name == "Stable Player")
        .one()
    )
    assert stable.team_abbreviation == "MIA"
    assert stable.per == pytest.approx(20.0)


def test_prev_season_players_per_game_ignores_tot(db_session):
    df = pd.DataFrame(
        [
            {"Player": "Traded Player", "Team": "TOT", "MP": 30.0},
            {"Player": "Traded Player", "Team": "DET", "MP": 22.0},
            {"Player": "Traded Player", "Team": "CHI", "MP": 28.5},
        ]
    )
    parsed, errors = csv_import.parse_players_per_game_prev_season(df)
    assert errors == []

    csv_import.apply_players_per_game_prev_season(parsed, db_session, season="2024-2025")

    traded = (
        db_session.query(PreviousSeasonPlayerStat)
        .filter(PreviousSeasonPlayerStat.player_name == "Traded Player")
        .one()
    )
    assert traded.team_abbreviation == "CHI"
    assert traded.mpg == pytest.approx(28.5)


def test_prev_season_advanced_and_per_game_merge_on_same_stat_row(db_session):
    """Même principe de mise à jour partielle que Player : les deux fichiers
    (Advanced, Per Game) renseignent chacun un seul champ de la même ligne."""
    advanced_df = pd.DataFrame([{"Player": "Stable Player", "Team": "MIA", "PER": 20.0}])
    per_game_df = pd.DataFrame([{"Player": "Stable Player", "Team": "MIA", "MP": 31.0}])

    parsed_adv, _ = csv_import.parse_players_advanced_prev_season(advanced_df)
    csv_import.apply_players_advanced_prev_season(parsed_adv, db_session, season="2024-2025")
    parsed_pg, _ = csv_import.parse_players_per_game_prev_season(per_game_df)
    csv_import.apply_players_per_game_prev_season(parsed_pg, db_session, season="2024-2025")

    stat = db_session.query(PreviousSeasonPlayerStat).filter(
        PreviousSeasonPlayerStat.player_name == "Stable Player"
    ).one()
    assert stat.per == pytest.approx(20.0)
    assert stat.mpg == pytest.approx(31.0)


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

    df = pd.DataFrame([{"Player": "Stable Player", "Team": "MIA", "PER": 20.0}])
    parsed, _ = csv_import.parse_players_advanced_prev_season(df)
    csv_import.apply_players_advanced_prev_season(parsed, db_session, season="2024-2025")

    # La donnée N-1 (équipe MIA, PER 20.0) ne doit pas avoir modifié le
    # Player courant (toujours BOS, PER 99.0).
    db_session.refresh(current_player)
    assert current_player.team_id == team.id
    assert current_player.per == pytest.approx(99.0)
    assert db_session.query(Player).filter(Player.name == "Stable Player").count() == 1
