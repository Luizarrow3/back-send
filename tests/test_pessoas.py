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


def test_criar_pessoa_com_sucesso() -> None:
    payload = {
        "nome": "Maria Silva",
        "cpf": _cpf_valido(),
        "sexo": "FEMININO",
        "data_nascimento": "1990-05-10",
    }

    response = client.post("/pessoas", json=payload, headers=_auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["nome"] == "Maria Silva"
    assert body["cpf"] == body["cpf_mascarado"]
    assert body["cpf_mascarado"].startswith("***.")
    assert body["cpf_mascarado"].endswith("-**")
    assert body["status"] == "PENDENTE"


def test_criar_pessoa_rejeita_cpf_invalido() -> None:
    payload = {
        "nome": "Fulano",
        "cpf": "123.456.789-00",
        "sexo": "MASCULINO",
        "data_nascimento": "1985-11-20",
    }

    response = client.post("/pessoas", json=payload, headers=_auth_headers())

    assert response.status_code == 422
    assert "CPF inválido" in str(response.json()["detail"])


def test_criar_pessoa_normaliza_nome_e_cpf() -> None:
    headers = _auth_headers()
    cpf = _cpf_valido()
    response = client.post(
        "/pessoas",
        headers=headers,
        json={
            "nome": "  Maria   da Silva  ",
            "cpf": f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}",
            "sexo": "FEMININO",
            "data_nascimento": "1990-05-10",
        },
    )

    assert response.status_code == 200
    assert response.json()["nome"] == "Maria da Silva"
    assert response.json()["cpf_mascarado"] == f"***.{cpf[3:6]}.{cpf[6:9]}-**"


def test_criar_pessoa_rejeita_dados_invalidos() -> None:
    response = client.post(
        "/pessoas",
        headers=_auth_headers(),
        json={
            "nome": "Pessoa",
            "cpf": _cpf_valido(),
            "sexo": "INVALIDO",
            "data_nascimento": "2999-01-01",
        },
    )

    assert response.status_code == 422


def test_listar_e_editar_pessoa() -> None:
    headers = _auth_headers()
    payload = {
        "nome": "Carlos Almeida",
        "cpf": _cpf_valido(),
        "sexo": "MASCULINO",
        "data_nascimento": "1978-08-03",
    }
    created = client.post("/pessoas", json=payload, headers=headers)
    pessoa_id = created.json()["id"]

    list_response = client.get("/pessoas", headers=headers)
    assert list_response.status_code == 200
    assert isinstance(list_response.json(), list)

    update_response = client.put(
        f"/pessoas/{pessoa_id}",
        json={"nome": "Carlos Almeida Jr."},
        headers=headers,
    )

    assert update_response.status_code == 200
    assert update_response.json()["nome"] == "Carlos Almeida Jr."


def test_busca_por_nome_com_sucesso() -> None:
    headers = _auth_headers()
    nome = "Ana Maria da Silva"
    payload = {
        "nome": nome,
        "cpf": _cpf_valido(),
        "sexo": "FEMININO",
        "data_nascimento": "1992-02-15",
    }
    client.post("/pessoas", json=payload, headers=headers)

    response = client.get("/pessoas/search", params={"nome": "ana m"}, headers=headers)

    assert response.status_code == 200
    assert any(item["nome"] == nome for item in response.json())


def test_busca_por_cpf_exato() -> None:
    headers = _auth_headers()
    cpf = _cpf_valido()
    payload = {
        "nome": "Bruno Costa",
        "cpf": cpf,
        "sexo": "MASCULINO",
        "data_nascimento": "1988-07-02",
    }
    client.post("/pessoas", json=payload, headers=headers)

    response = client.get("/pessoas/search", params={"cpf": cpf}, headers=headers)

    assert response.status_code == 200
    assert response.json()[0]["cpf_mascarado"].startswith("***.")


def test_busca_requer_parametro_ou_token() -> None:
    headers = _auth_headers()
    response = client.get("/pessoas/search", headers=headers)
    assert response.status_code == 400

    response_without_token = client.get("/pessoas/search", params={"nome": "ana"})
    assert response_without_token.status_code == 401


def test_sem_token_rejeita_acesso() -> None:
    response = client.get("/pessoas")

    assert response.status_code == 401
    assert "detail" in response.json()
