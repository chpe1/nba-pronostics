"""Parsing des rapports officiels NBA "Injury Report" (PDF).

Particularités du gabarit officiel, constatées sur des rapports réels
(tests/fixtures/Injury-Report_*.pdf) :

- Le texte brut colle les mots sans espace pour certaines cellules
  (ex: "HoustonRockets", "PorterJr.,Michael") -> nécessite une reconnaissance
  par dictionnaire (équipes) ou par correspondance normalisée (joueurs)
  plutôt qu'une simple lecture du texte.
- Les colonnes GameDate/GameTime/Matchup/Team ne sont répétées qu'au début
  d'un nouveau match/équipe (cellules "fusionnées" visuellement) -> report
  en cascade nécessaire.
- Le champ Reason peut être écrit sur plusieurs lignes, et ces lignes
  peuvent apparaître avant OU après la ligne du joueur (le bloc est centré
  verticalement), y compris en traversant un saut de page.
- L'en-tête de colonnes n'apparaît que sur la première page.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from app.models import InjuryStatus
from app.services.nba_teams import NBA_TEAMS, resolve_team_name

COLUMN_NAMES = [
    "game_date",
    "game_time",
    "matchup",
    "team",
    "player_name",
    "current_status",
    "reason",
]

# Ancrages x0 par défaut (constatés identiques sur 3 rapports officiels réels
# à des dates différentes) : utilisés si l'en-tête n'est pas détecté sur la
# première page (garde-fou défensif).
DEFAULT_COLUMN_ANCHORS = {
    "game_date": 23.1,
    "game_time": 119.6,
    "matchup": 200.0,
    "team": 264.2,
    "player_name": 425.0,
    "current_status": 585.7,
    "reason": 666.1,
}

HEADER_LABELS = {
    "game_date": "GameDate",
    "game_time": "GameTime",
    "matchup": "Matchup",
    "team": "Team",
    "player_name": "PlayerName",
    "current_status": "CurrentStatus",
    "reason": "Reason",
}
HEADER_LABEL_TEXTS = set(HEADER_LABELS.values())

FOOTER_PATTERN = re.compile(r"^Page\d+of\d+$")
TITLE_MARKER = "Report:"

STATUS_MAP = {
    "Out": InjuryStatus.OUT,
    "Questionable": InjuryStatus.QUESTIONABLE,
    "Doubtful": InjuryStatus.DOUBTFUL,
    "Probable": InjuryStatus.PROBABLE,
    "Available": InjuryStatus.AVAILABLE,
}

ROW_TOP_TOLERANCE = 2.0


@dataclass
class InjuryReportEntry:
    game_date: date | None
    game_time_raw: str
    matchup: str
    team_raw: str
    team_full_name: str | None
    team_abbreviation: str | None
    player_name_raw: str
    status: InjuryStatus | None
    status_raw: str
    reason: str


@dataclass
class _PendingEntry:
    game_date: date | None
    game_time_raw: str
    matchup: str
    team_raw: str
    player_name_raw: str
    status_raw: str
    reason_fragments: list[tuple[tuple[int, float], str]] = field(default_factory=list)


class InjuryReportParseError(Exception):
    pass


def _compute_column_breakpoints(anchors: dict[str, float]) -> list[float]:
    ordered = [anchors[name] for name in COLUMN_NAMES]
    return [(ordered[i] + ordered[i + 1]) / 2 for i in range(len(ordered) - 1)]


def _assign_column(x0: float, breakpoints: list[float]) -> str:
    for i, breakpoint in enumerate(breakpoints):
        if x0 < breakpoint:
            return COLUMN_NAMES[i]
    return COLUMN_NAMES[-1]


def _group_words_into_rows(words: list[dict]) -> list[list[dict]]:
    words_sorted = sorted(words, key=lambda w: (w["top"], w["x0"]))
    rows: list[list[dict]] = []
    current_row: list[dict] = []
    current_top: float | None = None
    for w in words_sorted:
        if current_top is None or abs(w["top"] - current_top) <= ROW_TOP_TOLERANCE:
            current_row.append(w)
            current_top = w["top"] if current_top is None else current_top
        else:
            rows.append(current_row)
            current_row = [w]
            current_top = w["top"]
    if current_row:
        rows.append(current_row)
    return rows


def _row_to_cells(row: list[dict], breakpoints: list[float]) -> dict[str, str]:
    cells: dict[str, list[str]] = {name: [] for name in COLUMN_NAMES}
    for w in sorted(row, key=lambda w: w["x0"]):
        column = _assign_column(w["x0"], breakpoints)
        cells[column].append(w["text"])
    return {name: " ".join(parts).strip() for name, parts in cells.items()}


def _parse_game_date(raw: str) -> date | None:
    try:
        return datetime.strptime(raw, "%m/%d/%Y").date()
    except ValueError:
        return None


def parse_injury_report_pdf(pdf) -> list[InjuryReportEntry]:
    """Parse un rapport de blessures NBA déjà ouvert avec pdfplumber.

    `pdf` est un objet `pdfplumber.PDF` (utiliser `pdfplumber.open(...)` côté
    appelant, pour laisser le choix entre un chemin fichier et des bytes).
    """
    anchors: dict[str, float] | None = None
    breakpoints: list[float] | None = None

    current_game_date: date | None = None
    current_game_time = ""
    current_matchup = ""
    current_team_raw = ""

    all_entries: list[_PendingEntry] = []
    current_open_entry: _PendingEntry | None = None

    for page_index, page in enumerate(pdf.pages):
        words = page.extract_words()

        if anchors is None:
            header_words = {w["text"]: w["x0"] for w in words if w["text"] in HEADER_LABEL_TEXTS}
            if len(header_words) == len(HEADER_LABELS):
                anchors = {key: header_words[label] for key, label in HEADER_LABELS.items()}
            else:
                anchors = dict(DEFAULT_COLUMN_ANCHORS)
            breakpoints = _compute_column_breakpoints(anchors)

        data_words = [
            w
            for w in words
            if w["text"] not in HEADER_LABEL_TEXTS and not FOOTER_PATTERN.match(w["text"])
        ]
        rows = _group_words_into_rows(data_words)
        # La ligne de titre ("Injury Report: ...") est répétée sur chaque page.
        rows = [row for row in rows if not any(w["text"] == TITLE_MARKER for w in row)]

        cell_rows = [_row_to_cells(row, breakpoints) for row in rows]

        anchor_indices = [
            i for i, cells in enumerate(cell_rows) if cells["player_name"] and cells["current_status"]
        ]
        page_entries: dict[int, _PendingEntry] = {}
        # Snapshot pris avant la Passe 1 : c'est la dernière entrée de la
        # page PRÉCÉDENTE, nécessaire pour rattacher une éventuelle ligne de
        # continuation en tout début de page (Passe 2). `current_open_entry`
        # est réassigné pendant la Passe 1 ci-dessous et ne doit plus servir
        # à cet effet une fois la Passe 1 lancée.
        entry_from_previous_page = current_open_entry

        # Passe 1 : créer les entrées (lignes "ancres") et reporter en
        # cascade GameDate/GameTime/Matchup/Team.
        for i, cells in enumerate(cell_rows):
            if cells["game_date"]:
                parsed_date = _parse_game_date(cells["game_date"])
                if parsed_date:
                    current_game_date = parsed_date
            if cells["game_time"]:
                current_game_time = cells["game_time"]
            if cells["matchup"]:
                current_matchup = cells["matchup"]
            if cells["team"]:
                current_team_raw = cells["team"]

            if i in anchor_indices:
                entry = _PendingEntry(
                    game_date=current_game_date,
                    game_time_raw=current_game_time,
                    matchup=current_matchup,
                    team_raw=current_team_raw,
                    player_name_raw=cells["player_name"],
                    status_raw=cells["current_status"],
                )
                if cells["reason"]:
                    entry.reason_fragments.append(((page_index, rows[i][0]["top"]), cells["reason"]))
                page_entries[i] = entry
                all_entries.append(entry)
                current_open_entry = entry

        # Passe 2 : rattacher les lignes de continuation du champ Reason
        # (qui peuvent apparaître avant OU après la ligne du joueur, le bloc
        # étant centré verticalement autour du nom).
        for i, cells in enumerate(cell_rows):
            if i in anchor_indices:
                continue
            if not cells["reason"] or cells["player_name"] or cells["current_status"]:
                continue  # ligne non exploitable, ignorée silencieusement

            row_top = rows[i][0]["top"]
            prev_anchor = max((a for a in anchor_indices if a < i), default=None)
            next_anchor = min((a for a in anchor_indices if a > i), default=None)

            if prev_anchor is not None:
                prev_entry, prev_top = page_entries[prev_anchor], rows[prev_anchor][0]["top"]
            else:
                # Pas d'ancre avant cette ligne sur CETTE page : la seule
                # candidate "précédente" possible est la dernière entrée de
                # la page précédente (le rendu ne peut pas avoir pré-affiché
                # du contenu centré d'un joueur futur avant le début de la
                # page courante).
                prev_entry, prev_top = entry_from_previous_page, None

            if next_anchor is not None:
                next_entry, next_top = page_entries[next_anchor], rows[next_anchor][0]["top"]
            else:
                next_entry = None

            if prev_entry is None:
                target = next_entry
            elif next_entry is None or prev_top is None:
                # prev_top is None => prev_entry vient d'une page précédente :
                # la distance géométrique n'est pas comparable au delà d'un
                # saut de page, on privilégie systématiquement prev_entry.
                target = prev_entry
            else:
                target = prev_entry if abs(row_top - prev_top) <= abs(row_top - next_top) else next_entry

            if target is not None:
                target.reason_fragments.append(((page_index, row_top), cells["reason"]))

        if page_entries:
            current_open_entry = all_entries[-1]

    return [_finalize_entry(entry) for entry in all_entries]


def _finalize_entry(entry: _PendingEntry) -> InjuryReportEntry:
    reason = " ".join(text for _, text in sorted(entry.reason_fragments, key=lambda item: item[0]))
    team_full_name = resolve_team_name(entry.team_raw)
    return InjuryReportEntry(
        game_date=entry.game_date,
        game_time_raw=entry.game_time_raw,
        matchup=entry.matchup,
        team_raw=entry.team_raw,
        team_full_name=team_full_name,
        team_abbreviation=NBA_TEAMS.get(team_full_name) if team_full_name else None,
        player_name_raw=entry.player_name_raw,
        status=STATUS_MAP.get(entry.status_raw),
        status_raw=entry.status_raw,
        reason=reason,
    )
