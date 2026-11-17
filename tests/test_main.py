from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "censo-previdenciario",
    }


def test_app_has_expected_metadata() -> None:
    assert app.title == "Censo Previdenciário"
    assert app.version == "0.1.0"
