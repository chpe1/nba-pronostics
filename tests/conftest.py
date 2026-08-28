import os
import tempfile
from pathlib import Path

# Isole le fichier de log des tests du vrai logs/app.log : importer app.main
# ci-dessous déclenche setup_logging(), donc cette variable doit être fixée
# avant cet import (même convention que DATABASE_URL -- jamais dans .env).
# Fichier de test conservé après le run (pas de nettoyage automatique) pour
# rester consultable si une suite de tests échoue de façon confuse.
os.environ.setdefault("LOG_FILE", str(Path(tempfile.gettempdir()) / "nba_pronostics_test.log"))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import create_access_token, hash_password
from app.database import Base, enable_sqlite_foreign_keys, get_db
from app.main import app

TEST_ADMIN_USERNAME = "admin"
TEST_ADMIN_PASSWORD = "test-password-123"


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def admin_env(monkeypatch):
    """Configure les variables d'environnement admin/JWT pour la durée du test."""
    monkeypatch.setenv("ADMIN_USERNAME", TEST_ADMIN_USERNAME)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", hash_password(TEST_ADMIN_PASSWORD))
    # >= 32 octets (app.core.security.MIN_JWT_SECRET_BYTES) -- représentatif
    # d'une config valide, pas un secret plus court que ce que l'app accepte.
    monkeypatch.setenv("JWT_SECRET_KEY", "test-only-secret-key-not-for-production")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480")
    return {"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD}


@pytest.fixture()
def auth_headers(admin_env):
    token = create_access_token(admin_env["username"])
    return {"Authorization": f"Bearer {token}"}
