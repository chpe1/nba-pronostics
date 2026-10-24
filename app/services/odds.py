"""Service des cotes : validation/normalisation à l'écriture, et règle de doublon.

Validation volontairement en dehors du modèle (pas de @validates SQLAlchemy, pas de CHECK en base) --
même choix que MAX_REALISTIC_MPG (app/api/players.py), levée en HTTPException texte simple dans la route.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models import Odds, OddsMarket, OddsSide

# Liste connue des bookmakers. Une chaîne libre validée contre cette liste, PAS un type énuméré SQL :
# ajouter un troisième bookmaker ne doit demander qu'une entrée ici, jamais une migration (décision du
# 2026-10-24).
KNOWN_ODDS_SOURCES: tuple[str, ...] = ("winamax", "unibet")

MIN_ODDS_VALUE = 1.01
MAX_ODDS_VALUE = 100.0

# Tolérance de comparaison flottante pour "même valeur qu'avant" -- les cotes réelles ont 2 à 3
# décimales, cette tolérance est largement sous le moindre écart significatif.
_VALUE_EQUALITY_TOLERANCE = 1e-9


class InvalidOddsSourceError(ValueError):
    pass


class InvalidOddsValueError(ValueError):
    pass


def normalize_odds_source(raw: str) -> str:
    """Replie la casse (« Winamax » et « winamax » sont la même source, jamais deux lignes) et valide
    contre KNOWN_ODDS_SOURCES. Lève InvalidOddsSourceError sinon -- jamais une création silencieuse d'une
    source inconnue (une faute de frappe créerait un troisième bookmaker fantôme, invisible du reste de
    l'écran qui n'affiche que Winamax/Unibet)."""
    normalized = raw.strip().casefold()
    if normalized not in KNOWN_ODDS_SOURCES:
        raise InvalidOddsSourceError(
            f"Source de cote inconnue : « {raw} ». Sources acceptées : {', '.join(KNOWN_ODDS_SOURCES)}."
        )
    return normalized


def parse_odds_value(raw: str) -> float:
    """Accepte la virgule décimale française ET le point (« je ne veux pas d'erreur parce que j'ai tapé
    un point »). Refuse sous 1,01 ou au-dessus de 100 -- plancher ET plafond, comme MAX_REALISTIC_MPG
    (Décision d'architecture n°21)."""
    text = raw.strip().replace(",", ".")
    try:
        value = float(text)
    except ValueError as exc:
        raise InvalidOddsValueError(f"Cote invalide : « {raw} » n'est pas un nombre.") from exc
    if not (MIN_ODDS_VALUE <= value <= MAX_ODDS_VALUE):
        raise InvalidOddsValueError(
            f"Cote invalide ({value}) : doit être comprise entre {MIN_ODDS_VALUE} et {MAX_ODDS_VALUE}."
        )
    return value


def to_naive_utc(moment: datetime) -> datetime:
    """Convertit un datetime AWARE (offset envoyé par le frontend, ex. heure de Paris) en UTC naïf, la
    convention du projet pour un instant qui n'est pas une date de calendrier de match (voir Odds.recorded_at).
    Un datetime déjà naïf est renvoyé tel quel (supposé déjà en UTC par l'appelant)."""
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


@dataclass
class OddsWriteOutcome:
    odds: Odds
    action: str  # "created" | "updated" | "unchanged"


def record_odds(
    db: Session,
    game_id: int,
    side: OddsSide,
    source: str,
    value: float,
    recorded_at: datetime,
    market: OddsMarket = OddsMarket.WINNER,
) -> OddsWriteOutcome:
    """Applique la règle de doublon à TROIS cas (décidée et validée le 2026-10-24) :
    1. même valeur que le dernier relevé connu pour (game, market, side, source) -> rien n'est écrit ;
    2. valeur différente, même `recorded_at` qu'un relevé déjà en base -> ce relevé est corrigé en place ;
    3. valeur différente, `recorded_at` différent (ou aucun relevé antérieur) -> nouvelle ligne.
    Ne commit jamais : à charge de l'appelant (même convention que les upserts CSV, csv_import.py)."""
    latest = (
        db.query(Odds)
        .filter(Odds.game_id == game_id, Odds.market == market, Odds.side == side, Odds.source == source)
        .order_by(desc(Odds.recorded_at), desc(Odds.id))
        .first()
    )
    if latest is not None and abs(latest.value - value) < _VALUE_EQUALITY_TOLERANCE:
        return OddsWriteOutcome(odds=latest, action="unchanged")

    same_instant = (
        db.query(Odds)
        .filter(
            Odds.game_id == game_id,
            Odds.market == market,
            Odds.side == side,
            Odds.source == source,
            Odds.recorded_at == recorded_at,
        )
        .one_or_none()
    )
    if same_instant is not None:
        same_instant.value = value
        db.flush()
        return OddsWriteOutcome(odds=same_instant, action="updated")

    odds = Odds(game_id=game_id, market=market, side=side, source=source, value=value, recorded_at=recorded_at)
    db.add(odds)
    db.flush()
    return OddsWriteOutcome(odds=odds, action="created")


def latest_odds_by_cell(db: Session, game_ids: list[int], market: OddsMarket = OddsMarket.WINNER) -> dict:
    """Pour l'écran de saisie : le DERNIER relevé de chaque (game_id, side, source), en une seule requête
    (pas une par cellule -- une soirée de 11 matchs fait déjà 44 cellules)."""
    if not game_ids:
        return {}
    rows = (
        db.query(Odds)
        .filter(Odds.game_id.in_(game_ids), Odds.market == market)
        .order_by(Odds.game_id, Odds.side, Odds.source, desc(Odds.recorded_at), desc(Odds.id))
        .all()
    )
    latest: dict[tuple[int, OddsSide, str], Odds] = {}
    for row in rows:
        key = (row.game_id, row.side, row.source)
        if key not in latest:  # le premier rencontré, grâce au tri ci-dessus, est le plus récent
            latest[key] = row
    return latest
