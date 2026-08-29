from datetime import date, datetime, timedelta

from app.models import Game, GameStatus, Prediction, ReliabilityLevel, Team

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


def test_list_games_is_public(client, db_session):
    home, away = _teams(db_session)
    game_date = date.today()
    _game(db_session, home, away, game_date)

    response = client.get("/api/games", params={"date": game_date.isoformat()})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["home_team_name"] == "Boston Celtics"
    assert body[0]["manually_overridden"] is False


def test_update_game_requires_authentication(client, db_session):
    home, away = _teams(db_session)
    game = _game(db_session, home, away, date.today())

    response = client.patch(f"/api/games/{game.id}", json={"home_score": 100})
    assert response.status_code == 401


def test_update_game_unknown_id_returns_404(client, auth_headers):
    response = client.patch("/api/games/999999", json={"home_score": 100}, headers=auth_headers)
    assert response.status_code == 404


def test_update_game_reschedule_only_does_not_lock_out_sync(client, db_session, auth_headers):
    """Scénario demandé explicitement : correction de la date d'un match
    reporté (pas encore joué, aucun score) doit pouvoir laisser
    manually_overridden=False si le frontend l'envoie explicitement --
    le match reste éligible à un futur sync automatique de son score."""
    home, away = _teams(db_session)
    game = _game(db_session, home, away, date.today())
    new_date = datetime.combine(date.today() + timedelta(days=2), datetime.min.time()).replace(hour=20)

    response = client.patch(
        f"/api/games/{game.id}",
        json={"game_date": new_date.isoformat(), "manually_overridden": False},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["manually_overridden"] is False
    db_session.refresh(game)
    assert game.manually_overridden is False
    assert game.game_date == new_date


def test_update_game_manual_score_locks_out_sync_when_flagged(client, db_session, auth_headers):
    home, away = _teams(db_session)
    game = _game(db_session, home, away, date.today())

    response = client.patch(
        f"/api/games/{game.id}",
        json={"home_score": 101, "away_score": 98, "manually_overridden": True},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["manually_overridden"] is True
    assert body["status"] == "finished"
    assert body["home_score"] == 101
    assert body["away_score"] == 98


def test_update_game_scores_without_status_auto_finishes(client, db_session, auth_headers):
    home, away = _teams(db_session)
    game = _game(db_session, home, away, date.today())

    response = client.patch(
        f"/api/games/{game.id}",
        json={"home_score": 110, "away_score": 105},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "finished"


def test_update_game_without_manually_overridden_field_leaves_existing_value(client, db_session, auth_headers):
    home, away = _teams(db_session)
    game = _game(db_session, home, away, date.today())
    game.manually_overridden = True
    db_session.flush()

    response = client.patch(
        f"/api/games/{game.id}",
        json={"home_score": 100, "away_score": 90},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["manually_overridden"] is True


# --- Garde-fou anti double-booking (point 2, retour d'usage réel) ----------


def test_update_game_reschedule_rejects_home_team_double_booking(client, db_session, auth_headers):
    """Un report qui ferait jouer l'équipe à domicile un deuxième match le
    même jour doit être refusé (409), pas accepté silencieusement."""
    home, away = _teams(db_session)
    third = Team(name="Miami Heat", abbreviation="MIA")
    db_session.add(third)
    db_session.flush()

    target_date = date.today() + timedelta(days=5)
    # Match existant : home (Celtics) reçoit déjà Miami ce jour-là.
    _game(db_session, home, third, target_date)
    # Match à reporter : Celtics @ Lakers, actuellement un autre jour.
    game = _game(db_session, home, away, date.today())

    new_date = datetime.combine(target_date, datetime.min.time()).replace(hour=20)
    response = client.patch(
        f"/api/games/{game.id}",
        json={"game_date": new_date.isoformat()},
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert "Boston Celtics" in response.json()["detail"]
    db_session.refresh(game)
    assert game.game_date.date() == date.today()  # inchangé


def test_update_game_reschedule_rejects_away_team_double_booking(client, db_session, auth_headers):
    """Même contrôle côté équipe à l'extérieur."""
    home, away = _teams(db_session)
    third = Team(name="Miami Heat", abbreviation="MIA")
    db_session.add(third)
    db_session.flush()

    target_date = date.today() + timedelta(days=5)
    # Match existant : away (Lakers) joue déjà à l'extérieur chez Miami ce jour-là.
    _game(db_session, third, away, target_date)
    game = _game(db_session, home, away, date.today())

    new_date = datetime.combine(target_date, datetime.min.time()).replace(hour=20)
    response = client.patch(
        f"/api/games/{game.id}",
        json={"game_date": new_date.isoformat()},
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert "Los Angeles Lakers" in response.json()["detail"]


def test_update_game_reschedule_to_free_date_succeeds(client, db_session, auth_headers):
    home, away = _teams(db_session)
    game = _game(db_session, home, away, date.today())
    new_date = datetime.combine(date.today() + timedelta(days=5), datetime.min.time()).replace(hour=20)

    response = client.patch(
        f"/api/games/{game.id}",
        json={"game_date": new_date.isoformat()},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["game_date"] == new_date.isoformat()


def test_update_game_reschedule_excludes_itself_from_conflict_check(client, db_session, auth_headers):
    """Changer seulement l'heure (même jour) ne doit jamais se heurter au
    match lui-même dans la vérification de conflit."""
    home, away = _teams(db_session)
    game = _game(db_session, home, away, date.today())
    new_time = datetime.combine(date.today(), datetime.min.time()).replace(hour=21, minute=30)

    response = client.patch(
        f"/api/games/{game.id}",
        json={"game_date": new_time.isoformat()},
        headers=auth_headers,
    )

    assert response.status_code == 200


# --- DELETE /api/games/{id} (suppression manuelle) --------------------------


def test_delete_game_requires_authentication(client, db_session):
    home, away = _teams(db_session)
    game = _game(db_session, home, away, date.today())
    assert client.delete(f"/api/games/{game.id}").status_code == 401


def test_delete_game_returns_404_for_unknown_id(client, auth_headers):
    response = client.delete("/api/games/999999", headers=auth_headers)
    assert response.status_code == 404


def test_delete_game_removes_it(client, db_session, auth_headers):
    home, away = _teams(db_session)
    game = _game(db_session, home, away, date.today())

    response = client.delete(f"/api/games/{game.id}", headers=auth_headers)

    assert response.status_code == 204
    assert db_session.get(Game, game.id) is None


def test_delete_game_also_removes_its_prediction(client, db_session, auth_headers):
    """Prediction.game_id référence games.id (FK, PRAGMA foreign_keys=ON) --
    supprimer le match échouerait si son pronostic n'était pas nettoyé
    d'abord (comportement en cascade explicite, pas une erreur bloquante)."""
    home, away = _teams(db_session)
    game = _game(db_session, home, away, date.today())
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

    response = client.delete(f"/api/games/{game.id}", headers=auth_headers)

    assert response.status_code == 204
    assert db_session.get(Game, game.id) is None
    assert db_session.query(Prediction).filter(Prediction.game_id == game.id).count() == 0


def test_delete_game_without_prediction_does_not_error(client, db_session, auth_headers):
    """Cas normal (aucun pronostic calculé pour ce match) -- ne doit pas
    planter sur l'absence de Prediction à nettoyer."""
    home, away = _teams(db_session)
    game = _game(db_session, home, away, date.today())
    assert db_session.query(Prediction).filter(Prediction.game_id == game.id).count() == 0

    response = client.delete(f"/api/games/{game.id}", headers=auth_headers)
    assert response.status_code == 204
