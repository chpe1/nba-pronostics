from app.models import Team


def test_list_teams_is_public_and_sorted_by_name(client, db_session):
    db_session.add_all(
        [
            Team(name="Los Angeles Lakers", abbreviation="LAL"),
            Team(name="Boston Celtics", abbreviation="BOS"),
        ]
    )
    db_session.commit()

    response = client.get("/api/teams")
    assert response.status_code == 200
    body = response.json()
    assert [t["name"] for t in body] == ["Boston Celtics", "Los Angeles Lakers"]
    assert body[0]["abbreviation"] == "BOS"


def test_list_teams_includes_full_detail(client, db_session):
    """Depuis la correction manuelle d'équipe (Admin > Équipes) : la réponse
    inclut les win_pct, pas seulement id/name/abbreviation."""
    db_session.add(Team(name="Boston Celtics", abbreviation="BOS", win_pct_home=0.7, win_pct_away=0.5))
    db_session.commit()

    body = client.get("/api/teams").json()

    assert body[0]["win_pct_home"] == 0.7
    assert body[0]["win_pct_away"] == 0.5


# --- PATCH /api/teams/{team_id} (correction manuelle admin) -----------------


def test_update_team_requires_authentication(client, db_session):
    team = Team(name="Boston Celtics", abbreviation="BOS")
    db_session.add(team)
    db_session.commit()

    response = client.patch(f"/api/teams/{team.id}", json={"win_pct_home": 0.6})
    assert response.status_code == 401


def test_update_team_returns_404_for_unknown_id(client, auth_headers):
    response = client.patch("/api/teams/999999", json={"win_pct_home": 0.6}, headers=auth_headers)
    assert response.status_code == 404


def test_update_team_applies_partial_changes(client, db_session, auth_headers):
    team = Team(name="Boston Celtics", abbreviation="BOS", win_pct_home=0.5, win_pct_away=0.4)
    db_session.add(team)
    db_session.commit()

    response = client.patch(
        f"/api/teams/{team.id}",
        json={"win_pct_home": 0.75, "conference": "Est"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["win_pct_home"] == 0.75
    assert body["conference"] == "Est"
    assert body["win_pct_away"] == 0.4  # champ non fourni -> inchangé

    db_session.expire_all()
    assert db_session.get(Team, team.id).win_pct_home == 0.75


def test_update_team_rejects_name_collision_with_another_team(client, db_session, auth_headers):
    db_session.add_all(
        [
            Team(name="Boston Celtics", abbreviation="BOS"),
            Team(name="Los Angeles Lakers", abbreviation="LAL"),
        ]
    )
    db_session.commit()
    lakers = db_session.query(Team).filter(Team.abbreviation == "LAL").one()

    response = client.patch(
        f"/api/teams/{lakers.id}", json={"name": "Boston Celtics"}, headers=auth_headers
    )
    assert response.status_code == 409


def test_update_team_rejects_abbreviation_collision_with_another_team(client, db_session, auth_headers):
    db_session.add_all(
        [
            Team(name="Boston Celtics", abbreviation="BOS"),
            Team(name="Los Angeles Lakers", abbreviation="LAL"),
        ]
    )
    db_session.commit()
    lakers = db_session.query(Team).filter(Team.abbreviation == "LAL").one()

    response = client.patch(
        f"/api/teams/{lakers.id}", json={"abbreviation": "BOS"}, headers=auth_headers
    )
    assert response.status_code == 409


def test_update_team_allows_keeping_its_own_name_and_abbreviation(client, db_session, auth_headers):
    """Un PATCH qui ne change qu'un win_pct, sans toucher name/abbreviation,
    ne doit jamais se heurter au garde-fou 409 contre lui-même."""
    team = Team(name="Boston Celtics", abbreviation="BOS")
    db_session.add(team)
    db_session.commit()

    response = client.patch(
        f"/api/teams/{team.id}",
        json={"name": "Boston Celtics", "win_pct_home": 0.6},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["win_pct_home"] == 0.6
