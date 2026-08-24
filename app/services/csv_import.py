"""Import des exports CSV Basketball-Reference (téléchargés manuellement).

Cinq types de fichiers reconnus :
- teams_home_away  : table "Expanded Standings" (colonnes Team/Home/Road) -> Team.win_pct_home/away
- players_advanced : table "Advanced" (colonne PER)                       -> Player.per
- players_per_game : table "Per Game" (colonne MP = minutes/match)        -> Player.mpg
- draft             : table de la page Draft (colonnes Pk/Tm/Player)       -> Player (création rookie) + draft_pick
- schedule          : export "Games" (colonnes Date/Start (ET)/Visitor/Home) -> Game (upsert)

Chacun des trois premiers types peut en plus être importé pour la saison
PRÉCÉDENTE (season_type="previous", voir app/api/imports.py) : les données
vont alors dans Team.*_prev_season ou dans PreviousSeasonPlayerStat (jamais
dans Player/Team courants), pour la détection des transferts (Étape 6bis).
"""
from __future__ import annotations

import io
import re
from datetime import datetime, time, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app.models import Game, GameStatus, ImportType, Player, PreviousSeasonPlayerStat, Team
from app.services.nba_teams import ABBREVIATION_TO_NAME, NBA_TEAMS, resolve_team_name

REQUIRED_COLUMNS: dict[ImportType, set[str]] = {
    ImportType.TEAMS_HOME_AWAY: {"Team", "Home", "Road"},
    ImportType.PLAYERS_ADVANCED: {"Player", "Team", "PER"},
    ImportType.PLAYERS_PER_GAME: {"Player", "Team", "MP"},
    ImportType.DRAFT: {"Pk", "Tm", "Player"},
    ImportType.SCHEDULE: {"Date", "Start (ET)", "Visitor/Neutral", "Home/Neutral"},
}

# Basketball-Reference ajoute une ligne agrégée "TOT" (toutes équipes
# confondues) pour un joueur échangé en cours de saison, en plus d'une ligne
# par équipe jouée. Sans objet pour nous : jamais une "vraie" équipe.
_AGGREGATE_TEAM_MARKER = "TOT"

_SCHEDULE_TIME_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})([ap])$", re.IGNORECASE)


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
    if {"Date", "Visitor/Neutral", "Home/Neutral"}.issubset(columns):
        return ImportType.SCHEDULE
    if {"Pk", "Tm", "Player"}.issubset(columns):
        return ImportType.DRAFT
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


def _parse_players_common_prev_season(
    df: pd.DataFrame, value_column: str, output_key: str
) -> tuple[list[dict], list[dict]]:
    """Variante de `_parse_players_common` pour un import saison N-1.

    Les exports Advanced/Per Game de Basketball-Reference contiennent, pour
    un joueur échangé en cours de saison N-1, une ligne par équipe jouée
    *plus* une ligne agrégée `Tm="TOT"`. Cette ligne TOT est ignorée
    silencieusement ici (ce n'est pas une erreur, juste une ligne à ne pas
    importer) -- contrairement à `_parse_players_common`, qui la rejetterait
    comme "équipe inconnue" puisqu'elle n'est utilisée que pour la saison
    courante, où ce cas ne se présente pas dans notre usage.

    Quand plusieurs lignes d'équipe réelles existent pour un même joueur
    (trade en cours de saison N-1), elles sont toutes conservées dans
    l'ordre du fichier : c'est l'upsert de `apply_*_prev_season` (par
    `(season, player_name)`, sans l'équipe dans la clé) qui ne garde en
    base que la DERNIÈRE rencontrée -- toujours l'équipe de fin de saison
    chez Basketball-Reference.
    """
    parsed: list[dict] = []
    errors: list[dict] = []
    for idx, row in df.iterrows():
        row_num = int(idx) + 2
        name = str(row.get("Player", "")).strip()
        team_abbr = str(row.get("Team", "")).strip()
        if not name or not team_abbr:
            errors.append({"row": row_num, "message": "Colonne Player ou Team manquante"})
            continue
        if team_abbr == _AGGREGATE_TEAM_MARKER:
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


def parse_players_advanced_prev_season(df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    return _parse_players_common_prev_season(df, value_column="PER", output_key="per")


def parse_players_per_game_prev_season(df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    return _parse_players_common_prev_season(df, value_column="MP", output_key="mpg")


def parse_draft(df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    parsed: list[dict] = []
    errors: list[dict] = []
    for idx, row in df.iterrows():
        row_num = int(idx) + 2
        name = str(row.get("Player", "")).strip()
        team_abbr = str(row.get("Tm", "")).strip()
        if not name or not team_abbr:
            errors.append({"row": row_num, "message": "Colonne Player ou Tm manquante"})
            continue
        if team_abbr not in ABBREVIATION_TO_NAME:
            errors.append({"row": row_num, "message": f"Équipe inconnue : {team_abbr!r}"})
            continue
        try:
            pick = int(row["Pk"])
        except (ValueError, TypeError, KeyError):
            errors.append({"row": row_num, "message": f"Pk invalide pour {name!r}"})
            continue
        parsed.append({"name": name, "team_abbreviation": team_abbr, "draft_pick": pick})
    return parsed, errors


def _parse_schedule_time(raw: str) -> time | None:
    """"3:00p" -> 15:00, "10:30a" -> 10:30, "12:00p" -> 12:00 (midi),
    "12:00a" -> 00:00 (minuit)."""
    match = _SCHEDULE_TIME_PATTERN.match(raw.strip())
    if match is None:
        return None
    hour, minute, meridiem = int(match.group(1)), int(match.group(2)), match.group(3).lower()
    if not (1 <= hour <= 12 and 0 <= minute <= 59):
        return None
    if hour == 12:
        hour = 0
    if meridiem == "p":
        hour += 12
    return time(hour=hour, minute=minute)


def parse_schedule(df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """Le fichier attendu est un export Basketball-Reference "Games" tel
    quel. Deux anomalies structurelles sont volontairement traitées comme
    des ERREURS DE LIGNE explicites plutôt qu'ignorées silencieusement :

    - une ligne d'en-tête répétée (`Date == "Date"`) ne peut survenir que si
      plusieurs exports mensuels ont été collés sans retirer les en-têtes
      intermédiaires -- signe d'un fichier mal assemblé, à corriger avant
      import plutôt qu'à masquer ;
    - une ligne entièrement vide, même raison.

    (Contrairement aux lignes Tm="TOT" de l'Étape 6bis, qui sont un artefact
    garanti et légitime du format Basketball-Reference dès qu'un joueur est
    échangé -- pas le signe d'une erreur de préparation du fichier.)
    """
    parsed: list[dict] = []
    errors: list[dict] = []
    for idx, row in df.iterrows():
        row_num = int(idx) + 2

        if row.isna().all():
            errors.append({"row": row_num, "message": "Ligne vide"})
            continue

        raw_date = str(row.get("Date", "")).strip()
        if raw_date == "Date":
            errors.append(
                {"row": row_num, "message": "En-tête de colonnes répétée — fichier probablement mal assemblé"}
            )
            continue

        raw_visitor = str(row.get("Visitor/Neutral", "")).strip()
        raw_home = str(row.get("Home/Neutral", "")).strip()
        raw_time = str(row.get("Start (ET)", "")).strip()
        if not raw_date or not raw_visitor or not raw_home or not raw_time:
            errors.append({"row": row_num, "message": "Colonne Date, Start (ET), Visitor/Neutral ou Home/Neutral manquante"})
            continue

        try:
            game_date = datetime.strptime(raw_date, "%a %b %d %Y").date()
        except ValueError:
            errors.append({"row": row_num, "message": f"Date invalide : {raw_date!r}"})
            continue

        game_time = _parse_schedule_time(raw_time)
        if game_time is None:
            errors.append({"row": row_num, "message": f"Heure invalide : {raw_time!r}"})
            continue

        away_full_name = resolve_team_name(raw_visitor)
        if away_full_name is None:
            errors.append({"row": row_num, "message": f"Équipe inconnue : {raw_visitor!r}"})
            continue
        home_full_name = resolve_team_name(raw_home)
        if home_full_name is None:
            errors.append({"row": row_num, "message": f"Équipe inconnue : {raw_home!r}"})
            continue

        away_pts_raw = row.get("PTS")
        home_pts_raw = row.get("PTS.1")
        away_has_score = pd.notna(away_pts_raw) and str(away_pts_raw).strip() != ""
        home_has_score = pd.notna(home_pts_raw) and str(home_pts_raw).strip() != ""
        if away_has_score != home_has_score:
            errors.append({"row": row_num, "message": "Score partiel (une seule des deux équipes a un score renseigné)"})
            continue

        away_score = home_score = None
        if away_has_score and home_has_score:
            try:
                away_score = int(float(away_pts_raw))
                home_score = int(float(home_pts_raw))
            except (ValueError, TypeError):
                errors.append({"row": row_num, "message": "Score invalide"})
                continue

        parsed.append(
            {
                "game_date": game_date,
                "game_time": game_time,
                "away_team_abbreviation": NBA_TEAMS[away_full_name],
                "home_team_abbreviation": NBA_TEAMS[home_full_name],
                "away_score": away_score,
                "home_score": home_score,
            }
        )
    return parsed, errors


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


def apply_draft(parsed: list[dict], db: Session) -> int:
    """Crée le Player s'il n'existe pas encore (cas normal pour un rookie
    sans stats), ou met juste à jour draft_pick sinon. Upsert par
    (name, team_id) -- la même clé que apply_players_advanced/per_game -- de
    sorte que l'arrivée ultérieure des vraies stats de ce joueur retrouve
    cette même ligne au lieu d'en créer une deuxième."""
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
        player.draft_pick = item["draft_pick"]
        count += 1
    db.flush()
    return count


def apply_teams_home_away_prev_season(parsed: list[dict], db: Session, season: str | None = None) -> int:
    """Comme apply_teams_home_away, mais écrit dans les colonnes _prev_season
    (Team n'a pas de notion de "saison" en tant que telle : une seule paire
    de colonnes N-1, toujours écrasée par le dernier import précédent en
    date -- `season` n'est pas utilisé ici, accepté seulement pour uniformiser
    la signature avec les appliers joueurs N-1)."""
    count = 0
    for item in parsed:
        team = db.query(Team).filter(Team.abbreviation == item["abbreviation"]).one_or_none()
        if team is None:
            team = Team(name=item["name"], abbreviation=item["abbreviation"])
            db.add(team)
        team.win_pct_home_prev_season = item["win_pct_home"]
        team.win_pct_away_prev_season = item["win_pct_away"]
        count += 1
    db.flush()
    return count


def _upsert_prev_season_stat(
    db: Session, cache: dict[str, PreviousSeasonPlayerStat], season: str, name: str, team_abbreviation: str
) -> PreviousSeasonPlayerStat:
    """La session applicative tourne avec autoflush=False : sans cache,
    deux lignes pour le même joueur dans un seul appel (ex: équipes
    successives d'un joueur échangé en cours de saison N-1) ne se
    verraient pas l'une l'autre via une requête DB tant que flush() n'a pas
    été appelé, et créeraient deux lignes en conflit avec la contrainte
    UNIQUE(season, player_name) au lieu de fusionner en une seule."""
    stat = cache.get(name)
    if stat is None:
        stat = (
            db.query(PreviousSeasonPlayerStat)
            .filter(PreviousSeasonPlayerStat.season == season, PreviousSeasonPlayerStat.player_name == name)
            .one_or_none()
        )
    if stat is None:
        stat = PreviousSeasonPlayerStat(season=season, player_name=name, team_abbreviation=team_abbreviation)
        db.add(stat)
    stat.team_abbreviation = team_abbreviation
    cache[name] = stat
    return stat


def apply_players_advanced_prev_season(parsed: list[dict], db: Session, season: str) -> int:
    count = 0
    cache: dict[str, PreviousSeasonPlayerStat] = {}
    for item in parsed:
        stat = _upsert_prev_season_stat(db, cache, season, item["name"], item["team_abbreviation"])
        stat.per = item["per"]
        count += 1
    db.flush()
    return count


def apply_players_per_game_prev_season(parsed: list[dict], db: Session, season: str) -> int:
    count = 0
    cache: dict[str, PreviousSeasonPlayerStat] = {}
    for item in parsed:
        stat = _upsert_prev_season_stat(db, cache, season, item["name"], item["team_abbreviation"])
        stat.mpg = item["mpg"]
        count += 1
    db.flush()
    return count


def apply_schedule(parsed: list[dict], db: Session, season: str) -> int:
    """Upsert par (date, équipe domicile, équipe extérieure) -- l'heure
    n'entre pas dans la clé, pour qu'un ré-import avec un horaire corrigé
    (changement de diffuseur TV, "flex scheduling") mette à jour la ligne
    existante plutôt que d'en créer une deuxième.

    Protection anti-régression : un Game déjà FINISHED n'est jamais
    rétrogradé vers SCHEDULED si la ligne réimportée n'a plus de score (ex:
    réimport accidentel d'un fichier plus ancien) -- le score/statut
    existant est alors préservé, seule la date/heure est mise à jour.

    Protection manually_overridden : un Game corrigé manuellement par
    l'admin (formulaire de report/score, voir app/api/games.py) n'est
    jamais modifié par le réimport -- ni date, ni score, ni statut."""
    count = 0
    cache: dict[tuple, Game] = {}
    for item in parsed:
        home_team = _get_or_create_team(db, item["home_team_abbreviation"])
        away_team = _get_or_create_team(db, item["away_team_abbreviation"])
        key = (item["game_date"], home_team.id, away_team.id)

        game = cache.get(key)
        if game is None:
            day_start = datetime.combine(item["game_date"], time.min)
            day_end = day_start + timedelta(days=1)
            game = (
                db.query(Game)
                .filter(
                    Game.home_team_id == home_team.id,
                    Game.away_team_id == away_team.id,
                    Game.game_date >= day_start,
                    Game.game_date < day_end,
                )
                .one_or_none()
            )
        if game is None:
            game = Game(home_team_id=home_team.id, away_team_id=away_team.id, status=GameStatus.SCHEDULED)
            db.add(game)

        cache[key] = game
        count += 1

        if game.manually_overridden:
            continue

        game.season = season
        game.game_date = datetime.combine(item["game_date"], item["game_time"])

        if item["home_score"] is not None and item["away_score"] is not None:
            game.status = GameStatus.FINISHED
            game.home_score = item["home_score"]
            game.away_score = item["away_score"]
        elif game.status != GameStatus.FINISHED:
            game.status = GameStatus.SCHEDULED
            game.home_score = None
            game.away_score = None
        # sinon : déjà FINISHED et la ligne réimportée n'a pas de score ->
        # on ne touche pas au statut/score existant.
    db.flush()
    return count


PARSERS = {
    ImportType.TEAMS_HOME_AWAY: parse_teams_home_away,
    ImportType.PLAYERS_ADVANCED: parse_players_advanced,
    ImportType.PLAYERS_PER_GAME: parse_players_per_game,
    ImportType.DRAFT: parse_draft,
    ImportType.SCHEDULE: parse_schedule,
}

# NB: apply_schedule n'apparaît pas ici -- signature (parsed, db, season),
# comme les appliers "saison précédente" (season toujours requis pour ce
# type, indépendamment de season_type). Appelé directement par
# app/api/imports.py, comme DRAFT y est déjà spécialisé pour la raison
# inverse (season_type ignoré).
APPLIERS = {
    ImportType.TEAMS_HOME_AWAY: apply_teams_home_away,
    ImportType.PLAYERS_ADVANCED: apply_players_advanced,
    ImportType.PLAYERS_PER_GAME: apply_players_per_game,
    ImportType.DRAFT: apply_draft,
}

# Sans objet pour DRAFT (pas de notion de saison précédente).
PREV_SEASON_PARSERS = {
    ImportType.TEAMS_HOME_AWAY: parse_teams_home_away,
    ImportType.PLAYERS_ADVANCED: parse_players_advanced_prev_season,
    ImportType.PLAYERS_PER_GAME: parse_players_per_game_prev_season,
}

# Signature uniforme (parsed, db, season) pour simplifier le dispatch côté
# API, même si apply_teams_home_away_prev_season ignore `season`.
PREV_SEASON_APPLIERS = {
    ImportType.TEAMS_HOME_AWAY: apply_teams_home_away_prev_season,
    ImportType.PLAYERS_ADVANCED: apply_players_advanced_prev_season,
    ImportType.PLAYERS_PER_GAME: apply_players_per_game_prev_season,
}
