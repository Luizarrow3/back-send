from app.cpf import cifrar_cpf, hash_cpf, limpar_cpf, mascarar_cpf, validar_cpf


def test_limpar_cpf_remove_mascara() -> None:
    assert limpar_cpf("123.456.789-09") == "12345678909"


def test_validar_cpf_com_cpf_valido() -> None:
    assert validar_cpf("123.456.789-09") is True


def test_validar_cpf_rejeita_repetidos() -> None:
    assert validar_cpf("111.111.111-11") is False


def test_validar_cpf_rejeita_invalido() -> None:
    assert validar_cpf("123.456.789-00") is False


def test_mascarar_cpf_e_hash() -> None:
    assert mascarar_cpf("12345678909") == "***.456.789-**"
    assert hash_cpf("12345678909", "segredo")
    assert cifrar_cpf("12345678909", "segredo")
