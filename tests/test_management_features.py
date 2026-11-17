import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _cpf_valido() -> str:
    base = str(uuid.uuid4().int % 10**9).zfill(9)
    valores = [int(digito) for digito in base]
    soma = sum(valor * (10 - indice) for indice, valor in enumerate(valores))
    primeiro = 0 if soma % 11 < 2 else 11 - soma % 11
    valores.append(primeiro)
    soma = sum(valor * (11 - indice) for indice, valor in enumerate(valores))
    segundo = 0 if soma % 11 < 2 else 11 - soma % 11
    valores.append(segundo)
    return "".join(str(valor) for valor in valores)


def _auth_headers() -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"email": "admin@local.test", "password": "admin123456"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _criar_pessoa(headers: dict[str, str], nome: str) -> int:
    response = client.post(
        "/pessoas",
        headers=headers,
        json={
            "nome": nome,
            "cpf": _cpf_valido(),
            "sexo": "FEMININO",
            "data_nascimento": "1990-01-01",
        },
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_listagem_paginada_filtra_por_nome() -> None:
    headers = _auth_headers()
    nome = f"Busca Paginada {uuid.uuid4().hex}"
    _criar_pessoa(headers, nome)

    response = client.get(
        "/pessoas/paginado",
        params={"q": nome, "page": 1, "page_size": 5},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["nome"] == nome
    assert response.json()["pages"] == 1


def test_listagem_paginada_busca_por_cpf() -> None:
    headers = _auth_headers()
    cpf = _cpf_valido()
    created = client.post(
        "/pessoas",
        headers=headers,
        json={
            "nome": f"Busca CPF {uuid.uuid4().hex}",
            "cpf": cpf,
            "sexo": "MASCULINO",
            "data_nascimento": "1980-02-02",
        },
    )
    response = client.get(
        "/pessoas/paginado",
        params={"q": cpf},
        headers=headers,
    )

    assert created.status_code == 200
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == created.json()["id"]


def test_validacao_facial_registra_simulacao_e_exporta_csv() -> None:
    headers = _auth_headers()
    nome = f"Pessoa Biometria {uuid.uuid4().hex}"
    pessoa_id = _criar_pessoa(headers, nome)

    validacao = client.post(
        f"/pessoas/{pessoa_id}/validacao-facial",
        json={"correspondencia_simulada": True},
        headers=headers,
    )
    relatorio = client.get(
        "/relatorios/pessoas.csv",
        params={"q": nome},
        headers=headers,
    )

    assert validacao.status_code == 200
    assert validacao.json()["resultado"] == "CORRESPONDENTE"
    assert validacao.json()["modo_simulacao"] is True
    assert validacao.json()["assertividade_simulada"] == 96.4
    assert relatorio.status_code == 200
    assert nome in relatorio.text
    assert "CPF" in relatorio.text


def test_csv_escapa_valores_que_podem_ser_interpretados_como_formula() -> None:
    headers = _auth_headers()
    nome = f"=HYPERLINK(\"https://invalid.test\", \"{uuid.uuid4().hex}\")"
    pessoa_id = _criar_pessoa(headers, nome)

    response = client.get(
        "/relatorios/pessoas.csv",
        params={"q": nome},
        headers=headers,
    )

    assert response.status_code == 200
    assert "'=HYPERLINK" in response.text
    client.delete(f"/pessoas/{pessoa_id}", headers=headers)


def test_exclusao_de_recenseado() -> None:
    headers = _auth_headers()
    pessoa_id = _criar_pessoa(headers, f"Pessoa Excluir {uuid.uuid4().hex}")

    response = client.delete(f"/pessoas/{pessoa_id}", headers=headers)

    assert response.status_code == 204
    assert client.get(f"/pessoas/{pessoa_id}", headers=headers).status_code == 404


def test_foto_enviada_pode_ser_visualizada_com_autenticacao() -> None:
    headers = _auth_headers()
    pessoa_id = _criar_pessoa(headers, f"Pessoa Foto {uuid.uuid4().hex}")
    conteudo = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
    upload = client.post(
        f"/pessoas/{pessoa_id}/documentos",
        headers=headers,
        files={"arquivo": ("foto.png", conteudo, "image/png")},
    )
    foto = client.get(f"/pessoas/{pessoa_id}/foto", headers=headers)

    assert upload.status_code == 200
    assert foto.status_code == 200
    assert foto.content == conteudo
