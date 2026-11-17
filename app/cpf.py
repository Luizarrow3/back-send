import hashlib
import hmac
import re
from base64 import urlsafe_b64encode

from cryptography.fernet import Fernet


def limpar_cpf(cpf: str) -> str:
    if cpf is None:
        raise ValueError("CPF não pode ser nulo")
    return re.sub(r"\D", "", str(cpf))


def validar_cpf(cpf: str) -> bool:
    cpf_limpo = limpar_cpf(cpf)

    if len(cpf_limpo) != 11:
        return False

    if cpf_limpo == cpf_limpo[0] * 11:
        return False

    try:
        valores = [int(digito) for digito in cpf_limpo]
    except ValueError:
        return False

    soma = 0
    for indice, valor in enumerate(valores[:9], start=1):
        soma += valor * (11 - indice)

    digito_1 = 0 if soma % 11 < 2 else 11 - (soma % 11)
    if valores[9] != digito_1:
        return False

    soma = 0
    for indice, valor in enumerate(valores[:10], start=1):
        soma += valor * (12 - indice)

    digito_2 = 0 if soma % 11 < 2 else 11 - (soma % 11)
    return valores[10] == digito_2


def mascarar_cpf(cpf: str) -> str:
    cpf_limpo = limpar_cpf(cpf)
    if len(cpf_limpo) != 11:
        return "***.***.***-**"
    return f"***.{cpf_limpo[3:6]}.{cpf_limpo[6:9]}-**"


def hash_cpf(cpf: str, segredo: str) -> str:
    cpf_limpo = limpar_cpf(cpf)
    digest = hmac.new(segredo.encode("utf-8"), cpf_limpo.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()


def cifrar_cpf(cpf: str, segredo: str) -> str:
    cpf_limpo = limpar_cpf(cpf)
    chave = urlsafe_b64encode(hashlib.sha256(segredo.encode("utf-8")).digest())
    fernet = Fernet(chave)
    return fernet.encrypt(cpf_limpo.encode("utf-8")).decode("utf-8")


def decifrar_cpf(valor_cifrado: str, segredo: str) -> str:
    chave = urlsafe_b64encode(hashlib.sha256(segredo.encode("utf-8")).digest())
    fernet = Fernet(chave)
    return fernet.decrypt(valor_cifrado.encode("utf-8")).decode("utf-8")
