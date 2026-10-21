from datetime import date

from pydantic import BaseModel


class ScoreSyncRecordedGame(BaseModel):
    """Match RÉELLEMENT enregistré par la synchro (une valeur a changé en base)."""

    game_id: int
    away_team_name: str
    away_team_abbreviation: str
    home_team_name: str
    home_team_abbreviation: str
    away_score: int | None
    home_score: int | None
    # Le match était déjà terminé : seul son score a été corrigé.
    correction: bool


class ScoreSyncStatusChange(BaseModel):
    """Match dont le statut a changé sans devenir terminé (ex. reporté)."""

    game_id: int
    away_team_name: str
    home_team_name: str
    previous_status: str
    new_status: str


class ScoreSyncSkipped(BaseModel):
    label: str
    reason: str  # clé stable (unknown_team, not_in_database, manually_overridden, unknown_date)
    reason_label: str  # phrase lisible


class ScoreSyncDay(BaseModel):
    date: date
    found: int
    recorded_count: int
    already_final_count: int
    not_finished_count: int
    status_change_count: int
    skipped_count: int
    recorded: list[ScoreSyncRecordedGame]
    status_changes: list[ScoreSyncStatusChange]
    skipped: list[ScoreSyncSkipped]


class ScoreSyncReport(BaseModel):
    """Compte-rendu de POST /api/scores/sync. Le décompte « enregistrés » ne compte QUE les matchs dont
    une valeur a changé en base (limitation n°36) : un match déjà à jour est compté à part."""

    date_from: date
    date_to: date
    days_count: int
    found: int
    recorded_count: int
    already_final_count: int
    not_finished_count: int
    status_change_count: int
    skipped_count: int
    # False => aucune écriture n'a eu lieu en base.
    written: bool
    days: list[ScoreSyncDay]
