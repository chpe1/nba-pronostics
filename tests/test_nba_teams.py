from app.services.nba_teams import normalize_abbreviation


def test_normalize_abbreviation_maps_known_basketball_reference_aliases():
    assert normalize_abbreviation("BRK") == "BKN"
    assert normalize_abbreviation("PHO") == "PHX"
    assert normalize_abbreviation("CHO") == "CHA"


def test_normalize_abbreviation_leaves_canonical_and_unknown_values_untouched():
    assert normalize_abbreviation("BKN") == "BKN"
    assert normalize_abbreviation("ZZZ") == "ZZZ"
