"""Pourcentages de victoires domicile/extérieur de la SAISON EN COURS, calculés depuis les matchs terminés (chantier
(b2), limitation n°30) -- au lieu d'être saisis ou importés à la main.

Ce module ne change PAS le calcul de la note : il ne fait que remplir `Team.win_pct_home` / `Team.win_pct_away`, que la
note lit déjà (compute_note_de_base). Seule la provenance des deux valeurs change.

Règles :
  - comptés : matchs de la saison en cours (`Settings.current_season`), `FINISHED`, avec les DEUX scores, scores
    différents. Le côté (domicile/extérieur) est celui de la base, y compris sur terrain neutre ;
  - EXCLUS et signalés (jamais comptés comme victoire ni défaite) : un match terminé sans score (vainqueur inconnu), un
    match terminé à égalité (impossible en NBA : erreur de saisie). Un match reporté ou à venir n'est pas terminé ;
  - un côté sans aucun match compté vaut None (NULL en base), JAMAIS 0 : un zéro silencieux est exactement la panne de
    la limitation n°30. La note reste alors sur la saison précédente (compute_team_note).

Pas de filtre de date : la valeur stockée reflète tous les matchs terminés à l'instant du calcul, comme le classement
importé à la main qu'elle remplace. Les pronostics de matchs passés ne se recalculent jamais (Décision n°24).

Relancé à chaque écriture de score (Décision n°41 : le moteur écrit ce qu'il calcule) : synchronisation balldontlie
(bouton et tâche planifiée), correction et suppression d'un match (écran Matchs), réimport du calendrier.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from app.models import Game, GameStatus, Settings, Team

logger = logging.getLogger(__name__)

EXCLUDED_NO_SCORE = "terminé sans score"
EXCLUDED_TIE = "terminé à égalité"


@dataclass
class SideRecord:
    wins: int = 0
    losses: int = 0

    @property
    def games(self) -> int:
        return self.wins + self.losses

    @property
    def pct(self) -> float | None:
        # Aucun match compté : inconnu (None), jamais 0.
        return self.wins / self.games if self.games else None


@dataclass
class TeamRecord:
    home: SideRecord = field(default_factory=SideRecord)
    away: SideRecord = field(default_factory=SideRecord)
    last_game_date: date | None = None


@dataclass
class ExcludedGame:
    game_id: int
    game_date: date
    home_team_id: int
    away_team_id: int
    reason: str


@dataclass
class SeasonRecords:
    season: str
    by_team: dict[int, TeamRecord] = field(default_factory=dict)
    excluded: list[ExcludedGame] = field(default_factory=list)

    def for_team(self, team_id: int) -> TeamRecord:
        return self.by_team.get(team_id) or TeamRecord()


def count_season_records(db: Session, season: str) -> SeasonRecords:
    """Bilans domicile/extérieur de chaque équipe sur les matchs terminés de `season`. Lecture seule."""
    records = SeasonRecords(season=season)
    games = db.query(Game).filter(Game.season == season, Game.status == GameStatus.FINISHED).all()
    for game in games:
        day = game.game_date.date() if hasattr(game.game_date, "date") else game.game_date
        if game.home_score is None or game.away_score is None or game.home_score == game.away_score:
            reason = EXCLUDED_TIE if game.home_score is not None and game.away_score is not None else EXCLUDED_NO_SCORE
            records.excluded.append(ExcludedGame(game.id, day, game.home_team_id, game.away_team_id, reason))
            continue
        home_won = game.home_score > game.away_score
        home = records.by_team.setdefault(game.home_team_id, TeamRecord())
        away = records.by_team.setdefault(game.away_team_id, TeamRecord())
        if home_won:
            home.home.wins += 1
            away.away.losses += 1
        else:
            home.home.losses += 1
            away.away.wins += 1
        for record in (home, away):
            if record.last_game_date is None or day > record.last_game_date:
                record.last_game_date = day
    records.excluded.sort(key=lambda g: (g.game_date, g.game_id))
    return records


def current_season(db: Session) -> str | None:
    settings = db.query(Settings).first()
    return settings.current_season if settings is not None else None


def recompute_current_season_win_pct(db: Session) -> int:
    """Réécrit `win_pct_home`/`win_pct_away` des 30 équipes depuis les matchs terminés de la saison en cours. N'écrit
    que les valeurs qui changent ; ne valide PAS la transaction (à charge de l'appelant, qui la valide avec l'écriture
    de score qui a déclenché le calcul). Retourne le nombre d'équipes dont au moins une valeur a changé."""
    season = current_season(db)
    if season is None:
        logger.warning("Aucune ligne Settings : saison en cours inconnue, pourcentages de victoires non recalculés")
        return 0
    records = count_season_records(db, season)
    changed = 0
    for team in db.query(Team).all():
        record = records.for_team(team.id)
        new_home, new_away = record.home.pct, record.away.pct
        if (team.win_pct_home, team.win_pct_away) != (new_home, new_away):
            team.win_pct_home, team.win_pct_away = new_home, new_away
            changed += 1
    db.flush()
    return changed
