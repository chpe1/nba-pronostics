"""Verdicts OBLIGATOIRES pour confirmer un import d'effectif, sous condition (Décision d'architecture
n°39) : quand les DEUX ensembles sont non vides -- au moins une ligne du fichier sans correspondance,
ET au moins un joueur actif de la base absent du fichier. La garde est côté SERVEUR : elle tient même
quand l'écran n'envoie aucun verdict."""
import io
import json

import pytest

from app.models import Player, Settings, Team


@pytest.fixture()
def base(db_session):
    db_session.add(Settings(current_season="2026-2027"))
    bos = Team(name="Boston Celtics", abbreviation="BOS")
    db_session.add(bos)
    db_session.flush()
    kept = Player(name="Kept Starter", team_id=bos.id)
    db_session.add(kept)
    db_session.commit()
    return {"bos": bos, "kept": kept}


def _csv(rows) -> bytes:
    return ("\n".join(["Player,Team"] + [f"{n},{t}" for n, t in rows]) + "\n").encode("utf-8")


def _post(client, auth_headers, rows, dry_run=False, verdicts=None):
    return client.post(
        "/api/imports/stats",
        params={"dry_run": dry_run},
        data={"verdicts": json.dumps(verdicts)} if verdicts is not None else None,
        files={"file": ("roster.csv", io.BytesIO(_csv(rows)), "text/csv")},
        headers=auth_headers,
    )


def _names(db_session):
    db_session.expire_all()
    return sorted(p.name for p in db_session.query(Player).all())


# --- les deux ensembles non vides : blocage -----------------------------------------------------


def test_confirmation_is_refused_when_a_row_has_no_match_and_a_player_is_absent(client, auth_headers, db_session, base):
    db_session.add(Player(name="Absent Veteran", team_id=base["bos"].id))
    db_session.commit()
    response = _post(client, auth_headers, [("Kept Starter", "BOS"), ("Ronald Holland II", "BOS")])
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "1 ligne(s)" in detail and "Ronald Holland II" in detail  # combien, et lesquelles
    assert "1 joueur(s) de la base sont absents" in detail
    assert _names(db_session) == ["Absent Veteran", "Kept Starter"]  # rien n'a été écrit


def test_refusal_counts_and_names_every_row_without_verdict(client, auth_headers, db_session, base):
    db_session.add(Player(name="Absent Veteran", team_id=base["bos"].id))
    db_session.commit()
    rows = [("Kept Starter", "BOS"), ("Alpha New", "BOS"), ("Beta New", "BOS"), ("Gamma New", "BOS")]
    response = _post(client, auth_headers, rows, verdicts=[{"file_name": "Beta New", "verdict": "recruit"}])
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "2 ligne(s)" in detail
    assert "Alpha New" in detail and "Gamma New" in detail
    assert "Beta New" not in detail  # celle-là a un verdict


def test_confirmation_goes_through_once_every_row_has_a_verdict(client, auth_headers, db_session, base):
    db_session.add(Player(name="Absent Veteran", team_id=base["bos"].id))
    db_session.commit()
    rows = [("Kept Starter", "BOS"), ("Alpha New", "BOS")]
    response = _post(client, auth_headers, rows, verdicts=[{"file_name": "Alpha New", "verdict": "recruit"}])
    assert response.status_code == 200
    assert "Alpha New" in _names(db_session)


def test_an_already_detached_free_agent_counts_as_a_player_absent_from_the_file(client, auth_headers, db_session, base):
    """Un agent libre actif absent du fichier peut être la cible d'une association : le risque existe."""
    db_session.add(Player(name="Free Agent F", team_id=None))
    db_session.commit()
    assert _post(client, auth_headers, [("Kept Starter", "BOS"), ("Newcomer", "BOS")]).status_code == 400


# --- un des deux ensembles vide : pas de blocage -------------------------------------------------


def test_no_block_when_no_player_is_absent_from_the_file(client, auth_headers, db_session, base):
    """Aucun joueur absent côté base : une ligne sans correspondance ne peut être qu'une recrue."""
    response = _post(client, auth_headers, [("Kept Starter", "BOS"), ("Brand New Rookie", "BOS")])
    assert response.status_code == 200
    assert _names(db_session) == ["Brand New Rookie", "Kept Starter"]


def test_no_block_when_every_row_has_a_match(client, auth_headers, db_session, base):
    """Des joueurs absents mais aucune ligne sans correspondance : rien à trancher, rien n'est bloqué."""
    db_session.add(Player(name="Absent Veteran", team_id=base["bos"].id))
    db_session.commit()
    response = _post(client, auth_headers, [("Kept Starter", "BOS")])
    assert response.status_code == 200
    assert "Absent Veteran" in _names(db_session)  # rien n'est détaché sans demande explicite


def test_inactive_players_do_not_count_as_absent(client, auth_headers, db_session, base):
    db_session.add(Player(name="Retired Guy", team_id=base["bos"].id, is_active=False))
    db_session.commit()
    assert _post(client, auth_headers, [("Kept Starter", "BOS"), ("Brand New Rookie", "BOS")]).status_code == 200


# --- l'aperçu expose la règle (une seule source de vérité) --------------------------------------------


def test_preview_says_verdicts_are_required_when_both_sets_are_non_empty(client, auth_headers, db_session, base):
    db_session.add(Player(name="Absent Veteran", team_id=base["bos"].id))
    db_session.commit()
    body = _post(client, auth_headers, [("Kept Starter", "BOS"), ("Newcomer", "BOS")], dry_run=True).json()
    assert body["verdicts_required"] is True


def test_preview_says_verdicts_are_not_required_without_absent_player(client, auth_headers, db_session, base):
    body = _post(client, auth_headers, [("Kept Starter", "BOS"), ("Newcomer", "BOS")], dry_run=True).json()
    assert body["verdicts_required"] is False


def test_preview_says_verdicts_are_not_required_without_unmatched_row(client, auth_headers, db_session, base):
    db_session.add(Player(name="Absent Veteran", team_id=base["bos"].id))
    db_session.commit()
    body = _post(client, auth_headers, [("Kept Starter", "BOS")], dry_run=True).json()
    assert body["verdicts_required"] is False
