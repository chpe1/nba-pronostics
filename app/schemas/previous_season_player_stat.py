from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PreviousSeasonPlayerStatCreate(BaseModel):
    season: str
    player_name: str
    team_abbreviation: str
    per: float | None = None
    mpg: float | None = None


class PreviousSeasonPlayerStatUpdate(BaseModel):
    """Aucun champ n'a de valeur par défaut implicite : seul un champ fourni
    est modifié (même convention que PlayerManualUpdate)."""

    season: str | None = None
    player_name: str | None = None
    team_abbreviation: str | None = None
    per: float | None = None
    mpg: float | None = None


class PreviousSeasonPlayerStatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    season: str
    player_name: str
    team_abbreviation: str
    per: float | None
    mpg: float | None
    created_at: datetime
    updated_at: datetime


class PreviousSeasonPlayerStatListRead(BaseModel):
    """Enveloppe de pagination de GET /api/previous-season-stats (limitation
    n°14) -- se décrit elle-même plutôt que de forcer le client à connaître
    une constante serveur à l'avance : `total` porte le compte sous les
    filtres courants (avant découpage), `page` est un écho fidèle de la page
    demandée (jamais rabotée -- une page hors bornes renvoie `items: []` avec
    le vrai `total`, plutôt que de servir silencieusement une autre page),
    `size` est la taille réellement appliquée (DEFAULT_PAGE_SIZE, le seul
    canal par lequel le client l'apprend, puisqu'elle n'est pas un paramètre
    d'entrée). Le client dérive `pages = ceil(total / size)` lui-même --
    `total` et `size` étant dans la même charge utile, cette dérivation ne
    peut pas diverger de la vérité serveur. Pas un `Page[T]` générique :
    convention écrite (docs/design-v1.md §11), pas un socle partagé --
    n°12 reprendra les mêmes noms sans importer ce schéma."""

    items: list[PreviousSeasonPlayerStatRead]
    total: int
    page: int
    size: int
