from datetime import date

from app.models import Pessoa


def calcular_faixa_etaria(data_nascimento: date) -> str:
    hoje = date.today()
    idade = hoje.year - data_nascimento.year - ((hoje.month, hoje.day) < (data_nascimento.month, data_nascimento.day))

    if idade < 18:
        return "MENOR_18"
    if idade < 30:
        return "18_29"
    if idade < 40:
        return "30_39"
    if idade < 50:
        return "40_49"
    if idade < 60:
        return "50_59"
    if idade < 70:
        return "60_69"
    return "70_PLUS"


def gerar_estatisticas(pessoas: list[Pessoa]) -> dict[str, object]:
    total = len(pessoas)
    por_status: dict[str, int] = {}
    por_sexo: dict[str, int] = {}
    por_faixa: dict[str, int] = {}
    idades: list[int] = []

    for pessoa in pessoas:
        status = pessoa.status
        por_status[status] = por_status.get(status, 0) + 1

        sexo = pessoa.sexo
        por_sexo[sexo] = por_sexo.get(sexo, 0) + 1

        hoje = date.today()
        idade = hoje.year - pessoa.data_nascimento.year - ((hoje.month, hoje.day) < (pessoa.data_nascimento.month, pessoa.data_nascimento.day))
        idades.append(idade)

        faixa = calcular_faixa_etaria(pessoa.data_nascimento)
        por_faixa[faixa] = por_faixa.get(faixa, 0) + 1

    idade_media = 0.0
    if idades:
        total_idades = 0
        for idade in idades:
            total_idades += idade
        idade_media = total_idades / len(idades)

    return {
        "total_pessoas": total,
        "pendentes": por_status.get("PENDENTE", 0),
        "por_status": por_status,
        "por_sexo": por_sexo,
        "por_faixa_etaria": por_faixa,
        "idade_media": round(idade_media, 2),
    }
