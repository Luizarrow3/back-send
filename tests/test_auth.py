from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_login_returns_token_for_valid_user() -> None:
    response = client.post(
        "/auth/login",
        json={"email": "admin@local.test", "password": "admin123456"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "access_token" in payload
    assert payload["token_type"] == "bearer"


def test_login_rejects_invalid_password() -> None:
    response = client.post(
        "/auth/login",
        json={"email": "admin@local.test", "password": "senhaerrada"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Credenciais inválidas"


def test_me_requires_valid_token() -> None:
    response = client.get("/auth/me")

    assert response.status_code == 401
    assert "detail" in response.json()
