from pydantic import BaseModel


class InjuryUnmatchedEntry(BaseModel):
    """Entrée du rapport qu'aucun joueur de la base n'a pu recevoir."""

    player_name_raw: str
    team_abbreviation: str | None
    team_raw: str
    status_raw: str
    reason: str
    # Équipes (abréviations) sous lesquelles un joueur de même nom EXISTE en
    # base alors que le rapport l'indique ailleurs : le signe qu'un joueur a
    # changé d'équipe sans que la base le sache (voir CLAUDE.md, limitation n°25).
    exists_in_database_on_teams: list[str]


class InjuryWeighingPlayer(BaseModel):
    name: str
    team_abbreviation: str
    status: str
    per: float
    mpg: float


class InjuryUpdateReport(BaseModel):
    """Compte-rendu de POST /api/injuries/refresh, affiché tel quel par l'écran."""

    report_url: str
    report_time_new_york: str
    report_time_paris: str
    game_dates: list[str]
    entries_read: int
    # True quand le PDF ne contient que « NOT YET SUBMITTED » (aucune entrée) :
    # PAS « aucun blessé » -- les équipes n'ont simplement rien soumis.
    not_yet_submitted: bool
    not_yet_submitted_count: int
    # False => aucune écriture n'a eu lieu en base.
    written: bool
    matched_count: int
    unmatched_count: int
    unmatched: list[InjuryUnmatchedEntry]
    status_counts: dict[str, int]
    absent_count: int
    mpg_threshold: float
    weighing_count: int
    weighing: list[InjuryWeighingPlayer]
