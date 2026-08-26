from datetime import date, datetime, timedelta

from app.models import Game, GameStatus, Prediction, ReliabilityLevel, Team
from app.services.nba_calendar import current_nba_date

SEASON = "2025-2026"


def _teams(db_session) -> tuple[Team, Team]:
    home = Team(
        name="Boston Celtics",
        abbreviation="BOS",
        win_pct_home=0.8,
        win_pct_away=0.5,
        win_pct_home_prev_season=0.7,
        win_pct_away_prev_season=0.4,
    )
    away = Team(
        name="Los Angeles Lakers",
        abbreviation="LAL",
        win_pct_home=0.6,
        win_pct_away=0.3,
        win_pct_home_prev_season=0.5,
        win_pct_away_prev_season=0.2,
    )
    db_session.add_all([home, away])
    db_session.flush()
    return home, away


def _game(db_session, home: Team, away: Team, game_date: date) -> Game:
    game = Game(
        season=SEASON,
        game_date=datetime.combine(game_date, datetime.min.time()).replace(hour=19),
        home_team_id=home.id,
        away_team_id=away.id,
        status=GameStatus.SCHEDULED,
    )
    db_session.add(game)
    db_session.flush()
    return game


def test_today_predictions_is_public(client, db_session):
    home, away = _teams(db_session)
    game_date = current_nba_date()
    _game(db_session, home, away, game_date)

    response = client.get("/api/predictions/today")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["prediction"] is None  # aucun recalcul déclenché par le GET
    assert body[0]["home_team_name"] == "Boston Celtics"
    assert body[0]["away_team_abbreviation"] == "LAL"


def test_today_predictions_includes_recent_record(client, db_session):
    home, away = _teams(db_session)
    game_date = current_nba_date()
    # Un match précédent gagné par home (donc perdu par away).
    prior = _game(db_session, home, away, game_date - timedelta(days=3))
    prior.status = GameStatus.FINISHED
    prior.home_score = 100
    prior.away_score = 90
    db_session.flush()

    _game(db_session, home, away, game_date)

    response = client.get("/api/predictions/today")
    body = [g for g in response.json() if g["status"] == "scheduled"][0]
    assert body["home_team_recent_record"] == {"wins": 1, "losses": 0, "games_considered": 1}
    assert body["away_team_recent_record"] == {"wins": 0, "losses": 1, "games_considered": 1}


def test_today_predictions_includes_existing_prediction(client, db_session):
    home, away = _teams(db_session)
    game = _game(db_session, home, away, current_nba_date())
    db_session.add(
        Prediction(
            game_id=game.id,
            home_team_note=0.7,
            away_team_note=0.4,
            predicted_winner_team_id=home.id,
            spread=0.3,
            reliability=ReliabilityLevel.FAIBLE,
            breakdown={},
        )
    )
    db_session.commit()

    response = client.get("/api/predictions/today")
    body = response.json()
    assert body[0]["prediction"] is not None
    assert body[0]["prediction"]["predicted_winner_team_id"] == home.id


def test_recalculate_requires_authentication(client):
    assert client.post("/api/predictions/recalculate").status_code == 401


def test_recalculate_creates_predictions_for_the_date(client, db_session, auth_headers):
    home, away = _teams(db_session)
    game_date = current_nba_date()
    game = _game(db_session, home, away, game_date)

    response = client.post(
        "/api/predictions/recalculate", params={"date": game_date.isoformat()}, headers=auth_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["game_id"] == game.id
    assert db_session.query(Prediction).filter(Prediction.game_id == game.id).count() == 1


def test_recalculate_upserts_without_duplicating(client, db_session, auth_headers):
    home, away = _teams(db_session)
    game_date = current_nba_date()
    game = _game(db_session, home, away, game_date)

    client.post("/api/predictions/recalculate", params={"date": game_date.isoformat()}, headers=auth_headers)
    client.post("/api/predictions/recalculate", params={"date": game_date.isoformat()}, headers=auth_headers)

    assert db_session.query(Prediction).filter(Prediction.game_id == game.id).count() == 1


def test_recalculate_ignores_games_on_other_dates(client, db_session, auth_headers):
    home, away = _teams(db_session)
    _game(db_session, home, away, date(2020, 1, 1))

    response = client.post(
        "/api/predictions/recalculate", params={"date": current_nba_date().isoformat()}, headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json() == []
