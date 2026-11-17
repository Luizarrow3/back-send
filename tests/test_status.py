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


def _criar_pessoa(headers: dict[str, str], cpf: str, nome: str = "Pessoa Teste") -> int:
    payload = {
        "nome": nome,
        "cpf": cpf,
        "sexo": "FEMININO",
        "data_nascimento": "1990-01-01",
    }
    response = client.post("/pessoas", json=payload, headers=headers)
    assert response.status_code == 200
    return response.json()["id"]


def test_transicao_status_valida() -> None:
    headers = _auth_headers()
    pessoa_id = _criar_pessoa(headers, _cpf_valido())

    response = client.post(f"/pessoas/{pessoa_id}/status?novo_status=EM_ANALISE", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "EM_ANALISE"


def test_rejeicao_exige_motivo() -> None:
    headers = _auth_headers()
    pessoa_id = _criar_pessoa(headers, _cpf_valido())
    client.post(f"/pessoas/{pessoa_id}/status?novo_status=EM_ANALISE", headers=headers)

    response = client.post(
        f"/pessoas/{pessoa_id}/status?novo_status=REJEITADO",
        headers=headers,
    )

    assert response.status_code == 400
    assert "Motivo" in response.json()["detail"]


def test_status_invalido_retorna_409() -> None:
    headers = _auth_headers()
    pessoa_id = _criar_pessoa(headers, _cpf_valido())

    response = client.post(f"/pessoas/{pessoa_id}/status?novo_status=RECENSEADO", headers=headers)

    assert response.status_code == 409
    assert "Transição inválida" in response.json()["detail"]


def test_sem_login_nao_acessa_status() -> None:
    response = client.post("/pessoas/1/status?novo_status=EM_ANALISE")
    assert response.status_code == 401
