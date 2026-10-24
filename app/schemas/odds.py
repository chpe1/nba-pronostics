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
