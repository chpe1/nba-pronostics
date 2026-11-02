from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_current_admin
from app.database import get_db
from app.models import Team
from app.schemas import TeamRead, TeamUpdate
from app.schemas.team import CurrentSeasonRecordRead, ExcludedGameRead, SideRecordRead
from app.services.team_win_pct import SeasonRecords, count_season_records, current_season

# Calculés par le moteur depuis les matchs terminés (chantier (b2)) : jamais modifiables à la main.
READ_ONLY_FIELDS = ("win_pct_home", "win_pct_away")

router = APIRouter(prefix="/api/teams", tags=["teams"])


def _side(record) -> SideRecordRead:
    return SideRecordRead(wins=record.wins, losses=record.losses, games=record.games, pct=record.pct)


def _with_record(team: Team, records: SeasonRecords | None) -> TeamRead:
    """TeamRead + bilan de la saison en cours recompté maintenant (nombre de matchs, dernier match compté) et
    comparé à la valeur stockée, celle que lit la note."""
    read = TeamRead.model_validate(team)
    if records is None:
        return read
    record = records.for_team(team.id)
    read.current_season_record = CurrentSeasonRecordRead(
        season=records.season,
        home=_side(record.home),
        away=_side(record.away),
        last_game_date=record.last_game_date,
        stored_matches_recount=(team.win_pct_home, team.win_pct_away) == (record.home.pct, record.away.pct),
        excluded_games=[
            ExcludedGameRead(game_id=g.game_id, game_date=g.game_date, reason=g.reason)
            for g in records.excluded
            if team.id in (g.home_team_id, g.away_team_id)
        ],
    )
    return read


def _season_records(db: Session) -> SeasonRecords | None:
    season = current_season(db)
    return count_season_records(db, season) if season is not None else None


@router.get("", response_model=list[TeamRead])
def list_teams(db: Session = Depends(get_db)):
    """Route publique : les win_pct/nom/abréviation d'équipe sont déjà
    exposés publiquement ailleurs (ex: /api/predictions/today), donc rien de
    nouveau côté confidentialité. Réponse complète (TeamRead, pas un résumé)
    depuis la correction manuelle d'équipe (Admin > Équipes) : sert aussi au
    sélecteur d'équipe d'AdminPlayersView.vue, qui ignore simplement les
    champs en plus."""
    records = _season_records(db)
    return [_with_record(team, records) for team in db.query(Team).order_by(Team.name).all()]


@router.patch("/{team_id}", response_model=TeamRead, dependencies=[Depends(get_current_admin)])
def update_team(team_id: int, payload: TeamUpdate, db: Session = Depends(get_db)):
    """Correction manuelle admin d'une équipe -- même esprit que le
    formulaire joueurs (Étape 7) : un ajustement ponctuel, pas verrouillé
    contre un futur réimport CSV (upsert existant inchangé, la dernière
    valeur importée l'emporte). Pas de création : les 30 équipes NBA
    existent déjà via les imports, aucun besoin identifié d'en créer une de
    plus à la main."""
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Équipe introuvable")

    fields = payload.model_dump(exclude_unset=True)

    sent_read_only = [f for f in READ_ONLY_FIELDS if f in fields]
    if sent_read_only:
        raise HTTPException(
            status_code=422,
            detail=(
                "Les pourcentages de victoires de la saison en cours sont calculés depuis les matchs terminés : "
                f"lecture seule ({', '.join(sent_read_only)}). Corriger le score du match concerné (écran Matchs)."
            ),
        )

    if "name" in fields or "abbreviation" in fields:
        target_name = fields.get("name", team.name)
        target_abbreviation = fields.get("abbreviation", team.abbreviation)
        conflict = (
            db.query(Team)
            .filter(
                Team.id != team.id,
                (Team.name == target_name) | (Team.abbreviation == target_abbreviation),
            )
            .first()
        )
        if conflict is not None:
            raise HTTPException(
                status_code=409,
                detail="Une autre équipe existe déjà avec ce nom ou cette abréviation",
            )

    for field, value in fields.items():
        setattr(team, field, value)

    db.commit()
    db.refresh(team)
    return _with_record(team, _season_records(db))
