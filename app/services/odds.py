"""Service des cotes : validation/normalisation à l'écriture, et règle de doublon.

Validation volontairement en dehors du modèle (pas de @validates SQLAlchemy, pas de CHECK en base) --
même choix que MAX_REALISTIC_MPG (app/api/players.py), levée en HTTPException texte simple dans la route.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models import Odds, OddsCollection, OddsMarket, OddsSide

# Bookmakers acceptés en SAISIE MANUELLE. Une chaîne libre validée contre cette liste, PAS un type énuméré SQL :
# ajouter un bookmaker ne doit demander qu'une entrée ici, jamais une migration (décision du 2026-10-24).
# Identifiants EXACTS de the-odds-api.com depuis le 2026-11-03 (un relevé automatique et une saisie du même
# bookmaker portent la même source et se distinguent par `Odds.collection`). Le relevé automatique, lui,
# stocke TOUS les bookmakers renvoyés par l'API, sans passer par cette liste (app/services/odds_fetcher.py).
KNOWN_ODDS_SOURCES: tuple[str, ...] = ("winamax_fr", "unibet_fr")

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
    Ces trois règles ne regardent que les SAISIES MANUELLES (collection MANUEL) : un relevé automatique du même
    bookmaker est une autre série, qui ne rend jamais une saisie « inchangée » et n'est jamais corrigée par elle.
    Ne commit jamais : à charge de l'appelant (même convention que les upserts CSV, csv_import.py)."""
    manual = OddsCollection.MANUEL
    latest = (
        db.query(Odds)
        .filter(Odds.game_id == game_id, Odds.market == market, Odds.side == side, Odds.source == source,
                Odds.collection == manual)
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
            Odds.collection == manual,
            Odds.recorded_at == recorded_at,
        )
        .one_or_none()
    )
    if same_instant is not None:
        same_instant.value = value
        db.flush()
        return OddsWriteOutcome(odds=same_instant, action="updated")

    odds = Odds(game_id=game_id, market=market, side=side, source=source, value=value, recorded_at=recorded_at,
                collection=manual)
    db.add(odds)
    db.flush()
    return OddsWriteOutcome(odds=odds, action="created")


def latest_odds_by_cell(
    db: Session, game_ids: list[int], sources: tuple[str, ...], market: OddsMarket = OddsMarket.WINNER
) -> dict:
    """Pour l'écran de saisie : le DERNIER relevé de chaque (game_id, side, source), QUELLE QU'EN SOIT L'ORIGINE
    (saisie ou relevé automatique : l'écran dit laquelle), en une seule requête -- pas une par cellule.

    Filtré sur les seules `sources` de l'écran : le relevé automatique stocke ~19 bookmakers, achat et vente, toutes
    les 30 minutes ; sans ce filtre, l'écran chargerait des milliers de lignes qu'il n'affiche pas. La requête
    s'appuie sur l'index de la contrainte uq_odds_snapshot (game_id, market, side, source, ...)."""
    if not game_ids:
        return {}
    rows = (
        db.query(Odds)
        .filter(Odds.game_id.in_(game_ids), Odds.market == market, Odds.source.in_(sources))
        .order_by(Odds.game_id, Odds.side, Odds.source, desc(Odds.recorded_at), desc(Odds.id))
        .all()
    )
    latest: dict[tuple[int, OddsSide, str], Odds] = {}
    for row in rows:
        key = (row.game_id, row.side, row.source)
        if key not in latest:  # le premier rencontré, grâce au tri ci-dessus, est le plus récent
            latest[key] = row
    return latest
