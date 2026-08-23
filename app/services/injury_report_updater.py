"""Rapproche les entrées parsées d'un rapport de blessures avec les joueurs
en base, et met à jour leur statut.

Limite connue (MVP) : seuls les joueurs présents dans le rapport sont mis à
jour. Un joueur qui disparaît du rapport (blessure résolue) n'est PAS remis
automatiquement à `healthy` — cette politique de "reset" devra être décidée
avec les vraies données de la saison (par équipe/jour de match) avant mise
en production.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import Player, Team
from app.services.injury_report_parser import InjuryReportEntry

_NON_ALNUM = re.compile(r"[^a-z0-9]")


def _normalize(s: str) -> str:
    return _NON_ALNUM.sub("", s.lower())


def build_match_key(player_name_raw: str) -> str:
    """"Last,First" (format du rapport PDF) -> clé normalisée comparable à
    un nom "First Last" issu d'un import CSV (ordre Prénom puis Nom)."""
    last, _, first = player_name_raw.partition(",")
    return _normalize(first) + _normalize(last)


def resolve_player(db: Session, entry: InjuryReportEntry) -> Player | None:
    if entry.team_abbreviation is None:
        return None
    team = db.query(Team).filter(Team.abbreviation == entry.team_abbreviation).one_or_none()
    if team is None:
        return None
    key = build_match_key(entry.player_name_raw)
    for player in db.query(Player).filter(Player.team_id == team.id).all():
        if _normalize(player.name) == key:
            return player
    return None


@dataclass
class ApplyResult:
    matched_count: int = 0
    unmatched_entries: list[InjuryReportEntry] = field(default_factory=list)


def apply_injury_report(db: Session, entries: list[InjuryReportEntry]) -> ApplyResult:
    result = ApplyResult()
    # Colonne DateTime naïve (cohérent avec created_at/updated_at ailleurs
    # dans l'app, stockés en UTC naïf via CURRENT_TIMESTAMP côté SQLite).
    now = datetime.now(UTC).replace(tzinfo=None)
    for entry in entries:
        if entry.status is None:
            result.unmatched_entries.append(entry)
            continue
        player = resolve_player(db, entry)
        if player is None:
            result.unmatched_entries.append(entry)
            continue
        player.injury_status = entry.status
        player.injury_updated_at = now
        result.matched_count += 1
    db.flush()
    return result
