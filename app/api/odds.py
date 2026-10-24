from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_admin
from app.database import get_db
from app.models import Game, Odds, OddsSide
from app.schemas import (
    OddsBatchResult,
    OddsBatchResultEntry,
    OddsBatchWrite,
    OddsCellRead,
    OddsDayRead,
    OddsGameRead,
)
from app.services.nba_calendar import current_nba_date
from app.services.odds import (
    InvalidOddsSourceError,
    InvalidOddsValueError,
    latest_odds_by_cell,
    normalize_odds_source,
    parse_odds_value,
    record_odds,
    to_naive_utc,
)
from app.services.pronostic_calculator import has_game_started

router = APIRouter(prefix="/api/odds", tags=["odds"], dependencies=[Depends(get_current_admin)])

# Les deux seules sources affichées par CET écran (quatre champs fixes par match, exigence du point 2).
# Rien n'empêche KNOWN_ODDS_SOURCES (app/services/odds.py) d'en compter d'autres plus tard sans migration
# -- mais cet écran-ci, câblé sur exactement ces deux colonnes dans le schéma de lecture, demandera alors
# un vrai changement de code.


def _empty_cell() -> OddsCellRead:
    return OddsCellRead(value=None, recorded_at=None)


def _cell_from_odds(odds: Odds | None) -> OddsCellRead:
    if odds is None:
        return _empty_cell()
    # ISO 8601 avec "Z" explicite (UTC) -- jamais une chaîne naïve ambiguë lue comme heure locale par
    # `new Date(...)` côté navigateur (voir CLAUDE.md, limitation n°35).
    return OddsCellRead(value=odds.value, recorded_at=odds.recorded_at.isoformat() + "Z")


@router.get("", response_model=OddsDayRead)
def list_odds(
    date_param: date = Query(default_factory=current_nba_date, alias="date"),
    db: Session = Depends(get_db),
):
    """Les matchs d'une date donnée (fuseau US/ET, comme GET /api/games), avec le DERNIER relevé connu de
    chacune des 4 cellules -- pour pré-remplir l'écran de saisie avec ce qui est déjà en base."""
    start = datetime.combine(date_param, time.min)
    end = start + timedelta(days=1)
    games = (
        db.query(Game)
        .filter(Game.game_date >= start, Game.game_date < end)
        .order_by(Game.game_date)
        .all()
    )
    latest = latest_odds_by_cell(db, [g.id for g in games])

    def cell(game_id: int, side: OddsSide, source: str) -> OddsCellRead:
        return _cell_from_odds(latest.get((game_id, side, source)))

    return OddsDayRead(
        date=date_param.isoformat(),
        games=[
            OddsGameRead(
                id=g.id,
                game_date=g.game_date.isoformat(),
                home_team_name=g.home_team.name,
                home_team_abbreviation=g.home_team.abbreviation,
                away_team_name=g.away_team.name,
                away_team_abbreviation=g.away_team.abbreviation,
                started=has_game_started(g),
                winamax_home=cell(g.id, OddsSide.HOME, "winamax"),
                winamax_away=cell(g.id, OddsSide.AWAY, "winamax"),
                unibet_home=cell(g.id, OddsSide.HOME, "unibet"),
                unibet_away=cell(g.id, OddsSide.AWAY, "unibet"),
            )
            for g in games
        ],
    )


@router.post("", response_model=OddsBatchResult)
def record_odds_batch(payload: OddsBatchWrite, db: Session = Depends(get_db)):
    """Enregistre un lot de cellules saisies. Validation et écriture CELLULE PAR CELLULE : une cote
    absurde sur une ligne ne doit jamais faire perdre les 43 autres d'une même soirée (toutes valides
    sont écrites, la réponse détaille celles qui ne l'ont pas été et pourquoi) -- rien n'est validé en
    bloc, rien n'est rejeté en bloc."""
    recorded_at = to_naive_utc(payload.recorded_at)
    results: list[OddsBatchResultEntry] = []
    games_cache: dict[int, Game | None] = {}

    for entry in payload.entries:
        game = games_cache.get(entry.game_id)
        if game is None and entry.game_id not in games_cache:
            game = db.get(Game, entry.game_id)
            games_cache[entry.game_id] = game
        if game is None:
            results.append(OddsBatchResultEntry(
                game_id=entry.game_id, side=entry.side, source=entry.source,
                outcome="rejected", detail="Match introuvable.",
            ))
            continue
        if has_game_started(game):
            results.append(OddsBatchResultEntry(
                game_id=entry.game_id, side=entry.side, source=entry.source,
                outcome="skipped_started", detail="Coup d'envoi déjà passé : cote non enregistrée.",
            ))
            continue
        try:
            source = normalize_odds_source(entry.source)
            value = parse_odds_value(entry.value)
        except (InvalidOddsSourceError, InvalidOddsValueError) as exc:
            results.append(OddsBatchResultEntry(
                game_id=entry.game_id, side=entry.side, source=entry.source,
                outcome="rejected", detail=str(exc),
            ))
            continue

        outcome = record_odds(
            db, game_id=entry.game_id, side=OddsSide(entry.side), source=source,
            value=value, recorded_at=recorded_at,
        )
        results.append(OddsBatchResultEntry(
            game_id=entry.game_id, side=entry.side, source=source, outcome=outcome.action,
        ))

    db.commit()
    return OddsBatchResult(
        created_count=sum(1 for r in results if r.outcome == "created"),
        updated_count=sum(1 for r in results if r.outcome == "updated"),
        unchanged_count=sum(1 for r in results if r.outcome == "unchanged"),
        skipped_count=sum(1 for r in results if r.outcome == "skipped_started"),
        rejected_count=sum(1 for r in results if r.outcome == "rejected"),
        entries=results,
    )
