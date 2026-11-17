from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, hash_password
from app.database import get_db
from app.models import Auditoria, User
from app.schemas import AuditoriaResponse, UsuarioCreate, UsuarioResponse

router = APIRouter(tags=["admin"])


def _validar_admin(current_user: User) -> None:
    if current_user.perfil != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito ao administrador",
        )


def registrar_auditoria(
    db: Session,
    current_user: User,
    entidade: str,
    entidade_id: int | None,
    acao: str,
    detalhes: str | None = None,
) -> None:
    registro = Auditoria(
        usuario_id=current_user.id,
        entidade=entidade,
        entidade_id=entidade_id,
        acao=acao,
        detalhes=detalhes,
    )
    db.add(registro)


@router.get("/usuarios", response_model=list[UsuarioResponse])
def listar_usuarios(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[UsuarioResponse]:
    _validar_admin(current_user)
    usuarios = db.query(User).order_by(User.id).all()
    return [
        UsuarioResponse(
            id=usuario.id,
            email=usuario.email,
            nome=usuario.nome,
            perfil=usuario.perfil,
            ativo=usuario.ativo,
        )
        for usuario in usuarios
    ]


@router.post("/usuarios", response_model=UsuarioResponse)
def criar_usuario(
    payload: UsuarioCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UsuarioResponse:
    _validar_admin(current_user)

    if payload.perfil not in {"ADMIN", "OPERADOR"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Perfil inválido. Use ADMIN ou OPERADOR",
        )

    usuario_existente = db.query(User).filter(User.email == payload.email).first()
    if usuario_existente is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="E-mail já cadastrado",
        )

    usuario = User(
        email=payload.email,
        nome=payload.nome.strip(),
        senha_hash=hash_password(payload.password),
        perfil=payload.perfil,
        ativo=True,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)

    registrar_auditoria(
        db,
        current_user,
        entidade="user",
        entidade_id=usuario.id,
        acao="criar",
        detalhes=f"Usuário {usuario.email} criado",
    )
    db.commit()

    return UsuarioResponse(
        id=usuario.id,
        email=usuario.email,
        nome=usuario.nome,
        perfil=usuario.perfil,
        ativo=usuario.ativo,
    )


@router.get("/auditoria", response_model=list[AuditoriaResponse])
def listar_auditoria(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AuditoriaResponse]:
    _validar_admin(current_user)
    registros = db.query(Auditoria).order_by(Auditoria.id.desc()).all()
    return [
        AuditoriaResponse(
            id=registro.id,
            usuario_id=registro.usuario_id,
            entidade=registro.entidade,
            entidade_id=registro.entidade_id,
            acao=registro.acao,
            detalhes=registro.detalhes,
            criado_em=registro.criado_em,
        )
        for registro in registros
    ]
