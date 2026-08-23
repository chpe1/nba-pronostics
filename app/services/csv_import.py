"""Import des exports CSV Basketball-Reference (téléchargés manuellement).

Trois types de fichiers reconnus :
- teams_home_away  : table "Expanded Standings" (colonnes Team/Home/Road) -> Team.win_pct_home/away
- players_advanced : table "Advanced" (colonne PER)                       -> Player.per
- players_per_game : table "Per Game" (colonne MP = minutes/match)        -> Player.mpg
"""
from __future__ import annotations

import io

import pandas as pd
from sqlalchemy.orm import Session

from app.models import ImportType, Player, Team
from app.services.nba_teams import ABBREVIATION_TO_NAME, NBA_TEAMS, resolve_team_name

REQUIRED_COLUMNS: dict[ImportType, set[str]] = {
    ImportType.TEAMS_HOME_AWAY: {"Team", "Home", "Road"},
    ImportType.PLAYERS_ADVANCED: {"Player", "Team", "PER"},
    ImportType.PLAYERS_PER_GAME: {"Player", "Team", "MP"},
}


class CsvImportError(Exception):
    """Erreur bloquante : fichier illisible ou type non détectable."""


def read_csv(file_bytes: bytes) -> pd.DataFrame:
    try:
        df = pd.read_csv(io.BytesIO(file_bytes), encoding="utf-8-sig")
    except (UnicodeDecodeError, pd.errors.ParserError) as exc:
        raise CsvImportError(f"Fichier CSV illisible : {exc}") from exc
    # Basketball-Reference intercale des colonnes vides séparatrices entre
    # groupes de statistiques (héritées du HTML source) -> pandas les nomme
    # "Unnamed: N".
    df = df.loc[:, ~df.columns.astype(str).str.match(r"^Unnamed")]
    df.columns = [str(c).strip() for c in df.columns]
    return df


def detect_import_type(df: pd.DataFrame) -> ImportType | None:
    columns = set(df.columns)
    if {"Player", "PER"}.issubset(columns):
        return ImportType.PLAYERS_ADVANCED
    if {"Player", "MP"}.issubset(columns) and "PER" not in columns:
        return ImportType.PLAYERS_PER_GAME
    if {"Team", "Home", "Road"}.issubset(columns):
        return ImportType.TEAMS_HOME_AWAY
    return None


def validate_columns(df: pd.DataFrame, import_type: ImportType) -> list[str]:
    """Retourne la liste des colonnes requises manquantes (triée)."""
    required = REQUIRED_COLUMNS[import_type]
    return sorted(required - set(df.columns))


def _parse_win_loss(value: object) -> tuple[int, int] | None:
    try:
        wins_str, losses_str = str(value).split("-")
        return int(wins_str), int(losses_str)
    except (ValueError, AttributeError):
        return None


def parse_teams_home_away(df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    parsed: list[dict] = []
    errors: list[dict] = []
    for idx, row in df.iterrows():
        row_num = int(idx) + 2  # +1 en-tête, +1 index 1-based
        raw_name = str(row.get("Team", "")).strip()
        full_name = resolve_team_name(raw_name)
        if full_name is None:
            errors.append({"row": row_num, "message": f"Équipe inconnue : {raw_name!r}"})
            continue

        home = _parse_win_loss(row.get("Home"))
        road = _parse_win_loss(row.get("Road"))
        if home is None or road is None:
            errors.append(
                {"row": row_num, "message": f"Format Home/Road invalide pour {full_name}"}
            )
            continue

        home_wins, home_losses = home
        road_wins, road_losses = road
        home_total = home_wins + home_losses
        road_total = road_wins + road_losses
        parsed.append(
            {
                "name": full_name,
                "abbreviation": NBA_TEAMS[full_name],
                "win_pct_home": (home_wins / home_total) if home_total else 0.0,
                "win_pct_away": (road_wins / road_total) if road_total else 0.0,
            }
        )
    return parsed, errors


def _parse_players_common(
    df: pd.DataFrame, value_column: str, output_key: str
) -> tuple[list[dict], list[dict]]:
    parsed: list[dict] = []
    errors: list[dict] = []
    for idx, row in df.iterrows():
        row_num = int(idx) + 2
        name = str(row.get("Player", "")).strip()
        team_abbr = str(row.get("Team", "")).strip()
        if not name or not team_abbr:
            errors.append({"row": row_num, "message": "Colonne Player ou Team manquante"})
            continue
        if team_abbr not in ABBREVIATION_TO_NAME:
            errors.append({"row": row_num, "message": f"Équipe inconnue : {team_abbr!r}"})
            continue
        try:
            value = float(row[value_column])
        except (ValueError, TypeError, KeyError):
            errors.append(
                {"row": row_num, "message": f"{value_column} invalide pour {name!r}"}
            )
            continue
        parsed.append({"name": name, "team_abbreviation": team_abbr, output_key: value})
    return parsed, errors


def parse_players_advanced(df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    return _parse_players_common(df, value_column="PER", output_key="per")


def parse_players_per_game(df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    return _parse_players_common(df, value_column="MP", output_key="mpg")


def apply_teams_home_away(parsed: list[dict], db: Session) -> int:
    count = 0
    for item in parsed:
        team = db.query(Team).filter(Team.abbreviation == item["abbreviation"]).one_or_none()
        if team is None:
            team = Team(name=item["name"], abbreviation=item["abbreviation"])
            db.add(team)
        team.win_pct_home = item["win_pct_home"]
        team.win_pct_away = item["win_pct_away"]
        count += 1
    db.flush()
    return count


def _get_or_create_team(db: Session, abbreviation: str) -> Team:
    team = db.query(Team).filter(Team.abbreviation == abbreviation).one_or_none()
    if team is None:
        team = Team(name=ABBREVIATION_TO_NAME[abbreviation], abbreviation=abbreviation)
        db.add(team)
        db.flush()
    return team


def apply_players_advanced(parsed: list[dict], db: Session) -> int:
    count = 0
    for item in parsed:
        team = _get_or_create_team(db, item["team_abbreviation"])
        player = (
            db.query(Player)
            .filter(Player.name == item["name"], Player.team_id == team.id)
            .one_or_none()
        )
        if player is None:
            player = Player(name=item["name"], team_id=team.id)
            db.add(player)
        player.per = item["per"]
        count += 1
    db.flush()
    return count


def apply_players_per_game(parsed: list[dict], db: Session) -> int:
    count = 0
    for item in parsed:
        team = _get_or_create_team(db, item["team_abbreviation"])
        player = (
            db.query(Player)
            .filter(Player.name == item["name"], Player.team_id == team.id)
            .one_or_none()
        )
        if player is None:
            player = Player(name=item["name"], team_id=team.id)
            db.add(player)
        player.mpg = item["mpg"]
        count += 1
    db.flush()
    return count


PARSERS = {
    ImportType.TEAMS_HOME_AWAY: parse_teams_home_away,
    ImportType.PLAYERS_ADVANCED: parse_players_advanced,
    ImportType.PLAYERS_PER_GAME: parse_players_per_game,
}

APPLIERS = {
    ImportType.TEAMS_HOME_AWAY: apply_teams_home_away,
    ImportType.PLAYERS_ADVANCED: apply_players_advanced,
    ImportType.PLAYERS_PER_GAME: apply_players_per_game,
}
