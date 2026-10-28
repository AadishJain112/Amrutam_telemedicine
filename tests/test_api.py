import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["JWT_SECRET"] = "test-secret-with-more-than-32-characters"

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health():
    assert client.get("/healthz").json() == {"status": "ok"}


def test_register_and_login():
    email = "patient@example.com"
    response = client.post("/v1/auth/register", json={"email": email, "password": "strong-password-123"})
    assert response.status_code == 201
    login = client.post("/v1/auth/login", json={"email": email, "password": "strong-password-123"})
    assert login.status_code == 200
    assert login.json()["token_type"] == "bearer"


def test_invalid_login_is_not_disclosed():
    response = client.post("/v1/auth/login", json={"email": "missing@example.com", "password": "strong-password-123"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"
