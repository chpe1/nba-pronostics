"""Jeu de données de simulation réutilisable pour les tests de calibrage
(Étape 6) : 6 équipes fictives couvrant un spectre de force réaliste, des
effectifs aux PER/MPG variés, et un calendrier construit pour garantir des
situations B2B / 3-en-4 / repos et une équipe en "début de saison" déterministes
à `TARGET_DATE`.

Noms de joueurs volontairement génériques ("BOS Player 1"...), comme pour les
fixtures CSV de l'Étape 2 — aucune donnée réelle, seuls les PER/MPG/dates
comptent pour les besoins de calibrage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Game, GameStatus, InjuryStatus, Player, Team

SIMULATED_SEASON = "2025-2026"
TARGET_DATE = date(2026, 1, 15)

# Équipes utilisées pour le "padding" de matchs (tout le monde sauf CHA, qui
# doit rester délibérément sous la barre des 10 matchs joués).
REGULAR_TEAM_ABBRS = ["BOS", "DEN", "MIA", "CHI", "DET"]

TEAM_DEFS: dict[str, dict] = {
    "BOS": dict(
        name="Boston Celtics",
        win_pct_home=0.80, win_pct_away=0.65,
        win_pct_home_prev_season=0.75, win_pct_away_prev_season=0.60,
    ),
    "DEN": dict(
        name="Denver Nuggets",
        win_pct_home=0.78, win_pct_away=0.62,
        win_pct_home_prev_season=0.70, win_pct_away_prev_season=0.55,
    ),
    "MIA": dict(
        name="Miami Heat",
        win_pct_home=0.55, win_pct_away=0.45,
        win_pct_home_prev_season=0.50, win_pct_away_prev_season=0.40,
    ),
    "CHI": dict(
        name="Chicago Bulls",
        win_pct_home=0.48, win_pct_away=0.38,
        win_pct_home_prev_season=0.45, win_pct_away_prev_season=0.35,
    ),
    "DET": dict(
        name="Detroit Pistons",
        win_pct_home=0.30, win_pct_away=0.20,
        win_pct_home_prev_season=0.25, win_pct_away_prev_season=0.15,
    ),
    # "Début de saison" : win_pct courant très différent de N-1, et seulement
    # 3 matchs joués cette saison (voir pad_games_played, volontairement exclue).
    "CHA": dict(
        name="Charlotte Hornets",
        win_pct_home=0.28, win_pct_away=0.18,
        win_pct_home_prev_season=0.55, win_pct_away_prev_season=0.45,
    ),
    # Adversaires "jetables" : ne servent qu'à donner à MIA/CHI/CHA leurs
    # matchs de calendrier déclencheurs (B2B/3in4/début de saison), sans
    # jamais être eux-mêmes le sujet d'un scénario -- évite qu'une équipe
    # "de contrôle" (ex: DET, censée être reposée) hérite d'un match
    # incident dans la fenêtre des 3 jours en servant d'adversaire à une
    # autre équipe.
    "OPA": dict(name="Opponent Alpha", win_pct_home=0.50, win_pct_away=0.40,
                win_pct_home_prev_season=0.50, win_pct_away_prev_season=0.40),
    "OPB": dict(name="Opponent Beta", win_pct_home=0.50, win_pct_away=0.40,
                win_pct_home_prev_season=0.50, win_pct_away_prev_season=0.40),
}

# (PER, MPG) par équipe, triés du meilleur au moins bon joueur pour la lisibilité
# (le "star" est identifié par PER max, pas par position dans la liste).
ROSTER_DEFS: dict[str, list[tuple[float, float]]] = {
    "BOS": [(29.0, 36.0), (22.0, 34.0), (20.0, 28.0), (16.0, 30.0), (14.0, 22.0), (12.0, 18.0), (11.0, 20.0), (9.0, 10.0)],
    "DEN": [(30.0, 35.0), (21.0, 33.0), (17.0, 30.0), (16.0, 29.0), (15.0, 24.0), (13.0, 22.0), (10.0, 16.0), (8.0, 9.0)],
    "MIA": [(22.0, 33.0), (19.0, 32.0), (14.0, 26.0), (13.0, 25.0), (12.0, 20.0), (11.0, 22.0), (10.0, 18.0), (7.0, 7.0)],
    "CHI": [(20.0, 34.0), (18.0, 29.0), (17.0, 31.0), (15.0, 27.0), (12.0, 24.0), (11.0, 22.0), (9.0, 15.0), (8.0, 12.0)],
    "DET": [(21.0, 34.0), (16.0, 26.0), (14.0, 28.0), (13.0, 27.0), (11.0, 22.0), (10.0, 24.0), (9.0, 18.0), (6.0, 8.0)],
    "CHA": [(22.0, 32.0), (15.0, 30.0), (14.0, 29.0), (13.0, 24.0), (9.0, 20.0), (8.0, 16.0), (7.0, 14.0), (6.0, 7.0)],
}

# Recrue #1 pick ajoutée à part sur CHA (équipe "début de saison"), pour le
# scénario de bonus draft.
CHA_ROOKIE_PER = 16.0
CHA_ROOKIE_MPG = 28.0


@dataclass
class TeamRoster:
    team: Team
    star: Player  # PER le plus haut de l'effectif
    bench_player: Player  # MPG le plus bas (sous le seuil de 15)
    others: list[Player]
    rookie: Player | None = None


@dataclass
class League:
    teams: dict[str, Team]
    rosters: dict[str, TeamRoster]
    target_date: date
    back_to_back_team: str
    three_in_four_team: str
    rested_team: str
    early_season_team: str


def _finished_game(
    db: Session, home: Team, away: Team, game_date: date, home_score: int = 100, away_score: int = 90
) -> Game:
    game = Game(
        season=SIMULATED_SEASON,
        game_date=datetime.combine(game_date, datetime.min.time()),
        home_team_id=home.id,
        away_team_id=away.id,
        status=GameStatus.FINISHED,
        home_score=home_score,
        away_score=away_score,
    )
    db.add(game)
    db.flush()
    return game


def create_scheduled_game(
    db: Session, home: Team, away: Team, game_date: date = TARGET_DATE, hour: int = 19
) -> Game:
    game = Game(
        season=SIMULATED_SEASON,
        game_date=datetime.combine(game_date, datetime.min.time()).replace(hour=hour),
        home_team_id=home.id,
        away_team_id=away.id,
        status=GameStatus.SCHEDULED,
    )
    db.add(game)
    db.flush()
    return game


def create_teams(db: Session) -> dict[str, Team]:
    teams = {}
    for abbr, kwargs in TEAM_DEFS.items():
        team = Team(abbreviation=abbr, **kwargs)
        db.add(team)
        teams[abbr] = team
    db.flush()
    return teams


def create_rosters(db: Session, teams: dict[str, Team]) -> dict[str, TeamRoster]:
    rosters = {}
    for abbr, defs in ROSTER_DEFS.items():
        team = teams[abbr]
        players = []
        for i, (per, mpg) in enumerate(defs):
            player = Player(
                name=f"{abbr} Player {i + 1}",
                team_id=team.id,
                per=per,
                mpg=mpg,
                injury_status=InjuryStatus.HEALTHY,
            )
            db.add(player)
            players.append(player)
        db.flush()

        rookie = None
        if abbr == "CHA":
            rookie = Player(
                name="CHA Rookie",
                team_id=team.id,
                per=CHA_ROOKIE_PER,
                mpg=CHA_ROOKIE_MPG,
                injury_status=InjuryStatus.HEALTHY,
                draft_pick=1,
            )
            db.add(rookie)
            db.flush()

        rosters[abbr] = TeamRoster(
            team=team,
            star=max(players, key=lambda p: p.per),
            bench_player=min(players, key=lambda p: p.mpg),
            others=players,
            rookie=rookie,
        )
    return rosters


def setup_calendar_history(db: Session, teams: dict[str, Team], target_date: date) -> None:
    # MIA : Back-to-Back pur (a joué la veille contre un adversaire jetable,
    # rien d'autre dans la fenêtre des 3 jours).
    _finished_game(db, teams["MIA"], teams["OPA"], target_date - timedelta(days=1))

    # CHI : 3-matchs-en-4-nuits, ce qui inclut de fait un B2B la veille aussi
    # (sert à vérifier que seul le malus 3in4, le plus sévère, s'applique).
    _finished_game(db, teams["CHI"], teams["OPB"], target_date - timedelta(days=1))
    _finished_game(db, teams["CHI"], teams["OPA"], target_date - timedelta(days=3))

    # DET : bien reposé (dernier match hors de la fenêtre des 3 jours, contre
    # un adversaire jetable -- jamais BOS/DEN/etc. pour ne pas leur donner un
    # match incident dans la fenêtre des 3 jours par ricochet).
    _finished_game(db, teams["DET"], teams["OPB"], target_date - timedelta(days=6))

    # CHA : "début de saison" -> exactement 3 matchs joués cette saison, tous
    # bien avant target_date (hors fenêtre calendrier).
    for i in range(3):
        _finished_game(db, teams["CHA"], teams["OPA"], target_date - timedelta(days=20 + i * 3))


def pad_games_played(db: Session, teams: dict[str, Team], target_date: date, games_per_team: int = 9) -> None:
    """Porte chaque équipe "régulière" (hors CHA) à >= 10 matchs joués cette
    saison, sans jamais empiéter sur la fenêtre de calcul B2B/3in4 (3 jours)."""
    day_offset = 30
    played = {abbr: 0 for abbr in REGULAR_TEAM_ABBRS}
    i = 0
    while min(played.values()) < games_per_team:
        home_abbr = REGULAR_TEAM_ABBRS[i % len(REGULAR_TEAM_ABBRS)]
        away_abbr = REGULAR_TEAM_ABBRS[(i + 1) % len(REGULAR_TEAM_ABBRS)]
        _finished_game(db, teams[home_abbr], teams[away_abbr], target_date - timedelta(days=day_offset))
        played[home_abbr] += 1
        played[away_abbr] += 1
        day_offset += 2
        i += 1


def build_league(db: Session, target_date: date = TARGET_DATE) -> League:
    teams = create_teams(db)
    rosters = create_rosters(db, teams)
    setup_calendar_history(db, teams, target_date)
    pad_games_played(db, teams, target_date)
    return League(
        teams=teams,
        rosters=rosters,
        target_date=target_date,
        back_to_back_team="MIA",
        three_in_four_team="CHI",
        rested_team="DET",
        early_season_team="CHA",
    )


def create_full_slate(db: Session, league: League) -> list[Game]:
    """Une petite journée complète de matchs, toutes équipes confondues,
    pour le garde-fou "aucun spread aberrant" (scénario 9). Datée sur
    `league.target_date`, pas systématiquement TARGET_DATE -- cohérent avec
    la date utilisée pour construire cette League (voir build_league)."""
    pairings = [
        ("BOS", "DET"), ("DEN", "CHA"), ("MIA", "CHI"),
        ("BOS", "CHI"), ("DEN", "DET"), ("MIA", "CHA"),
    ]
    return [
        create_scheduled_game(db, league.teams[h], league.teams[a], game_date=league.target_date)
        for h, a in pairings
    ]
