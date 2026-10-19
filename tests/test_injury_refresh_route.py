"""POST /api/injuries/refresh -- aucun appel réseau : le téléchargement est remplacé
par un PDF réel stocké dans tests/fixtures (fetch_latest_report est monkeypatché)."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.models import InjuryStatus, Player, Settings, Team
from app.services import injury_report_runner
from app.services.injury_report_fetcher import FetchedReport, InjuryReportFetchError

FIXTURES = Path(__file__).parent / "fixtures"
NY = ZoneInfo("America/New_York")
URL = "https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-04-08_03_45PM.pdf"


def _fetched(filename: str, report_time: datetime, url: str = URL) -> FetchedReport:
    return FetchedReport(content=(FIXTURES / filename).read_bytes(), url=url, report_time=report_time)


@pytest.fixture()
def league(db_session):
    atl = Team(name="Atlanta Hawks", abbreviation="ATL")
    cle = Team(name="Cleveland Cavaliers", abbreviation="CLE")
    bos = Team(name="Boston Celtics", abbreviation="BOS")
    db_session.add_all([atl, cle, bos, Settings(current_season="2026-2027", mpg_threshold=15.0)])
    db_session.flush()
    landale = Player(name="Jock Landale", team_id=atl.id, per=14.0, mpg=25.0)
    dennis = Player(name="RayJ Dennis", team_id=atl.id, per=9.0, mpg=8.0)
    # "Bryant, Thomas" est indiqué CLE par le rapport mais rattaché à BOS en base.
    bryant = Player(name="Thomas Bryant", team_id=bos.id, per=12.0, mpg=20.0)
    db_session.add_all([landale, dennis, bryant])
    db_session.commit()
    return {"landale": landale, "dennis": dennis, "bryant": bryant}


def test_requires_authentication(client):
    assert client.post("/api/injuries/refresh").status_code == 401


def test_success_applies_statuses_and_reports_everything(client, auth_headers, db_session, league, monkeypatch):
    monkeypatch.setattr(
        injury_report_runner,
        "fetch_latest_report",
        lambda client=None, now=None: _fetched(
            "Injury-Report_2026-04-08_03_45PM.pdf", datetime(2026, 4, 8, 15, 45, tzinfo=NY)
        ),
    )
    response = client.post("/api/injuries/refresh", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()

    assert body["report_url"] == URL
    assert body["report_time_new_york"] == "08/04/2026 15:45 (heure de New York, UTC-04:00)"
    assert body["report_time_paris"] == "08/04/2026 21:45 (heure de Paris, UTC+02:00)"
    assert body["game_dates"] == ["2026-04-08", "2026-04-09"]
    assert body["entries_read"] == 78
    assert body["not_yet_submitted"] is False
    assert body["written"] is True

    # Jock Landale (OUT) et RayJ Dennis (Questionable) sont les deux seuls joueurs de la base
    # présents dans ce rapport de 78 entrées.
    assert body["matched_count"] == 2
    assert body["unmatched_count"] == 76
    assert body["status_counts"] == {"out": 1, "questionable": 1}
    # Un seul joueur absent (OUT/DOUBTFUL) ; son MPG (25) dépasse le seuil de 15.
    assert body["absent_count"] == 1
    assert body["mpg_threshold"] == 15.0
    assert body["weighing_count"] == 1
    assert body["weighing"] == [
        {"name": "Jock Landale", "team_abbreviation": "ATL", "status": "out", "per": 14.0, "mpg": 25.0}
    ]

    # Un nom non retrouvé est listé avec l'équipe du rapport ET l'équipe où il existe en base.
    unmatched = {entry["player_name_raw"]: entry for entry in body["unmatched"]}
    assert len(body["unmatched"]) == 76
    bryant = unmatched["Bryant,Thomas"]
    assert bryant["team_abbreviation"] == "CLE"
    assert bryant["exists_in_database_on_teams"] == ["BOS"]
    assert unmatched["Gilbert,Keshon"]["exists_in_database_on_teams"] == []

    db_session.expire_all()
    assert league["landale"].injury_status == InjuryStatus.OUT
    assert league["dennis"].injury_status == InjuryStatus.QUESTIONABLE
    assert league["bryant"].injury_status == InjuryStatus.HEALTHY
    assert league["landale"].injury_updated_at is not None


def test_not_yet_submitted_report_is_flagged_and_writes_nothing(
    client, auth_headers, db_session, league, monkeypatch
):
    url = "https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-10-19_02_30PM.pdf"
    monkeypatch.setattr(
        injury_report_runner,
        "fetch_latest_report",
        lambda client=None, now=None: _fetched(
            "Injury-Report_2026-10-19_02_30PM.pdf", datetime(2026, 10, 19, 14, 30, tzinfo=NY), url
        ),
    )
    response = client.post("/api/injuries/refresh", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()

    assert body["entries_read"] == 0
    assert body["not_yet_submitted"] is True
    assert body["not_yet_submitted_count"] == 6
    assert body["game_dates"] == ["2026-10-20"]
    assert body["written"] is False
    assert body["matched_count"] == 0 and body["unmatched"] == []
    assert body["status_counts"] == {} and body["weighing"] == []

    db_session.expire_all()
    for player in league.values():
        assert player.injury_status == InjuryStatus.HEALTHY
        assert player.injury_updated_at is None


def test_download_failure_returns_the_real_error_message(client, auth_headers, league, monkeypatch):
    message = "Aucun rapport de blessures trouvé en remontant 48 h depuis 2026-10-19T14:30-04:00 (heure de New York), 193 créneaux sondés"

    def failing(client=None, now=None):
        raise InjuryReportFetchError(message)

    monkeypatch.setattr(injury_report_runner, "fetch_latest_report", failing)
    response = client.post("/api/injuries/refresh", headers=auth_headers)
    assert response.status_code == 502
    assert response.json()["detail"] == message


def test_unreadable_pdf_returns_a_clear_error_and_writes_nothing(
    client, auth_headers, db_session, league, monkeypatch
):
    monkeypatch.setattr(
        injury_report_runner,
        "fetch_latest_report",
        lambda client=None, now=None: FetchedReport(
            content=b"not a pdf", url=URL, report_time=datetime(2026, 4, 8, 15, 45, tzinfo=NY)
        ),
    )
    response = client.post("/api/injuries/refresh", headers=auth_headers)
    assert response.status_code == 422
    assert "Lecture du PDF impossible" in response.json()["detail"]
    db_session.expire_all()
    assert league["landale"].injury_status == InjuryStatus.HEALTHY
