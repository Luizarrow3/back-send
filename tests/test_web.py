from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_redireciona_para_login() -> None:
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/login"


def test_login_page_serve_html() -> None:
    response = client.get("/login")

    assert response.status_code == 200
    content = response.text.lower()
    assert "login" in content
    assert "e-mail" in content or "email" in content


def test_painel_page_serve_html() -> None:
    response = client.get("/painel")

    assert response.status_code == 200
    content = response.text.lower()
    assert "painel do censo" in content
    assert "search-form" in content or "buscar" in content


def test_static_js_serve() -> None:
    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "localStorage" in response.text
