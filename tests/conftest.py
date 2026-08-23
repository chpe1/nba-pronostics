import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import create_access_token, hash_password
from app.database import Base, get_db
from app.main import app

TEST_ADMIN_USERNAME = "admin"
TEST_ADMIN_PASSWORD = "test-password-123"


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
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
    monkeypatch.setenv("JWT_SECRET_KEY", "test-only-secret-key")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480")
    return {"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD}


@pytest.fixture()
def auth_headers(admin_env):
    token = create_access_token(admin_env["username"])
    return {"Authorization": f"Bearer {token}"}
