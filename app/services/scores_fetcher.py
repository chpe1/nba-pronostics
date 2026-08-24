"""Synchronisation automatique des scores via l'API balldontlie.io
(https://docs.balldontlie.io/#nba-games), en remplacement d'un réimport CSV
manuel pour les résultats -- nécessaires au jour le jour pour les malus de
calendrier (B2B/3in4) et le bilan récent des équipes.

Compte gratuit requis (BALLDONTLIE_API_KEY), limite 5 req/min sur le tier
gratuit -- largement suffisant ici (2 appels par exécution : hier + aujourd'hui).

Un Game est retrouvé en base par (date, équipe domicile, équipe extérieure),
même principe que l'upsert de l'import CSV du calendrier
(app/services/csv_import.py::apply_schedule). Un Game introuvable ou dont
les équipes ne sont pas reconnues est ignoré (journalisé), jamais créé ici --
la création des matchs reste le rôle de l'import CSV. Un Game
manually_overridden=True (corrigé à la main via l'admin, voir
app/api/games.py) n'est jamais modifié par cette synchro.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta

import httpx
from sqlalchemy.orm import Session

from app.models import Game, GameStatus, Team

logger = logging.getLogger(__name__)

BASE_URL = "https://api.balldontlie.io/v1/games"


def fetch_games_for_date(client: httpx.Client, api_key: str, target_date: date) -> list[dict]:
    """Retourne la liste brute des objets "game" de l'API pour cette date
    (peut être vide, ex: aucun match ce jour-là)."""
    response = client.get(
        BASE_URL,
        params={"dates[]": target_date.isoformat(), "per_page": 100},
        headers={"Authorization": api_key},
    )
    response.raise_for_status()
    return response.json().get("data", [])


def _resolve_status(raw_game: dict) -> GameStatus:
    if raw_game.get("postponed"):
        return GameStatus.POSTPONED
    if raw_game.get("status_state") == "final":
        return GameStatus.FINISHED
    return GameStatus.SCHEDULED


def sync_scores_for_date(
    db: Session, api_key: str, target_date: date, client: httpx.Client | None = None
) -> dict:
    """Récupère et applique les scores balldontlie.io pour une date donnée.
    Retourne un résumé {fetched, updated, skipped} -- ne lève jamais pour une
    donnée individuelle inattendue (équipe/match introuvable), seulement
    pour une erreur réseau/HTTP (à charge de l'appelant de la traiter, voir
    run_scores_sync_job qui l'attrape et journalise)."""
    owns_client = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        raw_games = fetch_games_for_date(client, api_key, target_date)
    finally:
        if owns_client:
            client.close()

    updated = 0
    skipped = 0
    day_start = datetime.combine(target_date, time.min)
    day_end = day_start + timedelta(days=1)

    for raw_game in raw_games:
        home_abbr = raw_game.get("home_team", {}).get("abbreviation")
        away_abbr = raw_game.get("visitor_team", {}).get("abbreviation")
        home_team = db.query(Team).filter(Team.abbreviation == home_abbr).one_or_none()
        away_team = db.query(Team).filter(Team.abbreviation == away_abbr).one_or_none()
        if home_team is None or away_team is None:
            logger.warning("Équipe balldontlie non reconnue : %s @ %s", away_abbr, home_abbr)
            skipped += 1
            continue

        game = (
            db.query(Game)
            .filter(
                Game.home_team_id == home_team.id,
                Game.away_team_id == away_team.id,
                Game.game_date >= day_start,
                Game.game_date < day_end,
            )
            .one_or_none()
        )
        if game is None:
            logger.warning(
                "Match balldontlie introuvable en base : %s @ %s le %s", away_abbr, home_abbr, target_date
            )
            skipped += 1
            continue
        if game.manually_overridden:
            skipped += 1
            continue

        game.status = _resolve_status(raw_game)
        if game.status == GameStatus.FINISHED:
            game.home_score = raw_game.get("home_team_score")
            game.away_score = raw_game.get("visitor_team_score")
        updated += 1

    db.commit()
    return {"fetched": len(raw_games), "updated": updated, "skipped": skipped}
