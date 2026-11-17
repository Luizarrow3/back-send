from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Pessoa


def obter(db: Session, pessoa_id: int) -> Pessoa | None:
    return db.query(Pessoa).filter(Pessoa.id == pessoa_id).first()


def listar(
    db: Session,
    *,
    termo: str | None = None,
    cpf_hash: str | None = None,
    status: str | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> tuple[list[Pessoa], int]:
    consulta = db.query(Pessoa)
    if termo:
        consulta = consulta.filter(func.lower(Pessoa.nome).contains(termo.lower()))
    if cpf_hash:
        consulta = consulta.filter(Pessoa.cpf_hash == cpf_hash)
    if status:
        consulta = consulta.filter(Pessoa.status == status)

    total = consulta.count()
    consulta = consulta.order_by(Pessoa.id)
    if limit is not None:
        consulta = consulta.offset(offset).limit(limit)
    return consulta.all(), total


def salvar(db: Session, pessoa: Pessoa) -> Pessoa:
    db.add(pessoa)
    db.commit()
    db.refresh(pessoa)
    return pessoa


def excluir(db: Session, pessoa: Pessoa) -> None:
    db.delete(pessoa)
    db.commit()
