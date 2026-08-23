"""Récupération automatique du dernier rapport de blessures NBA publié.

La NBA republie le rapport toutes les 30 minutes environ, sans URL directe
stable : il faut scraper la page listant les rapports du jour pour trouver le
lien le plus récent, puis le télécharger.

Non vérifié en conditions réelles (saison 2025-26 non commencée au moment de
l'écriture ; la page officielle n'a pas pu être inspectée, timeout réseau).
Le scraping est volontairement tolérant à la structure exacte du DOM (simple
recherche de <a href> correspondant au nom de fichier attendu) plutôt que de
dépendre de sélecteurs CSS précis. À valider dès que possible avant le début
de saison (20 octobre).
"""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.config import NBA_INJURY_REPORT_SEASON

LISTING_URL_TEMPLATE = "https://official.nba.com/nba-injury-report-{season}-season/"

# Pattern fourni par l'utilisateur, confirmé pour les rapports officiels.
FILENAME_PATTERN = re.compile(
    r"Injury-Report_(\d{4}-\d{2}-\d{2})_(\d{2})_(\d{2})(AM|PM)\.pdf", re.IGNORECASE
)


class InjuryReportFetchError(Exception):
    pass


def _listing_url() -> str:
    return LISTING_URL_TEMPLATE.format(season=NBA_INJURY_REPORT_SEASON)


def _parse_report_datetime(href: str) -> datetime | None:
    match = FILENAME_PATTERN.search(href)
    if not match:
        return None
    date_str, hour_str, minute_str, am_pm = match.groups()
    try:
        return datetime.strptime(
            f"{date_str} {hour_str}:{minute_str} {am_pm.upper()}", "%Y-%m-%d %I:%M %p"
        )
    except ValueError:
        return None


def find_latest_report_url(html: str, base_url: str) -> str | None:
    """Cherche, parmi tous les liens de la page, celui dont le nom de
    fichier correspond au pattern des rapports officiels et porte
    l'horodatage le plus récent."""
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[tuple[datetime, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        report_dt = _parse_report_datetime(href)
        if report_dt is not None:
            candidates.append((report_dt, urljoin(base_url, href)))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1]


def fetch_latest_report_bytes(client: httpx.Client | None = None) -> bytes | None:
    """Retourne les octets du dernier rapport PDF publié, ou None si aucun
    lien de rapport n'a été trouvé sur la page de listing."""
    owns_client = client is None
    client = client or httpx.Client(timeout=30.0, follow_redirects=True)
    try:
        listing_url = _listing_url()
        response = client.get(listing_url)
        response.raise_for_status()

        latest_url = find_latest_report_url(response.text, base_url=listing_url)
        if latest_url is None:
            return None

        pdf_response = client.get(latest_url)
        pdf_response.raise_for_status()
        return pdf_response.content
    finally:
        if owns_client:
            client.close()
