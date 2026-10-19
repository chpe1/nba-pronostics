from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.services.injury_report_fetcher import (
    FetchedReport,
    InjuryReportFetchError,
    build_report_url,
    fetch_latest_report,
)

NY = ZoneInfo("America/New_York")
BASE = "https://ak-static.cms.nba.com/referee/injury/"


def _client(existing: set[str], seen: list[str] | None = None, status_for_absent: int = 403, overrides=None):
    """Client httpx dont le transport est simulé : aucun appel réseau. HEAD/GET
    répondent 200 pour les adresses de `existing`, `status_for_absent` sinon."""
    overrides = overrides or {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "HEAD" and seen is not None:
            seen.append(url)
        if url in overrides:
            return httpx.Response(overrides[url])
        if url in existing:
            return httpx.Response(200, content=b"%PDF-fake " + url.encode())
        return httpx.Response(status_for_absent)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _url(filename: str) -> str:
    return BASE + filename


# --- construction de l'adresse -------------------------------------------------


def test_build_url_matches_real_example():
    moment = datetime(2026, 3, 11, 15, 30, tzinfo=NY)
    assert build_report_url(moment) == _url("Injury-Report_2026-03-11_03_30PM.pdf")


def test_build_url_midnight_and_noon_use_12_hour_clock():
    assert build_report_url(datetime(2026, 3, 11, 0, 0, tzinfo=NY)) == _url("Injury-Report_2026-03-11_12_00AM.pdf")
    assert build_report_url(datetime(2026, 3, 11, 0, 15, tzinfo=NY)) == _url("Injury-Report_2026-03-11_12_15AM.pdf")
    assert build_report_url(datetime(2026, 3, 11, 12, 0, tzinfo=NY)) == _url("Injury-Report_2026-03-11_12_00PM.pdf")
    assert build_report_url(datetime(2026, 3, 11, 23, 45, tzinfo=NY)) == _url("Injury-Report_2026-03-11_11_45PM.pdf")


def test_build_url_converts_other_timezones_to_new_york_time():
    # 20:30 UTC le 19 octobre 2026 (heure d'été : UTC-4) = 4:30 PM à New York
    moment = datetime(2026, 10, 19, 20, 30, tzinfo=UTC)
    assert build_report_url(moment) == _url("Injury-Report_2026-10-19_04_30PM.pdf")
    # après le retour à l'heure d'hiver (UTC-5) : 20:30 UTC = 3:30 PM
    winter = datetime(2026, 11, 20, 20, 30, tzinfo=UTC)
    assert build_report_url(winter) == _url("Injury-Report_2026-11-20_03_30PM.pdf")


def test_build_url_changes_date_with_new_york_date_not_utc_date():
    # 02:00 UTC le 20 = 22:00 à New York le 19
    moment = datetime(2026, 10, 20, 2, 0, tzinfo=UTC)
    assert build_report_url(moment) == _url("Injury-Report_2026-10-19_10_00PM.pdf")


# --- recherche à rebours ----------------------------------------------------------


NOW = datetime(2026, 10, 19, 18, 22, tzinfo=UTC)  # 14:22 à New York -> départ à 14:15


def test_first_slot_answers_immediately():
    existing = {_url("Injury-Report_2026-10-19_02_15PM.pdf")}
    seen: list[str] = []
    report = fetch_latest_report(client=_client(existing, seen), now=NOW)
    assert isinstance(report, FetchedReport)
    assert report.url == _url("Injury-Report_2026-10-19_02_15PM.pdf")
    assert report.report_time == datetime(2026, 10, 19, 14, 15, tzinfo=NY)
    assert report.content.startswith(b"%PDF-fake")
    assert seen == [report.url]  # une seule requête HEAD


def test_goes_back_several_slots_until_a_report_exists():
    existing = {_url("Injury-Report_2026-10-19_01_30PM.pdf")}
    seen: list[str] = []
    report = fetch_latest_report(client=_client(existing, seen), now=NOW)
    assert report.report_time == datetime(2026, 10, 19, 13, 30, tzinfo=NY)
    assert [u.rsplit("_", 2)[-2:] for u in seen] == [["02", "15PM.pdf"], ["02", "00PM.pdf"], ["01", "45PM.pdf"], ["01", "30PM.pdf"]]


def test_goes_back_across_midnight_to_previous_day():
    # il est 00:05 à New York le 19 : le créneau 00:00 du 19 n'existe pas encore
    now = datetime(2026, 10, 19, 4, 5, tzinfo=UTC)
    existing = {_url("Injury-Report_2026-10-18_11_45PM.pdf")}
    report = fetch_latest_report(client=_client(existing), now=now)
    assert report.report_time == datetime(2026, 10, 18, 23, 45, tzinfo=NY)


def test_nothing_found_within_48_hours_raises_clear_error():
    seen: list[str] = []
    with pytest.raises(InjuryReportFetchError, match="Aucun rapport de blessures trouvé en remontant 48 h"):
        fetch_latest_report(client=_client(set(), seen), now=NOW)
    assert len(seen) == 48 * 4 + 1  # 193 créneaux, bornes comprises
    assert len(set(seen)) == len(seen)  # aucun créneau sondé deux fois


def test_report_just_inside_the_48_hour_limit_is_found():
    existing = {_url("Injury-Report_2026-10-17_02_15PM.pdf")}  # exactement 48 h avant le départ
    report = fetch_latest_report(client=_client(existing), now=NOW)
    assert report.report_time == datetime(2026, 10, 17, 14, 15, tzinfo=NY)


def test_report_just_outside_the_48_hour_limit_is_not_found():
    existing = {_url("Injury-Report_2026-10-17_02_00PM.pdf")}  # 48 h 15 min avant le départ
    with pytest.raises(InjuryReportFetchError):
        fetch_latest_report(client=_client(existing), now=NOW)


def test_past_report_date_starts_from_end_of_that_day():
    existing = {_url("Injury-Report_2026-03-11_11_45PM.pdf")}
    seen: list[str] = []
    report = fetch_latest_report(report_date=date(2026, 3, 11), client=_client(existing, seen), now=NOW)
    assert report.report_time == datetime(2026, 3, 11, 23, 45, tzinfo=NY)
    assert len(seen) == 1


def test_404_is_treated_as_absent_like_403():
    existing = {_url("Injury-Report_2026-10-19_02_00PM.pdf")}
    report = fetch_latest_report(client=_client(existing, status_for_absent=404), now=NOW)
    assert report.report_time == datetime(2026, 10, 19, 14, 0, tzinfo=NY)


def test_unexpected_status_is_an_error_not_an_absence():
    overrides = {_url("Injury-Report_2026-10-19_02_15PM.pdf"): 503}
    with pytest.raises(InjuryReportFetchError, match="503"):
        fetch_latest_report(client=_client(set(), overrides=overrides), now=NOW)


def test_network_error_is_wrapped():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(InjuryReportFetchError, match="Erreur réseau"):
        fetch_latest_report(client=client, now=NOW)
