from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class OddsEntryWrite(BaseModel):
    """Une cellule de l'écran de saisie. `value` est le texte TEL QUE TAPÉ (« 1,85 » ou « 1.85 ») --
    parsé et validé côté serveur (app/services/odds.py::parse_odds_value), jamais pré-converti par le
    frontend : un seul endroit sait ce qu'est une cote valide."""

    game_id: int
    side: Literal["home", "away"]
    source: str
    value: str


class OddsBatchWrite(BaseModel):
    # Un seul instant de relevé pour tout le lot (l'écran saisit une soirée entière à la fois) ; peut
    # porter un fuseau (converti en UTC naïf côté serveur, voir to_naive_utc) ou être naïf (supposé déjà
    # UTC). Les cellules VIDES ne figurent simplement pas dans `entries` -- aucune ligne "valeur nulle".
    recorded_at: datetime
    entries: list[OddsEntryWrite]


class OddsBatchResultEntry(BaseModel):
    game_id: int
    side: Literal["home", "away"]
    source: str
    outcome: Literal["created", "updated", "unchanged", "skipped_started", "rejected"]
    detail: str | None = None


class OddsBatchResult(BaseModel):
    created_count: int
    updated_count: int
    unchanged_count: int
    skipped_count: int
    rejected_count: int
    entries: list[OddsBatchResultEntry]


class OddsCellRead(BaseModel):
    """Dernier relevé connu pour une cellule (source x côté), ou valeurs nulles si aucun encore. `recorded_at`
    est rendu en ISO 8601 avec un « Z » explicite (UTC) -- jamais une chaîne naïve ambiguë, qui serait lue
    comme une heure locale par `new Date(...)` côté navigateur (voir CLAUDE.md, limitation n°35)."""

    value: float | None = None
    recorded_at: str | None = None
    # Comment ce dernier relevé a été pris (saisie à la main ou relevé automatique), pour que l'écran le dise.
    collection: Literal["manuel", "api"] | None = None


class OddsGameRead(BaseModel):
    id: int
    game_date: str  # heure murale US/ET, même convention que le reste du projet (Décision n°3)
    home_team_name: str
    home_team_abbreviation: str
    away_team_name: str
    away_team_abbreviation: str
    started: bool
    winamax_home: OddsCellRead
    winamax_away: OddsCellRead
    unibet_home: OddsCellRead
    unibet_away: OddsCellRead


class OddsDayRead(BaseModel):
    date: str
    games: list[OddsGameRead]


class OddsFetchRunRead(BaseModel):
    """Une ligne du journal des appels à the-odds-api.com. Instants en ISO 8601 avec « Z » (UTC). `report` (le
    compte-rendu complet) n'est renvoyé que par le bouton et pour le dernier appel de l'état ; les autres lignes du
    journal n'en portent que les comptes."""

    id: int
    fetched_at: str
    trigger: Literal["scheduled", "button"]
    http_status: int | None = None
    error: str | None = None
    credits_used: int | None = None
    credits_remaining: int | None = None
    events_returned: int
    rows_written: int
    matched_count: int
    unmatched_count: int
    no_odds_yet_count: int
    ignored_count: int
    time_gap_count: int
    anomaly_count: int
    report: dict | None = None


class KickoffAlertRead(BaseModel):
    """L'API annonce un coup d'envoi PLUS TÔT que notre calendrier, pour un match à venir. Rien n'est corrigé :
    l'alerte informe, l'utilisateur décide (écran Matchs)."""

    game_id: int
    label: str
    api_start: str
    our_start: str
    minutes_earlier: int
    fetched_at: str


class OddsFetchStatusRead(BaseModel):
    scheduler_enabled: bool
    api_key_configured: bool
    credits_threshold: int
    last_known_credits: int | None = None
    last_known_credits_at: str | None = None
    # Dernier solde connu sous le seuil : la tâche planifiée n'appelle plus (le bouton, si).
    scheduled_suspended: bool
    latest_run: OddsFetchRunRead | None = None
    recent_runs: list[OddsFetchRunRead]
    alerts: list[KickoffAlertRead]
