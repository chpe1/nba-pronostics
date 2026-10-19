"""Récupération automatique du dernier rapport de blessures NBA publié.

Les PDF sont servis sans protection par ak-static.cms.nba.com, à une adresse
PRÉVISIBLE construite sur la date et l'heure de publication, en heure de New
York (US/Eastern) :

    https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-03-11_03_30PM.pdf

La page de listing official.nba.com, elle, renvoie 403 (pare-feu Akamai) --
on ne passe donc plus par elle : on construit l'adresse directement et on
remonte dans le temps par pas de 15 minutes jusqu'à trouver un rapport.

Rythme de publication mesuré le 2026-10-19 (requêtes HEAD, voir CLAUDE.md) :
un rapport tous les quarts d'heure (:00, :15, :30, :45), 96 par jour, de
00:00 à 23:45 heure de New York, y compris les jours sans match. Un fichier
ABSENT répond 403 (pas 404) sur ce serveur.

Heure : les heures du nom de fichier sont en heure de New York, au format 12 h
avec AM/PM (12:00 AM = minuit, 12:00 PM = midi). Les créneaux sont parcourus
sur l'axe UTC (pas de 15 minutes exactes) puis convertis en heure de New York
pour écrire le nom : le changement d'heure ne peut ni fausser le pas ni
sauter un créneau existant.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

import httpx

from app.services.nba_calendar import NBA_TIMEZONE

logger = logging.getLogger(__name__)

REPORT_URL_TEMPLATE = (
    "https://ak-static.cms.nba.com/referee/injury/"
    "Injury-Report_{day}_{hour:02d}_{minute:02d}{meridiem}.pdf"
)
SEARCH_STEP = timedelta(minutes=15)
MAX_LOOKBACK = timedelta(hours=48)
# Un rapport absent répond 403 sur ce serveur (comportement d'un stockage
# objet sans listing), 404 par prudence : les deux signifient "pas de fichier
# à ce créneau". Tout autre code non-200 (429, 5xx...) n'est PAS une absence.
ABSENT_STATUS_CODES = {403, 404}


class InjuryReportFetchError(Exception):
    pass


@dataclass(frozen=True)
class FetchedReport:
    content: bytes
    url: str
    # Horodatage du rapport retenu, en heure de New York (aware), tel que
    # lu dans le nom de fichier -- pour savoir de QUEL rapport viennent les données.
    report_time: datetime


def build_report_url(report_time: datetime) -> str:
    """Adresse du rapport publié à `report_time` (convertie en heure de New
    York si elle est dans un autre fuseau ; une valeur naïve est prise telle
    quelle comme heure de New York)."""
    if report_time.tzinfo is not None:
        report_time = report_time.astimezone(NBA_TIMEZONE)
    hour24 = report_time.hour
    return REPORT_URL_TEMPLATE.format(
        day=report_time.strftime("%Y-%m-%d"),
        hour=hour24 % 12 or 12,
        minute=report_time.minute,
        meridiem="AM" if hour24 < 12 else "PM",
    )


def _floor_to_step(moment: datetime) -> datetime:
    step_seconds = int(SEARCH_STEP.total_seconds())
    timestamp = int(moment.timestamp())
    return datetime.fromtimestamp(timestamp - timestamp % step_seconds, tz=UTC)


def _search_start(report_date: date | None, now: datetime | None) -> datetime:
    """Point de départ (UTC) de la recherche à rebours : maintenant, ou la
    fin de `report_date` (23:45 heure de New York) si cette date est passée.
    `report_date` future : on part de maintenant (rien n'existe encore)."""
    now_utc = (now or datetime.now(UTC)).astimezone(UTC)
    if report_date is None:
        return _floor_to_step(now_utc)
    end_of_day = datetime.combine(report_date, time(23, 45), tzinfo=NBA_TIMEZONE).astimezone(UTC)
    return _floor_to_step(min(now_utc, end_of_day))


def fetch_latest_report(
    report_date: date | None = None,
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> FetchedReport:
    """Rapport le plus récent disponible pour `report_date` (aujourd'hui, heure
    de New York, par défaut) : on part de maintenant -- ou de la fin de cette
    date si elle est passée --, on remonte par pas de 15 minutes avec des
    requêtes HEAD jusqu'à un 200, puis on télécharge ce PDF. La recherche
    peut franchir minuit vers la veille (début de journée, avant le premier
    rapport), d'où `report_time` dans le retour. Plafond : 48 h en arrière,
    puis InjuryReportFetchError.

    Lève InjuryReportFetchError si rien n'est trouvé dans la plage, ou sur un
    code HTTP inattendu / une erreur réseau -- jamais de None silencieux."""
    owns_client = client is None
    client = client or httpx.Client(timeout=30.0, follow_redirects=True)
    try:
        start = _search_start(report_date, now)
        earliest = start - MAX_LOOKBACK
        slot = start
        probes = 0
        while slot >= earliest:
            url = build_report_url(slot)
            probes += 1
            try:
                head = client.head(url)
            except httpx.HTTPError as exc:
                raise InjuryReportFetchError(f"Erreur réseau sur {url} : {exc!r}") from exc
            if head.status_code == 200:
                try:
                    response = client.get(url)
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    raise InjuryReportFetchError(f"Échec du téléchargement de {url} : {exc!r}") from exc
                report_time = slot.astimezone(NBA_TIMEZONE)
                logger.info(
                    "Rapport de blessures retenu : %s (heure de New York : %s, %d requête(s) HEAD)",
                    url,
                    report_time.isoformat(timespec="minutes"),
                    probes,
                )
                return FetchedReport(content=response.content, url=url, report_time=report_time)
            if head.status_code not in ABSENT_STATUS_CODES:
                raise InjuryReportFetchError(
                    f"Réponse inattendue {head.status_code} sur {url} (ni 200 ni créneau absent 403/404)"
                )
            slot -= SEARCH_STEP
        raise InjuryReportFetchError(
            f"Aucun rapport de blessures trouvé en remontant 48 h depuis "
            f"{start.astimezone(NBA_TIMEZONE).isoformat(timespec='minutes')} (heure de New York), "
            f"{probes} créneaux sondés"
        )
    finally:
        if owns_client:
            client.close()


def fetch_latest_report_bytes(client: httpx.Client | None = None) -> bytes:
    """Compatibilité avec le planificateur (scheduler.py) : octets du dernier
    rapport. Lève InjuryReportFetchError si rien n'est trouvé (le
    planificateur journalise toute exception de récupération)."""
    return fetch_latest_report(client=client).content
