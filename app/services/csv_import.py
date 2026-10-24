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
from dataclasses import dataclass
from datetime import datetime, time, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app.models import (
    MAX_REALISTIC_MPG,
    Game,
    GameStatus,
    ImportType,
    Player,
    PreviousSeasonPlayerStat,
    Settings,
    Team,
)
from app.services.nba_teams import ABBREVIATION_TO_NAME, NBA_TEAMS, normalize_abbreviation, resolve_team_name
from app.services.player_matching import (  # noqa: F401 -- fold_diacritics et _roster_match_key restent importables d'ici
    fold_diacritics,
    find_prev_season_stat_by_name,
    normalize_player_name,
    tolerant_name_key as _roster_match_key,
)

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
    # Number/Position/Height/Weight/Last Attended/Country peuvent être présentes
    # dans le fichier réel (export "ligue entière" du roster) mais ne sont ni
    # lues ni stockées (arbitrage explicite, voir plan du chantier ROSTER) --
    # Player et Team sont les deux seules colonnes que parse_roster consomme.
    ImportType.ROSTER: ("Player", "Team"),
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
    # ROSTER doit être vérifié APRÈS PLAYERS_ADVANCED, jamais avant : un
    # export Advanced "ligue entière" a lui aussi Player ET Team (en plus de
    # PER/G/MP) -- si ce test passait en premier, un tel fichier serait
    # détecté à tort comme ROSTER. L'ordre des `if` de cette fonction fait foi
    # (pas un ensemble non ordonné) ; ne jamais déplacer ce bloc avant celui
    # de PLAYERS_ADVANCED.
    if {"Player", "Team"}.issubset(columns):
        return ImportType.ROSTER
    if {"Team", "Home", "Road"}.issubset(columns):
        return ImportType.TEAMS_HOME_AWAY
    return None


def validate_columns(df: pd.DataFrame, import_type: ImportType) -> list[str]:
    """Retourne la liste des colonnes requises manquantes (triée)."""
    required = REQUIRED_COLUMNS[import_type]
    return sorted(set(required) - set(df.columns))


# Modèles CSV téléchargeables (aide-mémoire du format attendu, back-office
# Imports) : 6 clés pour les 5 types + les 2 variantes de players_advanced
# (avec/sans colonne Team -- voir docstring du module).
TEMPLATE_KEYS: tuple[str, ...] = (
    "teams_home_away",
    "players_advanced_league",
    "players_advanced_team",
    "draft",
    "schedule",
    "roster",
)

_TEMPLATE_IMPORT_TYPE: dict[str, ImportType] = {
    "teams_home_away": ImportType.TEAMS_HOME_AWAY,
    "players_advanced_league": ImportType.PLAYERS_ADVANCED,
    "players_advanced_team": ImportType.PLAYERS_ADVANCED,
    "draft": ImportType.DRAFT,
    "schedule": ImportType.SCHEDULE,
    "roster": ImportType.ROSTER,
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


# --- Rapprochement league-wide, partagé entre apply_players_advanced,
# apply_draft, apply_roster et POST /api/players (app/api/players.py) --------
#
# Introduit avec apply_roster (chantier ROSTER, 2026-09-12), généralisé ici
# (chantier fermeture du doublon, 2026-09-12) : find_player_by_name
# (player_matching.py, règle stricte, restreint à UNE équipe) crée une
# nouvelle ligne dès que le nom diverge d'orthographe (diacritique,
# ponctuation, suffixe Jr./Sr./II/III) OU que le joueur a changé d'équipe
# depuis le dernier import -- un doublon, jamais un rapprochement manqué
# signalé. Mesuré sur le vrai fichier ROSTER : 27 des 60 draftés avaient
# changé d'équipe, 13 des 488 noms rapprochés avaient une orthographe
# divergente -- aucun des deux cas n'est marginal.
#
# Ces deux fonctions restent volontairement dans csv_import.py, PAS dans
# player_matching.py : ce dernier reste le point d'entrée unique du reste du
# projet (détection de transferts, PATCH /api/players -- son contrôle de
# conflit sert un autre but, voir plus bas) -- élargir sa règle de
# comparaison changerait leur comportement à tous d'un coup, sans qu'aucun
# n'ait été audité pour ce risque élargi. Pas de préfixe `_` (contrairement à
# _get_or_create_team, _upsert_prev_season_stat) : ce sont les deux seules
# fonctions de ce module importées depuis un autre module (app/api/players.py).


def build_active_player_index(db: Session) -> dict[str, Player]:
    """Index de tous les Player actifs, toutes équipes confondues, par
    _roster_match_key -- à construire UNE FOIS par appel d'un applier
    (jamais reconstruit ligne à ligne), puis passé à
    find_or_create_player_league_wide pour chaque ligne du fichier."""
    active_players = db.query(Player).filter(Player.is_active.is_(True)).all()
    return {_roster_match_key(p.name): p for p in active_players}


def find_or_create_player_league_wide(
    db: Session, player_by_key: dict[str, Player], name: str, team: Team
) -> tuple[Player, bool]:
    """Retrouve `name` dans TOUT l'effectif actif (pas restreint à `team`) ;
    déplace la ligne trouvée (team_id mis à jour) si son équipe actuelle
    diffère de `team` ; n'en crée une nouvelle que si aucune correspondance
    n'existe nulle part dans la ligue. Retourne (player, was_created).

    `player_by_key` est mis à jour en place à chaque création (pas seulement
    lu) : un même nom apparaissant deux fois dans le même fichier se
    retrouve lui-même dès sa seconde occurrence, sans passer par une requête
    DB (la session tourne avec autoflush=False, voir _upsert_prev_season_stat
    pour le même raisonnement)."""
    key = _roster_match_key(name)
    player = player_by_key.get(key)
    was_created = player is None
    if was_created:
        player = Player(name=name, team_id=team.id)
        db.add(player)
        db.flush()
        player_by_key[key] = player
    elif player.team_id != team.id:
        player.team_id = team.id
    return player, was_created


def apply_players_advanced(parsed: list[dict], db: Session) -> int:
    """mpg est dérivé ici (mp/g), pas au parsing -- gère explicitement g=0
    (joueur sans match joué) pour éviter une division par zéro."""
    count = 0
    player_by_key = build_active_player_index(db)
    for item in parsed:
        team = _get_or_create_team(db, item["team_abbreviation"])
        player, _ = find_or_create_player_league_wide(db, player_by_key, item["name"], team)
        player.per = item["per"]
        player.mpg = item["mp"] / item["g"] if item["g"] else 0.0
        player.games_played_this_season = int(item["g"])
        count += 1
    db.flush()
    return count


def apply_draft(parsed: list[dict], db: Session) -> int:
    """Crée le Player s'il n'existe nulle part dans l'effectif actif (cas
    normal pour un rookie sans stats), le déplace s'il existe sous une autre
    équipe, ou met juste à jour draft_pick sinon. Upsert league-wide -- la
    même clé que apply_players_advanced -- de sorte que l'arrivée ultérieure
    des vraies stats de ce joueur retrouve cette même ligne au lieu d'en
    créer une deuxième."""
    count = 0
    player_by_key = build_active_player_index(db)
    for item in parsed:
        team = _get_or_create_team(db, item["team_abbreviation"])
        player, _ = find_or_create_player_league_wide(db, player_by_key, item["name"], team)
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


# --- Effectif complet (ligue entière) ---------------------------------------
#
# Import ROSTER : nom + équipe pour l'intégralité de la ligue, en un seul
# fichier. Number/Position/Height/Weight/Last Attended/Country peuvent être
# présentes dans le fichier réel mais ne sont jamais lues au-delà de
# REQUIRED_COLUMNS -- arbitrage explicite du chantier, aucune des deux
# n'alimente le moteur ni ne rejoint le modèle Player.
#
# Rapprochement par nom : ROSTER a besoin d'un rapprochement plus agressif
# que le reste du projet (diacritiques, ponctuation, suffixes Jr./Sr./II/III)
# pour retrouver correctement les 582 PreviousSeasonPlayerStat et les Player
# déjà en base. _roster_match_key() ci-dessous est volontairement LOCALE à
# ce chantier -- elle n'étend PAS et ne remplace PAS
# player_matching.normalize_player_name (le point d'entrée unique du reste
# du projet : import Advanced/Draft, formulaire admin, détection de
# transferts). Partagée par analyze_roster_import et apply_roster pour
# qu'aperçu et confirmation ne puissent jamais diverger sur une même ligne
# (même principe que la source de vérité unique retenue pour
# compute_calendar_flags, voir CLAUDE.md, Décision d'architecture n°13).

def _levenshtein_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous_row = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current_row = [i] + [0] * len(b)
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            current_row[j] = min(
                previous_row[j] + 1,
                current_row[j - 1] + 1,
                previous_row[j - 1] + cost,
            )
        previous_row = current_row
    return previous_row[-1]


def _closest_name(target: str, candidates: list[str]) -> tuple[str, int] | None:
    """Suggestion purement informative pour le récapitulatif -- JAMAIS
    appliquée automatiquement : un faux positif mesuré ("Caleb Wilson" à
    distance 2 de "Jalen Wilson", deux joueurs sans rapport) interdit de
    fusionner deux noms sur ce seul critère. Comparaison faite sur
    _roster_match_key des deux côtés, pas sur les chaînes brutes."""
    best_name: str | None = None
    best_distance: int | None = None
    target_key = _roster_match_key(target)
    for candidate in candidates:
        distance = _levenshtein_distance(target_key, _roster_match_key(candidate))
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_name = candidate
    if best_name is None:
        return None
    return best_name, best_distance


def parse_roster(df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """Pure -- aucun accès DB, même contrat que les autres parse_* (voir
    docstring de module). N'extrait que Player/Team ; toute autre colonne du
    fichier réel (Number/Position/Height/Weight/Last Attended/Country) est
    ignorée silencieusement, jamais lue."""
    parsed: list[dict] = []
    errors: list[dict] = []
    for idx, row in df.iterrows():
        row_num = int(idx) + 2
        name = str(row.get("Player", "")).strip()
        raw_team = str(row.get("Team", "")).strip()
        if not name or not raw_team:
            errors.append({"row": row_num, "message": "Colonne Player ou Team manquante"})
            continue
        team_abbr = normalize_abbreviation(raw_team)
        if team_abbr not in ABBREVIATION_TO_NAME:
            errors.append({"row": row_num, "message": f"Équipe inconnue : {team_abbr!r}"})
            continue
        parsed.append({"name": name, "team_abbreviation": team_abbr})
    return parsed, errors


@dataclass
class UnmatchedRosterName:
    name: str
    closest_match: str | None
    distance: int | None


@dataclass
class MovedRosterEntry:
    name: str
    from_team: str
    to_team: str


@dataclass
class DetachablePlayer:
    """Futur agent libre (Décision n°39) : joueur actif rattaché à une équipe
    qu'aucune ligne du fichier ne désigne. Le PER/MPG N-1 est celui de sa ligne
    PreviousSeasonPlayerStat retrouvée par _roster_match_key (None sans ligne)."""

    id: int
    name: str
    team_abbreviation: str
    draft_pick: int | None
    per_n1: float | None
    mpg_n1: float | None


@dataclass
class FileRowWithoutMatch:
    """Ligne du fichier qu'aucun joueur actif de la base ne reconnaît : une
    recrue, OU un joueur déjà en base sous un autre nom (cas « Ronald Holland II »
    contre « Ron Holland »). `closest_absent_player` n'est qu'une SUGGESTION
    (ressemblance de noms, jamais appliquée) parmi les futurs agents libres."""

    name: str
    team_abbreviation: str
    closest_absent_player: str | None
    distance: int | None


@dataclass
class AssociationCandidate:
    """Joueur actif de la base qu'aucune ligne du fichier ne désigne : cible
    possible d'un verdict « c'est le même joueur que… » (agents libres compris,
    d'où l'équipe optionnelle)."""

    id: int
    name: str
    team_abbreviation: str | None


@dataclass
class RosterImportAnalysis:
    """Les 5 sections du récapitulatif (plan du chantier, point b) --
    produites par analyze_roster_import, jamais persistées (comme
    resolved_team_name pour le roster par équipe : portée dry-run
    uniquement, jamais dans ImportHistory)."""

    matched_count: int
    unmatched: list[UnmatchedRosterName]
    orphans: list[str]
    moved: list[MovedRosterEntry]
    no_prior_data: list[str]
    # Garde-fou du détachement (Décision n°39) : si le fichier ne laisse AUCUNE
    # ligne sans correspondance, tout joueur absent est réellement parti.
    detachable: list[DetachablePlayer]
    file_rows_without_match: list[FileRowWithoutMatch]
    association_candidates: list[AssociationCandidate]
    # Verdicts OBLIGATOIRES pour confirmer (Décision n°39) : il existe au moins une ligne
    # sans correspondance ET au moins un joueur actif de la base absent du fichier --
    # la seule configuration où une ligne peut être un joueur déjà en base sous un autre nom.
    verdicts_required: bool


def analyze_roster_import(db: Session, parsed: list[dict]) -> RosterImportAnalysis:
    """Lecture seule (aucun db.add/flush) -- appelée UNIQUEMENT pendant
    l'aperçu (dry_run=True), jamais pendant la confirmation. apply_roster ne
    reçoit jamais son résultat : il recalcule ses propres décisions
    indépendamment, à partir du même _roster_match_key (voir plan du
    chantier, point a -- stateless par choix, aucun état de session entre
    aperçu et confirmation)."""
    settings = db.query(Settings).first()
    prev_season = settings.previous_season if settings is not None else None

    csv_keys = {_roster_match_key(item["name"]) for item in parsed}

    n1_rows = (
        db.query(PreviousSeasonPlayerStat).filter(PreviousSeasonPlayerStat.season == prev_season).all()
        if prev_season is not None
        else []
    )
    n1_by_key: dict[str, PreviousSeasonPlayerStat] = {
        _roster_match_key(stat.player_name): stat for stat in n1_rows
    }

    matched_count = 0
    unmatched_names: list[str] = []
    for item in parsed:
        if _roster_match_key(item["name"]) in n1_by_key:
            matched_count += 1
        else:
            unmatched_names.append(item["name"])

    # Bassin de suggestion : uniquement les lignes N-1 qu'AUCUN nom du CSV
    # n'a réclamées -- comparer un échec à un nom N-1 déjà rapproché par
    # ailleurs produirait une suggestion trompeuse (deux noms CSV différents
    # pointant vers la même ligne N-1 déjà prise).
    n1_orphan_names = [stat.player_name for key, stat in n1_by_key.items() if key not in csv_keys]

    unmatched: list[UnmatchedRosterName] = []
    for name in unmatched_names:
        suggestion = _closest_name(name, n1_orphan_names)
        if suggestion is None:
            unmatched.append(UnmatchedRosterName(name=name, closest_match=None, distance=None))
        else:
            closest, distance = suggestion
            unmatched.append(UnmatchedRosterName(name=name, closest_match=closest, distance=distance))

    active_players = db.query(Player).filter(Player.is_active.is_(True)).all()
    player_by_key: dict[str, Player] = {_roster_match_key(p.name): p for p in active_players}

    # Un agent libre (team_id NULL, Décision n°39) absent du fichier est déjà
    # détaché : ne pas le reproposer à chaque import comme futur agent libre.
    orphans = sorted(p.name for key, p in player_by_key.items() if key not in csv_keys and p.team_id is not None)

    moved: list[MovedRosterEntry] = []
    for item in parsed:
        player = player_by_key.get(_roster_match_key(item["name"]))
        # Un agent libre présent dans le fichier est « déplacé » depuis aucune
        # équipe : player.team vaut None (Décision n°39).
        if player is not None and (player.team is None or player.team.abbreviation != item["team_abbreviation"]):
            moved.append(
                MovedRosterEntry(
                    name=item["name"],
                    from_team=player.team.abbreviation if player.team is not None else "agent libre",
                    to_team=item["team_abbreviation"],
                )
            )

    # Sans ligne N-1 ET sans draft_pick connu : signalé pour saisie manuelle
    # (arbitrage du chantier -- corrigé après mesure, voir plan révisé). Un
    # joueur sans ligne N-1 mais déjà connu comme drafté (draft_pick non nul)
    # est un rookie normal, jamais signalé ici.
    no_prior_data: list[str] = []
    for name in unmatched_names:
        player = player_by_key.get(_roster_match_key(name))
        if player is not None and player.draft_pick is not None:
            continue
        no_prior_data.append(name)

    # Futurs agents libres : les mêmes joueurs que `orphans`, avec de quoi décider
    # (identifiant, équipe, draft_pick, PER/MPG N-1). Les agents libres déjà
    # détachés n'en font pas partie (rien à détacher).
    detachable: list[DetachablePlayer] = []
    for key, player in player_by_key.items():
        if key in csv_keys or player.team_id is None:
            continue
        stat = n1_by_key.get(key)
        detachable.append(
            DetachablePlayer(
                id=player.id,
                name=player.name,
                team_abbreviation=player.team.abbreviation,
                draft_pick=player.draft_pick,
                per_n1=stat.per if stat is not None else None,
                mpg_n1=stat.mpg if stat is not None else None,
            )
        )
    detachable.sort(key=lambda d: (d.team_abbreviation, d.name))

    association_candidates = sorted(
        (
            AssociationCandidate(
                id=player.id,
                name=player.name,
                team_abbreviation=player.team.abbreviation if player.team is not None else None,
            )
            for key, player in player_by_key.items()
            if key not in csv_keys
        ),
        key=lambda c: (c.team_abbreviation or "", c.name),
    )

    # Lignes du fichier sans correspondance dans les joueurs actifs (mesure
    # exacte : la même que celle de l'import, pas une ressemblance de noms).
    detachable_names = [d.name for d in detachable]
    file_rows_without_match: list[FileRowWithoutMatch] = []
    seen_keys: set[str] = set()
    for item in parsed:
        key = _roster_match_key(item["name"])
        if key in player_by_key or key in seen_keys:
            continue
        seen_keys.add(key)
        suggestion = _closest_name(item["name"], detachable_names)
        file_rows_without_match.append(
            FileRowWithoutMatch(
                name=item["name"],
                team_abbreviation=item["team_abbreviation"],
                closest_absent_player=suggestion[0] if suggestion else None,
                distance=suggestion[1] if suggestion else None,
            )
        )

    return RosterImportAnalysis(
        matched_count=matched_count,
        unmatched=unmatched,
        orphans=orphans,
        moved=moved,
        no_prior_data=sorted(no_prior_data),
        detachable=detachable,
        file_rows_without_match=file_rows_without_match,
        association_candidates=association_candidates,
        verdicts_required=bool(file_rows_without_match) and bool(association_candidates),
    )


def apply_roster(parsed: list[dict], db: Session, associations: dict[str, Player] | None = None) -> int:
    """N'écrit jamais per/mpg/is_active/previous_team_id/draft_pick/
    games_played_this_season -- seuls `name` (à la création) et `team_id`
    sont modifiés. Le rapprochement PER N-1 se fait au moment du calcul
    (pronostic_calculator._effective_per_mpg), jamais ici : ce n'est pas une
    lacune, c'est le mécanisme déjà en place qui s'applique automatiquement
    dès que games_played_this_season reste sous le seuil (voir plan du
    chantier, point a).

    Recherche par NOM SEUL (arbitrage du chantier) : un joueur déjà en base
    sous une autre équipe est DÉPLACÉ (team_id mis à jour), jamais dupliqué
    -- il conserve ainsi son draft_pick, son games_played_this_season, son
    historique. C'est aussi ce qui rend l'import idempotent : le relancer sur
    le même fichier ne crée et ne modifie plus rien après le premier passage.

    Depuis le chantier fermeture du doublon (2026-09-12), cette recherche
    league-wide est partagée avec apply_players_advanced/apply_draft/
    POST /api/players via build_active_player_index/
    find_or_create_player_league_wide, ci-dessus -- extraction pure de ce qui
    était déjà ici, comportement inchangé (mêmes requêtes, même ordre, même
    flush par création)."""
    count = 0
    player_by_key = build_active_player_index(db)
    associations = associations or {}
    for item in parsed:
        team = _get_or_create_team(db, item["team_abbreviation"])
        associated = associations.get(_roster_match_key(item["name"]))
        if associated is not None:
            # Verdict « c'est le même joueur que… » (Décision n°39) : rapprochement
            # normal avec ce joueur -- son équipe est mise à jour, aucun doublon
            # n'est créé, et SON NOM EN BASE N'EST PAS MODIFIÉ (il doit continuer
            # de retrouver sa ligne N-1).
            if associated.team_id != team.id:
                associated.team_id = team.id
        else:
            find_or_create_player_league_wide(db, player_by_key, item["name"], team)
        count += 1
    db.flush()
    return count


class DetachRefusedError(Exception):
    """Demande de détachement refusée (message destiné à l'utilisateur) : rien
    n'a été appliqué."""


class VerdictRefusedError(Exception):
    """Verdict sur une ligne sans correspondance refusé : rien n'a été appliqué."""


@dataclass
class RowVerdict:
    """Verdict explicite, ligne par ligne, sur une ligne du fichier sans
    correspondance (Décision n°39) : `recruit` (le joueur est créé) ou
    `same_player` (rattachée au joueur existant `player_id`)."""

    file_name: str
    verdict: str
    player_id: int | None = None


@dataclass
class ValidatedVerdicts:
    recruits: list[str]  # noms (tels qu'écrits dans le fichier)
    associations: list[tuple[str, Player]]  # (nom dans le fichier, joueur existant)

    @property
    def resolved_count(self) -> int:
        return len(self.recruits) + len(self.associations)

    def association_map(self) -> dict[str, Player]:
        return {_roster_match_key(name): player for name, player in self.associations}


def _unmatched_file_row_names(parsed: list[dict], db: Session) -> dict[str, str]:
    """clé -> nom (première occurrence) des lignes du fichier qu'aucun joueur
    ACTIF de la base ne reconnaît -- la même mesure que l'import et que
    l'aperçu (analyze_roster_import)."""
    index = build_active_player_index(db)
    unmatched: dict[str, str] = {}
    for item in parsed:
        key = _roster_match_key(item["name"])
        if key not in index and key not in unmatched:
            unmatched[key] = item["name"]
    return unmatched


def validate_row_verdicts(db: Session, parsed: list[dict], verdicts: list[RowVerdict]) -> ValidatedVerdicts:
    """Gardes SERVEUR sur les verdicts, avant toute écriture. Lève
    VerdictRefusedError (rien n'est appliqué) si :
      - un verdict ne vise pas une ligne réellement SANS correspondance du fichier soumis ;
      - deux verdicts visent la même ligne ;
      - une association n'a pas de joueur, vise un joueur inexistant ou inactif ;
      - un `recruit` porte un joueur (ambigu) ;
      - deux lignes sont associées au même joueur ;
      - le joueur visé est déjà rapproché par une AUTRE ligne du fichier."""
    if not verdicts:
        return ValidatedVerdicts(recruits=[], associations=[])
    unmatched = _unmatched_file_row_names(parsed, db)
    csv_keys = {_roster_match_key(item["name"]) for item in parsed}
    seen_keys: set[str] = set()
    recruits: list[str] = []
    associations: list[tuple[str, Player]] = []
    target_ids: dict[int, str] = {}
    for verdict in verdicts:
        key = _roster_match_key(verdict.file_name)
        if key not in unmatched:
            raise VerdictRefusedError(
                f"Verdict refusé : « {verdict.file_name} » n'est pas une ligne sans correspondance du fichier "
                "(absente du fichier, ou déjà rapprochée d'un joueur de la base)."
            )
        if key in seen_keys:
            raise VerdictRefusedError(f"Verdict refusé : deux verdicts pour la ligne « {verdict.file_name} ».")
        seen_keys.add(key)
        file_name = unmatched[key]
        if verdict.verdict == "recruit":
            if verdict.player_id is not None:
                raise VerdictRefusedError(
                    f"Verdict refusé : « {file_name} » est déclarée recrue mais désigne aussi un joueur."
                )
            recruits.append(file_name)
        elif verdict.verdict == "same_player":
            if verdict.player_id is None:
                raise VerdictRefusedError(f"Verdict refusé : « {file_name} » : le joueur de la base n'est pas désigné.")
            player = db.get(Player, verdict.player_id)
            if player is None:
                raise VerdictRefusedError(
                    f"Verdict refusé : « {file_name} » désigne un joueur inexistant (identifiant {verdict.player_id})."
                )
            if not player.is_active:
                raise VerdictRefusedError(
                    f"Verdict refusé : « {file_name} » désigne un joueur inactif ({player.name})."
                )
            if player.id in target_ids:
                raise VerdictRefusedError(
                    f"Verdict refusé : « {target_ids[player.id]} » et « {file_name} » sont associées au même "
                    f"joueur ({player.name})."
                )
            if _roster_match_key(player.name) in csv_keys:
                raise VerdictRefusedError(
                    f"Verdict refusé : « {file_name} » désigne {player.name}, déjà rapproché par une autre "
                    "ligne du fichier."
                )
            target_ids[player.id] = file_name
            associations.append((file_name, player))
        else:
            raise VerdictRefusedError(f"Verdict refusé : verdict inconnu {verdict.verdict!r} pour « {verdict.file_name} ».")
    return ValidatedVerdicts(recruits=recruits, associations=associations)


def require_verdicts_when_risky(db: Session, parsed: list[dict], verdicts: ValidatedVerdicts) -> None:
    """Garde SERVEUR de la confirmation d'un import d'effectif (Décision n°39) : les verdicts
    sont OBLIGATOIRES quand les DEUX ensembles sont non vides --
      - au moins une ligne du fichier sans correspondance,
      - ET au moins un joueur actif de la base absent du fichier.
    C'est la seule configuration où une ligne sans correspondance peut être, en réalité, un joueur
    déjà en base sous un autre nom (« Ronald Holland II » pour « Ron Holland ») : sans verdict,
    elle serait importée comme recrue et créerait un doublon. Si aucun joueur n'est absent côté
    base, une ligne sans correspondance ne peut être qu'une recrue : pas de verdict exigé.
    Lève VerdictRefusedError (rien n'est écrit) en disant combien de lignes, et lesquelles."""
    unmatched = _unmatched_file_row_names(parsed, db)
    if not unmatched:
        return
    csv_keys = {_roster_match_key(item["name"]) for item in parsed}
    absent = [p for p in db.query(Player).filter(Player.is_active.is_(True)).all() if _roster_match_key(p.name) not in csv_keys]
    if not absent:
        return
    resolved_keys = {_roster_match_key(name) for name in verdicts.recruits} | {
        _roster_match_key(name) for name, _ in verdicts.associations
    }
    without_verdict = [name for key, name in unmatched.items() if key not in resolved_keys]
    if without_verdict:
        raise VerdictRefusedError(
            f"Confirmation refusée : {len(without_verdict)} ligne(s) du fichier sans correspondance n'ont pas "
            f"de verdict ({', '.join(without_verdict)}) alors que {len(absent)} joueur(s) de la base sont absents "
            "du fichier : une de ces lignes pourrait être l'un d'eux, écrit autrement. Chaque ligne doit être "
            "tranchée (recrue, ou même joueur qu'un joueur de la base) avant de confirmer."
        )


def describe_roster_row_errors(df: pd.DataFrame, errors: list[dict]) -> list[dict]:
    """Enrichit les erreurs de parse_roster (n° de ligne + message) avec ce que le
    fichier contient réellement à cette ligne (nom et équipe tels qu'écrits) :
    ces lignes bloquent tout détachement, il faut savoir quoi corriger sans deviner."""
    described: list[dict] = []
    for error in errors:
        position = error["row"] - 2  # parse_roster : row_num = index + 2 (en-tête = ligne 1)
        name = team = None
        if 0 <= position < len(df):
            record = df.iloc[position]
            name = str(record.get("Player", "")).strip() or None
            team = str(record.get("Team", "")).strip() or None
        described.append({"row": error["row"], "player_name": name, "team": team, "message": error["message"]})
    return described

def validate_detach_request(
    db: Session,
    parsed: list[dict],
    player_ids: list[int],
    has_row_errors: bool,
    verdicts: ValidatedVerdicts | None = None,
) -> list[Player]:
    """Gardes SERVEUR du détachement (Décision n°39), à appeler AVANT toute
    écriture de l'import : ne retourne que des joueurs explicitement demandés,
    toujours absents du fichier au moment de la confirmation. Liste vide ou
    absente -> aucun joueur (jamais de détachement par défaut). Lève
    DetachRefusedError (rien appliqué) si :
      - le fichier a des lignes en erreur (un nom illisible rendrait « absent du
        fichier » non fiable) ;
      - un identifiant n'existe pas, ou désigne un joueur inactif (jamais proposé) ;
      - un identifiant désigne un joueur PRÉSENT dans le fichier.
    Un joueur déjà agent libre est accepté (idempotence) mais ne sera pas recompté."""
    ids = list(dict.fromkeys(player_ids))
    if not ids:
        return []
    if has_row_errors:
        raise DetachRefusedError(
            "Détachement refusé : le fichier contient des lignes en erreur, donc la liste des joueurs "
            "absents n'est pas fiable. Corrigez le fichier d'abord."
        )
    players = {p.id: p for p in db.query(Player).filter(Player.id.in_(ids)).all()}
    unknown = [i for i in ids if i not in players]
    if unknown:
        raise DetachRefusedError(f"Détachement refusé : identifiant(s) de joueur inconnu(s) : {unknown}.")
    inactive = [players[i].name for i in ids if not players[i].is_active]
    if inactive:
        raise DetachRefusedError(
            f"Détachement refusé : joueur(s) inactif(s), jamais proposé(s) : {', '.join(inactive)}."
        )
    csv_keys = {_roster_match_key(item["name"]) for item in parsed}
    present = [players[i].name for i in ids if _roster_match_key(players[i].name) in csv_keys]
    if present:
        raise DetachRefusedError(
            f"Détachement refusé : {', '.join(present)} figure(nt) dans le fichier (un joueur présent "
            "dans le fichier n'est jamais détaché)."
        )
    # Cœur du garde-fou (Décision n°39) : aucun détachement tant qu'une ligne sans
    # correspondance n'a pas reçu de verdict -- pour détacher ne serait-ce qu'un
    # joueur, il faut avoir regardé TOUTES ces lignes.
    verdicts = verdicts or ValidatedVerdicts(recruits=[], associations=[])
    resolved_keys = {_roster_match_key(name) for name in verdicts.recruits} | {
        _roster_match_key(name) for name, _ in verdicts.associations
    }
    without_verdict = [name for key, name in _unmatched_file_row_names(parsed, db).items() if key not in resolved_keys]
    if without_verdict:
        raise DetachRefusedError(
            f"Détachement refusé : {len(without_verdict)} ligne(s) du fichier sans correspondance n'ont pas "
            f"de verdict ({', '.join(without_verdict)}). Chaque ligne doit être tranchée (recrue, ou même "
            "joueur qu'un joueur de la base) avant tout détachement."
        )
    # Contradiction : un joueur associé à une ligne du fichier est présent dans le fichier.
    associated_ids = {player.id for _, player in verdicts.associations}
    contradictory = [players[i].name for i in ids if i in associated_ids]
    if contradictory:
        raise DetachRefusedError(
            f"Détachement refusé : {', '.join(contradictory)} est associé à une ligne du fichier ; un joueur "
            "associé est présent dans le fichier et ne peut pas être détaché."
        )
    return [players[i] for i in ids]


def detach_players(db: Session, players: list[Player]) -> list[str]:
    """Détache les joueurs validés par validate_detach_request : `team_id` passe à
    NULL (agent libre) et RIEN d'autre -- `is_active` reste vrai (il doit rester
    dans l'index de l'import et être retrouvable par le malus de départ) et
    `previous_team_id` n'est pas écrit (colonne morte, limitation n°31). Un
    joueur déjà agent libre est ignoré (idempotence). Retourne les noms
    réellement détachés, dans l'ordre demandé."""
    detached: list[str] = []
    for player in players:
        if player.team_id is None:
            continue
        player.team_id = None
        detached.append(player.name)
    db.flush()
    return detached


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
