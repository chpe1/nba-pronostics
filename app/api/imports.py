from __future__ import annotations

import logging

import json
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.core.security import get_current_admin
from app.database import get_db
from app.models import ImportHistory, ImportStatus, ImportType, SeasonType, Team
from app.schemas import (
    AssociationCandidateRead,
    AssociationRead,
    RosterRowErrorRead,
    DetachablePlayerRead,
    FileRowWithoutMatchRead,
    ImportHistoryRead,
    ImportPreviewResponse,
    ImportResultResponse,
    MovedRosterEntryRead,
    RosterImportPreviewResponse,
    UnmatchedRosterNameRead,
)
from app.services import csv_import

logger = logging.getLogger(__name__)


class RowVerdictIn(BaseModel):
    """Verdict envoyé par l'écran à la confirmation d'un import d'effectif (champ de
    formulaire `verdicts`, liste JSON de ces objets) -- voir Décision n°39."""

    file_name: str
    verdict: Literal["recruit", "same_player"]
    player_id: int | None = None


def _parse_verdicts(raw: str | None) -> list[csv_import.RowVerdict]:
    if not raw:
        return []
    try:
        items = json.loads(raw)
        if not isinstance(items, list):
            raise ValueError("une liste est attendue")
        return [csv_import.RowVerdict(**RowVerdictIn(**item).model_dump()) for item in items]
    except (ValueError, TypeError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=f"Verdicts illisibles : {exc}") from exc

router = APIRouter(prefix="/api/imports", tags=["imports"], dependencies=[Depends(get_current_admin)])


@router.post("/stats", response_model=ImportPreviewResponse | RosterImportPreviewResponse | ImportResultResponse)
async def import_stats(
    file: UploadFile = File(...),
    dry_run: bool = Query(True, description="Aperçu sans écriture en base si true"),
    import_type: ImportType | None = Query(
        None, description="Force le type de fichier au lieu de la détection auto"
    ),
    season_type: SeasonType = Query(
        SeasonType.CURRENT,
        description="Saison courante ou précédente (sans objet pour le type draft)",
    ),
    season: str | None = Query(
        None, description="Libellé de la saison N-1, ex: '2024-2025' (requis si season_type=previous)"
    ),
    team_id: int | None = Query(
        None,
        description=(
            "ID de l'équipe -- requis uniquement pour un roster Advanced "
            "d'une seule équipe (fichier sans colonne Team), quelle que soit la saison."
        ),
    ),
    detach_player_ids: list[int] = Query(
        default=[],
        description=(
            "Identifiants des joueurs à détacher de leur équipe (agents libres, Décision n°39) -- "
            "UNIQUEMENT pour la confirmation (dry_run=false) d'un import d'effectif ROSTER. "
            "Rien n'est jamais détaché par défaut : liste absente ou vide = aucun détachement."
        ),
    ),
    verdicts: str | None = Form(
        default=None,
        description=(
            "Verdicts sur les lignes du fichier sans correspondance (liste JSON de "
            "{file_name, verdict: 'recruit'|'same_player', player_id}) -- confirmation d'un "
            "import d'effectif uniquement (Décision n°39)."
        ),
    ),
    db: Session = Depends(get_db),
):
    file_bytes = await file.read()
    try:
        df = csv_import.read_csv(file_bytes)
    except csv_import.CsvImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    detected_type = import_type or csv_import.detect_import_type(df)
    if detected_type is None:
        raise HTTPException(
            status_code=400,
            detail="Impossible de déterminer le type de fichier (colonnes attendues non trouvées).",
        )

    missing = csv_import.validate_columns(df, detected_type)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Colonnes manquantes pour {detected_type.value} : {', '.join(missing)}",
        )

    # players_advanced accepte un roster d'une seule équipe (pas de colonne
    # Team, l'équipe est alors implicite au fichier) : team_id devient
    # obligatoire dans ce cas précis. resolved_team_* est renvoyé dans
    # l'aperçu dry-run -- seule protection contre une erreur de sélection
    # dans le menu déroulant, puisque le fichier ne contient aucune info
    # d'équipe à croiser.
    team_abbreviation_param: str | None = None
    resolved_team_name: str | None = None
    resolved_team_abbreviation: str | None = None
    if detected_type == ImportType.PLAYERS_ADVANCED and "Team" not in df.columns:
        if team_id is None:
            raise HTTPException(
                status_code=400,
                detail="Le paramètre 'team_id' est requis pour un roster par équipe (fichier sans colonne Team).",
            )
        team = db.get(Team, team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="Équipe introuvable")
        team_abbreviation_param = team.abbreviation
        resolved_team_name = team.name
        resolved_team_abbreviation = team.abbreviation

    # La draft n'a pas de notion de saison précédente (toujours l'effectif
    # actuel) -- ROSTER non plus, pour la même raison (l'effectif complet
    # décrit toujours la saison courante, jamais N-1). Le calendrier n'a pas
    # cette notion non plus, mais pour la raison inverse : `season` y est
    # TOUJOURS requis (pas de "courant" par défaut déductible des dates, cf.
    # plan-etape6ter.md).
    if detected_type == ImportType.SCHEDULE:
        effective_season_type = SeasonType.CURRENT
        if not season:
            raise HTTPException(
                status_code=400,
                detail="Le paramètre 'season' (ex: '2026-2027') est requis pour importer un calendrier.",
            )
    elif detected_type in (ImportType.DRAFT, ImportType.ROSTER):
        effective_season_type = SeasonType.CURRENT
    else:
        effective_season_type = season_type
        if effective_season_type == SeasonType.PREVIOUS and not season:
            raise HTTPException(
                status_code=400,
                detail="Le paramètre 'season' (ex: '2024-2025') est requis pour un import de saison précédente.",
            )

    if detected_type == ImportType.SCHEDULE:
        parser = csv_import.PARSERS[detected_type]
        applier = None  # apply_schedule appelé directement plus bas (signature dédiée)
    elif detected_type == ImportType.ROSTER:
        # Hors des dicts génériques PARSERS/APPLIERS, comme SCHEDULE ci-dessus
        # -- l'aperçu ROSTER a besoin d'analyze_roster_import (lecture DB),
        # que rien d'autre ne fait à ce stade (voir plan du chantier).
        parser = csv_import.parse_roster
        applier = csv_import.apply_roster
    elif effective_season_type == SeasonType.PREVIOUS:
        parser = csv_import.PREV_SEASON_PARSERS[detected_type]
        applier = csv_import.PREV_SEASON_APPLIERS[detected_type]
    else:
        parser = csv_import.PARSERS[detected_type]
        applier = csv_import.APPLIERS[detected_type]

    if detected_type == ImportType.PLAYERS_ADVANCED:
        parsed, errors = parser(df, team_abbreviation=team_abbreviation_param)
    else:
        parsed, errors = parser(df)
    filename = file.filename or "fichier.csv"

    # Détachement (agents libres, Décision n°39) : réservé à la CONFIRMATION d'un
    # import d'effectif. Gardes serveur évaluées AVANT toute écriture -- un refus
    # laisse la base intacte (aucun commit n'a eu lieu).
    players_to_detach: list = []
    validated_verdicts = csv_import.ValidatedVerdicts(recruits=[], associations=[])
    row_verdicts = _parse_verdicts(verdicts)
    if (row_verdicts or detach_player_ids) and (dry_run or detected_type != ImportType.ROSTER):
        raise HTTPException(
            status_code=400,
            detail=(
                "'detach_player_ids' et 'verdicts' ne sont acceptés que pour la confirmation "
                "(dry_run=false) d'un import d'effectif."
            ),
        )
    if not dry_run and detected_type == ImportType.ROSTER:
        # Toute confirmation d'un effectif passe par ces gardes, avec ou sans verdicts envoyés : la
        # règle « verdicts obligatoires quand une ligne sans correspondance ET un joueur absent
        # côté base coexistent » doit tenir même si l'écran n'envoie rien.
        try:
            validated_verdicts = csv_import.validate_row_verdicts(db, parsed, row_verdicts)
            csv_import.require_verdicts_when_risky(db, parsed, validated_verdicts)
            players_to_detach = csv_import.validate_detach_request(
                db, parsed, detach_player_ids, has_row_errors=bool(errors), verdicts=validated_verdicts
            )
        except (csv_import.DetachRefusedError, csv_import.VerdictRefusedError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if dry_run:
        if detected_type == ImportType.ROSTER:
            # Récapitulatif AVANT toute écriture (plan du chantier, point a)
            # -- analyze_roster_import ne fait que lire, jamais db.add/flush.
            analysis = csv_import.analyze_roster_import(db, parsed)
            return RosterImportPreviewResponse(
                import_type=detected_type,
                filename=filename,
                row_count=len(parsed),
                error_count=len(errors),
                errors=errors,
                matched_count=analysis.matched_count,
                unmatched=[
                    UnmatchedRosterNameRead(
                        name=item.name, closest_match=item.closest_match, distance=item.distance
                    )
                    for item in analysis.unmatched
                ],
                orphans=analysis.orphans,
                moved=[
                    MovedRosterEntryRead(name=item.name, from_team=item.from_team, to_team=item.to_team)
                    for item in analysis.moved
                ],
                no_prior_data=analysis.no_prior_data,
                detachable=[
                    DetachablePlayerRead(
                        id=item.id,
                        name=item.name,
                        team_abbreviation=item.team_abbreviation,
                        draft_pick=item.draft_pick,
                        per_n1=item.per_n1,
                        mpg_n1=item.mpg_n1,
                    )
                    for item in analysis.detachable
                ],
                association_candidates=[
                    AssociationCandidateRead(id=c.id, name=c.name, team_abbreviation=c.team_abbreviation)
                    for c in analysis.association_candidates
                ],
                verdicts_required=analysis.verdicts_required,
                row_errors=[
                    RosterRowErrorRead(**item) for item in csv_import.describe_roster_row_errors(df, errors)
                ],
                detachment_blocked=bool(errors),
                detachment_blocked_reason=(
                    f"{len(errors)} ligne(s) du fichier en erreur : tout détachement est bloqué tant que "
                    "le fichier n'est pas corrigé (voir row_errors)."
                    if errors
                    else None
                ),
                file_rows_without_match_count=len(analysis.file_rows_without_match),
                file_rows_without_match=[
                    FileRowWithoutMatchRead(
                        name=item.name,
                        team_abbreviation=item.team_abbreviation,
                        closest_absent_player=item.closest_absent_player,
                        distance=item.distance,
                    )
                    for item in analysis.file_rows_without_match
                ],
            )
        return ImportPreviewResponse(
            import_type=detected_type,
            filename=filename,
            row_count=len(parsed),
            error_count=len(errors),
            sample_rows=parsed[:10],
            errors=errors,
            season_type=effective_season_type,
            season=season if detected_type == ImportType.SCHEDULE or effective_season_type == SeasonType.PREVIOUS else None,
            resolved_team_name=resolved_team_name,
            resolved_team_abbreviation=resolved_team_abbreviation,
        )

    if detected_type == ImportType.SCHEDULE:
        row_count = csv_import.apply_schedule(parsed, db, season)
    elif detected_type == ImportType.ROSTER:
        row_count = csv_import.apply_roster(parsed, db, associations=validated_verdicts.association_map())
    elif effective_season_type == SeasonType.PREVIOUS:
        row_count = applier(parsed, db, season)
    else:
        row_count = applier(parsed, db)

    if errors and parsed:
        status = ImportStatus.PARTIAL
    elif errors and not parsed:
        status = ImportStatus.ERROR
    else:
        status = ImportStatus.SUCCESS

    history = ImportHistory(
        import_type=detected_type,
        filename=filename,
        row_count=row_count,
        error_count=len(errors),
        status=status,
        errors=errors,
        season_type=effective_season_type,
        season=season if detected_type == ImportType.SCHEDULE or effective_season_type == SeasonType.PREVIOUS else None,
    )
    db.add(history)

    detached_names: list[str] = []
    if players_to_detach:
        detached_names = csv_import.detach_players(db, players_to_detach)
        logger.info(
            "Import d'effectif %s : %d joueur(s) détaché(s) (agents libres) : %s",
            filename,
            len(detached_names),
            ", ".join(detached_names),
        )

    db.commit()
    db.refresh(history)

    if validated_verdicts.resolved_count:
        logger.info(
            "Import d'effectif %s : %d ligne(s) tranchée(s) (%d recrue(s) : %s ; %d association(s) : %s)",
            filename,
            validated_verdicts.resolved_count,
            len(validated_verdicts.recruits),
            ", ".join(validated_verdicts.recruits),
            len(validated_verdicts.associations),
            ", ".join(f"{name} -> {player.name}" for name, player in validated_verdicts.associations),
        )

    return ImportResultResponse(
        import_history=history,
        resolved_rows_count=validated_verdicts.resolved_count,
        recruit_count=len(validated_verdicts.recruits),
        recruit_names=validated_verdicts.recruits,
        association_count=len(validated_verdicts.associations),
        associations=[
            AssociationRead(file_name=name, player_id=player.id, player_name=player.name)
            for name, player in validated_verdicts.associations
        ],
        detached_count=len(detached_names),
        detached_names=detached_names,
    )


@router.get("/template")
def download_template(
    type: str = Query(..., description="Un de : " + ", ".join(csv_import.TEMPLATE_KEYS)),
):
    """Aide-mémoire rapide du format actuellement attendu par chaque type de
    fichier -- généré depuis REQUIRED_COLUMNS (même source de vérité que la
    validation à l'import), pas une liste recopiée à la main."""
    try:
        content = csv_import.generate_template_csv(type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="modele_{type}.csv"'},
    )


@router.get("/history", response_model=list[ImportHistoryRead])
def get_import_history(db: Session = Depends(get_db)):
    return (
        db.query(ImportHistory)
        .order_by(ImportHistory.created_at.desc())
        .all()
    )
