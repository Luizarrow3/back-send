from datetime import datetime, time

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.cpf import cifrar_cpf, hash_cpf, validar_cpf
from app.models import Pessoa, User
from app.repositories import pessoas as repository
from app.schemas import PessoaCreate, PessoaUpdate


def criar(db: Session, payload: PessoaCreate, usuario: User, segredo: str) -> Pessoa:
    if not validar_cpf(payload.cpf):
        raise HTTPException(status_code=400, detail="CPF inválido")

    cpf_hash = hash_cpf(payload.cpf, segredo)
    existente = db.query(Pessoa).filter(Pessoa.cpf_hash == cpf_hash).first()
    if existente is not None:
        raise HTTPException(status_code=409, detail="CPF já cadastrado")

    pessoa = Pessoa(
        nome=payload.nome.strip(),
        cpf_cifrado=cifrar_cpf(payload.cpf, segredo),
        cpf_hash=cpf_hash,
        sexo=payload.sexo,
        data_nascimento=datetime.combine(payload.data_nascimento, time.min),
        status="PENDENTE",
        usuario_id=usuario.id,
    )
    return repository.salvar(db, pessoa)


def atualizar(db: Session, pessoa: Pessoa, payload: PessoaUpdate) -> Pessoa:
    if payload.nome is not None:
        pessoa.nome = payload.nome.strip()
    if payload.sexo is not None:
        pessoa.sexo = payload.sexo
    if payload.data_nascimento is not None:
        pessoa.data_nascimento = datetime.combine(payload.data_nascimento, time.min)
    if payload.motivo_rejeicao is not None:
        pessoa.motivo_rejeicao = payload.motivo_rejeicao
    if not payload.model_fields_set:
        raise HTTPException(status_code=400, detail="Nenhum campo informado para atualização")
    return repository.salvar(db, pessoa)


def obter_ou_404(db: Session, pessoa_id: int) -> Pessoa:
    pessoa = repository.obter(db, pessoa_id)
    if pessoa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pessoa não encontrada")
    return pessoa
