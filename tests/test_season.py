from app.services.season import previous_season_label


def test_previous_season_label_decrements_both_years():
    assert previous_season_label("2026-2027") == "2025-2026"
    assert previous_season_label("2000-2001") == "1999-2000"
