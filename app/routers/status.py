from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.cache import invalidar_resumo
from app.database import get_db
from app.models import Pessoa, StatusHistorico, User
from app.routers.admin import registrar_auditoria

router = APIRouter(tags=["status"])

TRANSICOES_PERMITIDAS = {
    "PENDENTE": {"EM_ANALISE"},
    "EM_ANALISE": {"RECENSEADO", "REJEITADO"},
    "RECENSEADO": set(),
    "REJEITADO": set(),
}


def _validar_permissao(current_user: User) -> None:
    if current_user.perfil not in {"ADMIN", "OPERADOR"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado para este perfil",
        )


@router.post("/{pessoa_id}/status")
def atualizar_status(
    pessoa_id: int,
    novo_status: str,
    motivo: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _validar_permissao(current_user)

    pessoa = db.query(Pessoa).filter(Pessoa.id == pessoa_id).first()
    if pessoa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pessoa não encontrada")

    status_atual = pessoa.status
    if novo_status not in TRANSICOES_PERMITIDAS.get(status_atual, set()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Transição inválida: {status_atual} -> {novo_status}",
        )

    if novo_status == "REJEITADO" and not motivo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Motivo é obrigatório para rejeição",
        )

    if novo_status == "RECENSEADO" and not pessoa.documentos:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pessoa precisa ter ao menos um documento para ser recenseada",
        )

    pessoa.status = novo_status
    pessoa.motivo_rejeicao = motivo

    historico = StatusHistorico(
        pessoa_id=pessoa.id,
        status=novo_status,
        motivo=motivo,
        usuario_id=current_user.id,
    )
    db.add(historico)
    registrar_auditoria(
        db,
        current_user,
        entidade="status",
        entidade_id=pessoa.id,
        acao="atualizar",
        detalhes=f"Status alterado para {novo_status}",
    )
    db.commit()
    invalidar_resumo()

    return {"id": pessoa.id, "status": pessoa.status, "motivo": pessoa.motivo_rejeicao}
