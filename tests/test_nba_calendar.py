from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.nba_calendar import current_nba_date


def test_current_nba_date_matches_america_new_york_now():
    expected = datetime.now(ZoneInfo("America/New_York")).date()
    assert current_nba_date() == expected


# ----------------------------------------------------------------------------- changements d'heure américains
#
# `Game.game_date` est une heure murale US/ET NAÏVE (Décision n°3) ; `game_start_utc` la convertit en UTC et
# `has_game_started` (protection « pas de recalcul après le coup d'envoi ») la compare à `utc_now()`. Les attendus
# ci-dessous sont calculés À LA MAIN, par décalage fixe choisi selon la date -- jamais par zoneinfo -- pour que le test
# ne dépende pas de ce qu'il vérifie :
#   heure d'été (EDT) = UTC-4, heure d'hiver (EST) = UTC-5.
#   Passage à l'heure d'hiver : dimanche 1er novembre 2026, 2 h -> 1 h.
#   Passage à l'heure d'été   : dimanche 14 mars 2027, 2 h -> 3 h  (le sens DANGEREUX pour la protection : une
#   conversion figée à UTC-5 placerait alors le coup d'envoi une heure trop TARD et laisserait recalculer un match
#   commencé ; le passage à l'heure d'hiver échoue du côté sûr, un coup d'envoi trop tôt bloquant seulement plus tôt).
# Vérifié sur les 11 matchs réels du 31 octobre et du 1er novembre 2026 (2026-11-01, calcul indépendant).

import pytest  # noqa: E402

from app.models import Game, GameStatus  # noqa: E402
from app.services import nba_calendar  # noqa: E402
from app.services import pronostic_calculator as calc  # noqa: E402

# (heure murale de New York, décalage en heures à AJOUTER pour obtenir l'UTC)
CONVERSIONS = [
    (datetime(2026, 10, 31, 20, 0), 4),   # veille du passage à l'hiver : EDT
    (datetime(2026, 11, 1, 0, 30), 4),    # encore EDT (avant 2 h)
    (datetime(2026, 11, 1, 15, 30), 5),   # BOS@ORL : EST -> 20 h 30 UTC
    (datetime(2026, 11, 1, 21, 0), 5),    # TOR@LAL : EST
    (datetime(2027, 3, 13, 19, 30), 5),   # veille du passage à l'été : EST
    (datetime(2027, 3, 14, 1, 30), 5),    # encore EST (avant 2 h)
    (datetime(2027, 3, 14, 3, 30), 4),    # EDT (2 h n'existe pas ce jour-là)
    (datetime(2027, 3, 14, 19, 30), 4),   # soir du passage à l'été : EDT -> 23 h 30 UTC
]


@pytest.mark.parametrize("local, offset", CONVERSIONS)
def test_game_start_utc_follows_the_american_clock_change(local, offset):
    assert nba_calendar.game_start_utc(local) == local + timedelta(hours=offset)


def test_the_conversion_is_not_a_fixed_offset():
    """Contre-épreuve de fond : deux heures murales identiques de part et d'autre d'un changement d'heure ne donnent
    PAS le même écart avec l'UTC. Un décalage fixe (UTC-4 ou UTC-5 pour toute l'année) échoue ici, quelle que soit sa valeur."""
    fall = nba_calendar.game_start_utc(datetime(2026, 11, 1, 19, 0)) - datetime(2026, 11, 1, 19, 0)
    before_fall = nba_calendar.game_start_utc(datetime(2026, 10, 31, 19, 0)) - datetime(2026, 10, 31, 19, 0)
    spring = nba_calendar.game_start_utc(datetime(2027, 3, 14, 19, 0)) - datetime(2027, 3, 14, 19, 0)
    before_spring = nba_calendar.game_start_utc(datetime(2027, 3, 13, 19, 0)) - datetime(2027, 3, 13, 19, 0)
    assert before_fall == timedelta(hours=4) and fall == timedelta(hours=5)
    assert before_spring == timedelta(hours=5) and spring == timedelta(hours=4)


def _game(local):
    # Objet en mémoire, jamais ajouté à une session : has_game_started ne lit que le statut et la date.
    return Game(season="2026-2027", game_date=local, home_team_id=1, away_team_id=2, status=GameStatus.SCHEDULED)


def _started(monkeypatch, local, now_utc):
    monkeypatch.setattr(nba_calendar, "utc_now", lambda: now_utc)
    return calc.has_game_started(_game(local))


def test_protection_around_the_fall_change_bos_orl(monkeypatch):
    kickoff = datetime(2026, 11, 1, 15, 30)  # = 20 h 30 UTC (EST)
    assert _started(monkeypatch, kickoff, datetime(2026, 11, 1, 19, 30)) is False   # 14 h 30 à New York
    assert _started(monkeypatch, kickoff, datetime(2026, 11, 1, 20, 29, 59)) is False
    assert _started(monkeypatch, kickoff, datetime(2026, 11, 1, 20, 30, 0)) is True  # coup d'envoi exact
    assert _started(monkeypatch, kickoff, datetime(2026, 11, 1, 21, 15)) is True


def test_protection_around_the_spring_change_is_the_dangerous_direction(monkeypatch):
    """14 mars 2027, 19 h 30 à New York = 23 h 30 UTC (EDT). Une conversion figée à UTC-5 dirait 00 h 30 UTC le
    lendemain : à 23 h 45 UTC le match a commencé depuis un quart d'heure, et la protection DOIT le savoir."""
    kickoff = datetime(2027, 3, 14, 19, 30)
    assert _started(monkeypatch, kickoff, datetime(2027, 3, 14, 23, 29, 59)) is False
    assert _started(monkeypatch, kickoff, datetime(2027, 3, 14, 23, 30, 0)) is True
    assert _started(monkeypatch, kickoff, datetime(2027, 3, 14, 23, 45)) is True   # trop tard avec UTC-5 : le piège
    assert _started(monkeypatch, kickoff, datetime(2027, 3, 15, 0, 15)) is True


def test_the_day_before_each_change_is_unaffected(monkeypatch):
    # Veille du passage à l'hiver (EDT) et veille du passage à l'été (EST) : la protection y est exacte aussi.
    assert _started(monkeypatch, datetime(2026, 10, 31, 20, 0), datetime(2026, 10, 31, 23, 59, 59)) is False
    assert _started(monkeypatch, datetime(2026, 10, 31, 20, 0), datetime(2026, 11, 1, 0, 0, 0)) is True
    assert _started(monkeypatch, datetime(2027, 3, 13, 19, 30), datetime(2027, 3, 14, 0, 29, 59)) is False
    assert _started(monkeypatch, datetime(2027, 3, 13, 19, 30), datetime(2027, 3, 14, 0, 30, 0)) is True
