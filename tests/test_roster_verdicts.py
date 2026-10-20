"""Étape 4 du chantier des agents libres (Décision d'architecture n°39) : trancher les lignes du
fichier sans correspondance -- verdict « recrue » ou « même joueur que <joueur de la base> » --,
et n'autoriser aucun détachement tant qu'une de ces lignes n'a pas de verdict.

Cas réel : « Ronald Holland II » (fichier NBA.com) contre « Ron Holland » (base, ligne N-1 PER 11,7)."""
import io
import json

import pytest

from app.models import Player, PreviousSeasonPlayerStat, Settings, Team
from app.services.pronostic_calculator import _effective_per_mpg

PREV = "2025-2026"
FILE = [("Starter A", "BOS"), ("Ronald Holland II", "BOS")]


@pytest.fixture()
def league(db_session):
    settings = Settings(current_season="2026-2027")
    db_session.add(settings)
    bos = Team(name="Boston Celtics", abbreviation="BOS")
    det = Team(name="Detroit Pistons", abbreviation="DET")
    db_session.add_all([bos, det])
    db_session.flush()
    a = Player(name="Starter A", team_id=bos.id)
    holland = Player(name="Ron Holland", team_id=det.id, per=0.0, mpg=0.0)  # base : « Ron Holland », DET
    gone = Player(name="Gone Veteran", team_id=bos.id)
    free = Player(name="Free Agent F", team_id=None)
    db_session.add_all([a, holland, gone, free])
    db_session.add(PreviousSeasonPlayerStat(season=PREV, player_name="Ron Holland", team_abbreviation="DET", per=11.7, mpg=19.88))
    db_session.commit()
    return {"settings": settings, "bos": bos, "det": det, "a": a, "holland": holland, "gone": gone, "free": free}


def _csv(rows) -> bytes:
    return ("\n".join(["Player,Team"] + [f"{n},{t}" for n, t in rows]) + "\n").encode("utf-8")


def _post(client, auth_headers, rows_or_bytes, dry_run=False, detach_ids=None, verdicts=None):
    content = rows_or_bytes if isinstance(rows_or_bytes, bytes) else _csv(rows_or_bytes)
    params: dict = {"dry_run": dry_run}
    if detach_ids is not None:
        params["detach_player_ids"] = detach_ids
    return client.post(
        "/api/imports/stats",
        params=params,
        data={"verdicts": json.dumps(verdicts)} if verdicts is not None else None,
        files={"file": ("roster.csv", io.BytesIO(content), "text/csv")},
        headers=auth_headers,
    )


def same(file_name, player):
    return {"file_name": file_name, "verdict": "same_player", "player_id": player.id}


def recruit(file_name):
    return {"file_name": file_name, "verdict": "recruit"}


def _unchanged(db_session, league):
    """Rien n'a été écrit : mêmes joueurs, mêmes équipes."""
    db_session.expire_all()
    assert db_session.query(Player).count() == 4
    assert db_session.get(Player, league["gone"].id).team_id == league["bos"].id
    assert db_session.get(Player, league["holland"].id).team_id == league["det"].id
    assert db_session.get(Player, league["holland"].id).name == "Ron Holland"


# --- association / recrue : comportement ---------------------------------------------------


def test_association_attaches_the_row_to_the_existing_player_without_duplicate_or_detach(client, auth_headers, db_session, league):
    response = _post(client, auth_headers, FILE, verdicts=[same("Ronald Holland II", league["holland"])])
    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.query(Player).count() == 4  # aucun doublon « Ronald Holland II »
    holland = db_session.get(Player, league["holland"].id)
    assert holland.team_id == league["bos"].id  # équipe mise à jour depuis le fichier (BOS)
    assert holland.is_active is True


def test_association_leaves_the_name_in_base_unchanged_and_the_n1_row_still_found(client, auth_headers, db_session, league):
    _post(client, auth_headers, FILE, verdicts=[same("Ronald Holland II", league["holland"])])
    db_session.expire_all()
    holland = db_session.get(Player, league["holland"].id)
    assert holland.name == "Ron Holland"  # nom en base PAS modifié
    # ... donc sa ligne N-1 (PER 11,7 / MPG 19,88) est toujours retrouvée par le moteur
    per, mpg = _effective_per_mpg(db_session, holland, PREV, db_session.query(Settings).one())
    assert (per, mpg) == (11.7, 19.88)


def test_recruit_verdict_creates_the_player(client, auth_headers, db_session, league):
    response = _post(client, auth_headers, FILE, verdicts=[recruit("Ronald Holland II")])
    assert response.status_code == 200
    db_session.expire_all()
    created = db_session.query(Player).filter(Player.name == "Ronald Holland II").one()
    assert created.team_id == league["bos"].id
    assert db_session.get(Player, league["holland"].id).team_id == league["det"].id  # l'autre n'a pas bougé
    assert db_session.query(Player).count() == 5


def test_report_says_how_many_rows_were_resolved_and_which(client, auth_headers, league):
    rows = FILE + [("New Guy", "LAL")]
    body = _post(client, auth_headers, rows, verdicts=[same("Ronald Holland II", league["holland"]), recruit("New Guy")]).json()
    assert body["resolved_rows_count"] == 2
    assert body["recruit_count"] == 1 and body["recruit_names"] == ["New Guy"]
    assert body["association_count"] == 1
    assert body["associations"] == [
        {"file_name": "Ronald Holland II", "player_id": league["holland"].id, "player_name": "Ron Holland"}
    ]
    assert body["detached_count"] == 0


def test_no_verdict_is_now_refused_when_a_row_has_no_match_and_a_player_is_absent(client, auth_headers, db_session, league):
    """Ligne sans correspondance (« Ronald Holland II ») ET joueurs absents côté base : plus de création
    silencieuse (c'était la cause du doublon) -- voir tests/test_roster_verdicts_required.py."""
    response = _post(client, auth_headers, FILE)  # ni verdict ni détachement
    assert response.status_code == 400
    assert "Ronald Holland II" in response.json()["detail"]
    _unchanged(db_session, league)


def test_an_associated_free_agent_is_replaced_on_the_team(client, auth_headers, db_session, league):
    rows = [("Starter A", "BOS"), ("Free Agent Fred", "LAL")]
    _post(client, auth_headers, rows, verdicts=[same("Free Agent Fred", league["free"])])
    db_session.expire_all()
    free = db_session.get(Player, league["free"].id)
    assert free.name == "Free Agent F" and free.team_id is not None


# --- gardes : verdicts -------------------------------------------------------------------


def test_refuses_a_verdict_on_a_row_that_has_a_match(client, auth_headers, db_session, league):
    response = _post(client, auth_headers, FILE, verdicts=[recruit("Starter A")])
    assert response.status_code == 400
    assert "n'est pas une ligne sans correspondance" in response.json()["detail"]
    _unchanged(db_session, league)


def test_refuses_a_verdict_on_a_row_absent_from_the_submitted_file(client, auth_headers, db_session, league):
    response = _post(client, auth_headers, FILE, verdicts=[recruit("Nobody Here")])
    assert response.status_code == 400
    _unchanged(db_session, league)


def test_refuses_an_association_to_a_nonexistent_player(client, auth_headers, db_session, league):
    response = _post(client, auth_headers, FILE, verdicts=[{"file_name": "Ronald Holland II", "verdict": "same_player", "player_id": 999999}])
    assert response.status_code == 400
    assert "inexistant" in response.json()["detail"]
    _unchanged(db_session, league)


def test_refuses_an_association_to_an_inactive_player(client, auth_headers, db_session, league):
    league["holland"].is_active = False
    db_session.commit()
    response = _post(client, auth_headers, FILE, verdicts=[same("Ronald Holland II", league["holland"])])
    assert response.status_code == 400
    assert "inactif" in response.json()["detail"]


def test_refuses_an_association_without_a_player(client, auth_headers, league):
    response = _post(client, auth_headers, FILE, verdicts=[{"file_name": "Ronald Holland II", "verdict": "same_player"}])
    assert response.status_code == 400


def test_refuses_two_rows_associated_to_the_same_player(client, auth_headers, db_session, league):
    rows = FILE + [("R. Holland", "BOS")]  # (« Ron Holland Jr » serait déjà rapproché : le suffixe Jr. est replié)
    response = _post(
        client, auth_headers, rows, verdicts=[same("Ronald Holland II", league["holland"]), same("R. Holland", league["holland"])]
    )
    assert response.status_code == 400
    assert "même joueur" in response.json()["detail"]
    _unchanged(db_session, league)


def test_refuses_an_association_to_a_player_already_matched_by_another_row(client, auth_headers, db_session, league):
    response = _post(client, auth_headers, FILE, verdicts=[same("Ronald Holland II", league["a"])])  # « Starter A » est déjà dans le fichier
    assert response.status_code == 400
    assert "déjà rapproché" in response.json()["detail"]
    _unchanged(db_session, league)


def test_refuses_two_verdicts_on_the_same_row(client, auth_headers, db_session, league):
    response = _post(client, auth_headers, FILE, verdicts=[recruit("Ronald Holland II"), same("Ronald Holland II", league["holland"])])
    assert response.status_code == 400
    _unchanged(db_session, league)


def test_refuses_a_recruit_verdict_that_also_designates_a_player(client, auth_headers, league):
    verdict = {"file_name": "Ronald Holland II", "verdict": "recruit", "player_id": league["holland"].id}
    assert _post(client, auth_headers, FILE, verdicts=[verdict]).status_code == 400


def test_refuses_malformed_verdicts(client, auth_headers, league):
    response = client.post(
        "/api/imports/stats",
        params={"dry_run": False},
        data={"verdicts": "ceci n'est pas du JSON"},
        files={"file": ("roster.csv", io.BytesIO(_csv(FILE)), "text/csv")},
        headers=auth_headers,
    )
    assert response.status_code == 400
    bad = _post(client, auth_headers, FILE, verdicts=[{"file_name": "X", "verdict": "peut-être"}])
    assert bad.status_code == 400


def test_refuses_verdicts_on_a_preview(client, auth_headers, league):
    assert _post(client, auth_headers, FILE, dry_run=True, verdicts=[recruit("Ronald Holland II")]).status_code == 400


# --- cœur du garde-fou : détachement ----------------------------------------------------------


def test_refuses_any_detachment_while_a_row_has_no_verdict(client, auth_headers, db_session, league):
    response = _post(client, auth_headers, FILE, detach_ids=[league["gone"].id])  # « Ronald Holland II » sans verdict
    assert response.status_code == 400
    assert "Ronald Holland II" in response.json()["detail"] and "verdict" in response.json()["detail"]
    _unchanged(db_session, league)


def test_refuses_detachment_when_only_some_rows_have_a_verdict(client, auth_headers, db_session, league):
    rows = FILE + [("New Guy", "LAL")]
    response = _post(client, auth_headers, rows, detach_ids=[league["gone"].id], verdicts=[recruit("New Guy")])
    assert response.status_code == 400
    assert "Ronald Holland II" in response.json()["detail"]
    _unchanged(db_session, league)


def test_detachment_accepted_once_every_row_has_a_verdict(client, auth_headers, db_session, league):
    response = _post(
        client, auth_headers, FILE, detach_ids=[league["gone"].id], verdicts=[same("Ronald Holland II", league["holland"])]
    )
    assert response.status_code == 200
    body = response.json()
    assert body["detached_count"] == 1 and body["detached_names"] == ["Gone Veteran"]
    assert body["association_count"] == 1
    db_session.expire_all()
    assert db_session.get(Player, league["gone"].id).team_id is None
    assert db_session.get(Player, league["holland"].id).team_id == league["bos"].id  # replacé, jamais détaché


def test_refuses_the_contradiction_association_and_detachment_of_the_same_player(client, auth_headers, db_session, league):
    response = _post(
        client,
        auth_headers,
        FILE,
        detach_ids=[league["holland"].id, league["gone"].id],
        verdicts=[same("Ronald Holland II", league["holland"])],
    )
    assert response.status_code == 400
    assert "associé" in response.json()["detail"]
    _unchanged(db_session, league)  # même « Gone Veteran » (valide) n'est pas détaché : rien n'est appliqué


def test_without_unmatched_row_detachment_works_like_step_3(client, auth_headers, db_session, league):
    response = _post(client, auth_headers, [("Starter A", "BOS"), ("Ron Holland", "DET")], detach_ids=[league["gone"].id])
    assert response.status_code == 200
    assert response.json()["detached_names"] == ["Gone Veteran"]


# --- aperçu -------------------------------------------------------------------------------------


def test_preview_exposes_association_candidates_including_free_agents(client, auth_headers, league):
    body = _post(client, auth_headers, FILE, dry_run=True).json()
    candidates = {c["name"]: c for c in body["association_candidates"]}
    assert set(candidates) == {"Ron Holland", "Gone Veteran", "Free Agent F"}
    assert candidates["Free Agent F"]["team_abbreviation"] is None
    assert candidates["Ron Holland"]["team_abbreviation"] == "DET"
    assert body["file_rows_without_match_count"] == 1
    assert body["file_rows_without_match"][0]["closest_absent_player"] == "Ron Holland"


def test_preview_exposes_row_errors_with_what_to_fix_and_blocks_detachment(client, auth_headers, league):
    content = b"Player,Team\nStarter A,BOS\nMystery Man,XXX\nOther Man,YYY\n"
    body = _post(client, auth_headers, content, dry_run=True).json()
    assert body["detachment_blocked"] is True
    assert "2 ligne(s)" in body["detachment_blocked_reason"]
    assert body["row_errors"] == [
        {"row": 3, "player_name": "Mystery Man", "team": "XXX", "message": "Équipe inconnue : 'XXX'"},
        {"row": 4, "player_name": "Other Man", "team": "YYY", "message": "Équipe inconnue : 'YYY'"},
    ]


def test_preview_without_errors_is_not_blocked(client, auth_headers, league):
    body = _post(client, auth_headers, FILE, dry_run=True).json()
    assert body["detachment_blocked"] is False and body["detachment_blocked_reason"] is None
    assert body["row_errors"] == []
