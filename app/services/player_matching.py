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

Principe (revirement du 2026-10-24, voir CLAUDE.md limitation n°8) : TOLÉRANT
POUR LIRE, STRICT POUR ÉCRIRE. Les `find_*` ci-dessous restent STRICTS : ils
servent aux écritures et aux contrôles qui protègent une contrainte d'unicité
de la base (UNIQUE(name, team_id), UNIQUE(season, player_name)), qui est
exacte -- un garde-fou doit être aussi exact que la contrainte qu'il protège.
Les variantes `*_tolerant` repliant accents, ponctuation et suffixes servent
aux LECTURES du moteur de calcul.
"""
from __future__ import annotations

import re
import unicodedata

from sqlalchemy.orm import Session

from app.models import Player, PreviousSeasonPlayerStat


_NAME_SUFFIX_PATTERN = re.compile(r"\b(jr\.?|sr\.?|ii|iii|iv|v)\.?$", re.IGNORECASE)


def fold_diacritics(text: str) -> str:
    """Retire les diacritiques (NFD puis suppression des marques combinantes) :
    "Topić" -> "Topic". Ne touche ni à la casse ni à la ponctuation. Partagée par
    tolerant_name_key et par le rapprochement du rapport de blessures
    (injury_report_updater._normalize). Déplacée ici depuis csv_import.py le
    2026-10-24 : player_matching est la brique basse, les dépendances vont du
    haut vers le bas."""
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))


def tolerant_name_key(name: str) -> str:
    """Replie diacritiques + ponctuation + suffixes générationnels, en plus
    du strip().casefold() habituel. Mesuré sur le vrai fichier (voir plan du
    chantier ROSTER) : résout les seuls échecs "cosmétiques" (accents,
    ponctuation, Jr./Sr./II/III) sans rapprocher à tort deux joueurs
    différents -- le faux positif mesuré par ailleurs (distance de
    Levenshtein entre "Caleb Wilson" et "Jalen Wilson") ne partage aucun de
    ces éléments et reste un échec ici aussi, comme attendu. Ex-
    csv_import._roster_match_key, comportement inchangé d'un caractère."""
    without_diacritics = fold_diacritics(name.strip().casefold())
    without_punct = re.sub(r"[^\w\s]", "", without_diacritics)
    without_suffix = _NAME_SUFFIX_PATTERN.sub("", without_punct).strip()
    return re.sub(r"\s+", " ", without_suffix).strip()


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


def _strict_then_tolerant(candidates, name: str, name_of):
    """Égalité stricte d'abord (aucune régression sur ce qui marchait), puis
    égalité tolérante. Si la clé tolérante désigne PLUS D'UN candidat (deux
    joueurs que seul un suffixe ou un accent distingue), aucun résultat : on
    ne choisit jamais au hasard."""
    strict_target = normalize_player_name(name)
    tolerant_matches = []
    tolerant_target = None
    for candidate in candidates:
        candidate_name = name_of(candidate)
        if normalize_player_name(candidate_name) == strict_target:
            return candidate
    tolerant_target = tolerant_name_key(name)
    for candidate in candidates:
        if tolerant_name_key(name_of(candidate)) == tolerant_target:
            tolerant_matches.append(candidate)
    return tolerant_matches[0] if len(tolerant_matches) == 1 else None


def find_active_player_by_name_tolerant(db: Session, name: str) -> Player | None:
    """Version TOLÉRANTE de find_active_player_by_name, pour les LECTURES du
    moteur de calcul (malus de départ). Jamais pour une écriture."""
    return _strict_then_tolerant(
        db.query(Player).filter(Player.is_active.is_(True)).all(), name, lambda p: p.name
    )


def find_prev_season_stat_by_name_tolerant(
    db: Session, season: str, name: str
) -> PreviousSeasonPlayerStat | None:
    """Version TOLÉRANTE de find_prev_season_stat_by_name, pour les LECTURES
    du moteur de calcul (PER/MPG N-1, crédit sans N-1, bonus de transferts).
    Jamais pour une écriture ni pour un contrôle de conflit d'unicité."""
    return _strict_then_tolerant(
        db.query(PreviousSeasonPlayerStat).filter(PreviousSeasonPlayerStat.season == season).all(),
        name,
        lambda stat: stat.player_name,
    )
