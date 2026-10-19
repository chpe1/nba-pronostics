"""Étape 2 du chantier des agents libres (Décision d'architecture n°39) : plus rien ne
plante quand un joueur n'a pas d'équipe (`Player.team_id` NULL).

On ne crée AUCUN agent libre par un chemin du produit (aucun détachement n'existe
encore) : ces tests posent la ligne directement en base de test, pour vérifier que le
reste de l'application la supporte."""
import io
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.models import InjuryStatus, Player, PreviousSeasonPlayerStat, Settings, Team
from app.services import injury_report_runner
from app.services.injury_report_fetcher import FetchedReport
from app.services.pronostic_calculator import (
    _relevant_players,
    compute_draft_bonus,
    compute_injury_penalty,
    compute_team_note,
    compute_transfer_bonus,
    compute_transfer_malus,
)

PREV = "2025-2026"
NY = ZoneInfo("America/New_York")
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def league(db_session):
    """BOS (un titulaire, un rookie drafté), LAL, et trois agents libres :
    - « Departed Star » : ligne N-1 BOS (PER 20, 30 MPG), OUT, donc un départ de BOS ;
    - « Free Rookie »   : draft_pick 1 (8 points de barème) ;
    - « Other Free Agent » : ligne N-1 LAL, sans lien avec BOS."""
    settings = Settings(
        current_season="2026-2027",
        mpg_threshold=15.0,
        transfer_impact_multiplier=0.4,
        draft_bonus_config={"1": 8.0, "2": 7.0},
    )
    bos = Team(name="Boston Celtics", abbreviation="BOS")
    lal = Team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add_all([settings, bos, lal])
    db_session.flush()

    starter = Player(name="Jayson Tatum", team_id=bos.id, per=24.0, mpg=36.0, games_played_this_season=0)
    rookie = Player(name="BOS Rookie", team_id=bos.id, draft_pick=2)
    departed = Player(name="Departed Star", team_id=None, per=25.0, mpg=30.0, injury_status=InjuryStatus.OUT)
    free_rookie = Player(name="Free Rookie", team_id=None, draft_pick=1)
    other = Player(name="Other Free Agent", team_id=None)
    db_session.add_all([starter, rookie, departed, free_rookie, other])
    db_session.add_all(
        [
            PreviousSeasonPlayerStat(season=PREV, player_name="Jayson Tatum", team_abbreviation="BOS", per=24.0, mpg=36.0),
            PreviousSeasonPlayerStat(season=PREV, player_name="Departed Star", team_abbreviation="BOS", per=20.0, mpg=30.0),
            PreviousSeasonPlayerStat(season=PREV, player_name="Other Free Agent", team_abbreviation="LAL", per=18.0, mpg=28.0),
        ]
    )
    db_session.commit()
    return {"settings": settings, "bos": bos, "lal": lal, "departed": departed, "free_rookie": free_rookie, "other": other}


# --- API joueurs ----------------------------------------------------------------


def test_list_players_answers_with_a_free_agent_in_base(client, auth_headers, league):
    response = client.get("/api/players", headers=auth_headers)
    assert response.status_code == 200
    by_name = {p["name"]: p for p in response.json()}
    assert by_name["Departed Star"]["team_id"] is None
    assert by_name["Departed Star"]["team_name"] is None
    assert by_name["Departed Star"]["team_abbreviation"] is None
    assert by_name["Jayson Tatum"]["team_abbreviation"] == "BOS"


def test_free_agent_filter_finds_only_free_agents(client, auth_headers, league):
    response = client.get("/api/players", params={"free_agent": True}, headers=auth_headers)
    assert response.status_code == 200
    assert {p["name"] for p in response.json()} == {"Departed Star", "Free Rookie", "Other Free Agent"}


def test_team_filter_never_returns_free_agents(client, auth_headers, league):
    response = client.get("/api/players", params={"team_id": league["bos"].id}, headers=auth_headers)
    assert {p["name"] for p in response.json()} == {"Jayson Tatum", "BOS Rookie"}


def test_free_agent_and_team_filters_are_exclusive(client, auth_headers, league):
    response = client.get("/api/players", params={"free_agent": True, "team_id": league["bos"].id}, headers=auth_headers)
    assert response.status_code == 400


def test_patch_can_replace_a_free_agent_on_a_team_but_never_detach(client, auth_headers, db_session, league):
    free_agent = league["other"]
    detach = client.patch(f"/api/players/{free_agent.id}", json={"team_id": None}, headers=auth_headers)
    assert detach.status_code == 400  # aucun détachement par cette route (Décision n°39)
    assert "agent libre" in detach.json()["detail"]

    placed = client.patch(f"/api/players/{free_agent.id}", json={"team_id": league["lal"].id}, headers=auth_headers)
    assert placed.status_code == 200
    assert placed.json()["team_abbreviation"] == "LAL"


def test_patch_other_fields_of_a_free_agent_works(client, auth_headers, league):
    response = client.patch(f"/api/players/{league['other'].id}", json={"per": 12.5}, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["per"] == 12.5 and response.json()["team_id"] is None


# --- moteur de calcul -----------------------------------------------------------


def test_engine_excludes_free_agent_from_roster_and_absents(db_session, league):
    relevant = _relevant_players(db_session, league["bos"], PREV, league["settings"])
    assert {p.name for p, _per, _mpg in relevant} == {"Jayson Tatum"}  # ni « Departed Star » (OUT, 30 MPG) ni les autres
    assert compute_injury_penalty(db_session, league["bos"], league["settings"], PREV) == 0.0  # Tatum est sain


def test_engine_excludes_free_agent_from_draft_bonus(db_session, league):
    # Seul le rookie de BOS (rang 2 = 7 points) compte ; « Free Rookie » (rang 1 = 8 points) n'a pas d'équipe.
    assert compute_draft_bonus(db_session, league["bos"], league["settings"]) == 7.0
    assert compute_draft_bonus(db_session, league["lal"], league["settings"]) == 0.0


def test_engine_excludes_free_agent_from_transfer_bonus(db_session, league):
    # « Other Free Agent » (N-1 : LAL, 28 MPG) n'est arrivé dans aucune équipe : aucun bonus, ni pour BOS ni pour LAL.
    assert compute_transfer_bonus(db_session, league["bos"], league["settings"], PREV) == 0.0
    assert compute_transfer_bonus(db_session, league["lal"], league["settings"], PREV) == 0.0


def test_engine_counts_free_agent_as_a_departure_for_its_previous_team(db_session, league):
    # « Departed Star » (N-1 : BOS, PER 20, 30 MPG), toujours actif mais sans équipe : un départ de BOS.
    assert compute_transfer_malus(db_session, league["bos"], league["settings"], PREV) == 20.0
    # « Other Free Agent » (N-1 : LAL, PER 18) : un départ de LAL.
    assert compute_transfer_malus(db_session, league["lal"], league["settings"], PREV) == 18.0


def test_team_note_applies_the_departure_malus_only_through_the_early_season_adjustment(db_session, league):
    from datetime import date

    note = compute_team_note(db_session, league["bos"], date(2026, 10, 20), "2026-2027", True, league["settings"])
    assert note.in_early_season is True
    assert note.draft_bonus == 7.0
    assert note.transfer_adjustment == pytest.approx((0.0 - 20.0) * 0.4)  # bonus 0, malus 20, multiplicateur 0,4


def test_inactive_free_agent_is_no_longer_counted_as_a_departure(db_session, league):
    """Raison pour laquelle l'agent libre doit rester is_active (Décision n°39) : inactif, il
    devient introuvable par find_active_player_by_name et son départ disparaît du malus."""
    league["departed"].is_active = False
    db_session.commit()
    assert compute_transfer_malus(db_session, league["bos"], league["settings"], PREV) == 0.0


# --- import d'effectif ----------------------------------------------------------


def _roster_csv(rows) -> bytes:
    return ("\n".join(["Player,Team"] + [f"{n},{t}" for n, t in rows]) + "\n").encode("utf-8")


def _post(client, auth_headers, content, dry_run):
    return client.post(
        "/api/imports/stats",
        params={"dry_run": dry_run},
        files={"file": ("roster.csv", io.BytesIO(content), "text/csv")},
        headers=auth_headers,
    )


def test_roster_preview_does_not_crash_and_does_not_repropose_free_agents(client, auth_headers, db_session, league):
    db_session.add(Player(name="Gone Veteran", team_id=league["bos"].id))
    db_session.commit()
    # Le fichier ne contient ni « Gone Veteran » ni aucun des agents libres.
    response = _post(client, auth_headers, _roster_csv([("Jayson Tatum", "BOS"), ("BOS Rookie", "BOS")]), True)
    assert response.status_code == 200
    body = response.json()
    assert body["orphans"] == ["Gone Veteran"]  # les trois agents libres ne sont PAS reproposés
    assert body["moved"] == []


def test_roster_preview_shows_a_free_agent_present_in_the_file_as_moved_from_free_agent(
    client, auth_headers, db_session, league
):
    response = _post(client, auth_headers, _roster_csv([("Departed Star", "LAL")]), True)
    assert response.status_code == 200
    moved = response.json()["moved"]
    assert moved == [{"name": "Departed Star", "from_team": "agent libre", "to_team": "LAL"}]


def test_roster_confirmed_import_replaces_a_free_agent_without_duplicating(client, auth_headers, db_session, league):
    response = _post(client, auth_headers, _roster_csv([("Departed Star", "LAL")]), False)
    assert response.status_code == 200
    db_session.expire_all()
    rows = db_session.query(Player).filter(Player.name == "Departed Star").all()
    assert len(rows) == 1  # pas de doublon
    assert rows[0].team_id == league["lal"].id  # replacé
    assert rows[0].injury_status == InjuryStatus.OUT and rows[0].per == 25.0  # historique conservé


# --- bouton blessures -----------------------------------------------------------


def test_injury_button_does_not_crash_on_a_name_matching_a_free_agent(client, auth_headers, db_session, league, monkeypatch):
    """« Bryant,Thomas » (CLE dans le rapport) existe en base comme agent libre : avant correction,
    team_abbreviation[None] levait une KeyError."""
    db_session.add(Team(name="Cleveland Cavaliers", abbreviation="CLE"))
    db_session.add(Player(name="Thomas Bryant", team_id=None))
    db_session.commit()
    monkeypatch.setattr(
        injury_report_runner,
        "fetch_latest_report",
        lambda client=None, now=None: FetchedReport(
            content=(FIXTURES / "Injury-Report_2026-04-08_03_45PM.pdf").read_bytes(),
            url="https://example.invalid/report.pdf",
            report_time=datetime(2026, 4, 8, 15, 45, tzinfo=NY),
        ),
    )
    response = client.post("/api/injuries/refresh", headers=auth_headers)
    assert response.status_code == 200
    unmatched = {e["player_name_raw"]: e for e in response.json()["unmatched"]}
    assert unmatched["Bryant,Thomas"]["team_abbreviation"] == "CLE"
    assert unmatched["Bryant,Thomas"]["exists_in_database_on_teams"] == ["agent libre"]
