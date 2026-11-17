import unicodedata
import re
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.cache import invalidar_resumo
from app.config import settings
from app.cpf import decifrar_cpf, hash_cpf, mascarar_cpf, validar_cpf
from app.database import get_db
from app.models import Pessoa, User, ValidacaoFacial
from app.repositories import pessoas as repository
from app.routers.admin import registrar_auditoria
from app.schemas import (
    PessoaCreate,
    PessoaPageResponse,
    PessoaResponse,
    PessoaUpdate,
    ValidacaoFacialRequest,
    ValidacaoFacialResponse,
)
from app.services import pessoas as service

router = APIRouter(tags=["pessoas"])


def _validar_permissao(current_user: User) -> None:
    if current_user.perfil not in {"ADMIN", "OPERADOR"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado para este perfil",
        )


def _normalizar_texto(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    return texto.lower().strip()


def _serializar_pessoa(pessoa: Pessoa) -> PessoaResponse:
    cpf_raw = decifrar_cpf(pessoa.cpf_cifrado, settings.JWT_SECRET_KEY)
    cpf_mascarado = mascarar_cpf(cpf_raw)
    return PessoaResponse(
        id=pessoa.id,
        nome=pessoa.nome,
        cpf=cpf_mascarado,
        cpf_mascarado=cpf_mascarado,
        sexo=pessoa.sexo,
        data_nascimento=pessoa.data_nascimento,
        status=pessoa.status,
        usuario_id=pessoa.usuario_id,
    )


@router.post("", response_model=PessoaResponse)
def criar_pessoa(
    payload: PessoaCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PessoaResponse:
    _validar_permissao(current_user)

    pessoa = service.criar(db, payload, current_user, settings.JWT_SECRET_KEY)
    invalidar_resumo()

    registrar_auditoria(
        db,
        current_user,
        entidade="pessoa",
        entidade_id=pessoa.id,
        acao="criar",
        detalhes=f"Pessoa criada: {pessoa.nome}",
    )
    db.commit()

    cpf_mascarado = mascarar_cpf(payload.cpf)
    return PessoaResponse(
        id=pessoa.id,
        nome=pessoa.nome,
        cpf=cpf_mascarado,
        cpf_mascarado=cpf_mascarado,
        sexo=pessoa.sexo,
        data_nascimento=pessoa.data_nascimento,
        status=pessoa.status,
        usuario_id=pessoa.usuario_id,
    )


@router.get("/search", response_model=list[PessoaResponse])
def buscar_pessoas(
    nome: str | None = None,
    cpf: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PessoaResponse]:
    _validar_permissao(current_user)

    if nome is None and cpf is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Informe nome ou CPF para buscar",
        )

    if nome is not None:
        termo = _normalizar_texto(nome)
        pessoas = db.query(Pessoa).all()
        resultados = []
        for pessoa in pessoas:
            if termo in _normalizar_texto(pessoa.nome):
                resultados.append(_serializar_pessoa(pessoa))
        return resultados

    if cpf is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Informe nome ou CPF para buscar",
        )
    cpf_limpo = cpf.strip()
    if not validar_cpf(cpf_limpo):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CPF inválido",
        )

    cpf_hash = hash_cpf(cpf_limpo, settings.JWT_SECRET_KEY)
    pessoas = db.query(Pessoa).filter(Pessoa.cpf_hash == cpf_hash).all()
    return [_serializar_pessoa(pessoa) for pessoa in pessoas]


@router.get("", response_model=list[PessoaResponse])
def listar_pessoas(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PessoaResponse]:
    _validar_permissao(current_user)

    pessoas, _ = repository.listar(db)
    return [_serializar_pessoa(pessoa) for pessoa in pessoas]


@router.get("/paginado", response_model=PessoaPageResponse)
def listar_pessoas_paginado(
    q: str | None = None,
    status_filtro: str | None = None,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PessoaPageResponse:
    _validar_permissao(current_user)
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(status_code=400, detail="Paginação inválida")

    termo = q.strip() if q and q.strip() else None
    cpf_hash = None
    if termo and re.fullmatch(r"[\d.\-/\s]+", termo):
        cpf_digits = re.sub(r"\D", "", termo)
        if len(cpf_digits) == 11:
            if not validar_cpf(cpf_digits):
                raise HTTPException(status_code=400, detail="CPF inválido")
            cpf_hash = hash_cpf(cpf_digits, settings.JWT_SECRET_KEY)
            termo = None

    pessoas, total = repository.listar(
        db,
        termo=termo,
        cpf_hash=cpf_hash,
        status=status_filtro,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return PessoaPageResponse(
        items=[_serializar_pessoa(pessoa) for pessoa in pessoas],
        total=total,
        page=page,
        page_size=page_size,
        pages=ceil(total / page_size) if total else 0,
    )


@router.get("/{pessoa_id}", response_model=PessoaResponse)
def buscar_pessoa(
    pessoa_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PessoaResponse:
    _validar_permissao(current_user)

    pessoa = service.obter_ou_404(db, pessoa_id)

    return _serializar_pessoa(pessoa)


@router.put("/{pessoa_id}", response_model=PessoaResponse)
def atualizar_pessoa(
    pessoa_id: int,
    payload: PessoaUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PessoaResponse:
    _validar_permissao(current_user)

    pessoa = service.obter_ou_404(db, pessoa_id)
    pessoa = service.atualizar(db, pessoa, payload)
    invalidar_resumo()

    registrar_auditoria(
        db,
        current_user,
        entidade="pessoa",
        entidade_id=pessoa.id,
        acao="editar",
        detalhes=f"Pessoa atualizada: {pessoa.nome}",
    )
    db.commit()

    return _serializar_pessoa(pessoa)


@router.delete("/{pessoa_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_pessoa(
    pessoa_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    _validar_permissao(current_user)
    pessoa = service.obter_ou_404(db, pessoa_id)
    registrar_auditoria(
        db,
        current_user,
        entidade="pessoa",
        entidade_id=pessoa.id,
        acao="excluir",
        detalhes=f"Pessoa excluída: {pessoa.nome}",
    )
    repository.excluir(db, pessoa)
    invalidar_resumo()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{pessoa_id}/validacao-facial",
    response_model=ValidacaoFacialResponse,
)
def simular_validacao_facial(
    pessoa_id: int,
    payload: ValidacaoFacialRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ValidacaoFacialResponse:
    _validar_permissao(current_user)
    pessoa = service.obter_ou_404(db, pessoa_id)
    validacao = ValidacaoFacial(
        pessoa_id=pessoa.id,
        usuario_id=current_user.id,
        resultado="CORRESPONDENTE" if payload.correspondencia_simulada else "DIVERGENTE",
        modo_simulacao=True,
    )
    db.add(validacao)
    registrar_auditoria(
        db,
        current_user,
        entidade="validacao_facial",
        entidade_id=pessoa.id,
        acao="simular",
        detalhes=f"Resultado da simulação facial: {validacao.resultado}",
    )
    db.commit()
    if validacao.resultado == "CORRESPONDENTE":
        invalidar_resumo()
    db.refresh(validacao)
    return ValidacaoFacialResponse(
        id=validacao.id,
        pessoa_id=validacao.pessoa_id,
        resultado=validacao.resultado,
        modo_simulacao=validacao.modo_simulacao,
        assertividade_simulada=96.4 if payload.correspondencia_simulada else 18.7,
        criado_em=validacao.criado_em,
    )
