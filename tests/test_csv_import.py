import io
from datetime import date, time
from pathlib import Path

import pandas as pd
import pytest

from app.models import Game, GameStatus, ImportType, Player, PreviousSeasonPlayerStat, Settings, Team
from app.services import csv_import

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _read(filename: str):
    return csv_import.read_csv((FIXTURES_DIR / filename).read_bytes())


def test_detect_teams_home_away():
    df = _read("teams_home_away.csv")
    assert csv_import.detect_import_type(df) == ImportType.TEAMS_HOME_AWAY
    assert csv_import.validate_columns(df, ImportType.TEAMS_HOME_AWAY) == []


# --- Résilience au séparateur (Excel FR réenregistre en point-virgule) ------


@pytest.mark.parametrize(
    "content,expected_columns,expected_type",
    [
        (
            b"Team;Home;Road\nBoston Celtics;24-6;18-16\n",
            ["Team", "Home", "Road"],
            ImportType.TEAMS_HOME_AWAY,
        ),
        (
            b"Player;Team;PER;G;MP\nJayson Tatum;BOS;24.3;72;2450\n",
            ["Player", "Team", "PER", "G", "MP"],
            ImportType.PLAYERS_ADVANCED,
        ),
        (
            b"Pk;Tm;Player\n1;BOS;Rookie One\n",
            ["Pk", "Tm", "Player"],
            ImportType.DRAFT,
        ),
        (
            b"Date;Start (ET);Visitor/Neutral;PTS;Home/Neutral;PTS\n"
            b"Tue Oct 20 2026;7:00p;Boston Celtics;;Detroit Pistons;\n",
            ["Date", "Start (ET)", "Visitor/Neutral", "PTS", "Home/Neutral", "PTS.1"],
            ImportType.SCHEDULE,
        ),
    ],
    ids=["teams_home_away", "players_advanced", "draft", "schedule"],
)
def test_read_csv_detects_semicolon_separator_for_every_type(content, expected_columns, expected_type):
    """Détection automatique du séparateur (pas une liste codée en dur) --
    Excel en localisation française réenregistre systématiquement les CSV
    en point-virgule. Vérifié sur les 4 types de fichiers gérés."""
    df = csv_import.read_csv(content)
    assert list(df.columns) == expected_columns
    assert csv_import.detect_import_type(df) == expected_type


def test_read_csv_still_rejects_genuinely_unreadable_content():
    with pytest.raises(csv_import.CsvImportError):
        csv_import.read_csv(b"")


def test_semicolon_separator_and_decimal_comma_combined_players_advanced():
    """Cas réel demandé explicitement : Excel en localisation française
    réenregistre le séparateur de colonnes ET le séparateur décimal
    ensemble à la sauvegarde (jamais l'un sans l'autre) -- PER "24,3" avec
    un point-virgule comme séparateur de colonnes doit être lu comme le
    flottant 24.3, pas rejeté comme "PER invalide"."""
    content = "Player;Team;PER;G;MP\nJayson Tatum;BOS;24,3;72;2450\n".encode("utf-8-sig")
    df = csv_import.read_csv(content)

    parsed, errors = csv_import.parse_players_advanced(df)

    assert errors == []
    assert parsed == [{"name": "Jayson Tatum", "team_abbreviation": "BOS", "per": 24.3, "g": 72.0, "mp": 2450.0}]


def test_comma_separator_keeps_dot_as_decimal_separator():
    """Contrepartie : un vrai fichier séparé par virgule (cas normal) ne
    doit jamais interpréter un point comme séparateur de milliers ou une
    virgule perdue comme décimale -- le point reste le séparateur décimal."""
    content = b"Player,Team,PER,G,MP\nJayson Tatum,BOS,24.3,72,2450\n"
    df = csv_import.read_csv(content)

    parsed, errors = csv_import.parse_players_advanced(df)

    assert errors == []
    assert parsed[0]["per"] == pytest.approx(24.3)


def test_real_classement_file_with_grouped_header_row_is_detected_and_parsed():
    """Vrai fichier Basketball-Reference "Expanded Standings" : même
    problème structurel que le vrai draft.csv (ligne de regroupement
    "Place"/"Conference"/"Division"/"All-Star"/"Margin"/"Month" au-dessus de
    la vraie ligne d'en-tête "Rk,Team,Overall,Home,Road,...") -- jamais
    vérifié sur un vrai export avant ce cas réel. Verrouille le comportement
    corrigé bout en bout (read_csv + detect + parse), même mécanisme
    générique que draft.csv (_promote_grouped_header_if_needed)."""
    df = _read("classement_saison_25_26.csv")
    assert csv_import.detect_import_type(df) == ImportType.TEAMS_HOME_AWAY
    assert csv_import.validate_columns(df, ImportType.TEAMS_HOME_AWAY) == []

    parsed, errors = csv_import.parse_teams_home_away(df)
    assert errors == []
    assert len(parsed) == 30

    thunder = next(item for item in parsed if item["abbreviation"] == "OKC")
    assert thunder["name"] == "Oklahoma City Thunder"
    assert thunder["win_pct_home"] == pytest.approx(34 / 42)
    assert thunder["win_pct_away"] == pytest.approx(30 / 40)


@pytest.mark.parametrize(
    "filename",
    [
        "teams_home_away.csv",
        "players_advanced.csv",
        "roster_exemple_equipe_advanced.csv",
        "calendrier_saison_26_27.csv",
    ],
)
def test_promote_grouped_header_does_not_trigger_on_normally_formed_real_files(filename):
    """Contrepartie du test précédent : un vrai fichier correctement formé
    (une seule ligne d'en-tête, comme la norme -- schedule, players_advanced
    ligue entière, players_advanced par équipe, teams_home_away) ne doit
    jamais être réinterprété par erreur par le mécanisme générique de
    promotion. _promote_grouped_header_if_needed doit laisser le DataFrame
    parfaitement inchangé (mêmes colonnes, même nombre de lignes)."""
    file_bytes = (FIXTURES_DIR / filename).read_bytes()
    raw = pd.read_csv(io.BytesIO(file_bytes), encoding="utf-8-sig")

    result = csv_import._promote_grouped_header_if_needed(raw, file_bytes)

    assert list(result.columns) == list(raw.columns)
    assert len(result) == len(raw)


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
    assert player_a.games_played_this_season == 58


def test_apply_players_advanced_g_zero_gives_mpg_zero(db_session):
    df = pd.DataFrame([{"Player": "Bench Warmer", "Team": "BOS", "PER": 5.0, "G": 0, "MP": 0}])
    parsed, errors = csv_import.parse_players_advanced(df)
    assert errors == []

    csv_import.apply_players_advanced(parsed, db_session)

    player = db_session.query(Player).filter(Player.name == "Bench Warmer").one()
    assert player.mpg == 0.0


def test_parse_players_advanced_rejects_unrealistic_mpg():
    """Point 2 (retour d'usage réel) : mpg dérivé (MP/G) au-delà du maximum
    réaliste sur une saison (~48 min/match) est une erreur de ligne, pas une
    valeur acceptée silencieusement."""
    df = pd.DataFrame([{"Player": "Iron Man", "Team": "BOS", "PER": 20.0, "G": 10, "MP": 500}])  # 50.0 mpg
    parsed, errors = csv_import.parse_players_advanced(df)
    assert parsed == []
    assert len(errors) == 1
    assert "MPG invalide" in errors[0]["message"]


def test_parse_players_advanced_accepts_mpg_at_the_boundary():
    df = pd.DataFrame([{"Player": "Iron Man", "Team": "BOS", "PER": 20.0, "G": 10, "MP": 480}])  # 48.0 mpg
    parsed, errors = csv_import.parse_players_advanced(df)
    assert errors == []
    assert len(parsed) == 1


def test_apply_players_advanced_upsert_is_case_insensitive(db_session):
    """Point 1 (retour d'usage réel) : "LEBRON JAMES" et "LeBron James"
    doivent être reconnus comme le même joueur -- met à jour la ligne
    existante, n'en crée pas une deuxième, et ne réécrit pas la casse déjà
    stockée en base (voir player_matching.py)."""
    team = Team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add(team)
    db_session.flush()
    db_session.add(Player(name="LeBron James", team_id=team.id, per=20.0, mpg=30.0))
    db_session.flush()

    df = pd.DataFrame([{"Player": "LEBRON JAMES", "Team": "LAL", "PER": 25.0, "G": 50, "MP": 1600}])
    parsed, errors = csv_import.parse_players_advanced(df)
    assert errors == []

    csv_import.apply_players_advanced(parsed, db_session)

    assert db_session.query(Player).filter(Player.team_id == team.id).count() == 1
    player = db_session.query(Player).filter(Player.team_id == team.id).one()
    assert player.name == "LeBron James"  # casse d'origine conservée
    assert player.per == pytest.approx(25.0)


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


def test_apply_draft_upsert_is_case_insensitive(db_session):
    """Même garantie que apply_players_advanced, côté draft : un rookie
    draftée puis complétée par un import Advanced avec une casse différente
    doit retrouver la même ligne."""
    draft_df = _draft_df([{"Pk": 1, "Tm": "BOS", "Player": "Rookie One"}])
    parsed, _ = csv_import.parse_draft(draft_df)
    csv_import.apply_draft(parsed, db_session)

    stats_df = pd.DataFrame([{"Player": "ROOKIE ONE", "Team": "BOS", "PER": 14.2, "G": 20, "MP": 300}])
    parsed_stats, errors = csv_import.parse_players_advanced(stats_df)
    assert errors == []
    csv_import.apply_players_advanced(parsed_stats, db_session)

    assert db_session.query(Player).count() == 1
    player = db_session.query(Player).one()
    assert player.name == "Rookie One"  # casse d'origine (draft) conservée
    assert player.draft_pick == 1
    assert player.per == pytest.approx(14.2)


# --- Fermeture du doublon : apply_players_advanced/apply_draft recherchent
# désormais league-wide (find_or_create_player_league_wide), comme
# apply_roster -- plus seulement dans l'équipe du fichier (chantier
# 2026-09-12). ----------------------------------------------------------------


def test_apply_players_advanced_matches_existing_player_through_diacritic_variant(db_session):
    """Cas réel mesuré au chantier ROSTER (13/488 noms) : le futur fichier
    Advanced peut orthographier un nom sans le diacritique déjà stocké en
    base. Avant ce chantier, find_player_by_name (règle stricte) aurait
    manqué le rapprochement et créé un second Player."""
    team = Team(name="Houston Rockets", abbreviation="HOU")
    db_session.add(team)
    db_session.flush()
    db_session.add(Player(name="Bogdan Bogdanović", team_id=team.id, is_active=True))
    db_session.flush()

    df = pd.DataFrame([{"Player": "Bogdan Bogdanovic", "Team": "HOU", "PER": 18.0, "G": 40, "MP": 1000}])
    parsed, errors = csv_import.parse_players_advanced(df)
    assert errors == []

    csv_import.apply_players_advanced(parsed, db_session)

    assert db_session.query(Player).count() == 1  # pas de doublon
    player = db_session.query(Player).one()
    assert player.name == "Bogdan Bogdanović"  # orthographe d'origine jamais réécrite
    assert player.per == pytest.approx(18.0)


def test_apply_players_advanced_moves_player_found_under_another_team(db_session):
    """Le joueur a changé d'équipe depuis le dernier import (27/60 draftés
    dans le vrai fichier ROSTER) : doit être déplacé, jamais dupliqué."""
    old_team = Team(name="Boston Celtics", abbreviation="BOS")
    new_team = Team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add_all([old_team, new_team])
    db_session.flush()
    db_session.add(Player(name="Traded Guy", team_id=old_team.id, draft_pick=12, is_active=True))
    db_session.flush()

    df = pd.DataFrame([{"Player": "Traded Guy", "Team": "LAL", "PER": 14.0, "G": 30, "MP": 600}])
    parsed, errors = csv_import.parse_players_advanced(df)
    assert errors == []

    csv_import.apply_players_advanced(parsed, db_session)

    assert db_session.query(Player).count() == 1  # déplacé, pas dupliqué
    player = db_session.query(Player).one()
    assert player.team.abbreviation == "LAL"
    assert player.draft_pick == 12  # jamais touché par apply_players_advanced
    assert player.per == pytest.approx(14.0)


def test_apply_draft_moves_player_found_under_another_team(db_session):
    """Même mécanisme partagé, côté apply_draft -- un rookie déjà en base
    sous une équipe (ex: import CSV précédent) retrouvé sous une autre est
    déplacé, pas dupliqué."""
    old_team = Team(name="Boston Celtics", abbreviation="BOS")
    new_team = Team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add_all([old_team, new_team])
    db_session.flush()
    db_session.add(Player(name="Rookie One", team_id=old_team.id, per=8.0, is_active=True))
    db_session.flush()

    df = _draft_df([{"Pk": 5, "Tm": "LAL", "Player": "Rookie One"}])
    parsed, errors = csv_import.parse_draft(df)
    assert errors == []

    csv_import.apply_draft(parsed, db_session)

    assert db_session.query(Player).count() == 1
    player = db_session.query(Player).one()
    assert player.team.abbreviation == "LAL"
    assert player.draft_pick == 5
    assert player.per == pytest.approx(8.0)  # jamais touché par apply_draft


def test_league_wide_index_documents_homonym_collision_risk(db_session):
    """Risque déjà accepté ailleurs dans le projet pour la même famille de
    raison (CLAUDE.md, Décision d'architecture n°4 -- pas de désambiguïsation
    d'homonymes) : deux joueurs RÉELLEMENT différents partageant la même
    _roster_match_key, sur deux équipes différentes, ne peuvent pas
    cohabiter dans l'index league-wide (une seule entrée par clé). Ce test
    ne "corrige" rien -- il rend le comportement visible et vérifiable
    plutôt que silencieux, comme demandé."""
    team_a = Team(name="Boston Celtics", abbreviation="BOS")
    team_b = Team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add_all([team_a, team_b])
    db_session.flush()
    # Deux "Chris Johnson" réellement distincts, sur deux équipes.
    db_session.add_all(
        [
            Player(name="Chris Johnson", team_id=team_a.id, per=5.0, is_active=True),
            Player(name="Chris Johnson", team_id=team_b.id, per=9.0, is_active=True),
        ]
    )
    db_session.flush()

    index = csv_import.build_active_player_index(db_session)
    # Une seule entrée survit pour la clé partagée -- l'ordre de la requête
    # (non trié) décide laquelle, pas une logique de désambiguïsation.
    assert sum(1 for name in ["Chris Johnson"] if csv_import._roster_match_key(name) in index) == 1


def test_create_or_upsert_player_league_wide_helper_never_creates_duplicate_on_repeat_call(db_session):
    """Non-régression directe sur find_or_create_player_league_wide : un
    même nom rencontré deux fois d'affilée (même index, non reconstruit)
    retrouve la ligne qu'il vient de créer, ne la duplique pas."""
    team = Team(name="Boston Celtics", abbreviation="BOS")
    db_session.add(team)
    db_session.flush()

    index = csv_import.build_active_player_index(db_session)
    player1, created1 = csv_import.find_or_create_player_league_wide(db_session, index, "New Guy", team)
    player2, created2 = csv_import.find_or_create_player_league_wide(db_session, index, "New Guy", team)

    assert created1 is True
    assert created2 is False
    assert player1.id == player2.id
    assert db_session.query(Player).count() == 1


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


def test_prev_season_players_advanced_ignores_nTM_and_keeps_last_team(db_session):
    """Découvert le 2026-08-27 sur un vrai export ligue entière : la table
    Advanced n'utilise pas "TOT" pour la ligne agrégée d'un joueur échangé,
    mais "2TM"/"3TM"/"4TM"... (nombre d'équipes jouées) -- même artefact
    garanti que TOT, à ignorer silencieusement de la même façon (voir
    _is_aggregate_team_marker)."""
    df = pd.DataFrame(
        [
            {"Player": "Traded Player", "Team": "2TM", "PER": 18.5, "G": 60, "MP": 1500},
            {"Player": "Traded Player", "Team": "BOS", "PER": 17.0, "G": 30, "MP": 700},
            {"Player": "Traded Player", "Team": "LAL", "PER": 19.8, "G": 30, "MP": 800},
            {"Player": "Well Traveled", "Team": "3TM", "PER": 10.0, "G": 60, "MP": 900},
            {"Player": "Well Traveled", "Team": "MIA", "PER": 9.0, "G": 40, "MP": 500},
        ]
    )
    parsed, errors = csv_import.parse_players_advanced_prev_season(df)
    assert errors == []  # 2TM/3TM ne sont pas des erreurs
    assert [p["team_abbreviation"] for p in parsed] == ["BOS", "LAL", "MIA"]

    csv_import.apply_players_advanced_prev_season(parsed, db_session, season="2024-2025")

    traded = (
        db_session.query(PreviousSeasonPlayerStat)
        .filter(PreviousSeasonPlayerStat.player_name == "Traded Player")
        .one()
    )
    assert traded.team_abbreviation == "LAL"  # dernière équipe, pas 2TM ni BOS
    assert traded.per == pytest.approx(19.8)


def test_prev_season_players_advanced_ignores_league_average_row():
    """Découvert le 2026-08-27 sur le même vrai fichier que le cas 2TM/3TM :
    l'export ligue entière se termine par une ligne "League Average" (colonne
    Team vide -- pandas la lit comme NaN, donc str(NaN) donne littéralement
    "nan", pas une chaîne vide). Artefact garanti du format source comme
    "Team Totals", à ignorer silencieusement (voir _AGGREGATE_PLAYER_MARKERS)."""
    df = pd.DataFrame(
        [
            {"Player": "Stable Player", "Team": "MIA", "PER": 20.0, "G": 40, "MP": 1000},
            {"Player": "League Average", "Team": None, "PER": 14.2, "G": None, "MP": None},
        ]
    )
    parsed, errors = csv_import.parse_players_advanced_prev_season(df)
    assert errors == []  # "League Average" n'est pas une erreur
    assert [p["name"] for p in parsed] == ["Stable Player"]


def test_parse_players_advanced_ignores_league_average_row():
    """Même artefact, côté saison courante (parse_players_advanced)."""
    df = pd.DataFrame(
        [
            {"Player": "Stable Player", "Team": "MIA", "PER": 20.0, "G": 40, "MP": 1000},
            {"Player": "League Average", "Team": None, "PER": 14.2, "G": None, "MP": None},
        ]
    )
    parsed, errors = csv_import.parse_players_advanced(df)
    assert errors == []
    assert [p["name"] for p in parsed] == ["Stable Player"]


def test_parse_players_advanced_prev_season_rejects_unrealistic_mpg():
    df = pd.DataFrame([{"Player": "Iron Man", "Team": "BOS", "PER": 20.0, "G": 10, "MP": 500}])  # 50.0 mpg
    parsed, errors = csv_import.parse_players_advanced_prev_season(df)
    assert parsed == []
    assert len(errors) == 1
    assert "MPG invalide" in errors[0]["message"]


def test_prev_season_advanced_upsert_is_case_insensitive(db_session):
    """Point 1 (retour d'usage réel) : même garantie côté import N-1
    (apply_players_advanced_prev_season / _upsert_prev_season_stat) -- une
    casse différente de celle déjà en base met à jour la ligne existante."""
    db_session.add(
        PreviousSeasonPlayerStat(
            season="2024-2025", player_name="LeBron James", team_abbreviation="LAL", per=20.0, mpg=30.0
        )
    )
    db_session.flush()

    df = pd.DataFrame([{"Player": "LEBRON JAMES", "Team": "LAL", "PER": 22.0, "G": 50, "MP": 1600}])
    parsed, errors = csv_import.parse_players_advanced_prev_season(df)
    assert errors == []
    csv_import.apply_players_advanced_prev_season(parsed, db_session, season="2024-2025")

    stats = db_session.query(PreviousSeasonPlayerStat).filter(
        PreviousSeasonPlayerStat.season == "2024-2025"
    ).all()
    assert len(stats) == 1
    assert stats[0].player_name == "LeBron James"  # casse d'origine conservée
    assert stats[0].per == pytest.approx(22.0)


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


# --- Modèles CSV téléchargeables ---------------------------------------------


def test_generate_template_csv_unknown_key_raises():
    with pytest.raises(ValueError):
        csv_import.generate_template_csv("not_a_real_key")


@pytest.mark.parametrize("key", csv_import.TEMPLATE_KEYS)
def test_generate_template_csv_has_header_and_non_empty_example_row(key):
    content = csv_import.generate_template_csv(key)
    lines = content.strip("\r\n").split("\r\n")
    assert len(lines) == 2
    header = lines[0].split(",")
    example = lines[1].split(",")
    assert len(header) == len(example)
    assert all(cell.strip() != "" for cell in example)


def test_generate_template_players_advanced_league_includes_team_column():
    content = csv_import.generate_template_csv("players_advanced_league")
    header = content.splitlines()[0].split(",")
    assert header == ["Player", "Team", "PER", "G", "MP"]


def test_generate_template_players_advanced_team_excludes_team_column():
    content = csv_import.generate_template_csv("players_advanced_team")
    header = content.splitlines()[0].split(",")
    assert "Team" not in header
    assert header == ["Player", "PER", "G", "MP"]


def test_generate_template_columns_match_required_columns_order():
    """Vérifie que le modèle est bien dérivé de REQUIRED_COLUMNS (même ordre,
    même source de vérité que la validation à l'import), pas d'une liste
    recopiée séparément."""
    for key, import_type in [
        ("teams_home_away", ImportType.TEAMS_HOME_AWAY),
        ("players_advanced_team", ImportType.PLAYERS_ADVANCED),
        ("draft", ImportType.DRAFT),
        ("schedule", ImportType.SCHEDULE),
    ]:
        header = csv_import.generate_template_csv(key).splitlines()[0].split(",")
        assert header == list(csv_import.REQUIRED_COLUMNS[import_type])


def test_every_required_column_has_an_example_value():
    """Test anti-désynchronisation demandé explicitement : si une future
    colonne requise est ajoutée à REQUIRED_COLUMNS sans exemple associé,
    ce test échoue bruyamment plutôt que de produire un modèle avec une
    cellule vide (ou un KeyError en prod)."""
    all_required_columns = {
        column
        for columns in csv_import.REQUIRED_COLUMNS.values()
        for column in columns
    }
    all_required_columns.add("Team")  # réintégré pour players_advanced_league
    missing = all_required_columns - csv_import._EXAMPLE_VALUES.keys()
    assert missing == set()


# --- Effectif complet (type ROSTER) ------------------------------------------


def _settings(**overrides) -> Settings:
    defaults = dict(current_season="2026-2027")
    defaults.update(overrides)
    return Settings(**defaults)


def test_detect_roster():
    df = pd.DataFrame(
        [{"Player": "Rookie One", "Team": "BOS", "Number": 0, "Position": "G", "Height": "6-2",
          "Weight": 180, "Last Attended": "College", "Country": "USA"}]
    )
    assert csv_import.detect_import_type(df) == ImportType.ROSTER
    assert csv_import.validate_columns(df, ImportType.ROSTER) == []


def test_detect_players_advanced_league_is_never_confused_with_roster():
    """Non-régression sur la contrainte d'ordre de detect_import_type : un
    export Advanced ligue entière a lui aussi Player ET Team, en plus de
    PER/G/MP -- doit rester détecté comme PLAYERS_ADVANCED, jamais ROSTER."""
    df = pd.DataFrame([{"Player": "Jayson Tatum", "Team": "BOS", "PER": 24.3, "G": 72, "MP": 2450}])
    assert csv_import.detect_import_type(df) == ImportType.PLAYERS_ADVANCED


def test_parse_roster_extracts_name_and_team_ignores_other_columns():
    df = pd.DataFrame(
        [{"Player": "Rookie One", "Team": "BOS", "Number": 0, "Position": "G", "Height": "6-2",
          "Weight": 180, "Last Attended": "College", "Country": "USA"}]
    )
    parsed, errors = csv_import.parse_roster(df)
    assert errors == []
    assert parsed == [{"name": "Rookie One", "team_abbreviation": "BOS"}]


def test_parse_roster_missing_player_or_team_reports_error():
    df = pd.DataFrame([{"Player": "", "Team": "BOS"}, {"Player": "Someone", "Team": ""}])
    parsed, errors = csv_import.parse_roster(df)
    assert parsed == []
    assert len(errors) == 2
    assert all("manquante" in e["message"] for e in errors)


def test_parse_roster_unknown_team_reports_error():
    df = pd.DataFrame([{"Player": "Someone", "Team": "ZZZ"}])
    parsed, errors = csv_import.parse_roster(df)
    assert parsed == []
    assert "inconnue" in errors[0]["message"]


def test_parse_roster_normalizes_basketball_reference_abbreviations():
    """Réutilise normalize_abbreviation (BRK/PHO/CHO), comme parse_draft --
    pas une nouvelle règle inventée pour ce type."""
    df = pd.DataFrame([{"Player": "Someone", "Team": "BRK"}])
    parsed, errors = csv_import.parse_roster(df)
    assert errors == []
    assert parsed[0]["team_abbreviation"] == "BKN"


# --- _roster_match_key : normalisation locale au chantier --------------------


@pytest.mark.parametrize(
    "a,b",
    [
        ("Jimmy Butler III", "Jimmy Butler"),
        ("DaRon Holmes II", "DaRon Holmes"),
        ("GG Jackson", "GG Jackson II"),
        ("Xavier Tillman", "Xavier Tillman Sr."),
        ("Walter Clayton Jr.", "Walter Clayton"),
        ("Terrence Shannon Jr", "Terrence Shannon Jr."),
        ("AJ Green", "A.J. Green"),
        ("Alperen Sengun", "Alperen Şengün"),
        ("Nolan Traore", "Nolan Traoré"),
        ("David Jones Garcia", "David Jones García"),
    ],
    ids=[
        "suffix-iii", "suffix-ii-a", "suffix-ii-b", "suffix-sr", "suffix-jr-dot",
        "suffix-jr-nodot", "punctuation", "diacritic-turkish", "diacritic-french",
        "diacritic-spanish",
    ],
)
def test_roster_match_key_folds_diacritics_punctuation_and_suffixes(a, b):
    assert csv_import._roster_match_key(a) == csv_import._roster_match_key(b)


def test_roster_match_key_does_not_conflate_unrelated_players_with_close_spelling():
    """Non-régression sur le faux positif mesuré au constat : "Caleb Wilson"
    est à distance de Levenshtein 2 de "Jalen Wilson" (joueurs sans rapport)
    -- la clé de rapprochement doit les garder distincts, la distance ne
    devant jamais servir de critère de fusion automatique."""
    assert csv_import._roster_match_key("Caleb Wilson") != csv_import._roster_match_key("Jalen Wilson")
    # La distance existe bel et bien (c'est justement pour ça que Levenshtein
    # seul est dangereux) -- mais reste une suggestion, jamais une fusion.
    assert csv_import._levenshtein_distance("caleb wilson", "jalen wilson") == 2


def test_roster_match_key_does_not_fold_genuine_first_name_differences():
    """Contrepartie : un vrai prénom différent ("Ronald" vs "Ron") ne doit
    jamais être considéré comme une variante cosmétique, même si les deux
    noms partagent le même nom de famille et un suffixe."""
    assert csv_import._roster_match_key("Ronald Holland II") != csv_import._roster_match_key("Ron Holland")


# --- analyze_roster_import : les 5 sections du récapitulatif ----------------


@pytest.fixture()
def roster_analysis_fixture(db_session):
    """Effectif "avant import" + stats N-1, construit pour exercer les 5
    sections en une seule fois (voir plan du chantier, point b) :
    - "Rookie One" (BOS, draft_pick=5) : déjà en base, CSV le confirme sur la
      même équipe -- pas de ligne N-1, mais draft_pick connu -> jamais signalé
      en section 5 (rookie normal).
    - "Traded Veteran" (BOS, sans draft_pick) : le CSV le place à LAL -> doit
      apparaître en section 4 (déplacé) et section 5 (pas de ligne N-1, pas de
      draft_pick).
    - "Departed Veteran" (LAL) : absent du CSV -> section 3 (orphelin).
    - "Star Player" : ligne N-1 (LAL) réclamée exactement par le CSV ->
      section 1 (rapproché), pas de joueur existant avant import.
    - "Marcus Example" : ligne N-1 (BOS) jamais réclamée par le CSV -> sert
      de candidat de suggestion pour "Marcuz Example" (section 2)."""
    db_session.add(_settings())
    bos = Team(name="Boston Celtics", abbreviation="BOS")
    lal = Team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add_all([bos, lal])
    db_session.flush()

    db_session.add_all(
        [
            Player(name="Rookie One", team_id=bos.id, draft_pick=5, is_active=True),
            Player(name="Traded Veteran", team_id=bos.id, per=15.0, mpg=20.0, is_active=True),
            Player(name="Departed Veteran", team_id=lal.id, is_active=True),
            PreviousSeasonPlayerStat(
                season="2025-2026", player_name="Star Player", team_abbreviation="LAL", per=25.0, mpg=32.0
            ),
            PreviousSeasonPlayerStat(
                season="2025-2026", player_name="Marcus Example", team_abbreviation="BOS", per=10.0, mpg=18.0
            ),
        ]
    )
    db_session.flush()

    parsed = [
        {"name": "Rookie One", "team_abbreviation": "BOS"},
        {"name": "Traded Veteran", "team_abbreviation": "LAL"},
        {"name": "Marcuz Example", "team_abbreviation": "BOS"},
        {"name": "Star Player", "team_abbreviation": "LAL"},
    ]
    return parsed


def test_analyze_roster_import_matched_count(db_session, roster_analysis_fixture):
    analysis = csv_import.analyze_roster_import(db_session, roster_analysis_fixture)
    assert analysis.matched_count == 1  # seul "Star Player" a une ligne N-1 réclamée exactement


def test_analyze_roster_import_unmatched_with_suggestion(db_session, roster_analysis_fixture):
    analysis = csv_import.analyze_roster_import(db_session, roster_analysis_fixture)
    by_name = {u.name: u for u in analysis.unmatched}
    assert set(by_name) == {"Rookie One", "Traded Veteran", "Marcuz Example"}
    # "Marcuz Example" est une coquille à distance 1 de "Marcus Example", la
    # seule ligne N-1 non réclamée -- suggestion attendue précisément.
    assert by_name["Marcuz Example"].closest_match == "Marcus Example"
    assert by_name["Marcuz Example"].distance == 1


def test_analyze_roster_import_orphans(db_session, roster_analysis_fixture):
    analysis = csv_import.analyze_roster_import(db_session, roster_analysis_fixture)
    assert analysis.orphans == ["Departed Veteran"]


def test_analyze_roster_import_moved(db_session, roster_analysis_fixture):
    analysis = csv_import.analyze_roster_import(db_session, roster_analysis_fixture)
    assert len(analysis.moved) == 1
    assert analysis.moved[0].name == "Traded Veteran"
    assert analysis.moved[0].from_team == "BOS"
    assert analysis.moved[0].to_team == "LAL"


def test_analyze_roster_import_no_prior_data_excludes_known_rookie(db_session, roster_analysis_fixture):
    """Critère corrigé (voir plan révisé) : sans ligne N-1 ET sans
    draft_pick connu -> signalé. "Rookie One" a un draft_pick -> jamais
    signalé, même sans ligne N-1."""
    analysis = csv_import.analyze_roster_import(db_session, roster_analysis_fixture)
    assert set(analysis.no_prior_data) == {"Traded Veteran", "Marcuz Example"}
    assert "Rookie One" not in analysis.no_prior_data


def test_analyze_roster_import_never_writes_to_db(db_session, roster_analysis_fixture):
    """Lecture seule : aucun db.add/flush ne doit avoir créé, modifié ou
    déplacé quoi que ce soit (voir plan du chantier, point a)."""
    players_before = {p.id: (p.team_id, p.draft_pick) for p in db_session.query(Player).all()}
    csv_import.analyze_roster_import(db_session, roster_analysis_fixture)
    players_after = {p.id: (p.team_id, p.draft_pick) for p in db_session.query(Player).all()}
    assert players_before == players_after
    assert db_session.query(Player).count() == 3  # aucune création


# --- apply_roster : écriture, idempotence, arbitrages -----------------------


def test_apply_roster_creates_new_players_with_defaults(db_session):
    df = pd.DataFrame([{"Player": "Brand New Guy", "Team": "BOS"}])
    parsed, errors = csv_import.parse_roster(df)
    assert errors == []

    count = csv_import.apply_roster(parsed, db_session)

    assert count == 1
    player = db_session.query(Player).filter(Player.name == "Brand New Guy").one()
    assert player.team.abbreviation == "BOS"
    assert player.per == 0.0
    assert player.mpg == 0.0
    assert player.draft_pick is None
    assert player.is_active is True
    assert player.previous_team_id is None


def test_apply_roster_moves_existing_player_preserving_draft_pick_and_games_played(db_session):
    """Cœur de l'arbitrage 4 : rapprochement par nom seul -> déplacement,
    jamais duplication -- draft_pick/games_played_this_season/per/mpg tous
    préservés tels quels."""
    bos = Team(name="Boston Celtics", abbreviation="BOS")
    lal = Team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add_all([bos, lal])
    db_session.flush()
    db_session.add(
        Player(
            name="Star Rookie", team_id=bos.id, draft_pick=3,
            games_played_this_season=12, per=8.5, mpg=22.0, is_active=True,
        )
    )
    db_session.flush()

    parsed = [{"name": "Star Rookie", "team_abbreviation": "LAL"}]
    count = csv_import.apply_roster(parsed, db_session)

    assert count == 1
    assert db_session.query(Player).count() == 1  # déplacé, pas dupliqué
    player = db_session.query(Player).filter(Player.name == "Star Rookie").one()
    assert player.team.abbreviation == "LAL"
    assert player.draft_pick == 3
    assert player.games_played_this_season == 12
    assert player.per == pytest.approx(8.5)
    assert player.mpg == pytest.approx(22.0)


def test_apply_roster_matches_existing_player_through_diacritic_and_suffix_variants(db_session):
    """Le déplacement utilise la même clé que l'analyse (_roster_match_key)
    -- une variante orthographique du CSV ne doit jamais créer un doublon."""
    bos = Team(name="Boston Celtics", abbreviation="BOS")
    lal = Team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add_all([bos, lal])
    db_session.flush()
    db_session.add(Player(name="Alperen Sengun", team_id=bos.id, is_active=True))
    db_session.flush()

    parsed = [{"name": "Alperen Şengün", "team_abbreviation": "LAL"}]
    csv_import.apply_roster(parsed, db_session)

    assert db_session.query(Player).count() == 1
    player = db_session.query(Player).one()
    assert player.team.abbreviation == "LAL"
    assert player.name == "Alperen Sengun"  # casse/orthographe d'origine jamais réécrite


def test_apply_roster_never_touches_per_mpg_on_a_matched_player(db_session):
    bos = Team(name="Boston Celtics", abbreviation="BOS")
    db_session.add(bos)
    db_session.flush()
    db_session.add(Player(name="Same Team Guy", team_id=bos.id, per=12.0, mpg=25.0, is_active=True))
    db_session.flush()

    parsed = [{"name": "Same Team Guy", "team_abbreviation": "BOS"}]
    csv_import.apply_roster(parsed, db_session)

    player = db_session.query(Player).filter(Player.name == "Same Team Guy").one()
    assert player.per == pytest.approx(12.0)
    assert player.mpg == pytest.approx(25.0)


def test_apply_roster_never_deactivates_players_absent_from_file(db_session):
    lal = Team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add(lal)
    db_session.flush()
    db_session.add(Player(name="Not In This File", team_id=lal.id, is_active=True))
    db_session.flush()

    parsed = [{"name": "Someone Else Entirely", "team_abbreviation": "LAL"}]
    csv_import.apply_roster(parsed, db_session)

    player = db_session.query(Player).filter(Player.name == "Not In This File").one()
    assert player.is_active is True


def test_apply_roster_is_idempotent(db_session):
    """Arbitrage 4 : relancer le même import ne duplique rien -- deuxième
    passage sans effet, y compris sur les lignes déplacées au premier."""
    bos = Team(name="Boston Celtics", abbreviation="BOS")
    lal = Team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add_all([bos, lal])
    db_session.flush()
    db_session.add(Player(name="Moving Target", team_id=bos.id, draft_pick=7, is_active=True))
    db_session.flush()

    parsed = [
        {"name": "Moving Target", "team_abbreviation": "LAL"},
        {"name": "Fresh Face", "team_abbreviation": "LAL"},
    ]

    first_count = csv_import.apply_roster(parsed, db_session)
    assert first_count == 2
    assert db_session.query(Player).count() == 2

    snapshot = {
        p.name: (p.team_id, p.draft_pick, p.per, p.mpg) for p in db_session.query(Player).all()
    }

    second_count = csv_import.apply_roster(parsed, db_session)
    assert second_count == 2
    assert db_session.query(Player).count() == 2  # aucun doublon créé
    after = {p.name: (p.team_id, p.draft_pick, p.per, p.mpg) for p in db_session.query(Player).all()}
    assert after == snapshot  # rien n'a bougé au second passage
