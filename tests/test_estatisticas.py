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
    response = client.post(
        "/auth/login",
        json={"email": "admin@local.test", "password": "admin123456"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_resumo_estatisticas() -> None:
    headers = _auth_headers()
    pessoa_1 = client.post(
        "/pessoas",
        headers=headers,
        json={
            "nome": "Pessoa 1",
            "cpf": _cpf_valido(),
            "sexo": "FEMININO",
            "data_nascimento": "1990-01-01",
        },
    )
    pessoa_2 = client.post(
        "/pessoas",
        headers=headers,
        json={
            "nome": "Pessoa 2",
            "cpf": _cpf_valido(),
            "sexo": "MASCULINO",
            "data_nascimento": "1985-03-15",
        },
    )

    assert pessoa_1.status_code == 200
    assert pessoa_2.status_code == 200

    response = client.get("/resumo", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total_pessoas"] >= 2
    assert "por_status" in body
    assert "idade_media" in body
