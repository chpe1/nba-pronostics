"""Probabilité de victoire par un modèle d'écart de points -- calculée À CÔTÉ de la note, jamais à sa place.

Ce module ne lit rien de ce que lit la note (ni joueurs, ni blessures, ni réglages `Settings`) et la note ne lit
rien de ce qu'il produit : les deux restent comparables sur de vrais matchs avant toute décision.

Modèle (étude hors production `Tools/etude_amorcage`, réglages choisis sur 2023-24 → 2024-25 et vérifiés sans
retouche sur 2024-25 → 2025-26) :
    force(équipe)   = (W × C × écart_N-1 + somme des marges de la saison) / (W + n)
    marge attendue  = force(domicile) − force(extérieur) + AVANTAGE_TERRAIN
    P(domicile)     = Φ(marge attendue / SIGMA)       (Φ : loi normale centrée réduite)
  écart_N-1 : Team.point_diff_prev_season (marge moyenne par match la saison précédente, saisie à la main) ;
  n, somme  : matchs TERMINÉS de la saison du match, avec score, d'une date STRICTEMENT antérieure au jour du
              match (les matchs du même jour sont exclus : pas d'ordre fiable entre eux -- même règle que
              l'étude). Jamais un match à venir, reporté, sans score, d'une autre saison ou postérieur.

Les réglages sont des constantes validées, pas des curseurs (même raisonnement que la Décision n°12) ; leur
identifiant de version est DÉRIVÉ de leurs valeurs : changer un réglage change la version, sans qu'on puisse
oublier de l'incrémenter. `FORMULA_ID` ne change que si la formule elle-même change.

Ce que le modèle IGNORE, volontairement : les absents (convertir un PER en points n'a jamais été mesuré), le
calendrier (repos), les effectifs. L'écran doit le dire.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Game, GameStatus, Team

FORMULA_ID = "ecart1"
W = 8.0
C = 0.7
HOME_ADVANTAGE = 1.84
SIGMA = 14.13


def model_version(w: float = W, c: float = C, home_advantage: float = HOME_ADVANTAGE, sigma: float = SIGMA) -> str:
    return f"{FORMULA_ID}/w={w:g}/c={c:g}/hca={home_advantage:g}/sigma={sigma:g}"


MODEL_VERSION = model_version()


@dataclass
class TeamForm:
    team_id: int
    prev_point_diff: float | None
    games_used: int
    margin_sum: float
    force: float | None  # None si l'écart N-1 est inconnu


@dataclass
class WinProbability:
    version: str
    home: TeamForm
    away: TeamForm
    expected_margin: float | None
    home_win_probability: float | None
    missing_prev_point_diff: list[int] = field(default_factory=list)  # ids des équipes sans écart N-1


def season_margins_before(db: Session, team: Team, season: str, before_day: date) -> tuple[int, float]:
    """(nombre de matchs, somme des marges du point de vue de `team`) sur les matchs TERMINÉS avec score de
    `season`, joués un jour STRICTEMENT antérieur à `before_day`."""
    games = (
        db.query(Game)
        .filter(
            Game.season == season,
            Game.status == GameStatus.FINISHED,
            Game.game_date_only < before_day,
            Game.home_score.isnot(None),
            Game.away_score.isnot(None),
            or_(Game.home_team_id == team.id, Game.away_team_id == team.id),
        )
        .all()
    )
    total = 0.0
    for g in games:
        margin = g.home_score - g.away_score
        total += margin if g.home_team_id == team.id else -margin
    return len(games), total


def _team_form(db: Session, team: Team, season: str, before_day: date) -> TeamForm:
    n, total = season_margins_before(db, team, season, before_day)
    prev = team.point_diff_prev_season
    force = None if prev is None else (W * C * prev + total) / (W + n)
    return TeamForm(team_id=team.id, prev_point_diff=prev, games_used=n, margin_sum=total, force=force)


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def compute_win_probability(db: Session, game: Game) -> WinProbability:
    day = game.game_date_only
    home = _team_form(db, game.home_team, game.season, day)
    away = _team_form(db, game.away_team, game.season, day)
    missing = [f.team_id for f in (home, away) if f.prev_point_diff is None]
    if missing:
        return WinProbability(MODEL_VERSION, home, away, None, None, missing)
    margin = home.force - away.force + HOME_ADVANTAGE
    return WinProbability(MODEL_VERSION, home, away, margin, normal_cdf(margin / SIGMA), [])


def _form_to_dict(form: TeamForm) -> dict:
    return {
        "team_id": form.team_id,
        "prev_point_diff": form.prev_point_diff,
        "games_used": form.games_used,
        "margin_sum": form.margin_sum,
        "force": form.force,
    }


def inputs_to_dict(result: WinProbability) -> dict:
    """Valeurs ayant servi au calcul, stockées dans Prediction.probability_inputs (figées avec le pronostic)."""
    return {
        "params": {"w": W, "c": C, "home_advantage": HOME_ADVANTAGE, "sigma": SIGMA},
        "home": _form_to_dict(result.home),
        "away": _form_to_dict(result.away),
        "missing_prev_point_diff": result.missing_prev_point_diff,
    }
