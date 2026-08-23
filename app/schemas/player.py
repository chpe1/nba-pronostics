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
