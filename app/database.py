import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Surchargeable via DATABASE_URL (ex: pour une base de dev séparée lors des
# vérifications manuelles en navigateur, sans jamais toucher la vraie base
# une fois de vraies données chargées).
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nba_pronostics.db")

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
