"""Rapprochement de joueurs par nom, insensible à la casse.

Point d'entrée unique utilisé par tous les sites de rapprochement par nom :
import CSV Advanced (saison courante et N-1), import CSV Draft, formulaire
admin manuel (app/api/players.py), et détection de transferts
(pronostic_calculator.py) -- pour garantir un comportement identique partout
plutôt que de dupliquer la normalisation à chaque endroit.

Décision de casse de stockage/affichage (voir CLAUDE.md, "Décisions
d'architecture") : la comparaison ignore la casse, mais la casse du `name`
déjà en base n'est JAMAIS réécrite par un rapprochement -- seule une édition
explicite du champ `name` (formulaire admin, ligne d'un futur import avec un
nom légèrement différent) change la casse stockée. Pas de normalisation
automatique en Title Case à l'écriture : `str.title()` casse les noms à
apostrophe (ex: "De'Aaron Fox" -> "De'aaron Fox"), ce qui introduirait un
nouveau bug d'affichage pour en corriger un autre.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Player, PreviousSeasonPlayerStat


def normalize_player_name(name: str) -> str:
    """casefold() plutôt que lower() : repliement de casse correct même sur
    les caractères accentués (ex: "GARCÍA" et "García" doivent être égaux)."""
    return name.strip().casefold()


def find_player_by_name(db: Session, name: str, team_id: int) -> Player | None:
    """Joueur de `team_id` dont le nom correspond à `name`, casse ignorée.

    Comparaison faite en Python (pas via LOWER() en SQL) : le LOWER() natif
    de SQLite ne replie que les caractères ASCII, pas les caractères
    accentués -- une comparaison SQL serait donc incorrecte sur certains noms
    réels. Un effectif d'équipe ne dépasse jamais ~20 joueurs : charger la
    liste complète pour comparer en Python n'a pas d'impact de performance
    mesurable ici."""
    target = normalize_player_name(name)
    for candidate in db.query(Player).filter(Player.team_id == team_id).all():
        if normalize_player_name(candidate.name) == target:
            return candidate
    return None


def find_active_player_by_name(db: Session, name: str) -> Player | None:
    """Comme find_player_by_name, mais toutes équipes confondues (joueurs
    actifs uniquement) -- utilisé par la détection de transferts sortants
    (compute_transfer_malus), qui cherche un joueur par son ancien nom sans
    connaître sa nouvelle équipe actuelle.

    .first() plutôt qu'un .one_or_none() qui lèverait en cas d'homonyme :
    risque accepté, pas de désambiguïsation pour ce MVP (voir CLAUDE.md,
    "Décisions d'architecture", point sur le rapprochement par nom seul)."""
    target = normalize_player_name(name)
    for candidate in db.query(Player).filter(Player.is_active.is_(True)).all():
        if normalize_player_name(candidate.name) == target:
            return candidate
    return None


def find_prev_season_stat_by_name(
    db: Session, season: str, name: str
) -> PreviousSeasonPlayerStat | None:
    """Ligne PreviousSeasonPlayerStat de `season` dont player_name correspond
    à `name`, casse ignorée -- utilisé par la détection de transferts
    entrants (compute_transfer_bonus, qui cherche le joueur par son nom
    ACTUEL dans l'effectif N-1) et par l'upsert d'import CSV Advanced N-1
    (apply_players_advanced_prev_season)."""
    target = normalize_player_name(name)
    candidates = db.query(PreviousSeasonPlayerStat).filter(PreviousSeasonPlayerStat.season == season).all()
    for candidate in candidates:
        if normalize_player_name(candidate.player_name) == target:
            return candidate
    return None
