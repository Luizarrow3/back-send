import csv
import re
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.cache import guardar_resumo, obter_resumo
from app.database import get_db
from app.estatisticas import gerar_estatisticas
from app.models import Pessoa, User, ValidacaoFacial
from app.repositories import pessoas as repository
from app.cpf import decifrar_cpf, hash_cpf, mascarar_cpf, validar_cpf
from app.config import settings

router = APIRouter(tags=["estatisticas"])


def _campo_csv_seguro(value: str | int) -> str | int:
    if isinstance(value, str) and re.match(r"^\s*[=+\-@]", value):
        return f"'{value}"
    return value


def _validar_permissao(current_user: User) -> None:
    if current_user.perfil not in {"ADMIN", "OPERADOR"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado para este perfil",
        )


@router.get("/resumo")
def resumo_estatisticas(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _validar_permissao(current_user)
    resumo_cache = obter_resumo()
    if resumo_cache is not None:
        return resumo_cache
    pessoas = db.query(Pessoa).all()
    estatisticas = gerar_estatisticas(pessoas)
    estatisticas["validados_biometria"] = (
        db.query(func.count(func.distinct(ValidacaoFacial.pessoa_id)))
        .filter(ValidacaoFacial.resultado == "CORRESPONDENTE")
        .scalar()
        or 0
    )
    guardar_resumo(estatisticas)
    return estatisticas


@router.get("/relatorios/pessoas.csv")
def exportar_pessoas_csv(
    status_filtro: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    _validar_permissao(current_user)
    termo = q.strip() if q and q.strip() else None
    cpf_hash = None
    if termo and re.fullmatch(r"[\d.\-/\s]+", termo):
        cpf_digits = re.sub(r"\D", "", termo)
        if len(cpf_digits) == 11:
            if not validar_cpf(cpf_digits):
                raise HTTPException(status_code=400, detail="CPF inválido")
            cpf_hash = hash_cpf(cpf_digits, settings.JWT_SECRET_KEY)
            termo = None

    pessoas, _ = repository.listar(
        db,
        termo=termo,
        cpf_hash=cpf_hash,
        status=status_filtro,
    )
    conteudo = StringIO()
    escritor = csv.writer(conteudo)
    escritor.writerow(["ID", "Nome", "CPF", "Sexo", "Data de nascimento", "Status"])
    for pessoa in pessoas:
        cpf = decifrar_cpf(pessoa.cpf_cifrado, settings.JWT_SECRET_KEY)
        escritor.writerow(
            [
                pessoa.id,
                _campo_csv_seguro(pessoa.nome),
                mascarar_cpf(cpf),
                _campo_csv_seguro(pessoa.sexo),
                pessoa.data_nascimento.date().isoformat(),
                _campo_csv_seguro(pessoa.status),
            ]
        )

    return Response(
        content="\ufeff" + conteudo.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="recenseados.csv"'},
    )
