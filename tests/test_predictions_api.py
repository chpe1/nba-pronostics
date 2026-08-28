from datetime import date, datetime, timedelta

from app.models import Game, GameStatus, InjuryStatus, Player, Prediction, ReliabilityLevel, Settings, Team
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


# --- GET /api/predictions/by-team/{team_id} (diagnostic par équipe) --------


def test_predictions_by_team_requires_authentication(client):
    assert client.get("/api/predictions/by-team/1").status_code == 401


def test_predictions_by_team_empty_when_no_predictions_yet(client, db_session, auth_headers):
    home, _away = _teams(db_session)

    response = client.get(f"/api/predictions/by-team/{home.id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == []


def test_predictions_by_team_returns_games_for_home_and_away(client, db_session, auth_headers):
    home, away = _teams(db_session)
    other = Team(
        name="Miami Heat", abbreviation="MIA",
        win_pct_home=0.5, win_pct_away=0.5, win_pct_home_prev_season=0.5, win_pct_away_prev_season=0.5,
    )
    db_session.add(other)
    db_session.flush()

    game_date = current_nba_date()
    game = _game(db_session, home, away, game_date)
    client.post("/api/predictions/recalculate", params={"date": game_date.isoformat()}, headers=auth_headers)

    for team_id in (home.id, away.id):
        response = client.get(f"/api/predictions/by-team/{team_id}", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["id"] == game.id
        assert body[0]["prediction"] is not None
        assert "absent_players" in body[0]["prediction"]["breakdown"]["home"]

    # Une équipe qui ne joue pas ce match n'a rien à afficher.
    response = client.get(f"/api/predictions/by-team/{other.id}", headers=auth_headers)
    assert response.json() == []


# --- POST /api/predictions/simulate (simulateur ponctuel) ------------------


def test_simulate_requires_authentication(client):
    assert client.post("/api/predictions/simulate", json={"game_id": 1}).status_code == 401


def test_simulate_returns_404_for_unknown_game(client, auth_headers):
    response = client.post("/api/predictions/simulate", json={"game_id": 999}, headers=auth_headers)
    assert response.status_code == 404


def test_simulate_with_no_overrides_matches_real_settings(client, db_session, auth_headers):
    home, away = _teams(db_session)
    game_date = current_nba_date()
    game = _game(db_session, home, away, game_date)

    real = client.post("/api/predictions/recalculate", params={"date": game_date.isoformat()}, headers=auth_headers)
    real_body = real.json()[0]

    simulated = client.post("/api/predictions/simulate", json={"game_id": game.id}, headers=auth_headers)
    simulated_body = simulated.json()

    assert simulated_body["spread"] == real_body["spread"]
    assert simulated_body["predicted_winner_team_id"] == real_body["predicted_winner_team_id"]


def test_simulate_override_changes_result_without_persisting_anything(client, db_session, auth_headers):
    home, away = _teams(db_session)
    game_date = current_nba_date()
    game = _game(db_session, home, away, game_date)
    db_session.add(
        Player(
            name="Home Star", team_id=home.id, per=20.0, mpg=30.0,
            games_played_this_season=20, injury_status=InjuryStatus.OUT,
        )
    )
    db_session.flush()

    # Un premier appel crée la ligne Settings par défaut (mpg_threshold=15.0).
    baseline = client.post("/api/predictions/simulate", json={"game_id": game.id}, headers=auth_headers).json()
    assert baseline["home"]["injury_penalty"] == 20.0  # le joueur OUT compte (mpg 30 > seuil 15)
    assert len(baseline["home"]["absent_players"]) == 1
    assert baseline["home"]["absent_players"][0]["name"] == "Home Star"

    # Seuil MPG relevé au-dessus de 30 : le joueur OUT est écarté du calcul.
    overridden = client.post(
        "/api/predictions/simulate",
        json={"game_id": game.id, "overrides": {"mpg_threshold": 35.0}},
        headers=auth_headers,
    ).json()
    assert overridden["home"]["injury_penalty"] == 0.0
    assert overridden["home"]["absent_players"] == []

    # Rien n'a été écrit en base : la vraie ligne Settings garde sa valeur par défaut...
    settings = db_session.query(Settings).one()
    assert settings.mpg_threshold == 15.0
    # ...et aucune Prediction n'a été créée (seul /simulate a été appelé, jamais /recalculate).
    assert db_session.query(Prediction).filter(Prediction.game_id == game.id).count() == 0
