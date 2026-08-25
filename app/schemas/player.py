from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.player import InjuryStatus


class PlayerBase(BaseModel):
    name: str
    team_id: int
    previous_team_id: int | None = None
    per: float = 0.0
    mpg: float = 0.0
    injury_status: InjuryStatus = InjuryStatus.HEALTHY
    injury_updated_at: datetime | None = None
    draft_pick: int | None = None
    is_active: bool = True


class PlayerCreate(PlayerBase):
    pass


class PlayerUpdate(BaseModel):
    name: str | None = None
    team_id: int | None = None
    previous_team_id: int | None = None
    per: float | None = None
    mpg: float | None = None
    injury_status: InjuryStatus | None = None
    injury_updated_at: datetime | None = None
    draft_pick: int | None = None
    is_active: bool | None = None


class PlayerRead(PlayerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class PlayerManualCreate(BaseModel):
    """Corps du POST /api/players (formulaire admin d'ajout manuel).

    Volontairement restreint à ces 5 champs (pas de injury_status,
    previous_team_id, is_active -- gérés ailleurs, par le parsing du rapport
    de blessures et la détection de transferts, pas par ce formulaire)."""

    name: str
    team_id: int
    draft_pick: int | None = None
    per: float | None = None
    mpg: float | None = None


class PlayerManualUpdate(BaseModel):
    """Corps du PATCH /api/players/{id} (édition inline). Aucun champ n'a de
    valeur par défaut implicite : seul un champ fourni est modifié."""

    name: str | None = None
    team_id: int | None = None
    draft_pick: int | None = None
    per: float | None = None
    mpg: float | None = None


class PlayerWithTeamRead(BaseModel):
    """Vue enrichie (nom d'équipe) utilisée par AdminPlayersView.vue.
    injury_status/is_active sont en lecture seule ici -- affichés pour aider
    l'admin à distinguer deux entrées homonymes, mais jamais modifiables via
    ce formulaire (voir PlayerManualCreate/PlayerManualUpdate)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    team_id: int
    team_name: str
    team_abbreviation: str
    draft_pick: int | None
    per: float
    mpg: float
    injury_status: InjuryStatus
    is_active: bool
