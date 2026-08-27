"""Import des exports CSV Basketball-Reference (téléchargés manuellement).

Quatre types de fichiers reconnus :
- teams_home_away  : table "Expanded Standings" (colonnes Team/Home/Road) -> Team.win_pct_home/away
- players_advanced : table "Advanced" (colonnes PER/G/MP) -> Player.per + Player.mpg (dérivé de MP/G) + Player.games_played_this_season (= G, saison courante uniquement)
- draft             : table de la page Draft (colonnes Pk/Tm/Player)       -> Player (création rookie) + draft_pick
- schedule          : export "Games" (colonnes Date/Start (ET)/Visitor/Home) -> Game (upsert)

players_advanced accepte deux variantes de fichier, distinguées par la
présence ou non d'une colonne Team/Tm :
- export ligue entière (une ligne par joueur, colonne Team) -> comportement
  historique, team_abbreviation vient de chaque ligne ;
- export "roster d'une seule équipe" (pas de colonne Team, puisque c'est
  implicite) -> l'équipe est fournie explicitement en paramètre
  (team_abbreviation), résolue côté API depuis un `team_id` de requête. Une
  ligne finale `Player="Team Totals"` (agrégat, `Player-additional="-9999"`)
  y est un artefact garanti, ignoré silencieusement -- distinct de la ligne
  `Tm="TOT"` gérée plus bas (marqueur dans la colonne équipe, pas dans le nom).

Les deux premiers types peuvent en plus être importés pour la saison
PRÉCÉDENTE (season_type="previous", voir app/api/imports.py) : les données
vont alors dans Team.*_prev_season ou dans PreviousSeasonPlayerStat (jamais
dans Player/Team courants), pour la détection des transferts (Étape 6bis).
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, time, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app.models import MAX_REALISTIC_MPG, Game, GameStatus, ImportType, Player, PreviousSeasonPlayerStat, Team
from app.services.nba_teams import ABBREVIATION_TO_NAME, NBA_TEAMS, normalize_abbreviation, resolve_team_name
from app.services.player_matching import find_player_by_name, find_prev_season_stat_by_name, normalize_player_name

# Ordre figé (pas juste un ensemble) : c'est aussi la source de vérité pour
# l'ordre des colonnes des modèles CSV téléchargeables (generate_template_csv
# plus bas), en plus de la validation à l'import.
REQUIRED_COLUMNS: dict[ImportType, tuple[str, ...]] = {
    ImportType.TEAMS_HOME_AWAY: ("Team", "Home", "Road"),
    # Team volontairement absent : présent seulement dans la variante ligue
    # entière (voir docstring du module) -- validé séparément selon le cas.
    ImportType.PLAYERS_ADVANCED: ("Player", "PER", "G", "MP"),
    ImportType.DRAFT: ("Pk", "Tm", "Player"),
    ImportType.SCHEDULE: ("Date", "Start (ET)", "Visitor/Neutral", "Home/Neutral"),
}

# Basketball-Reference ajoute une ligne agrégée (toutes équipes confondues)
# pour un joueur échangé en cours de saison, en plus d'une ligne par équipe
# jouée. Notation différente selon la table : "TOT" (la plupart), ou
# "2TM"/"3TM"/"4TM"... (table Advanced -- découvert le 2026-08-27 sur un vrai
# export ligue entière, jamais rencontré avant sur les fichiers par équipe).
# Sans objet pour nous dans les deux cas : jamais une "vraie" équipe.
_AGGREGATE_TEAM_MARKER = "TOT"
_AGGREGATE_TEAM_COUNT_PATTERN = re.compile(r"^\d+TM$")


def _is_aggregate_team_marker(team_abbr: str) -> bool:
    return team_abbr == _AGGREGATE_TEAM_MARKER or bool(_AGGREGATE_TEAM_COUNT_PATTERN.match(team_abbr))


# Lignes d'agrégat en fin d'export players_advanced (colonne Player).
# Artefact distinct de _AGGREGATE_TEAM_MARKER ci-dessus : ce sont des noms de
# "joueur" spéciaux, pas un marqueur d'équipe. "Team Totals" apparaît sur
# l'export "roster d'une seule équipe" (une ligne par équipe) ; "League
# Average" apparaît sur l'export ligue entière (une seule ligne, colonne
# Team vide -- découvert le 2026-08-27 sur un vrai fichier). Les deux sont
# des artefacts garantis du format source, ignorés silencieusement de la
# même façon.
_AGGREGATE_PLAYER_MARKERS = ("Team Totals", "League Average")

_SCHEDULE_TIME_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})([ap])$", re.IGNORECASE)


class CsvImportError(Exception):
    """Erreur bloquante : fichier illisible ou type non détectable."""


def _promote_grouped_header_if_needed(df: pd.DataFrame, file_bytes: bytes) -> pd.DataFrame:
    """Basketball-Reference exporte parfois une ligne de REGROUPEMENT de
    colonnes au-dessus de la vraie ligne d'en-tête -- rencontré concrètement
    sur deux vrais fichiers de nature différente :
    - la page Draft : "Round 1"/"Totals"/"Shooting"/"Per Game"/"Advanced" en
      ligne 1, "Rk"/"Pk"/"Tm"/"Player"/... en ligne 2 ;
    - la page "Expanded Standings" (classement) : "Place"/"Conference"/
      "Division"/"All-Star"/"Margin"/"Month" en ligne 1, "Rk"/"Team"/
      "Overall"/"Home"/"Road"/... en ligne 2.
    Lue normalement, cette ligne de regroupement est prise pour l'en-tête
    par pandas : les vraies colonnes (cellules vides sur la ligne de
    regroupement, ex: Rk/Pk/Tm ou Rk/Team/Overall) deviennent des colonnes
    "Unnamed" et se retrouvent supprimées par le filtre juste en dessous,
    avant même que detect_import_type() ait une chance de s'exécuter.

    Signal utilisé, volontairement générique plutôt qu'un cas par type
    (même principe que le modèle CSV téléchargeable : REQUIRED_COLUMNS reste
    l'unique source de vérité) : si la première ligne de données contient,
    comme valeurs, toutes les colonnes requises d'un des types connus, elle
    est en réalité la vraie ligne d'en-tête -- on relit le fichier une ligne
    plus bas. Couvre aussi bien draft que le classement sans code dédié à
    chacun, et tout futur type qui aurait le même problème."""
    if len(df) == 0:
        return df
    first_row = {str(v).strip() for v in df.iloc[0].tolist()}
    if any(set(required).issubset(first_row) for required in REQUIRED_COLUMNS.values()):
        return _read_csv_auto_sep(file_bytes, header=1)
    return df


def _read_csv_auto_sep(file_bytes: bytes, header: int = 0) -> pd.DataFrame:
    """Détection automatique du séparateur de colonnes (`csv.Sniffer`,
    restreint à `,`/`;` -- les deux seuls rencontrés en pratique ici, pour
    un sniffing plus fiable qu'une détection non contrainte) plutôt qu'une
    liste codée en dur, sur n'importe lequel des types de fichiers gérés ici.

    Le séparateur DÉCIMAL suit le séparateur de colonnes détecté (`,` pour
    `;`, `.` pour `,`) plutôt que d'être fixé arbitrairement : Excel en
    localisation française réenregistre systématiquement les deux ensemble
    à la sauvegarde (jamais l'un sans l'autre en pratique) -- ex: PER
    "24,3" accompagne toujours un point-virgule comme séparateur de
    colonnes, jamais une virgule."""
    sample = file_bytes.decode("utf-8-sig", errors="replace")[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;")
    except csv.Error as exc:
        raise CsvImportError(f"Séparateur de colonnes non reconnu : {exc}") from exc
    separator = dialect.delimiter
    decimal = "," if separator == ";" else "."
    return pd.read_csv(
        io.BytesIO(file_bytes), encoding="utf-8-sig", sep=separator, decimal=decimal, header=header
    )


def read_csv(file_bytes: bytes) -> pd.DataFrame:
    try:
        df = _read_csv_auto_sep(file_bytes)
    except (UnicodeDecodeError, pd.errors.ParserError) as exc:
        raise CsvImportError(f"Fichier CSV illisible : {exc}") from exc
    df = _promote_grouped_header_if_needed(df, file_bytes)
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
    if {"Team", "Home", "Road"}.issubset(columns):
        return ImportType.TEAMS_HOME_AWAY
    return None


def validate_columns(df: pd.DataFrame, import_type: ImportType) -> list[str]:
    """Retourne la liste des colonnes requises manquantes (triée)."""
    required = REQUIRED_COLUMNS[import_type]
    return sorted(set(required) - set(df.columns))


# Modèles CSV téléchargeables (aide-mémoire du format attendu, back-office
# Imports) : 5 clés pour les 4 types + les 2 variantes de players_advanced
# (avec/sans colonne Team -- voir docstring du module).
TEMPLATE_KEYS: tuple[str, ...] = (
    "teams_home_away",
    "players_advanced_league",
    "players_advanced_team",
    "draft",
    "schedule",
)

_TEMPLATE_IMPORT_TYPE: dict[str, ImportType] = {
    "teams_home_away": ImportType.TEAMS_HOME_AWAY,
    "players_advanced_league": ImportType.PLAYERS_ADVANCED,
    "players_advanced_team": ImportType.PLAYERS_ADVANCED,
    "draft": ImportType.DRAFT,
    "schedule": ImportType.SCHEDULE,
}

# Valeurs d'exemple UNIQUEMENT cosmétiques (pour que le modèle montre à quoi
# ressemble une valeur plausible, pas juste un nom de colonne) -- ce n'est
# PAS une source de vérité sur les colonnes requises, qui reste
# REQUIRED_COLUMNS. Une valeur manquante ici est détectée par un test dédié
# (tests/test_csv_import.py), jamais silencieuse : contrairement à
# REQUIRED_COLUMNS, un oubli ici ne peut pas casser un vrai import,
# seulement rendre un modèle incomplet.
_EXAMPLE_VALUES: dict[str, str] = {
    "Team": "Boston Celtics",
    "Home": "24-6",
    "Road": "18-16",
    "Player": "Jayson Tatum",
    "PER": "24.3",
    "G": "72",
    "MP": "2450",
    "Pk": "1",
    "Tm": "BOS",
    "Date": "Tue Oct 21 2025",
    "Start (ET)": "7:30p",
    "Visitor/Neutral": "Los Angeles Lakers",
    "Home/Neutral": "Boston Celtics",
}


def generate_template_csv(key: str) -> str:
    """Génère un modèle CSV minimal (en-têtes + une ligne d'exemple) pour la
    clé de modèle donnée -- voir TEMPLATE_KEYS. Les colonnes viennent
    directement de REQUIRED_COLUMNS (même source de vérité que la
    validation à l'import) : un futur changement de colonnes requises se
    répercute automatiquement ici, sans liste séparée à maintenir à la main.

    Ne reproduit PAS les artefacts réels de Basketball-Reference (double
    en-tête de la draft, colonnes dupliquées MP/PTS/TRB/AST, colonnes
    optionnelles comme PTS) : le modèle représente la structure minimale
    propre attendue par l'app, pas une réplique exacte d'un export réel."""
    if key not in _TEMPLATE_IMPORT_TYPE:
        raise ValueError(f"Modèle inconnu : {key!r}")

    import_type = _TEMPLATE_IMPORT_TYPE[key]
    columns = list(REQUIRED_COLUMNS[import_type])
    if key == "players_advanced_league":
        # Seule exception : Team est volontairement exclu de
        # REQUIRED_COLUMNS[PLAYERS_ADVANCED] (variant-dépendant, voir
        # commentaire à sa définition) -- réintégré ici uniquement pour
        # cette variante précise du modèle.
        columns.insert(1, "Team")

    example_row = [_EXAMPLE_VALUES[column] for column in columns]

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    writer.writerow(example_row)
    return buffer.getvalue()


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


def parse_players_advanced(
    df: pd.DataFrame, team_abbreviation: str | None = None
) -> tuple[list[dict], list[dict]]:
    """Deux variantes de fichier, distinguées par la présence ou non d'une
    colonne Team (voir docstring du module) :
    - colonne Team présente (export ligue entière) -> team_abbreviation vient
      de chaque ligne, le paramètre `team_abbreviation` est ignoré ;
    - colonne Team absente (export roster d'une seule équipe) -> toutes les
      lignes utilisent `team_abbreviation` (résolu et validé par l'appelant,
      voir app/api/imports.py -- jamais None à ce stade pour cette variante).

    `mp`/`g` sont extraits ici mais PAS divisés (mpg = mp/g a lieu dans
    apply_players_advanced, pas au parsing)."""
    has_team_column = "Team" in df.columns
    parsed: list[dict] = []
    errors: list[dict] = []
    for idx, row in df.iterrows():
        row_num = int(idx) + 2
        name = str(row.get("Player", "")).strip()
        if name in _AGGREGATE_PLAYER_MARKERS:
            continue
        if not name:
            errors.append({"row": row_num, "message": "Colonne Player manquante"})
            continue

        if has_team_column:
            team_abbr = normalize_abbreviation(str(row.get("Team", "")).strip())
            if not team_abbr:
                errors.append({"row": row_num, "message": "Colonne Team manquante"})
                continue
            if team_abbr not in ABBREVIATION_TO_NAME:
                errors.append({"row": row_num, "message": f"Équipe inconnue : {team_abbr!r}"})
                continue
        else:
            team_abbr = team_abbreviation

        try:
            per = float(row["PER"])
        except (ValueError, TypeError, KeyError):
            errors.append({"row": row_num, "message": f"PER invalide pour {name!r}"})
            continue
        try:
            g = float(row["G"])
            mp = float(row["MP"])
        except (ValueError, TypeError, KeyError):
            errors.append({"row": row_num, "message": f"G/MP invalide pour {name!r}"})
            continue
        mpg_candidate = mp / g if g else 0.0
        if mpg_candidate > MAX_REALISTIC_MPG:
            errors.append(
                {
                    "row": row_num,
                    "message": (
                        f"MPG invalide pour {name!r} : {mpg_candidate:.1f} dépasse le maximum "
                        f"réaliste ({MAX_REALISTIC_MPG} min/match)"
                    ),
                }
            )
            continue

        parsed.append({"name": name, "team_abbreviation": team_abbr, "per": per, "g": g, "mp": mp})
    return parsed, errors


def parse_players_advanced_prev_season(
    df: pd.DataFrame, team_abbreviation: str | None = None
) -> tuple[list[dict], list[dict]]:
    """Variante saison N-1 de `parse_players_advanced`.

    Les exports Advanced de Basketball-Reference contiennent, pour un
    joueur échangé en cours de saison N-1, une ligne par équipe jouée *plus*
    une ligne agrégée dans la colonne équipe -- `Tm="TOT"` sur la plupart des
    tables, `"2TM"`/`"3TM"`/`"4TM"`... sur l'export ligue entière de la table
    Advanced (vu le 2026-08-27 sur un vrai fichier, jamais rencontré avant).
    Ces lignes sont ignorées silencieusement ici (pas une erreur, voir
    `_is_aggregate_team_marker`) -- contrairement à `parse_players_advanced`
    (saison courante), où ce cas ne se présente pas dans notre usage. Distinct
    de `_AGGREGATE_PLAYER_MARKERS` ("Team Totals"/"League Average", lignes de
    joueur spéciales) : ici c'est un marqueur dans la colonne équipe elle-même.

    Quand plusieurs lignes d'équipe réelles existent pour un même joueur
    (trade en cours de saison N-1), elles sont toutes conservées dans
    l'ordre du fichier : c'est l'upsert de `apply_players_advanced_prev_season`
    (par `(season, player_name)`, sans l'équipe dans la clé) qui ne garde en
    base que la DERNIÈRE rencontrée -- toujours l'équipe de fin de saison
    chez Basketball-Reference."""
    has_team_column = "Team" in df.columns
    parsed: list[dict] = []
    errors: list[dict] = []
    for idx, row in df.iterrows():
        row_num = int(idx) + 2
        name = str(row.get("Player", "")).strip()
        if name in _AGGREGATE_PLAYER_MARKERS:
            continue
        if not name:
            errors.append({"row": row_num, "message": "Colonne Player manquante"})
            continue

        if has_team_column:
            team_abbr = normalize_abbreviation(str(row.get("Team", "")).strip())
            if not team_abbr:
                errors.append({"row": row_num, "message": "Colonne Team manquante"})
                continue
            if _is_aggregate_team_marker(team_abbr):
                continue
            if team_abbr not in ABBREVIATION_TO_NAME:
                errors.append({"row": row_num, "message": f"Équipe inconnue : {team_abbr!r}"})
                continue
        else:
            team_abbr = team_abbreviation

        try:
            per = float(row["PER"])
        except (ValueError, TypeError, KeyError):
            errors.append({"row": row_num, "message": f"PER invalide pour {name!r}"})
            continue
        try:
            g = float(row["G"])
            mp = float(row["MP"])
        except (ValueError, TypeError, KeyError):
            errors.append({"row": row_num, "message": f"G/MP invalide pour {name!r}"})
            continue
        mpg_candidate = mp / g if g else 0.0
        if mpg_candidate > MAX_REALISTIC_MPG:
            errors.append(
                {
                    "row": row_num,
                    "message": (
                        f"MPG invalide pour {name!r} : {mpg_candidate:.1f} dépasse le maximum "
                        f"réaliste ({MAX_REALISTIC_MPG} min/match)"
                    ),
                }
            )
            continue

        parsed.append({"name": name, "team_abbreviation": team_abbr, "per": per, "g": g, "mp": mp})
    return parsed, errors


def parse_draft(df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    parsed: list[dict] = []
    errors: list[dict] = []
    for idx, row in df.iterrows():
        row_num = int(idx) + 2
        name = str(row.get("Player", "")).strip()
        team_abbr = normalize_abbreviation(str(row.get("Tm", "")).strip())
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
    """mpg est dérivé ici (mp/g), pas au parsing -- gère explicitement g=0
    (joueur sans match joué) pour éviter une division par zéro."""
    count = 0
    for item in parsed:
        team = _get_or_create_team(db, item["team_abbreviation"])
        player = find_player_by_name(db, item["name"], team.id)
        if player is None:
            player = Player(name=item["name"], team_id=team.id)
            db.add(player)
        player.per = item["per"]
        player.mpg = item["mp"] / item["g"] if item["g"] else 0.0
        player.games_played_this_season = int(item["g"])
        count += 1
    db.flush()
    return count


def apply_draft(parsed: list[dict], db: Session) -> int:
    """Crée le Player s'il n'existe pas encore (cas normal pour un rookie
    sans stats), ou met juste à jour draft_pick sinon. Upsert par
    (name, team_id) -- la même clé que apply_players_advanced -- de sorte
    que l'arrivée ultérieure des vraies stats de ce joueur retrouve cette
    même ligne au lieu d'en créer une deuxième."""
    count = 0
    for item in parsed:
        team = _get_or_create_team(db, item["team_abbreviation"])
        player = find_player_by_name(db, item["name"], team.id)
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
    key = normalize_player_name(name)
    stat = cache.get(key)
    if stat is None:
        stat = find_prev_season_stat_by_name(db, season, name)
    if stat is None:
        stat = PreviousSeasonPlayerStat(season=season, player_name=name, team_abbreviation=team_abbreviation)
        db.add(stat)
    stat.team_abbreviation = team_abbreviation
    cache[key] = stat
    return stat


def apply_players_advanced_prev_season(parsed: list[dict], db: Session, season: str) -> int:
    """mpg est dérivé ici (mp/g), même principe que apply_players_advanced."""
    count = 0
    cache: dict[str, PreviousSeasonPlayerStat] = {}
    for item in parsed:
        stat = _upsert_prev_season_stat(db, cache, season, item["name"], item["team_abbreviation"])
        stat.per = item["per"]
        stat.mpg = item["mp"] / item["g"] if item["g"] else 0.0
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


# NB: comme apply_schedule/DRAFT ci-dessous, PLAYERS_ADVANCED n'est appelé
# via ce dict que pour la variante "colonne Team présente" -- la variante
# "roster d'une seule équipe" (team_abbreviation à fournir) est appelée
# directement par app/api/imports.py, en dehors de ce dict.
PARSERS = {
    ImportType.TEAMS_HOME_AWAY: parse_teams_home_away,
    ImportType.PLAYERS_ADVANCED: parse_players_advanced,
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
    ImportType.DRAFT: apply_draft,
}

# Sans objet pour DRAFT (pas de notion de saison précédente).
PREV_SEASON_PARSERS = {
    ImportType.TEAMS_HOME_AWAY: parse_teams_home_away,
    ImportType.PLAYERS_ADVANCED: parse_players_advanced_prev_season,
}

# Signature uniforme (parsed, db, season) pour simplifier le dispatch côté
# API, même si apply_teams_home_away_prev_season ignore `season`.
PREV_SEASON_APPLIERS = {
    ImportType.TEAMS_HOME_AWAY: apply_teams_home_away_prev_season,
    ImportType.PLAYERS_ADVANCED: apply_players_advanced_prev_season,
}
