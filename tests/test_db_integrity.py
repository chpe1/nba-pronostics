"""Couvre les 4 points de l'audit de fiabilité du 2026-08-27 (avant premier
chargement de vraies données) : atomicité de l'import CSV (rollback
implicite de get_db), contraintes UNIQUE en base sur Player et Game, et
activation réelle de PRAGMA foreign_keys sur SQLite."""
from datetime import date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import app.database as database_module
from app.database import Base, enable_sqlite_foreign_keys, get_db
from app.models import Game, GameStatus, Player, Team


def _team(abbreviation: str, name: str) -> Team:
    return Team(name=name, abbreviation=abbreviation, win_pct_home=0.5, win_pct_away=0.5)


# --- Point 3 : PRAGMA foreign_keys ------------------------------------------


def test_foreign_keys_pragma_is_enabled(db_session):
    value = db_session.execute(text("PRAGMA foreign_keys")).scalar()
    assert value == 1


def test_foreign_key_violation_is_rejected(db_session):
    """Un Player pointant vers un Team inexistant doit être refusé par SQLite
    lui-même -- avant le 2026-08-27, la contrainte n'était que déclarative
    côté SQLAlchemy, jamais vérifiée réellement."""
    db_session.add(Player(name="Ghost Player", team_id=999999))
    with pytest.raises(IntegrityError):
        db_session.flush()


# --- Point 2 : UNIQUE(name, team_id) sur players ----------------------------


def test_player_name_team_unique_constraint_at_db_level(db_session):
    """Filet de sécurité complémentaire à find_player_by_name (comparaison
    insensible à la casse côté Python) -- bloque un doublon EXACT au niveau
    base, même si un futur bug contournait find_player_by_name."""
    team = _team("BOS", "Boston Celtics")
    db_session.add(team)
    db_session.flush()
    db_session.add(Player(name="Jayson Tatum", team_id=team.id))
    db_session.flush()

    db_session.add(Player(name="Jayson Tatum", team_id=team.id))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_player_name_team_unique_constraint_is_case_sensitive_at_db_level(db_session):
    """Documente explicitement la limite : la contrainte DB ne remplace PAS
    find_player_by_name pour la casse -- "LEBRON JAMES" et "LeBron James"
    ne collisionnent PAS au niveau SQLite (qui ne replie que l'ASCII)."""
    team = _team("LAL", "Los Angeles Lakers")
    db_session.add(team)
    db_session.flush()
    db_session.add(Player(name="LeBron James", team_id=team.id))
    db_session.flush()

    db_session.add(Player(name="LEBRON JAMES", team_id=team.id))
    db_session.flush()  # ne lève PAS -- casse différente, non couvert par la contrainte DB

    assert db_session.query(Player).filter(Player.team_id == team.id).count() == 2


def test_player_name_team_unique_constraint_allows_same_name_different_team(db_session):
    bos = _team("BOS", "Boston Celtics")
    lal = _team("LAL", "Los Angeles Lakers")
    db_session.add_all([bos, lal])
    db_session.flush()
    db_session.add(Player(name="Homonym Player", team_id=bos.id))
    db_session.flush()

    db_session.add(Player(name="Homonym Player", team_id=lal.id))
    db_session.flush()  # ne lève pas -- équipes différentes


# --- Point 2 : UNIQUE(game_date_only, home_team_id, away_team_id) ----------


def test_game_date_only_synced_automatically_from_game_date():
    """@validates("game_date") doit tenir game_date_only à jour à chaque
    affectation, sans qu'aucun site d'écriture n'ait besoin d'y penser."""
    game = Game(
        season="2025-2026",
        game_date=datetime(2026, 1, 15, 19, 0),
        home_team_id=1,
        away_team_id=2,
        status=GameStatus.SCHEDULED,
    )
    assert game.game_date_only == date(2026, 1, 15)

    game.game_date = datetime(2026, 1, 16, 21, 30)
    assert game.game_date_only == date(2026, 1, 16)


def test_game_unique_constraint_at_db_level(db_session):
    home = _team("BOS", "Boston Celtics")
    away = _team("LAL", "Los Angeles Lakers")
    db_session.add_all([home, away])
    db_session.flush()
    db_session.add(
        Game(
            season="2025-2026",
            game_date=datetime(2026, 1, 15, 19, 0),
            home_team_id=home.id,
            away_team_id=away.id,
            status=GameStatus.SCHEDULED,
        )
    )
    db_session.flush()

    db_session.add(
        Game(
            season="2025-2026",
            game_date=datetime(2026, 1, 15, 19, 0),
            home_team_id=home.id,
            away_team_id=away.id,
            status=GameStatus.SCHEDULED,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_game_unique_constraint_ignores_time_of_day(db_session):
    """Preuve que la contrainte protège bien la clé d'upsert réelle (date
    SANS l'heure) : deux lignes même jour mais à des heures différentes
    doivent quand même être bloquées -- une contrainte brute sur game_date
    (avec l'heure) ne l'aurait pas fait."""
    home = _team("BOS", "Boston Celtics")
    away = _team("LAL", "Los Angeles Lakers")
    db_session.add_all([home, away])
    db_session.flush()
    db_session.add(
        Game(
            season="2025-2026",
            game_date=datetime(2026, 1, 15, 19, 0),
            home_team_id=home.id,
            away_team_id=away.id,
            status=GameStatus.SCHEDULED,
        )
    )
    db_session.flush()

    db_session.add(
        Game(
            season="2025-2026",
            game_date=datetime(2026, 1, 15, 21, 30),  # même jour, heure différente
            home_team_id=home.id,
            away_team_id=away.id,
            status=GameStatus.SCHEDULED,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_game_unique_constraint_allows_same_day_different_matchup(db_session):
    home = _team("BOS", "Boston Celtics")
    away = _team("LAL", "Los Angeles Lakers")
    third = _team("MIA", "Miami Heat")
    db_session.add_all([home, away, third])
    db_session.flush()
    db_session.add(
        Game(
            season="2025-2026",
            game_date=datetime(2026, 1, 15, 19, 0),
            home_team_id=home.id,
            away_team_id=away.id,
            status=GameStatus.SCHEDULED,
        )
    )
    db_session.flush()

    db_session.add(
        Game(
            season="2025-2026",
            game_date=datetime(2026, 1, 15, 19, 30),
            home_team_id=third.id,
            away_team_id=away.id,
            status=GameStatus.SCHEDULED,
        )
    )
    db_session.flush()  # ne lève pas -- équipe à domicile différente


# --- Point 1 : rollback implicite de get_db() sur exception -----------------


def test_get_db_rolls_back_uncommitted_work_on_exception(tmp_path, monkeypatch):
    """Reproduit exactement le scénario audité manuellement le 2026-08-27 :
    un flush() réussi (données physiquement écrites dans la transaction
    ouverte) suivi d'un plantage inattendu avant db.commit() -- get_db() ne
    doit rien laisser en base."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{tmp_path / 'rollback_test.db'}")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(bind=engine)
    isolated_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(database_module, "SessionLocal", isolated_session_local)

    gen = get_db()
    db = next(gen)
    db.add(_team("BOS", "Boston Celtics"))
    db.flush()  # écrit physiquement dans la transaction ouverte, pas encore commité
    assert db.query(Team).count() == 1  # visible dans la transaction en cours

    with pytest.raises(RuntimeError):
        gen.throw(RuntimeError("panne simulée avant db.commit()"))

    fresh_session = isolated_session_local()
    assert fresh_session.query(Team).count() == 0  # rollback confirmé
    fresh_session.close()
