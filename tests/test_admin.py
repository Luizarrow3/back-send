import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _auth_headers(email: str = "admin@local.test", password: str = "admin123456") -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_admin_lista_usuarios() -> None:
    response = client.get("/admin/usuarios", headers=_auth_headers())

    assert response.status_code == 200
    usuarios = response.json()
    assert any(usuario["email"] == "admin@local.test" for usuario in usuarios)


def test_admin_cria_usuario_operador() -> None:
    email = f"operador_{uuid.uuid4().hex[:8]}@local.test"
    payload = {
        "email": email,
        "nome": "Operador Teste",
        "password": "senhavalida123",
        "perfil": "OPERADOR",
    }

    response = client.post("/admin/usuarios", json=payload, headers=_auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == email
    assert body["perfil"] == "OPERADOR"


def test_admin_cria_usuario_perfil_invalido() -> None:
    email = f"invalido_{uuid.uuid4().hex[:8]}@local.test"
    payload = {
        "email": email,
        "nome": "Teste",
        "password": "senhavalida123",
        "perfil": "VISITANTE",
    }

    response = client.post("/admin/usuarios", json=payload, headers=_auth_headers())

    assert response.status_code == 400
    assert "Perfil inválido" in response.json()["detail"]


def test_admin_auditoria_requer_login() -> None:
    response = client.get("/admin/auditoria")

    assert response.status_code == 401


def test_operador_nao_pode_acessar_admin() -> None:
    cliente = TestClient(app)
    admin_headers = _auth_headers()
    email = f"operador2_{uuid.uuid4().hex[:8]}@local.test"
    create_user = cliente.post(
        "/admin/usuarios",
        json={
            "email": email,
            "nome": "Operador 2",
            "password": "senhavalida123",
            "perfil": "OPERADOR",
        },
        headers=admin_headers,
    )
    assert create_user.status_code == 200

    operador_headers = _auth_headers(email, "senhavalida123")
    response = cliente.get("/admin/usuarios", headers=operador_headers)

    assert response.status_code == 403
