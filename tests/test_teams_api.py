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
