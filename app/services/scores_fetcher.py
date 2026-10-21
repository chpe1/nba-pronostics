"""Synchronisation automatique des scores via l'API balldontlie.io
(https://docs.balldontlie.io/#nba-games), en remplacement d'un réimport CSV
manuel pour les résultats -- nécessaires au jour le jour pour les malus de
calendrier (B2B/3in4) et le bilan récent des équipes.

Compte gratuit requis (BALLDONTLIE_API_KEY), limite 5 req/min sur le tier
gratuit. Plusieurs dates tiennent en UN SEUL appel (`dates[]` répété, pagination par curseur
au-delà de 100 matchs) : une plage de plusieurs jours ne consomme pas le quota date par date.

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
from dataclasses import dataclass, field
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

# Motifs d'écartement d'un match renvoyé par l'API (clés stables, rendues telles quelles).
SKIP_UNKNOWN_TEAM = "unknown_team"  # abréviation d'équipe inconnue en base
SKIP_NOT_IN_DATABASE = "not_in_database"  # aucun match (date, domicile, extérieur) en base
SKIP_MANUALLY_OVERRIDDEN = "manually_overridden"  # verrouillé à la main : jamais touché
SKIP_UNKNOWN_DATE = "unknown_date"  # l'API n'a pas donné de date exploitable


@dataclass(frozen=True)
class RecordedGame:
    """Match RÉELLEMENT enregistré par cette synchro (une valeur a changé en base)."""

    game_id: int
    away_team_name: str
    away_team_abbreviation: str
    home_team_name: str
    home_team_abbreviation: str
    away_score: int | None
    home_score: int | None
    correction: bool  # le match était déjà terminé, seul le score a changé


@dataclass(frozen=True)
class StatusChange:
    """Match dont le statut a changé SANS devenir terminé (ex. reporté)."""

    game_id: int
    away_team_name: str
    home_team_name: str
    previous_status: str
    new_status: str


@dataclass(frozen=True)
class SkippedGame:
    label: str  # « BOS @ DET » : l'équipe n'est pas toujours connue de la base
    reason: str


@dataclass
class DaySyncResult:
    """Décompte d'UNE date. `updated` ne compte QUE les matchs dont une valeur a vraiment changé
    (limitation n°36 : l'ancien compteur comptait tout match retrouvé, modifié ou non)."""

    date: date
    found: int = 0  # matchs renvoyés par l'API pour cette date
    recorded: list[RecordedGame] = field(default_factory=list)
    already_final: int = 0  # terminés ET déjà enregistrés à l'identique : non retouchés
    not_finished: int = 0  # pas terminés côté API (à venir ou en cours) et rien à changer
    status_changes: list[StatusChange] = field(default_factory=list)
    skipped: list[SkippedGame] = field(default_factory=list)

    @property
    def updated(self) -> int:
        return len(self.recorded) + len(self.status_changes)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)


def fetch_games_for_dates(client: httpx.Client, api_key: str, dates: list[date]) -> list[dict]:
    """Tous les matchs de ces dates en UN appel (`dates[]` répété), en suivant le curseur de pagination
    si l'API en renvoie un (plus de 100 matchs). Lève `httpx.HTTPStatusError` sur un code d'erreur."""
    games: list[dict] = []
    cursor: int | None = None
    while True:
        params: list[tuple[str, str]] = [("dates[]", d.isoformat()) for d in dates] + [("per_page", "100")]
        if cursor is not None:
            params.append(("cursor", str(cursor)))
        response = client.get(BASE_URL, params=params, headers={"Authorization": api_key})
        response.raise_for_status()
        body = response.json()
        games.extend(body.get("data", []))
        cursor = (body.get("meta") or {}).get("next_cursor")
        if cursor is None:
            return games


def _apply_raw_game(db: Session, raw_game: dict, target_date: date, result: DaySyncResult) -> None:
    home_abbr = raw_game.get("home_team", {}).get("abbreviation")
    away_abbr = raw_game.get("visitor_team", {}).get("abbreviation")
    label = f"{away_abbr} @ {home_abbr}"
    home_team = db.query(Team).filter(Team.abbreviation == home_abbr).one_or_none()
    away_team = db.query(Team).filter(Team.abbreviation == away_abbr).one_or_none()
    if home_team is None or away_team is None:
        logger.warning("Équipe balldontlie non reconnue : %s @ %s", away_abbr, home_abbr)
        result.skipped.append(SkippedGame(label, SKIP_UNKNOWN_TEAM))
        return

    day_start = datetime.combine(target_date, time.min)
    day_end = day_start + timedelta(days=1)
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
        logger.warning("Match balldontlie introuvable en base : %s @ %s le %s", away_abbr, home_abbr, target_date)
        result.skipped.append(SkippedGame(label, SKIP_NOT_IN_DATABASE))
        return
    if game.manually_overridden:
        result.skipped.append(SkippedGame(label, SKIP_MANUALLY_OVERRIDDEN))
        return

    new_status = _resolve_status(raw_game)
    previous_status = game.status
    if new_status == GameStatus.FINISHED:
        new_home, new_away = raw_game.get("home_team_score"), raw_game.get("visitor_team_score")
        status_changed = previous_status != GameStatus.FINISHED
        scores_changed = (game.home_score, game.away_score) != (new_home, new_away)
        if not status_changed and not scores_changed:
            result.already_final += 1
            return
        # Une valeur change vraiment : on n'écrit QUE dans ce cas (aucune affectation d'une valeur identique).
        game.status = new_status
        game.home_score, game.away_score = new_home, new_away
        result.recorded.append(
            RecordedGame(
                game_id=game.id,
                away_team_name=away_team.name,
                away_team_abbreviation=away_team.abbreviation,
                home_team_name=home_team.name,
                home_team_abbreviation=home_team.abbreviation,
                away_score=new_away,
                home_score=new_home,
                correction=not status_changed,
            )
        )
        return
    if previous_status == new_status:
        result.not_finished += 1
        return
    game.status = new_status
    result.status_changes.append(
        StatusChange(game.id, away_team.name, home_team.name, previous_status.value, new_status.value)
    )


def sync_scores_for_range(
    db: Session, api_key: str, date_from: date, date_to: date, client: httpx.Client | None = None
) -> list[DaySyncResult]:
    """Synchronise les scores de toutes les dates de `date_from` à `date_to` (incluses), en UN appel API.
    Ne valide PAS la transaction (à charge de l'appelant). Retourne un résultat par date, y compris
    pour une date sans match. Lève `httpx.HTTPStatusError`/`httpx.RequestError` si l'API échoue."""
    days: list[date] = []
    current = date_from
    while current <= date_to:
        days.append(current)
        current += timedelta(days=1)
    results = {d: DaySyncResult(date=d) for d in days}

    owns_client = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        raw_games = fetch_games_for_dates(client, api_key, days)
    finally:
        if owns_client:
            client.close()

    for raw_game in raw_games:
        raw_date = str(raw_game.get("date") or "")[:10]
        try:
            game_day = date.fromisoformat(raw_date)
        except ValueError:
            game_day = None
        if game_day not in results:
            # Date absente ou hors plage demandée : comptée « ignoré » sur la première date.
            first = results[days[0]]
            first.found += 1
            away = raw_game.get("visitor_team", {}).get("abbreviation")
            home = raw_game.get("home_team", {}).get("abbreviation")
            first.skipped.append(SkippedGame(f"{away} @ {home}", SKIP_UNKNOWN_DATE))
            continue
        results[game_day].found += 1
        _apply_raw_game(db, raw_game, game_day, results[game_day])
    db.flush()
    return [results[d] for d in days]


def sync_scores_for_date(
    db: Session, api_key: str, target_date: date, client: httpx.Client | None = None
) -> DaySyncResult:
    """Une seule date, avec validation de la transaction (utilisé par la tâche planifiée). Le décompte
    `updated` ne compte que les matchs dont une valeur a RÉELLEMENT changé."""
    (result,) = sync_scores_for_range(db, api_key, target_date, target_date, client=client)
    db.commit()
    return result
