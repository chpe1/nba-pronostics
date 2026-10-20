"""Mesure de la justesse des pronostics (partie calcul : ni route, ni écran, aucune écriture).

Règle d'un pronostic MESURABLE -- un match entre dans la mesure si, et seulement si :
  1. il est terminé (`GameStatus.FINISHED`) ET a un score pour les deux équipes ;
  2. il a un pronostic ;
  3. ce pronostic a été calculé STRICTEMENT AVANT l'heure de début du match (un pronostic
     calculé après le coup d'envoi n'est pas une prédiction) ;
  4. les deux scores diffèrent (un nul n'existe pas au basket : des scores égaux trahissent
     une saisie fausse, le match est écarté avec son motif, jamais compté comme victoire de
     quiconque).
Tout match écarté est compté PAR MOTIF et rendu avec le résultat, jamais caché.

Comparaison des heures (point délicat) : `Game.game_date` est une heure murale US/ET NAÏVE
(Décision n°3), `Prediction.computed_at` un UTC naïf (`CURRENT_TIMESTAMP` de SQLite). On
convertit le coup d'envoi en UTC avec `America/New_York` (zoneinfo) avant de comparer.
Limite connue : `computed_at` est la date du DERNIER calcul (une seule ligne par match,
réécrite en place) -- un pronostic recalculé après le coup d'envoi est écarté même si une
version antérieure existait ; cette version-là est perdue (pas d'historique, voir la docstring
de `Prediction`). Autre limite : l'heure de début vient de l'import du calendrier, elle n'est
pas vérifiée contre l'heure réelle de la rencontre.

Relation écart annoncé / écart réel : corrélation de rang de Spearman entre l'écart signé annoncé
(`Prediction.spread`, note domicile - note extérieur) et la marge réelle signée
(score domicile - score extérieur). Jamais une égalité d'amplitude : la note n'est pas une marge
en points (Décision n°38).
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Game, GameStatus, Prediction, ReliabilityLevel
from app.services.nba_calendar import game_start_utc


# Seuil d'échantillon : en dessous, aucune conclusion. Proposé à la validation de l'utilisateur
# (voir le compte-rendu) : à n = 30, l'intervalle à 95 % d'un taux de réussite vaut déjà environ
# ±18 points dans le pire cas (p = 0,5) -- plus bas, un taux ne distingue plus un moteur utile du hasard.
MIN_SAMPLE_SIZE = 30

# Motifs d'écartement (clés stables, rendues telles quelles).
NO_PREDICTION = "no_prediction"  # match terminé avec score, sans pronostic
NOT_FINISHED = "not_finished"  # pronostic, mais match non terminé (à venir, en cours, reporté)
FINISHED_WITHOUT_SCORE = "finished_without_score"  # terminé mais score absent ou partiel
PREDICTED_AFTER_KICKOFF = "predicted_after_kickoff"  # pronostic calculé à/après le coup d'envoi
TIED_SCORES = "tied_scores"  # deux scores égaux : impossible au basket, donnée suspecte


@dataclass(frozen=True)
class LevelAccuracy:
    reliability: ReliabilityLevel
    measured: int
    favorite_wins: int
    favorite_win_rate: float | None  # None si aucun match
    # Marge réelle du point de vue du favori annoncé : positive s'il a gagné de N points, négative s'il a perdu.
    mean_margin_for_favorite: float | None
    mean_absolute_margin: float | None
    insufficient_sample: bool


@dataclass(frozen=True)
class AccuracyReport:
    date_from: date | None
    date_to: date | None
    min_sample_size: int
    measured: int
    excluded: dict[str, int] = field(default_factory=dict)
    excluded_total: int = 0
    favorite_wins: int = 0
    favorite_win_rate: float | None = None
    by_reliability: dict[ReliabilityLevel, LevelAccuracy] = field(default_factory=dict)
    # Spearman entre écart annoncé signé et marge réelle signée ; None si moins de 2 matchs ou rang constant.
    rank_correlation: float | None = None
    insufficient_sample: bool = True  # sur le total ; chaque niveau porte son propre drapeau


def _average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        average = (i + j) / 2 + 1  # rangs 1-indexés, ex æquo à rang moyen
        for k in range(i, j + 1):
            ranks[order[k]] = average
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Corrélation de rang (Pearson sur les rangs moyens). None si < 2 points ou une série constante."""
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    rx, ry = _average_ranks(xs), _average_ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx == 0 or vy == 0:
        return None
    return cov / math.sqrt(vx * vy)


def compute_prediction_accuracy(
    db: Session,
    date_from: date | None = None,
    date_to: date | None = None,
    min_sample_size: int = MIN_SAMPLE_SIZE,
) -> AccuracyReport:
    """Lecture seule. `date_from`/`date_to` (inclus) filtrent sur la date calendaire US/ET du match."""
    query = db.query(Game, Prediction).outerjoin(Prediction, Prediction.game_id == Game.id)
    # Seuls les matchs qui ont un résultat OU un pronostic comptent : un match à venir sans pronostic
    # n'est ni mesurable ni « écarté », il n'existe pas encore pour la mesure.
    query = query.filter(or_(Game.status == GameStatus.FINISHED, Prediction.id.isnot(None)))
    if date_from is not None:
        query = query.filter(Game.game_date_only >= date_from)
    if date_to is not None:
        query = query.filter(Game.game_date_only <= date_to)

    excluded: Counter[str] = Counter()
    # (niveau, favori a gagné, marge du point de vue du favori, écart annoncé signé, marge réelle signée)
    measured_rows: list[tuple[ReliabilityLevel, bool, int, float, int]] = []

    for game, prediction in query.all():
        finished = game.status == GameStatus.FINISHED
        has_score = game.home_score is not None and game.away_score is not None
        if prediction is None:
            excluded[NO_PREDICTION if has_score else FINISHED_WITHOUT_SCORE] += 1
            continue
        if not finished:
            excluded[NOT_FINISHED] += 1
            continue
        if not has_score:
            excluded[FINISHED_WITHOUT_SCORE] += 1
            continue
        if not prediction.computed_at < game_start_utc(game.game_date):
            excluded[PREDICTED_AFTER_KICKOFF] += 1
            continue
        if game.home_score == game.away_score:
            excluded[TIED_SCORES] += 1
            continue
        home_margin = game.home_score - game.away_score
        winner_id = game.home_team_id if home_margin > 0 else game.away_team_id
        favorite_is_home = prediction.predicted_winner_team_id == game.home_team_id
        margin_for_favorite = home_margin if favorite_is_home else -home_margin
        measured_rows.append(
            (prediction.reliability, prediction.predicted_winner_team_id == winner_id, margin_for_favorite,
             prediction.spread, home_margin)
        )

    def level_stats(level: ReliabilityLevel) -> LevelAccuracy:
        rows = [r for r in measured_rows if r[0] == level]
        n = len(rows)
        wins = sum(1 for r in rows if r[1])
        return LevelAccuracy(
            reliability=level,
            measured=n,
            favorite_wins=wins,
            favorite_win_rate=wins / n if n else None,
            mean_margin_for_favorite=sum(r[2] for r in rows) / n if n else None,
            mean_absolute_margin=sum(abs(r[2]) for r in rows) / n if n else None,
            insufficient_sample=n < min_sample_size,
        )

    total = len(measured_rows)
    wins_total = sum(1 for r in measured_rows if r[1])
    return AccuracyReport(
        date_from=date_from,
        date_to=date_to,
        min_sample_size=min_sample_size,
        measured=total,
        excluded=dict(excluded),
        excluded_total=sum(excluded.values()),
        favorite_wins=wins_total,
        favorite_win_rate=wins_total / total if total else None,
        by_reliability={level: level_stats(level) for level in ReliabilityLevel},
        rank_correlation=spearman([r[3] for r in measured_rows], [float(r[4]) for r in measured_rows]),
        insufficient_sample=total < min_sample_size,
    )
