"""Étape 3 du chantier des agents libres (Décision d'architecture n°39) : le détachement
côté serveur -- aperçu enrichi (futurs agents libres, lignes du fichier sans
correspondance) et confirmation qui reçoit une liste EXPLICITE d'identifiants.

Aucun agent libre n'est créé hors de ces tests ; aucune base réelle n'est touchée."""
import io
import json

import pytest

from app.models import Player, PreviousSeasonPlayerStat, Settings, Team

PREV = "2025-2026"


@pytest.fixture()
def league(db_session):
    """BOS : Starter A et Starter B (dans le fichier), Gone C (absent, ligne N-1) ;
    LAL : Gone D (absent, draft_pick 40) ; E : déjà agent libre (absent du fichier)."""
    db_session.add(Settings(current_season="2026-2027"))
    bos = Team(name="Boston Celtics", abbreviation="BOS")
    lal = Team(name="Los Angeles Lakers", abbreviation="LAL")
    db_session.add_all([bos, lal])
    db_session.flush()
    a = Player(name="Starter A", team_id=bos.id)
    b = Player(name="Starter B", team_id=bos.id)
    c = Player(name="Gone C", team_id=bos.id)
    d = Player(name="Gone D", team_id=lal.id, draft_pick=40)
    e = Player(name="Free Agent E", team_id=None)
    db_session.add_all([a, b, c, d, e])
    db_session.add(PreviousSeasonPlayerStat(season=PREV, player_name="Gone C", team_abbreviation="BOS", per=11.5, mpg=22.0))
    db_session.commit()
    return {"bos": bos, "lal": lal, "a": a, "b": b, "c": c, "d": d, "e": e}


def _csv(rows) -> bytes:
    return ("\n".join(["Player,Team"] + [f"{n},{t}" for n, t in rows]) + "\n").encode("utf-8")


FILE_ALL_MATCHED = [("Starter A", "BOS"), ("Starter B", "BOS")]


def _post(client, auth_headers, content, dry_run, detach_ids=None, verdicts=None):
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


def _team_of(db_session, player):
    db_session.expire_all()
    return db_session.get(Player, player.id).team_id


# --- aperçu ----------------------------------------------------------------------


def test_preview_lists_future_free_agents_with_what_is_needed_to_decide(client, auth_headers, league):
    body = _post(client, auth_headers, _csv(FILE_ALL_MATCHED), True).json()
    detachable = {p["name"]: p for p in body["detachable"]}
    assert set(detachable) == {"Gone C", "Gone D"}  # le agent libre E n'y est PAS (déjà détaché)
    assert detachable["Gone C"] == {
        "id": league["c"].id,
        "name": "Gone C",
        "team_abbreviation": "BOS",
        "draft_pick": None,
        "per_n1": 11.5,
        "mpg_n1": 22.0,
    }
    assert detachable["Gone D"]["team_abbreviation"] == "LAL"
    assert detachable["Gone D"]["draft_pick"] == 40
    assert detachable["Gone D"]["per_n1"] is None and detachable["Gone D"]["mpg_n1"] is None  # pas de ligne N-1
    assert body["orphans"] == ["Gone C", "Gone D"]  # ancienne section conservée, même contenu


def test_preview_reports_zero_file_rows_without_match_when_every_row_matches(client, auth_headers, league):
    body = _post(client, auth_headers, _csv(FILE_ALL_MATCHED), True).json()
    assert body["file_rows_without_match_count"] == 0
    assert body["file_rows_without_match"] == []


def test_preview_reports_file_rows_without_match_with_a_suggestion(client, auth_headers, db_session, league):
    """Cas réel du 2026-10-19 : « Ronald Holland II » dans le fichier, « Ron Holland » en base."""
    db_session.add(Player(name="Ron Holland", team_id=league["bos"].id))
    db_session.commit()
    body = _post(client, auth_headers, _csv(FILE_ALL_MATCHED + [("Ronald Holland II", "BOS")]), True).json()
    assert body["file_rows_without_match_count"] == 1
    row = body["file_rows_without_match"][0]
    assert row["name"] == "Ronald Holland II" and row["team_abbreviation"] == "BOS"
    assert row["closest_absent_player"] == "Ron Holland"  # simple suggestion
    assert "Ron Holland" in {p["name"] for p in body["detachable"]}  # il est bien proposé au détachement


def test_preview_counts_each_unmatched_name_once(client, auth_headers, league):
    body = _post(client, auth_headers, _csv(FILE_ALL_MATCHED + [("New Guy", "BOS"), ("new guy", "BOS")]), True).json()
    assert body["file_rows_without_match_count"] == 1


def test_preview_writes_nothing(client, auth_headers, db_session, league):
    _post(client, auth_headers, _csv(FILE_ALL_MATCHED + [("New Guy", "BOS")]), True)
    assert db_session.query(Player).count() == 5
    assert _team_of(db_session, league["c"]) == league["bos"].id


# --- confirmation : détachement ------------------------------------------------------


def test_confirm_detaches_only_the_ids_sent_and_reports_them(client, auth_headers, db_session, league):
    content = _csv(FILE_ALL_MATCHED + [("New Guy", "BOS")])
    # « New Guy » est une ligne sans correspondance : elle doit avoir un verdict avant tout détachement (étape 4).
    verdicts = [{"file_name": "New Guy", "verdict": "recruit"}]
    response = _post(client, auth_headers, content, False, [league["c"].id], verdicts)
    assert response.status_code == 200
    body = response.json()
    assert body["detached_count"] == 1 and body["detached_names"] == ["Gone C"]
    assert body["import_history"]["import_type"] == "roster"

    assert _team_of(db_session, league["c"]) is None  # détaché
    assert _team_of(db_session, league["d"]) == league["lal"].id  # absent aussi, mais PAS envoyé : intact
    assert db_session.query(Player).filter(Player.name == "New Guy").count() == 1  # l'import a bien eu lieu


def test_detached_player_stays_active_and_previous_team_id_is_not_written(client, auth_headers, db_session, league):
    _post(client, auth_headers, _csv(FILE_ALL_MATCHED), False, [league["c"].id])
    db_session.expire_all()
    player = db_session.get(Player, league["c"].id)
    assert player.team_id is None
    assert player.is_active is True  # Décision n°39 : l'agent libre reste is_active
    assert player.previous_team_id is None  # colonne morte, jamais écrite
    assert player.per == 0.0 and player.name == "Gone C"  # rien d'autre n'a bougé


def test_confirm_with_several_ids_reports_exact_count_and_names(client, auth_headers, db_session, league):
    body = _post(client, auth_headers, _csv(FILE_ALL_MATCHED), False, [league["d"].id, league["c"].id]).json()
    assert body["detached_count"] == 2
    assert body["detached_names"] == ["Gone D", "Gone C"]  # ordre demandé
    assert _team_of(db_session, league["c"]) is None and _team_of(db_session, league["d"]) is None


def test_nothing_is_ever_detached_by_default(client, auth_headers, db_session, league):
    body = _post(client, auth_headers, _csv(FILE_ALL_MATCHED), False).json()  # paramètre absent
    assert body["detached_count"] == 0 and body["detached_names"] == []
    assert _team_of(db_session, league["c"]) == league["bos"].id
    assert _team_of(db_session, league["d"]) == league["lal"].id


def test_confirm_refuses_an_id_present_in_the_file_and_applies_nothing(client, auth_headers, db_session, league):
    content = _csv(FILE_ALL_MATCHED + [("New Guy", "BOS")])
    verdicts = [{"file_name": "New Guy", "verdict": "recruit"}]  # (verdict exigé : un joueur est absent côté base)
    response = _post(client, auth_headers, content, False, [league["c"].id, league["a"].id], verdicts)  # A figure dans le fichier
    assert response.status_code == 400
    assert "Starter A" in response.json()["detail"]
    assert _team_of(db_session, league["a"]) == league["bos"].id
    assert _team_of(db_session, league["c"]) == league["bos"].id  # C valide, mais rien n'est appliqué
    assert db_session.query(Player).filter(Player.name == "New Guy").count() == 0  # l'import non plus


def test_presence_in_the_file_is_checked_on_the_spelling_the_import_uses(client, auth_headers, db_session, league):
    """Un joueur écrit autrement dans le fichier (casse, ponctuation) y est bien PRÉSENT : jamais détaché."""
    content = _csv([("starter a", "BOS"), ("Starter B", "BOS")])
    response = _post(client, auth_headers, content, False, [league["a"].id])
    assert response.status_code == 400


def test_confirm_is_idempotent_for_already_detached_players(client, auth_headers, db_session, league):
    first = _post(client, auth_headers, _csv(FILE_ALL_MATCHED), False, [league["c"].id]).json()
    second = _post(client, auth_headers, _csv(FILE_ALL_MATCHED), False, [league["c"].id])
    assert first["detached_count"] == 1
    assert second.status_code == 200
    assert second.json()["detached_count"] == 0 and second.json()["detached_names"] == []
    assert _team_of(db_session, league["c"]) is None
    # un agent libre dès le départ (E) accepté sans erreur et non recompté
    third = _post(client, auth_headers, _csv(FILE_ALL_MATCHED), False, [league["e"].id])
    assert third.status_code == 200 and third.json()["detached_count"] == 0


def test_confirm_refuses_an_unknown_id_and_applies_nothing(client, auth_headers, db_session, league):
    verdicts = [{"file_name": "New Guy", "verdict": "recruit"}]
    response = _post(client, auth_headers, _csv(FILE_ALL_MATCHED + [("New Guy", "BOS")]), False, [league["c"].id, 999999], verdicts)
    assert response.status_code == 400
    assert "999999" in response.json()["detail"]
    assert _team_of(db_session, league["c"]) == league["bos"].id
    assert db_session.query(Player).filter(Player.name == "New Guy").count() == 0


def test_confirm_refuses_an_inactive_player(client, auth_headers, db_session, league):
    league["c"].is_active = False
    db_session.commit()
    response = _post(client, auth_headers, _csv(FILE_ALL_MATCHED), False, [league["c"].id])
    assert response.status_code == 400
    assert "inactif" in response.json()["detail"]


def test_confirm_refuses_detachment_when_the_file_has_row_errors(client, auth_headers, db_session, league):
    """Une ligne illisible (équipe inconnue) pourrait être un joueur « absent » à tort : rien n'est détaché."""
    content = _csv(FILE_ALL_MATCHED + [("Mystery Man", "XXX")])
    response = _post(client, auth_headers, content, False, [league["c"].id])
    assert response.status_code == 400
    assert "lignes en erreur" in response.json()["detail"]
    assert _team_of(db_session, league["c"]) == league["bos"].id


def test_detach_ids_are_refused_on_a_preview(client, auth_headers, db_session, league):
    response = _post(client, auth_headers, _csv(FILE_ALL_MATCHED), True, [league["c"].id])
    assert response.status_code == 400
    assert _team_of(db_session, league["c"]) == league["bos"].id


def test_detach_ids_are_refused_for_a_non_roster_import(client, auth_headers, db_session, league):
    content = b"Team,Home,Road\nBoston Celtics,24-6,18-16\n"
    response = _post(client, auth_headers, content, False, [league["c"].id])
    assert response.status_code == 400
    assert _team_of(db_session, league["c"]) == league["bos"].id


def test_detached_player_is_then_replaced_not_duplicated_by_a_later_import(client, auth_headers, db_session, league):
    _post(client, auth_headers, _csv(FILE_ALL_MATCHED), False, [league["c"].id])
    _post(client, auth_headers, _csv(FILE_ALL_MATCHED + [("Gone C", "LAL")]), False)
    db_session.expire_all()
    rows = db_session.query(Player).filter(Player.name == "Gone C").all()
    assert len(rows) == 1 and rows[0].team_id == league["lal"].id
