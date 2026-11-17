import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _cpf_valido() -> str:
    base = str(uuid.uuid4().int % 10**9).zfill(9)
    valores = [int(d) for d in base]
    soma = sum(v * (10 - i) for i, v in enumerate(valores))
    d1 = 0 if soma % 11 < 2 else 11 - (soma % 11)
    valores.append(d1)
    soma = sum(v * (11 - i) for i, v in enumerate(valores))
    d2 = 0 if soma % 11 < 2 else 11 - (soma % 11)
    valores.append(d2)
    return "".join(str(v) for v in valores)


def _auth_headers() -> dict[str, str]:
    login_response = client.post(
        "/auth/login",
        json={"email": "admin@local.test", "password": "admin123456"},
    )
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _criar_pessoa(headers: dict[str, str], cpf: str) -> int:
    payload = {
        "nome": "Pessoa Documento",
        "cpf": cpf,
        "sexo": "FEMININO",
        "data_nascimento": "1990-01-01",
    }
    response = client.post("/pessoas", json=payload, headers=headers)
    assert response.status_code == 200
    return response.json()["id"]


def test_upload_documento_valido() -> None:
    headers = _auth_headers()
    cpf = _cpf_valido()
    pessoa_id = _criar_pessoa(headers, cpf)
    arquivo = ("teste.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 40, "image/png")
    response = client.post(
        f"/pessoas/{pessoa_id}/documentos",
        files={"arquivo": arquivo},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["pessoa_id"] == pessoa_id
    assert body["nome_arquivo"].endswith(".png")


def test_upload_rejeita_tipo_invalido() -> None:
    headers = _auth_headers()
    cpf = _cpf_valido()
    pessoa_id = _criar_pessoa(headers, cpf)
    response = client.post(
        f"/pessoas/{pessoa_id}/documentos",
        files={"arquivo": ("teste.txt", b"texto", "text/plain")},
        headers=headers,
    )

    assert response.status_code == 400
    assert "Tipo de arquivo" in response.json()["detail"]


def test_upload_rejeita_sem_login() -> None:
    response = client.post(
        "/pessoas/1/documentos",
        files={"arquivo": ("teste.png", b"\x89PNG\r\n\x1a\n", "image/png")},
    )
    assert response.status_code == 401
