"""Moteur de calcul du pronostic (Note Finale) pour un match.

Formule (cahier des charges) :
    Note Finale = (Note de Base × Curseur A)
                - (PER des absents majeurs × Curseur B)
                - Malus Calendrier
                + Bonus Draft (règle des 10 premiers matchs)
                + Bonus/Malus Transferts (règle des 10 premiers matchs, Étape 6bis)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import (
    Game,
    GameStatus,
    InjuryStatus,
    Player,
    Prediction,
    PreviousSeasonPlayerStat,
    ReliabilityLevel,
    Settings,
    Team,
)

# Statuts comptant pour la soustraction du PER (joueurs "absents majeurs").
ABSENT_STATUSES = {InjuryStatus.OUT, InjuryStatus.DOUBTFUL}

# Une équipe est en "début de saison" tant qu'elle a joué moins de N matchs.
EARLY_SEASON_GAME_THRESHOLD = 10

# Fenêtre de calcul du 3-matchs-en-4-nuits : les 3 nuits précédant le match
# (le match du jour compte comme le 3e/4e match de la fenêtre de 4 nuits).
THREE_IN_FOUR_WINDOW_DAYS = 3
THREE_IN_FOUR_GAME_COUNT = 2  # nb de matchs précédents requis dans la fenêtre

# Nombre de matchs récents pris en compte pour le bilan V-D affiché sur le
# Dashboard (ex: "5V-2D sur les 7 derniers").
RECENT_RECORD_WINDOW = 7


@dataclass
class RecentRecord:
    wins: int
    losses: int
    games_considered: int


def compute_recent_record(
    db: Session, team: Team, before_date: date, window: int = RECENT_RECORD_WINDOW
) -> RecentRecord:
    """Bilan victoires/défaites de l'équipe sur ses `window` derniers matchs
    terminés avant `before_date`."""
    games = (
        db.query(Game)
        .filter(
            Game.status == GameStatus.FINISHED,
            Game.game_date < before_date,
            or_(Game.home_team_id == team.id, Game.away_team_id == team.id),
        )
        .order_by(Game.game_date.desc())
        .limit(window)
        .all()
    )

    wins = 0
    losses = 0
    for game in games:
        if game.home_score is None or game.away_score is None:
            continue
        team_is_home = game.home_team_id == team.id
        team_score = game.home_score if team_is_home else game.away_score
        opponent_score = game.away_score if team_is_home else game.home_score
        if team_score > opponent_score:
            wins += 1
        elif team_score < opponent_score:
            losses += 1

    return RecentRecord(wins=wins, losses=losses, games_considered=len(games))


@dataclass
class QuestionablePlayerInfo:
    """Purement informatif : n'entre pas dans le calcul du spread/vainqueur."""

    name: str
    per: float
    reason: str | None = None


@dataclass
class TeamNoteBreakdown:
    team_id: int
    team_name: str
    is_home: bool
    games_played_this_season: int
    in_early_season: bool
    note_de_base: float
    injury_penalty: float
    is_back_to_back: bool
    is_three_in_four: bool
    calendar_penalty: float
    draft_bonus: float
    transfer_adjustment: float
    final_note: float
    questionable_players: list[QuestionablePlayerInfo] = field(default_factory=list)


@dataclass
class MatchupResult:
    game_id: int
    home: TeamNoteBreakdown
    away: TeamNoteBreakdown
    spread: float
    predicted_winner_team_id: int
    reliability: ReliabilityLevel


def count_finished_games_this_season(
    db: Session, team: Team, season: str, before_date: date
) -> int:
    return (
        db.query(Game)
        .filter(
            Game.season == season,
            Game.status == GameStatus.FINISHED,
            Game.game_date < before_date,
            or_(Game.home_team_id == team.id, Game.away_team_id == team.id),
        )
        .count()
    )


def compute_note_de_base(team: Team, is_home: bool, in_early_season: bool) -> float:
    if in_early_season:
        return team.win_pct_home_prev_season if is_home else team.win_pct_away_prev_season
    return team.win_pct_home if is_home else team.win_pct_away


def _relevant_players_query(db: Session, team: Team, settings: Settings):
    return db.query(Player).filter(
        Player.team_id == team.id,
        Player.is_active.is_(True),
        Player.mpg > settings.mpg_threshold,
    )


def compute_injury_penalty(db: Session, team: Team, settings: Settings) -> float:
    absent_players = _relevant_players_query(db, team, settings).filter(
        Player.injury_status.in_(ABSENT_STATUSES)
    )
    return sum(p.per for p in absent_players.all())


def get_questionable_players(
    db: Session, team: Team, settings: Settings
) -> list[QuestionablePlayerInfo]:
    """Joueurs Questionable pertinents (filtre MPG), à titre informatif
    uniquement (badge "incertain" côté frontend) — n'affecte pas le calcul."""
    players = _relevant_players_query(db, team, settings).filter(
        Player.injury_status == InjuryStatus.QUESTIONABLE
    )
    return [
        QuestionablePlayerInfo(name=p.name, per=p.per, reason=p.injury_reason)
        for p in players.all()
    ]


def _team_games_before(db: Session, team: Team, before_date: date, since_date: date) -> list[Game]:
    return (
        db.query(Game)
        .filter(
            Game.status == GameStatus.FINISHED,
            Game.game_date >= since_date,
            Game.game_date < before_date,
            or_(Game.home_team_id == team.id, Game.away_team_id == team.id),
        )
        .all()
    )


def compute_calendar_penalty(db: Session, team: Team, game_date: date, settings: Settings) -> dict:
    """Retourne le détail (is_back_to_back, is_three_in_four, penalty) : si
    les deux conditions sont vraies, on applique le malus le plus sévère des
    deux plutôt que de les cumuler."""
    recent_games = _team_games_before(
        db, team, before_date=game_date, since_date=game_date - timedelta(days=THREE_IN_FOUR_WINDOW_DAYS)
    )
    recent_dates = {g.game_date.date() if hasattr(g.game_date, "date") else g.game_date for g in recent_games}

    is_back_to_back = (game_date - timedelta(days=1)) in recent_dates
    is_three_in_four = len(recent_dates) >= THREE_IN_FOUR_GAME_COUNT

    penalty = 0.0
    if is_back_to_back:
        penalty = max(penalty, settings.back_to_back_penalty)
    if is_three_in_four:
        penalty = max(penalty, settings.three_in_four_penalty)

    return {
        "is_back_to_back": is_back_to_back,
        "is_three_in_four": is_three_in_four,
        "penalty": penalty,
    }


def compute_draft_bonus(db: Session, team: Team, settings: Settings) -> float:
    """Somme des bonus de TOUS les rookies draftés dans l'effectif actif."""
    rookies = db.query(Player).filter(
        Player.team_id == team.id,
        Player.is_active.is_(True),
        Player.draft_pick.is_not(None),
    )
    total = 0.0
    for player in rookies.all():
        total += settings.draft_bonus_config.get(str(player.draft_pick), 0.0)
    return total


def previous_season_label(season: str) -> str:
    """"2025-2026" -> "2024-2025" """
    start, end = season.split("-")
    return f"{int(start) - 1}-{int(end) - 1}"


def compute_transfer_bonus(db: Session, team: Team, settings: Settings, prev_season: str) -> float:
    """Transferts ENTRANTS : somme des PER (saison N-1) des joueurs
    ACTUELLEMENT dans l'effectif de `team` qui évoluaient dans une autre
    équipe lors de `prev_season`.

    Filtré par le MPG N-1 (pas le MPG courant) au-dessus de
    settings.mpg_threshold -- ici, une APPROXIMATION : on ne connaît pas
    encore le rôle réel du joueur dans sa nouvelle équipe (échantillon trop
    petit en tout début de saison), donc son temps de jeu de la saison
    passée sert de meilleur signal disponible. Voir compute_transfer_malus
    pour le raisonnement symétrique côté équipe quittée, où ce même champ a
    un statut différent (mesure directe, pas une approximation)."""
    total = 0.0
    current_players = db.query(Player).filter(Player.team_id == team.id, Player.is_active.is_(True)).all()
    for player in current_players:
        stat = (
            db.query(PreviousSeasonPlayerStat)
            .filter(
                PreviousSeasonPlayerStat.season == prev_season,
                PreviousSeasonPlayerStat.player_name == player.name,
            )
            .one_or_none()
        )
        if stat is None or stat.per is None or stat.mpg is None:
            continue  # pas de donnée N-1 (rookie, etc.) -> pas un transfert
        if stat.team_abbreviation == team.abbreviation:
            continue  # déjà dans cette équipe la saison dernière
        if stat.mpg <= settings.mpg_threshold:
            continue
        total += stat.per
    return total


def compute_transfer_malus(db: Session, team: Team, settings: Settings, prev_season: str) -> float:
    """Transferts SORTANTS : somme des PER (N-1) des joueurs qui évoluaient
    dans `team` lors de `prev_season` et qui jouent désormais ailleurs. Un
    joueur introuvable dans l'effectif actuel (retraite, non reconduit...)
    est ignoré : on ne pénalise que les départs vérifiables vers une autre
    équipe actuelle, pas l'attrition générale (hors périmètre).

    Le filtre MPG (N-1) n'a pas le même statut ici que dans
    compute_transfer_bonus : il mesure directement l'importance du joueur
    DANS L'ANCIENNE équipe (`team`) la saison passée -- une donnée fiable et
    pertinente en soi pour juger l'ampleur de la perte -- et non une
    approximation faute de connaître son rôle ailleurs (ce qui est le cas
    côté bonus, où le MPG N-1 ne fait que pallier l'absence de MPG courant
    fiable dans la nouvelle équipe en tout début de saison)."""
    total = 0.0
    prev_roster = (
        db.query(PreviousSeasonPlayerStat)
        .filter(
            PreviousSeasonPlayerStat.season == prev_season,
            PreviousSeasonPlayerStat.team_abbreviation == team.abbreviation,
        )
        .all()
    )
    for stat in prev_roster:
        if stat.per is None or stat.mpg is None or stat.mpg <= settings.mpg_threshold:
            continue
        # .first() plutôt que .one_or_none() : en cas d'homonyme (risque
        # accepté, pas de désambiguïsation pour ce MVP) on ne veut pas
        # planter le calcul, juste accepter une association possiblement
        # imprécise.
        current_player = (
            db.query(Player)
            .filter(Player.name == stat.player_name, Player.is_active.is_(True))
            .first()
        )
        if current_player is None or current_player.team_id == team.id:
            continue
        total += stat.per
    return total


def compute_team_note(
    db: Session, team: Team, game_date: date, season: str, is_home: bool, settings: Settings
) -> TeamNoteBreakdown:
    games_played = count_finished_games_this_season(db, team, season, before_date=game_date)
    in_early_season = games_played < EARLY_SEASON_GAME_THRESHOLD

    note_de_base = compute_note_de_base(team, is_home, in_early_season)
    injury_penalty = compute_injury_penalty(db, team, settings)
    calendar = compute_calendar_penalty(db, team, game_date, settings)
    draft_bonus = compute_draft_bonus(db, team, settings) if in_early_season else 0.0
    if in_early_season:
        prev_season = previous_season_label(season)
        transfer_adjustment = (
            compute_transfer_bonus(db, team, settings, prev_season)
            - compute_transfer_malus(db, team, settings, prev_season)
        ) * settings.transfer_impact_multiplier
    else:
        transfer_adjustment = 0.0
    questionable_players = get_questionable_players(db, team, settings)

    final_note = (
        (note_de_base * settings.base_note_multiplier)
        - (injury_penalty * settings.per_impact_multiplier)
        - calendar["penalty"]
        + draft_bonus
        + transfer_adjustment
    )

    return TeamNoteBreakdown(
        team_id=team.id,
        team_name=team.name,
        is_home=is_home,
        games_played_this_season=games_played,
        in_early_season=in_early_season,
        note_de_base=note_de_base,
        injury_penalty=injury_penalty,
        is_back_to_back=calendar["is_back_to_back"],
        is_three_in_four=calendar["is_three_in_four"],
        calendar_penalty=calendar["penalty"],
        draft_bonus=draft_bonus,
        transfer_adjustment=transfer_adjustment,
        final_note=final_note,
        questionable_players=questionable_players,
    )


def _reliability_level(gap: float, settings: Settings) -> ReliabilityLevel:
    if gap >= settings.reliability_threshold_high:
        return ReliabilityLevel.FORTE
    if gap >= settings.reliability_threshold_low:
        return ReliabilityLevel.MOYENNE
    return ReliabilityLevel.FAIBLE


def compute_matchup(db: Session, game: Game, settings: Settings) -> MatchupResult:
    game_date = game.game_date.date() if hasattr(game.game_date, "date") else game.game_date

    home = compute_team_note(db, game.home_team, game_date, game.season, is_home=True, settings=settings)
    away = compute_team_note(db, game.away_team, game_date, game.season, is_home=False, settings=settings)

    spread = home.final_note - away.final_note
    predicted_winner_team_id = game.home_team_id if spread >= 0 else game.away_team_id
    reliability = _reliability_level(abs(spread), settings)

    return MatchupResult(
        game_id=game.id,
        home=home,
        away=away,
        spread=spread,
        predicted_winner_team_id=predicted_winner_team_id,
        reliability=reliability,
    )


def _breakdown_to_dict(breakdown: TeamNoteBreakdown) -> dict:
    return {
        "team_id": breakdown.team_id,
        "team_name": breakdown.team_name,
        "is_home": breakdown.is_home,
        "games_played_this_season": breakdown.games_played_this_season,
        "in_early_season": breakdown.in_early_season,
        "note_de_base": breakdown.note_de_base,
        "injury_penalty": breakdown.injury_penalty,
        "is_back_to_back": breakdown.is_back_to_back,
        "is_three_in_four": breakdown.is_three_in_four,
        "calendar_penalty": breakdown.calendar_penalty,
        "draft_bonus": breakdown.draft_bonus,
        "transfer_adjustment": breakdown.transfer_adjustment,
        "final_note": breakdown.final_note,
        "questionable_players": [
            {"name": p.name, "per": p.per, "reason": p.reason} for p in breakdown.questionable_players
        ],
    }


def save_prediction(db: Session, game: Game, settings: Settings) -> Prediction:
    result = compute_matchup(db, game, settings)

    prediction = db.query(Prediction).filter(Prediction.game_id == game.id).one_or_none()
    if prediction is None:
        prediction = Prediction(game_id=game.id)
        db.add(prediction)

    prediction.home_team_note = result.home.final_note
    prediction.away_team_note = result.away.final_note
    prediction.predicted_winner_team_id = result.predicted_winner_team_id
    prediction.spread = result.spread
    prediction.reliability = result.reliability
    prediction.breakdown = {
        "home": _breakdown_to_dict(result.home),
        "away": _breakdown_to_dict(result.away),
    }

    db.flush()
    return prediction
