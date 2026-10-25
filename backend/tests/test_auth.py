import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.models import User


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client, TestingSession
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_register_login_session_and_admin_count(client, monkeypatch):
    http, db_factory = client
    data = {"name": "  Ada   Lovelace ", "email": " ADA@example.com ", "password": "Secure-password-123", "role": "admin"}
    response = http.post("/api/auth/register", json=data)
    assert response.status_code == 201
    user = response.json()
    assert user["name"] == "Ada Lovelace"
    assert user["email"] == "ada@example.com"
    assert user["role"] == "user"
    assert "password" not in user and "password_hash" not in user
    with db_factory() as db:
        stored = db.query(User).filter_by(email="ada@example.com").one()
        assert stored.password_hash != data["password"]

    assert http.post("/api/auth/register", json=data).status_code == 409
    assert http.get("/api/auth/me").json()["id"] == user["id"]
    assert http.post("/api/auth/login", json={"email": data["email"], "password": "wrong-password"}).status_code == 401
    assert http.post("/api/auth/login", json={"email": "ada@example.com", "password": data["password"]}).status_code == 200
    assert http.get("/api/admin/users").status_code == 403

    monkeypatch.setenv("ADMIN_BOOTSTRAP_EMAIL", "ada@example.com")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_SECRET", "a-strong-bootstrap-secret-long")
    assert http.post("/api/admin/bootstrap", json={"secret": "bad-secret-that-is-long-enough"}).status_code == 403
    assert http.post("/api/admin/bootstrap", json={"secret": "a-strong-bootstrap-secret-long"}).status_code == 200
    assert http.get("/api/auth/me").json()["role"] == "admin"
    result = http.get("/api/admin/users?limit=10&offset=0").json()
    assert result["total"] == 1
    assert result["users"][0]["email"] == "ada@example.com"

    second = http.post("/api/auth/register", json={"name": "Grace", "email": "grace@example.com", "password": "another-secure-password"})
    assert second.status_code == 201
    assert http.post("/api/auth/login", json={"email": data["email"], "password": data["password"]}).status_code == 200
    result = http.get("/api/admin/users?limit=10&offset=0").json()
    assert result["total"] == 2
    assert http.post("/api/auth/logout").status_code == 204
    assert http.get("/api/auth/me").status_code == 401
    assert http.get("/api/admin/users").status_code == 401


def test_registration_validates_password_and_ignores_role(client):
    http, _ = client
    response = http.post("/api/auth/register", json={"name": "Test", "email": "test@example.com", "password": "short", "role": "admin"})
    assert response.status_code == 422
    assert http.get("/api/admin/users").status_code == 401
