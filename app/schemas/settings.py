from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SettingsUpdate(BaseModel):
    base_note_multiplier: float | None = None
    per_impact_multiplier: float | None = None
    back_to_back_penalty: float | None = None
    three_in_four_penalty: float | None = None
    mpg_threshold: float | None = None
    draft_bonus_config: dict | None = None
    reliability_threshold_low: float | None = None
    reliability_threshold_high: float | None = None
    transfer_impact_multiplier: float | None = None
    current_season: str | None = None


class SettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    base_note_multiplier: float
    per_impact_multiplier: float
    back_to_back_penalty: float
    three_in_four_penalty: float
    mpg_threshold: float
    draft_bonus_config: dict
    reliability_threshold_low: float
    reliability_threshold_high: float
    transfer_impact_multiplier: float
    current_season: str
    # Dérivée de current_season (Settings.previous_season, propriété calculée
    # -- jamais stockée séparément), pour que le frontend n'ait pas à
    # réimplémenter ce calcul.
    previous_season: str
    updated_at: datetime
