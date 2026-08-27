import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Surchargeable via DATABASE_URL (ex: pour une base de dev séparée lors des
# vérifications manuelles en navigateur, sans jamais toucher la vraie base
# une fois de vraies données chargées).
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nba_pronostics.db")

def enable_sqlite_foreign_keys(target_engine) -> None:
    """SQLite désactive la vérification des clés étrangères par défaut, sur
    CHAQUE connexion (ce n'est pas un réglage persistant du fichier .db) --
    sans ceci, les FK Game/Team, Player/Team, etc. ne sont que déclaratives
    côté SQLAlchemy, jamais vérifiées réellement par la base (confirmé par
    audit le 2026-08-27 : PRAGMA foreign_keys valait 0). Recette standard
    SQLAlchemy pour pysqlite.

    Fonction réutilisable (pas juste un event listener local à `engine`) :
    tests/conftest.py crée son propre moteur SQLite indépendant pour la base
    de test, qui doit recevoir la même protection -- sinon le fix ne serait
    jamais vérifié par la suite de tests."""

    @event.listens_for(target_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
enable_sqlite_foreign_keys(engine)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        # Explicite plutôt qu'implicite : un import CSV (ou toute autre
        # requête) qui plante en cours de route ne doit rien laisser en
        # base. close() seul fait déjà ce rollback (comportement par défaut
        # de SQLAlchemy, vérifié empiriquement le 2026-08-27), mais le
        # rendre explicite ici documente la garantie dans le code plutôt que
        # de compter sur un détail d'implémentation.
        db.rollback()
        raise
    finally:
        db.close()
