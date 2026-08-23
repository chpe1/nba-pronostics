from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SettingsUpdate(BaseModel):
    base_note_multiplier: float | None = None
    per_impact_multiplier: float | None = None
    back_to_back_penalty: float | None = None
    three_in_four_penalty: float | None = None
    mpg_threshold: float | None = None
    draft_bonus_config: dict | None = None


class SettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    base_note_multiplier: float
    per_impact_multiplier: float
    back_to_back_penalty: float
    three_in_four_penalty: float
    mpg_threshold: float
    draft_bonus_config: dict
    updated_at: datetime
