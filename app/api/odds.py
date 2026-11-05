from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_admin
from app.database import get_db
from app.models import Game, Odds, OddsFetchRun, OddsFetchTrigger, OddsSide
from app.schemas import (
    OddsBatchResult,
    OddsBatchResultEntry,
    OddsBatchWrite,
    OddsCellRead,
    OddsDayRead,
    KickoffAlertRead,
    OddsFetchRunRead,
    OddsFetchStatusRead,
    OddsGameRead,
)
from app.services import nba_calendar, odds_fetcher
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
from app.services.odds_fetcher import (
    MIN_CREDITS_FOR_SCHEDULED,
    KickoffAlert,
    active_kickoff_alerts,
    last_known_credits,
    run_odds_fetch,
)
from app.services.pronostic_calculator import has_game_started

router = APIRouter(prefix="/api/odds", tags=["odds"], dependencies=[Depends(get_current_admin)])

# Les deux seules sources affichées par CET écran (quatre champs fixes par match, exigence du point 2).
# Rien n'empêche KNOWN_ODDS_SOURCES (app/services/odds.py) d'en compter d'autres plus tard sans migration
# -- mais cet écran-ci, câblé sur exactement ces deux colonnes dans le schéma de lecture, demandera alors
# un vrai changement de code. Identifiants exacts de the-odds-api.com depuis le 2026-11-03.
SCREEN_SOURCES: tuple[str, ...] = ("winamax_fr", "unibet_fr")


def _empty_cell() -> OddsCellRead:
    return OddsCellRead(value=None, recorded_at=None)


def _cell_from_odds(odds: Odds | None) -> OddsCellRead:
    if odds is None:
        return _empty_cell()
    # ISO 8601 avec "Z" explicite (UTC) -- jamais une chaîne naïve ambiguë lue comme heure locale par
    # `new Date(...)` côté navigateur (voir CLAUDE.md, limitation n°35).
    return OddsCellRead(
        value=odds.value, recorded_at=odds.recorded_at.isoformat() + "Z", collection=odds.collection.value
    )


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
    latest = latest_odds_by_cell(db, [g.id for g in games], SCREEN_SOURCES)

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
                winamax_home=cell(g.id, OddsSide.HOME, "winamax_fr"),
                winamax_away=cell(g.id, OddsSide.AWAY, "winamax_fr"),
                unibet_home=cell(g.id, OddsSide.HOME, "unibet_fr"),
                unibet_away=cell(g.id, OddsSide.AWAY, "unibet_fr"),
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


# --------------------------------------------------------------------------- relevé automatique (the-odds-api.com)

# Nombre de lignes du journal renvoyées par l'état du relevé.
RECENT_RUNS_LIMIT = 20


def _z(moment: datetime | None) -> str | None:
    return moment.isoformat() + "Z" if moment is not None else None


def _run_read(run: OddsFetchRun, with_report: bool) -> OddsFetchRunRead:
    report = run.report or {}
    return OddsFetchRunRead(
        id=run.id,
        fetched_at=_z(run.fetched_at),
        trigger=run.trigger.value,
        http_status=run.http_status,
        error=run.error,
        credits_used=run.credits_used,
        credits_remaining=run.credits_remaining,
        events_returned=run.events_returned,
        rows_written=run.rows_written,
        matched_count=len(report.get("matched", [])),
        unmatched_count=len(report.get("unmatched", [])),
        no_odds_yet_count=len(report.get("no_odds_yet", [])),
        ignored_count=len(report.get("ignored", [])),
        time_gap_count=len(report.get("time_gaps", [])),
        anomaly_count=len(report.get("anomalies", [])),
        report=run.report if with_report else None,
    )


def _alert_read(alert: KickoffAlert) -> KickoffAlertRead:
    return KickoffAlertRead(
        game_id=alert.game_id,
        label=alert.label,
        api_start=_z(alert.api_start),
        our_start=_z(alert.our_start),
        minutes_earlier=alert.minutes_earlier,
        fetched_at=_z(alert.fetched_at),
    )


@router.post("/fetch", response_model=OddsFetchRunRead)
def fetch_odds_now(db: Session = Depends(get_db)):
    """Bouton « Relever les cotes maintenant » : UN appel (1 crédit), quelle que soit l'heure et sans le seuil de
    crédits de la tâche planifiée (c'est l'utilisateur qui décide). L'appel est journalisé même en échec : le
    journal est validé AVANT de renvoyer l'erreur (502, message de l'API, clé masquée)."""
    api_key = os.getenv("ODDS_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="ODDS_API_KEY absente de la configuration du serveur.")
    with odds_fetcher.make_client() as client:
        run = run_odds_fetch(db, client, api_key, OddsFetchTrigger.BUTTON, nba_calendar.utc_now())
    db.commit()
    if run.error is not None:
        raise HTTPException(status_code=502, detail=run.error)
    return _run_read(run, with_report=True)


@router.get("/fetch-status", response_model=OddsFetchStatusRead)
def odds_fetch_status(db: Session = Depends(get_db)):
    """État du relevé automatique : configuration, dernier solde de crédits connu, journal récent (le dernier appel
    avec son compte-rendu complet) et alertes « coup d'envoi annoncé plus tôt », recalculées à chaque lecture."""
    runs = (
        db.query(OddsFetchRun)
        .order_by(OddsFetchRun.fetched_at.desc(), OddsFetchRun.id.desc())
        .limit(RECENT_RUNS_LIMIT)
        .all()
    )
    credits_run = last_known_credits(db)
    credits = credits_run.credits_remaining if credits_run is not None else None
    return OddsFetchStatusRead(
        scheduler_enabled=os.getenv("ENABLE_ODDS_SCHEDULER", "false").lower() == "true",
        api_key_configured=bool(os.getenv("ODDS_API_KEY")),
        credits_threshold=MIN_CREDITS_FOR_SCHEDULED,
        last_known_credits=credits,
        last_known_credits_at=_z(credits_run.fetched_at) if credits_run is not None else None,
        scheduled_suspended=credits is not None and credits < MIN_CREDITS_FOR_SCHEDULED,
        latest_run=_run_read(runs[0], with_report=True) if runs else None,
        recent_runs=[_run_read(r, with_report=False) for r in runs],
        alerts=[_alert_read(a) for a in active_kickoff_alerts(db, nba_calendar.utc_now())],
    )
