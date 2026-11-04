"""Relevé automatique des cotes via the-odds-api.com (https://the-odds-api.com/liveapi/guides/v4/).

UN appel = 1 crédit (marché `h2h`, région `eu`), quel que soit le nombre de matchs : la réponse contient tous les
matchs NBA dont les bookmakers ont ouvert le marché. Plan gratuit : 500 crédits par mois, AUCUN historique (cotes
passées refusées en 401, vérifié le 2026-11-03) -- ce qui n'est pas relevé à temps est perdu définitivement.

Règles (validées par l'utilisateur le 2026-11-03) :
  - TOUS les bookmakers renvoyés sont stockés, sous leur identifiant exact de l'API (`winamax_fr`, `unibet_fr`,
    `betfair_ex_eu`, `winamax_de`...), achat (`h2h` -> WINNER) ET vente (`h2h_lay` -> WINNER_LAY, bourses
    d'échange). Rien n'est jugé au relevé : une bourse vide (1,01 / 1000) est stockée telle quelle ;
  - CHAQUE cote lue est écrite, même inchangée depuis le relevé précédent, avec `recorded_at` = instant de l'appel
    et `bookmaker_updated_at` = instant où le bookmaker l'a changée. Rien n'est jamais écrasé ;
  - un match est reconnu par une correspondance STRICTE : les deux libellés figurent dans ODDS_API_TEAM_ABBREVIATIONS,
    et un match existe en base à la même date de New York avec les mêmes équipes à domicile et à l'extérieur. Tout
    le reste est SIGNALÉ avec son motif, jamais deviné (même règle que les rapports de blessures) ;
  - un match terminé, reporté ou déjà commencé n'est pas relevé. « Commencé » se juge sur la PLUS TÔT des deux heures
    de coup d'envoi (la nôtre, celle de l'API) : une cote prise en cours de match ne passe jamais ;
  - tout écart d'heure de coup d'envoi est signalé ; une API PLUS TÔT que notre base est une ALERTE (notre protection
    « match commencé » se déclenche peut-être trop tard), recalculée à l'affichage tant que la base n'est pas corrigée
    (`active_kickoff_alerts`). Ni le calendrier ni la protection des pronostics ne sont corrigés ici ;
  - chaque appel, réussi ou non, laisse une ligne dans le journal (`OddsFetchRun`).

La clé (ODDS_API_KEY, `.env`, jamais dans le code ni dans Git) n'apparaît dans aucun message ni aucun journal.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.models import Game, GameStatus, Odds, OddsCollection, OddsFetchRun, OddsFetchTrigger, OddsMarket, OddsSide, Team
from app.services.nba_calendar import NBA_TIMEZONE, game_start_utc

logger = logging.getLogger(__name__)

_API_KEY_IN_URL = re.compile(r"(apiKey=)[^&\s\"']+")


class _RedactApiKeyFilter(logging.Filter):
    """httpx journalise CHAQUE requête au niveau INFO avec son adresse complète, et l'API de cotes exige la clé
    DANS l'adresse (`?apiKey=`) : sans ce filtre, chaque relevé l'écrirait en clair dans logs/app.log (constaté
    par un test le 2026-11-03). Il remplace la valeur par *** dans toute ligne du journal « httpx »."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "apiKey=" in message:
            record.msg = _API_KEY_IN_URL.sub(lambda m: m.group(1) + "***", message)
            record.args = None
        return True


_httpx_logger = logging.getLogger("httpx")
if not any(isinstance(f, _RedactApiKeyFilter) for f in _httpx_logger.filters):
    _httpx_logger.addFilter(_RedactApiKeyFilter())

ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds"
ODDS_API_PARAMS = {"regions": "eu", "markets": "h2h", "oddsFormat": "decimal"}
# Délai maximal d'un appel (secondes) : une API qui ne répond pas ne doit pas bloquer la tâche planifiée ni le bouton.
ODDS_API_TIMEOUT = 30.0


# Libellés EXACTS de l'API -> abréviation de nos 30 équipes. Recopiés de la réponse de
# /v4/sports/basketball_nba/participants du 2026-11-03 (32 entrées) ; aucun n'est déduit. 29 sont identiques au nom
# en base ; un seul diffère : « Los Angeles Clippers » (base : « LA Clippers »). Les deux entrées « Golden State
# Warriors Blue » / « Gold » (équipes du All-Star Game) n'y figurent volontairement pas : un match où elles jouent est
# signalé « équipe inconnue ».
ODDS_API_TEAM_ABBREVIATIONS: dict[str, str] = {
    "Atlanta Hawks": "ATL",
    "Boston Celtics": "BOS",
    "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI",
    "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL",
    "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW",
    "Houston Rockets": "HOU",
    "Indiana Pacers": "IND",
    "Los Angeles Clippers": "LAC",
    "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC",
    "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA",
    "Washington Wizards": "WAS",
}

# Marchés de l'API -> nos marchés. Tout autre marché est ignoré et signalé.
API_MARKETS: dict[str, OddsMarket] = {"h2h": OddsMarket.WINNER, "h2h_lay": OddsMarket.WINNER_LAY}

# Les deux bookmakers de l'écran Cotes : un match où l'un d'eux manque est signalé (l'utilisateur sait qu'il devra
# peut-être saisir à la main). Tous les autres sont stockés sans être suivis un par un.
SCREEN_BOOKMAKERS: tuple[str, ...] = ("winamax_fr", "unibet_fr")

SOURCE_MAX_LENGTH = 30  # Odds.source = String(30)

# Motifs (clés stables du compte-rendu, traduites par l'écran).
UNMATCHED_UNKNOWN_TEAM = "unknown_team"  # libellé absent de la table stricte
UNMATCHED_NOT_IN_DATABASE = "not_in_database"  # aucun match ce jour-là avec ces équipes
UNMATCHED_HOME_AWAY_REVERSED = "home_away_reversed"  # match en base avec domicile et extérieur inversés
UNMATCHED_BAD_START_TIME = "bad_start_time"  # heure de début illisible
UNMATCHED_DUPLICATE_EVENT = "duplicate_event"  # deux événements de l'API pour le même match
IGNORED_FINISHED = "finished"
IGNORED_POSTPONED = "postponed"
IGNORED_STARTED = "started"
NO_ODDS_NOT_IN_RESPONSE = "not_in_response"  # match du jour absent de la réponse : marché pas encore ouvert
NO_ODDS_NO_BOOKMAKER = "no_bookmaker"  # événement présent, aucun bookmaker
ANOMALY_UNKNOWN_MARKET = "unknown_market"
ANOMALY_OUTCOME_NAME = "outcome_name"  # nom d'une issue qui n'est ni l'équipe à domicile ni celle à l'extérieur
ANOMALY_BAD_PRICE = "bad_price"  # cote absente, non numérique ou <= 1
ANOMALY_BAD_SOURCE = "bad_source"  # identifiant de bookmaker vide ou trop long pour la colonne


class OddsApiError(Exception):
    """Appel impossible ou réponse inexploitable. Le message ne contient jamais la clé."""

    def __init__(self, message: str, http_status: int | None = None):
        super().__init__(message)
        self.http_status = http_status


@dataclass
class ApiResponse:
    events: list[dict]
    http_status: int
    credits_used: int | None
    credits_remaining: int | None


def _redact(text: str, api_key: str) -> str:
    return text.replace(api_key, "***") if api_key else text


def _int_header(headers: httpx.Headers, name: str) -> int | None:
    raw = headers.get(name)
    try:
        return int(float(raw)) if raw is not None else None
    except ValueError:
        return None


def fetch_odds(client: httpx.Client, api_key: str) -> ApiResponse:
    """UN appel à l'API. Lève OddsApiError (clé masquée) en cas d'échec réseau, de statut non 200 ou de réponse
    qui n'est pas une liste."""
    try:
        response = client.get(ODDS_API_URL, params={"apiKey": api_key, **ODDS_API_PARAMS})
    except httpx.HTTPError as exc:
        raise OddsApiError(_redact(f"Appel à the-odds-api impossible : {exc}", api_key)) from None
    if response.status_code != 200:
        raise OddsApiError(
            _redact(f"the-odds-api a répondu {response.status_code} : {response.text[:300]}", api_key),
            http_status=response.status_code,
        )
    try:
        events = response.json()
    except ValueError:
        raise OddsApiError("Réponse de the-odds-api illisible (pas du JSON).", http_status=200) from None
    if not isinstance(events, list):
        raise OddsApiError("Réponse de the-odds-api inattendue (pas une liste de matchs).", http_status=200)
    return ApiResponse(
        events=events,
        http_status=200,
        credits_used=_int_header(response.headers, "x-requests-last"),
        credits_remaining=_int_header(response.headers, "x-requests-remaining"),
    )


def _parse_api_instant(raw) -> datetime | None:
    """« 2026-11-05T00:00:00Z » -> UTC naïf. None si illisible."""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None  # sans fuseau, l'instant est ambigu : on ne devine pas
    return moment.astimezone(UTC).replace(tzinfo=None)


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() + "Z" if moment is not None else None


def _nba_date(moment_utc: datetime) -> date:
    return moment_utc.replace(tzinfo=UTC).astimezone(NBA_TIMEZONE).date()


def _label(game: Game) -> str:
    return f"{game.away_team.abbreviation}@{game.home_team.abbreviation}"


def _valid_price(raw) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    return value if value > 1.0 else None


def process_events(db: Session, events: list[dict], fetched_at: datetime, run: OddsFetchRun | None) -> dict:
    """Rapproche les événements de l'API des matchs en base et ajoute les cotes (sans commit). Retourne le
    compte-rendu (sérialisable en JSON). `fetched_at` : instant de l'appel, UTC naïf."""
    teams_by_abbr = {t.abbreviation: t for t in db.query(Team).all()}
    report: dict = {
        "matched": [],
        "unmatched": [],
        "ignored": [],
        "no_odds_yet": [],
        "time_gaps": [],
        "anomalies": [],
        "rows_written": 0,
    }
    seen_game_ids: set[int] = set()
    rows = 0

    for event in events:
        home_label, away_label = event.get("home_team"), event.get("away_team")
        raw_start = event.get("commence_time")
        base_entry = {"api_id": event.get("id"), "home_team": home_label, "away_team": away_label,
                      "api_start": raw_start}

        home_abbr = ODDS_API_TEAM_ABBREVIATIONS.get(home_label)
        away_abbr = ODDS_API_TEAM_ABBREVIATIONS.get(away_label)
        home_team = teams_by_abbr.get(home_abbr) if home_abbr else None
        away_team = teams_by_abbr.get(away_abbr) if away_abbr else None
        if home_team is None or away_team is None:
            unknown = [n for n, t in ((home_label, home_team), (away_label, away_team)) if t is None]
            report["unmatched"].append({**base_entry, "reason": UNMATCHED_UNKNOWN_TEAM, "unknown_labels": unknown})
            continue

        api_start = _parse_api_instant(raw_start)
        if api_start is None:
            report["unmatched"].append({**base_entry, "reason": UNMATCHED_BAD_START_TIME})
            continue
        day = _nba_date(api_start)

        game = (
            db.query(Game)
            .filter(Game.game_date_only == day, Game.home_team_id == home_team.id, Game.away_team_id == away_team.id)
            .one_or_none()
        )
        if game is None:
            reversed_game = (
                db.query(Game)
                .filter(Game.game_date_only == day, Game.home_team_id == away_team.id,
                        Game.away_team_id == home_team.id)
                .one_or_none()
            )
            reason = UNMATCHED_HOME_AWAY_REVERSED if reversed_game is not None else UNMATCHED_NOT_IN_DATABASE
            report["unmatched"].append({**base_entry, "reason": reason, "nba_date": day.isoformat()})
            continue
        if game.id in seen_game_ids:
            report["unmatched"].append({**base_entry, "reason": UNMATCHED_DUPLICATE_EVENT, "game_id": game.id})
            continue
        seen_game_ids.add(game.id)

        our_start = game_start_utc(game.game_date)
        gap_minutes = round((api_start - our_start).total_seconds() / 60)
        game_entry = {"game_id": game.id, "label": _label(game), "nba_date": day.isoformat(),
                      "api_start": _iso(api_start), "our_start": _iso(our_start), "gap_minutes": gap_minutes}

        if game.status == GameStatus.FINISHED:
            report["ignored"].append({**game_entry, "reason": IGNORED_FINISHED})
            continue
        if game.status == GameStatus.POSTPONED:
            report["ignored"].append({**game_entry, "reason": IGNORED_POSTPONED})
            continue
        if fetched_at >= min(our_start, api_start):
            report["ignored"].append({**game_entry, "reason": IGNORED_STARTED})
            continue

        if gap_minutes != 0:
            report["time_gaps"].append({**game_entry, "alert": gap_minutes < 0})

        bookmakers = event.get("bookmakers") or []
        if not bookmakers:
            report["no_odds_yet"].append({**game_entry, "reason": NO_ODDS_NO_BOOKMAKER})
            continue

        written_here = 0
        sources_here: list[str] = []
        for bookmaker in bookmakers:
            source = bookmaker.get("key")
            if not isinstance(source, str) or not source or len(source) > SOURCE_MAX_LENGTH:
                report["anomalies"].append({**game_entry, "bookmaker": source, "reason": ANOMALY_BAD_SOURCE})
                continue
            wrote_for_bookmaker = False
            for market in bookmaker.get("markets") or []:
                our_market = API_MARKETS.get(market.get("key"))
                if our_market is None:
                    report["anomalies"].append({**game_entry, "bookmaker": source, "market": market.get("key"),
                                                "reason": ANOMALY_UNKNOWN_MARKET})
                    continue
                updated_at = _parse_api_instant(market.get("last_update"))
                for outcome in market.get("outcomes") or []:
                    name = outcome.get("name")
                    side = OddsSide.HOME if name == home_label else OddsSide.AWAY if name == away_label else None
                    if side is None:
                        report["anomalies"].append({**game_entry, "bookmaker": source, "market": market.get("key"),
                                                    "outcome": name, "reason": ANOMALY_OUTCOME_NAME})
                        continue
                    price = _valid_price(outcome.get("price"))
                    if price is None:
                        report["anomalies"].append({**game_entry, "bookmaker": source, "market": market.get("key"),
                                                    "outcome": name, "price": outcome.get("price"),
                                                    "reason": ANOMALY_BAD_PRICE})
                        continue
                    db.add(Odds(
                        game_id=game.id, market=our_market, side=side, source=source, value=price,
                        recorded_at=fetched_at, collection=OddsCollection.API, bookmaker_updated_at=updated_at,
                        fetch_run=run,
                    ))
                    written_here += 1
                    wrote_for_bookmaker = True
            if wrote_for_bookmaker:
                sources_here.append(source)
        rows += written_here
        report["matched"].append({
            **game_entry,
            "rows": written_here,
            "bookmakers": len(sources_here),
            "missing_screen_bookmakers": [b for b in SCREEN_BOOKMAKERS if b not in sources_here],
        })

    # Matchs du jour NBA de l'appel, à venir, que la réponse ne contient pas : marché pas encore ouvert. Distinct
    # d'un match non reconnu (la réponse contient un événement qu'on ne sait pas rattacher).
    today = _nba_date(fetched_at)
    upcoming_today = (
        db.query(Game)
        .filter(Game.game_date_only == today, Game.status == GameStatus.SCHEDULED)
        .order_by(Game.game_date)
        .all()
    )
    for game in upcoming_today:
        if game.id in seen_game_ids or fetched_at >= game_start_utc(game.game_date):
            continue
        report["no_odds_yet"].append({"game_id": game.id, "label": _label(game), "nba_date": today.isoformat(),
                                      "our_start": _iso(game_start_utc(game.game_date)),
                                      "reason": NO_ODDS_NOT_IN_RESPONSE})

    db.flush()
    report["rows_written"] = rows
    return report


def run_odds_fetch(
    db: Session, client: httpx.Client, api_key: str, trigger: OddsFetchTrigger, fetched_at: datetime
) -> OddsFetchRun:
    """Un relevé complet : appel, rapprochement, écriture, journal. Ne valide PAS la transaction (à charge de
    l'appelant). Un échec d'appel est journalisé (statut, erreur) et n'écrit aucune cote."""
    run = OddsFetchRun(fetched_at=fetched_at, trigger=trigger, events_returned=0, rows_written=0)
    db.add(run)
    try:
        response = fetch_odds(client, api_key)
    except OddsApiError as exc:
        run.http_status = exc.http_status
        run.error = str(exc)
        db.flush()
        logger.warning("Relevé des cotes en échec : %s", run.error)
        return run
    run.http_status = response.http_status
    run.credits_used = response.credits_used
    run.credits_remaining = response.credits_remaining
    run.events_returned = len(response.events)
    report = process_events(db, response.events, fetched_at, run)
    run.rows_written = report["rows_written"]
    run.report = report
    db.flush()
    logger.info(
        "Cotes relevées : %s matchs renvoyés, %s reconnus, %s non reconnus, %s lignes écrites, %s crédits restants",
        run.events_returned, len(report["matched"]), len(report["unmatched"]), run.rows_written,
        run.credits_remaining,
    )
    return run


@dataclass(frozen=True)
class KickoffAlert:
    game_id: int
    label: str
    api_start: datetime  # UTC naïf
    our_start: datetime  # UTC naïf, heure ACTUELLE en base
    minutes_earlier: int
    fetched_at: datetime  # relevé qui l'a constaté


# L'alerte ne regarde que les relevés récents : une heure annoncée il y a plus longtemps n'est plus une information.
ALERT_LOOKBACK = timedelta(days=3)


def active_kickoff_alerts(db: Session, now: datetime) -> list[KickoffAlert]:
    """Matchs à venir pour lesquels le DERNIER relevé qui les contient annonce un coup d'envoi PLUS TÔT que l'heure
    actuellement en base. Recalculé à chaque affichage, rien n'est stocké à part : l'alerte disparaît d'elle-même dès
    que l'heure du match est corrigée sur l'écran Matchs (ou que l'API s'aligne), ou quand le match a commencé."""
    runs = (
        db.query(OddsFetchRun)
        .filter(OddsFetchRun.fetched_at >= now - ALERT_LOOKBACK, OddsFetchRun.report.isnot(None))
        .order_by(OddsFetchRun.fetched_at.desc(), OddsFetchRun.id.desc())
        .all()
    )
    latest: dict[int, tuple[datetime, datetime]] = {}  # game_id -> (heure annoncée par l'API, instant du relevé)
    for run in runs:
        report = run.report or {}
        for entry in [*report.get("matched", []), *report.get("no_odds_yet", []), *report.get("ignored", [])]:
            api_start = _parse_api_instant(entry.get("api_start"))
            game_id = entry.get("game_id")
            if game_id is None or api_start is None or game_id in latest:
                continue
            latest[game_id] = (api_start, run.fetched_at)
    alerts: list[KickoffAlert] = []
    for game_id, (api_start, seen_at) in latest.items():
        game = db.get(Game, game_id)
        if game is None or game.status != GameStatus.SCHEDULED:
            continue
        our_start = game_start_utc(game.game_date)
        if now >= min(our_start, api_start) or api_start >= our_start:
            continue
        alerts.append(KickoffAlert(
            game_id=game.id, label=_label(game), api_start=api_start, our_start=our_start,
            minutes_earlier=round((our_start - api_start).total_seconds() / 60), fetched_at=seen_at,
        ))
    alerts.sort(key=lambda a: a.api_start)
    return alerts
