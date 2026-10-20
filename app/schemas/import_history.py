from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.import_history import ImportStatus, ImportType, SeasonType


class ImportErrorDetail(BaseModel):
    row: int
    message: str


class ImportHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    import_type: ImportType
    filename: str
    row_count: int
    error_count: int
    status: ImportStatus
    errors: list[ImportErrorDetail]
    season_type: SeasonType
    season: str | None
    created_at: datetime


class ImportPreviewResponse(BaseModel):
    import_type: ImportType
    filename: str
    row_count: int
    error_count: int
    sample_rows: list[dict]
    errors: list[ImportErrorDetail]
    season_type: SeasonType
    season: str | None = None
    # Renseigné uniquement pour un roster Advanced d'une seule équipe (pas de
    # colonne Team dans le fichier) : seule protection visible contre une
    # erreur de sélection dans le menu déroulant équipe, le fichier lui-même
    # ne contenant aucune info d'équipe à croiser. Scope volontairement
    # limité à l'aperçu dry-run -- pas dans l'historique des imports.
    resolved_team_name: str | None = None
    resolved_team_abbreviation: str | None = None


class AssociationRead(BaseModel):
    file_name: str
    player_id: int
    player_name: str


class ImportResultResponse(BaseModel):
    import_history: ImportHistoryRead
    # Verdicts sur les lignes du fichier sans correspondance (Décision n°39, étape 4) :
    # combien ont été tranchées, en recrues, en associations -- et lesquelles.
    resolved_rows_count: int = 0
    recruit_count: int = 0
    recruit_names: list[str] = []
    association_count: int = 0
    associations: list[AssociationRead] = []
    # Agents libres créés par cet import (Décision n°39) : joueurs détachés de
    # leur équipe, sur demande explicite. 0 / [] pour tout import qui n'en
    # détache pas.
    detached_count: int = 0
    detached_names: list[str] = []


class UnmatchedRosterNameRead(BaseModel):
    name: str
    closest_match: str | None
    distance: int | None


class MovedRosterEntryRead(BaseModel):
    name: str
    from_team: str
    to_team: str


class DetachablePlayerRead(BaseModel):
    id: int
    name: str
    team_abbreviation: str
    draft_pick: int | None
    per_n1: float | None
    mpg_n1: float | None


class FileRowWithoutMatchRead(BaseModel):
    name: str
    team_abbreviation: str
    # Simple suggestion (ressemblance de noms) pour traiter la ligne -- ne commande jamais le garde-fou.
    closest_absent_player: str | None
    distance: int | None


class AssociationCandidateRead(BaseModel):
    id: int
    name: str
    team_abbreviation: str | None


class RosterRowErrorRead(BaseModel):
    row: int
    player_name: str | None
    team: str | None
    message: str


class RosterImportPreviewResponse(BaseModel):
    """Schéma dédié à l'aperçu ROSTER (dry_run=True) -- forme délibérément
    différente de ImportPreviewResponse : le récapitulatif ROSTER croise le
    fichier avec l'état de la base (PreviousSeasonPlayerStat, Player), ce
    qu'aucun des 4 autres types ne fait à l'aperçu. Jamais utilisé pour la
    confirmation (dry_run=False), qui reste sur ImportResultResponse comme
    les autres types -- ce récapitulatif n'est jamais persisté dans
    ImportHistory (même portée que resolved_team_name : dry-run uniquement).
    """

    import_type: ImportType
    filename: str
    row_count: int
    error_count: int
    errors: list[ImportErrorDetail]

    # Section 1 : joueurs du CSV dont le nom (après repli diacritiques/
    # ponctuation/suffixes) trouve une ligne PreviousSeasonPlayerStat N-1.
    matched_count: int
    # Section 2 : le reste -- avec, pour chacun, le nom N-1 non réclamé le
    # plus proche (suggestion informative, jamais appliquée automatiquement).
    unmatched: list[UnmatchedRosterNameRead]
    # Section 3 : Player actifs en base qu'aucun nom du CSV ne rapproche --
    # purement informatif, voir la ligne fixe portée par le frontend (aucun
    # levier de désactivation n'existe aujourd'hui dans l'admin).
    orphans: list[str]
    # Section 4 : joueurs déjà en base, retrouvés par nom sous une AUTRE
    # équipe que celle du CSV -- seront déplacés (team_id mis à jour), pas
    # dupliqués, à la confirmation.
    moved: list[MovedRosterEntryRead]
    # Section 5 : sans ligne N-1 ET sans draft_pick connu en base -- à
    # regarder de plus près (saisie manuelle PER/MPG potentielle). Un joueur
    # sans ligne N-1 mais déjà drafté (draft_pick renseigné) est un rookie
    # normal, jamais listé ici.
    no_prior_data: list[str]
    # Futurs agents libres (Décision n°39), avec de quoi décider ; les mêmes joueurs
    # que `orphans`, hors agents libres déjà détachés.
    detachable: list["DetachablePlayerRead"]
    # Garde-fou du détachement : lignes du fichier qu'aucun joueur actif de la base
    # ne reconnaît (recrue, ou joueur déjà en base sous un autre nom). Tant qu'il en
    # reste, le geste global « tout détacher » doit être interdit côté écran.
    file_rows_without_match_count: int
    file_rows_without_match: list["FileRowWithoutMatchRead"]
    # Cibles possibles d'un verdict « c'est le même joueur que… » : les joueurs actifs
    # qu'aucune ligne du fichier ne désigne (agents libres compris).
    association_candidates: list["AssociationCandidateRead"]
    # Verdicts obligatoires pour CONFIRMER : au moins une ligne sans correspondance ET au moins
    # un joueur actif de la base absent du fichier (Décision n°39). Même règle que la garde
    # serveur de la confirmation -- l'écran s'y fie plutôt que de la recalculer.
    verdicts_required: bool
    # Lignes en erreur du fichier : elles BLOQUENT tout détachement (un nom illisible
    # pourrait être un joueur « absent » à tort). Avec ce que le fichier contient
    # réellement à cette ligne, pour savoir quoi corriger sans deviner.
    row_errors: list["RosterRowErrorRead"]
    detachment_blocked: bool
    detachment_blocked_reason: str | None
