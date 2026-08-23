from app.services.injury_report_fetcher import find_latest_report_url

SAMPLE_HTML = """
<html><body>
<ul>
  <li><a href="/referee/injury/Injury-Report_2026-01-01_01_30PM.pdf">1:30 PM</a></li>
  <li><a href="https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-01-01_05_00PM.pdf">5:00 PM</a></li>
  <li><a href="/referee/injury/Injury-Report_2026-01-01_02_00PM.pdf">2:00 PM</a></li>
  <li><a href="/some/other/link">Not a report</a></li>
</ul>
</body></html>
"""


def test_picks_most_recent_report_by_filename_timestamp():
    url = find_latest_report_url(SAMPLE_HTML, base_url="https://official.nba.com/some-page/")
    assert url == "https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-01-01_05_00PM.pdf"


def test_resolves_relative_urls_against_base():
    html = '<a href="/referee/injury/Injury-Report_2026-01-01_01_30PM.pdf">link</a>'
    url = find_latest_report_url(html, base_url="https://official.nba.com/some-page/")
    assert url == "https://official.nba.com/referee/injury/Injury-Report_2026-01-01_01_30PM.pdf"


def test_returns_none_when_no_report_link_found():
    html = "<html><body><a href='/other'>nope</a></body></html>"
    assert find_latest_report_url(html, base_url="https://official.nba.com/") is None
