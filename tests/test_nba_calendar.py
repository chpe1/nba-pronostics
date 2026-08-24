from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.nba_calendar import current_nba_date


def test_current_nba_date_matches_america_new_york_now():
    expected = datetime.now(ZoneInfo("America/New_York")).date()
    assert current_nba_date() == expected
