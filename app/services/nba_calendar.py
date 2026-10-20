"""Convention de fuseau horaire pour toute notion de "date de match" dans
l'application : toujours la date calendaire US/ET, jamais convertie vers
l'heure locale du serveur.

`Game.game_date` (DateTime naïf) est déjà traité partout ailleurs dans le
code comme une heure murale ET brute (jamais de conversion de fuseau) — le
seul risque réel est de calculer "aujourd'hui" via l'horloge locale du
serveur (`date.today()`), qui diverge de la date ET autour de minuit heure
française. `current_nba_date()` est la seule façon correcte d'obtenir cette
date dans l'app (même principe que `app/services/scheduler.py`, qui utilise
déjà "America/New_York" pour la même raison côté planification).
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

NBA_TIMEZONE = ZoneInfo("America/New_York")


def current_nba_date() -> date:
    return datetime.now(NBA_TIMEZONE).date()


def utc_now() -> datetime:
    """Maintenant en UTC NAÏF (même convention que `Prediction.computed_at`). Point d'entrée unique de
    l'horloge pour « le match a-t-il commencé ? » : les tests le remplacent."""
    return datetime.now(UTC).replace(tzinfo=None)


def game_start_utc(game_date: datetime) -> datetime:
    """Coup d'envoi d'un match en UTC naïf. `Game.game_date` est une heure murale US/ET naïve (Décision
    n°3) : on la lit en `America/New_York` avant de convertir, jamais comme un UTC ni comme l'heure locale."""
    return game_date.replace(tzinfo=NBA_TIMEZONE).astimezone(UTC).replace(tzinfo=None)
