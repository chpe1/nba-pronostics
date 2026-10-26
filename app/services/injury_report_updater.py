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
from app.services.player_matching import fold_diacritics, tolerant_name_key
from app.services.injury_report_parser import InjuryReportEntry

_NON_ALNUM = re.compile(r"[^a-z0-9]")


def _normalize(s: str) -> str:
    # Le PDF de la NBA écrit les noms sans diacritiques ("Topic,Nikola"), la base
    # les contient ("Nikola Topić") : on replie AVANT de retirer le non-alphanumérique,
    # sinon "ć" est simplement supprimé ("topi"). Portée locale à cette source.
    return _NON_ALNUM.sub("", fold_diacritics(s.lower()))


def _reordered_name(player_name_raw: str) -> str:
    """Le PDF écrit "Nom,Prénom" (2 champs, un éventuel suffixe COLLÉ au nom : "LivelyII,Dereck")
    -- mais parfois "Nom,Suffixe,Prénom" (3 champs, le suffixe est son PROPRE champ :
    "Udeh,Jr.,Ernest"). Les deux formes cohabitent dans un même rapport (mesuré le 2026-10-26).
    Un découpage à la première virgule seulement (l'ancien comportement) fabrique, pour la forme
    à 3 champs, un prénom "Jr.,Ernest" qui ne correspond plus à rien -- le joueur n'était pas
    retrouvé, en silence.

    Reconstruit "Prénom Nom [Suffixe]" dans tous les cas, pour que le suffixe, quand il existe,
    se retrouve TOUJOURS en fin de chaîne -- condition nécessaire pour que tolerant_name_key
    (qui ne replie un suffixe qu'en fin de chaîne, voir player_matching.py) le reconnaisse."""
    fields = [f.strip() for f in player_name_raw.split(",")]
    if len(fields) == 3:
        last, suffix, first = fields
        return f"{first} {last} {suffix}"
    if len(fields) == 2:
        last, first = fields
        return f"{first} {last}"
    return player_name_raw  # forme jamais rencontrée (1 ou 4+ champs) : repli sur le texte brut


def build_match_key(player_name_raw: str) -> str:
    """"Last,First" ou "Last,Suffixe,First" (les deux formes réelles du rapport PDF, voir
    _reordered_name) -> clé normalisée STRICTE, comparable à un nom "First Last[ Suffixe]"
    issu d'un import CSV (ordre Prénom puis Nom)."""
    return _normalize(_reordered_name(player_name_raw))


def resolve_player(db: Session, entry: InjuryReportEntry) -> Player | None:
    if entry.team_abbreviation is None:
        return None
    team = db.query(Team).filter(Team.abbreviation == entry.team_abbreviation).one_or_none()
    if team is None:
        return None
    candidates = db.query(Player).filter(Player.team_id == team.id).all()

    key = build_match_key(entry.player_name_raw)
    strict_matches = [p for p in candidates if _normalize(p.name) == key]
    if len(strict_matches) == 1:
        return strict_matches[0]
    if strict_matches:
        # Deux joueurs d'une même équipe dont les noms STRICTS coïncident déjà : ambigu,
        # on ne choisit pas au hasard, l'entrée reste non rattachée.
        return None

    # Repli TOLÉRANT (accents, ponctuation, suffixe absent d'un seul des deux côtés) -- la
    # même clé tolérante que le moteur de calcul (player_matching.tolerant_name_key), jamais
    # une troisième normalisation réécrite ici. Même garde contre la confusion que partout
    # ailleurs où elle est utilisée (pronostic_calculator.py, csv_import.py) : si la clé
    # tolérante désigne plusieurs joueurs de l'équipe (ex. "Gary Payton" et "Gary Payton II"),
    # aucun résultat plutôt qu'un choix au hasard.
    tolerant_key = tolerant_name_key(_reordered_name(entry.player_name_raw))
    tolerant_matches = [p for p in candidates if tolerant_name_key(p.name) == tolerant_key]
    return tolerant_matches[0] if len(tolerant_matches) == 1 else None


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
        player.injury_reason = entry.reason or None
        player.injury_updated_at = now
        result.matched_count += 1
    db.flush()
    return result
