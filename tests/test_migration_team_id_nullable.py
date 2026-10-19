"""Migration b7c8d9e0f1a2 : players.team_id nullable (agents libres, Décision n°39).

Chaque test migre sa propre base SQLite temporaire (jamais nba_pronostics.db) via
l'API Alembic -- alembic/env.py lit DATABASE_URL, posée ici par monkeypatch (donc
retirée en fin de test, jamais dans .env)."""
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.models import Player, Team

REPO_ROOT = Path(__file__).resolve().parent.parent
BEFORE_REVISION = "a6b7c8d9e0f1"
THIS_REVISION = "b7c8d9e0f1a2"


@pytest.fixture()
def alembic_cfg(tmp_path, monkeypatch):
    db_path = tmp_path / "migration.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return cfg, db_path


def _players_schema(db_path):
    conn = sqlite3.connect(db_path)
    try:
        columns = {r[1]: r for r in conn.execute("pragma table_info(players)").fetchall()}
        unique_indexes = [
            tuple(i[2] for i in conn.execute(f"pragma index_info('{r[1]}')").fetchall())
            for r in conn.execute("pragma index_list(players)").fetchall()
            if r[2]
        ]
        foreign_keys = sorted((r[3], r[2], r[4]) for r in conn.execute("pragma foreign_key_list(players)").fetchall())
        return columns, unique_indexes, foreign_keys
    finally:
        conn.close()


def _insert_team(conn, team_id, abbreviation):
    conn.execute(
        "insert into teams (id, name, abbreviation, win_pct_home, win_pct_away, win_pct_home_prev_season, "
        "win_pct_away_prev_season) values (?, ?, ?, 0, 0, 0, 0)",
        (team_id, f"Team {abbreviation}", abbreviation),
    )


def _insert_player(conn, name, team_id):
    conn.execute(
        "insert into players (name, team_id, per, mpg, injury_status, is_active) values (?, ?, 0, 0, 'HEALTHY', 1)",
        (name, team_id),
    )


def test_upgrade_makes_team_id_nullable_and_loses_nothing(alembic_cfg):
    cfg, db_path = alembic_cfg
    command.upgrade(cfg, BEFORE_REVISION)

    before_columns, before_unique, before_fks = _players_schema(db_path)
    assert before_columns["team_id"][3] == 1  # NOT NULL avant

    conn = sqlite3.connect(db_path)
    _insert_team(conn, 1, "BOS")
    _insert_team(conn, 2, "LAL")
    _insert_player(conn, "Jayson Tatum", 1)
    _insert_player(conn, "LeBron James", 2)
    conn.commit()
    rows_before = conn.execute("select * from players order by id").fetchall()
    conn.close()

    command.upgrade(cfg, THIS_REVISION)

    after_columns, after_unique, after_fks = _players_schema(db_path)
    assert after_columns["team_id"][3] == 0  # nullable après
    # Rien d'autre n'a bougé : mêmes colonnes (noms, types, nullité des autres), même unicité, mêmes clés étrangères.
    assert {n: (c[2], c[3], c[4]) for n, c in after_columns.items() if n != "team_id"} == {
        n: (c[2], c[3], c[4]) for n, c in before_columns.items() if n != "team_id"
    }
    assert list(after_columns) == list(before_columns)
    assert after_unique == before_unique == [("name", "team_id")]
    assert after_fks == before_fks

    conn = sqlite3.connect(db_path)
    assert conn.execute("select * from players order by id").fetchall() == rows_before
    assert conn.execute("pragma integrity_check").fetchone()[0] == "ok"
    assert conn.execute("pragma foreign_key_check").fetchall() == []
    conn.close()


def test_upgraded_schema_accepts_a_free_agent_but_still_rejects_an_exact_duplicate(alembic_cfg):
    cfg, db_path = alembic_cfg
    command.upgrade(cfg, THIS_REVISION)
    conn = sqlite3.connect(db_path)
    _insert_team(conn, 1, "BOS")
    _insert_player(conn, "Free Agent", None)  # agent libre accepté
    _insert_player(conn, "Jayson Tatum", 1)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_player(conn, "Jayson Tatum", 1)  # doublon exact (nom, équipe) toujours refusé
    conn.rollback()
    conn.close()


def test_downgrade_refuses_while_a_free_agent_exists_and_changes_nothing(alembic_cfg):
    cfg, db_path = alembic_cfg
    command.upgrade(cfg, THIS_REVISION)
    conn = sqlite3.connect(db_path)
    _insert_team(conn, 1, "BOS")
    _insert_player(conn, "Free Agent", None)
    _insert_player(conn, "Jayson Tatum", 1)
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="Retour arrière refusé : 1 joueur"):
        command.downgrade(cfg, BEFORE_REVISION)

    conn = sqlite3.connect(db_path)
    assert conn.execute("select version_num from alembic_version").fetchall() == [(THIS_REVISION,)]
    assert conn.execute("select count(*) from players").fetchone()[0] == 2
    assert conn.execute("select count(*) from players where team_id is null").fetchone()[0] == 1
    conn.close()
    assert _players_schema(db_path)[0]["team_id"][3] == 0  # toujours nullable : table intacte


def test_downgrade_succeeds_once_no_free_agent_remains(alembic_cfg):
    cfg, db_path = alembic_cfg
    command.upgrade(cfg, THIS_REVISION)
    conn = sqlite3.connect(db_path)
    _insert_team(conn, 1, "BOS")
    _insert_player(conn, "Jayson Tatum", 1)
    conn.commit()
    conn.close()

    command.downgrade(cfg, BEFORE_REVISION)

    columns, unique, fks = _players_schema(db_path)
    assert columns["team_id"][3] == 1  # NOT NULL de nouveau
    assert unique == [("name", "team_id")]
    conn = sqlite3.connect(db_path)
    assert conn.execute("select name, team_id from players").fetchall() == [("Jayson Tatum", 1)]
    assert conn.execute("select version_num from alembic_version").fetchall() == [(BEFORE_REVISION,)]
    conn.close()


def test_model_accepts_a_free_agent_without_team(db_session):
    """Le modèle (pas seulement la migration) : un Player sans équipe se crée et se relit,
    et deux agents libres homonymes ne sont PAS arrêtés par UNIQUE(name, team_id)
    (SQLite : les NULL sont distincts) -- la déduplication reste portée par le code."""
    team = Team(name="Boston Celtics", abbreviation="BOS")
    db_session.add(team)
    db_session.flush()
    free_agent = Player(name="Free Agent", team_id=None)
    db_session.add(free_agent)
    db_session.flush()
    assert free_agent.team is None and free_agent.is_active is True

    db_session.add(Player(name="Free Agent", team_id=None))
    db_session.flush()  # ne lève pas : limite documentée, voir la migration
    assert db_session.query(Player).filter(Player.team_id.is_(None)).count() == 2
