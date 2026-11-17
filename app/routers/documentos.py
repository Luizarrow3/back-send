import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import Documento, Pessoa, User
from app.routers.admin import registrar_auditoria

router = APIRouter(tags=["documentos"])
UPLOAD_DIR = settings.UPLOAD_DIR
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_TYPES = {"image/jpeg", "image/png"}
MAX_SIZE = 5 * 1024 * 1024


def _tipo_real_arquivo(conteudo: bytes) -> str | None:
    if conteudo.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if conteudo.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


def _validar_permissao(current_user: User) -> None:
    if current_user.perfil not in {"ADMIN", "OPERADOR"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado para este perfil",
        )


@router.get("/{pessoa_id}/foto")
def obter_foto(
    pessoa_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    _validar_permissao(current_user)
    pessoa = db.query(Pessoa).filter(Pessoa.id == pessoa_id).first()
    if pessoa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pessoa não encontrada")

    documento = (
        db.query(Documento)
        .filter(Documento.pessoa_id == pessoa_id)
        .order_by(Documento.id.desc())
        .first()
    )
    if documento is None or not Path(documento.caminho_arquivo).is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Foto não encontrada")

    return FileResponse(
        documento.caminho_arquivo,
        media_type=documento.content_type,
        filename=documento.nome_arquivo,
    )


@router.post("/{pessoa_id}/documentos")
def upload_documento(
    pessoa_id: int,
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _validar_permissao(current_user)

    pessoa = db.query(Pessoa).filter(Pessoa.id == pessoa_id).first()
    if pessoa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pessoa não encontrada")

    conteudo = arquivo.file.read()
    if len(conteudo) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Arquivo vazio")
    if len(conteudo) > MAX_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Arquivo maior que 5MB")

    tipo_real = _tipo_real_arquivo(conteudo)
    if tipo_real is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tipo de arquivo inválido. Use JPG ou PNG.",
        )

    if arquivo.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tipo de arquivo inválido. Use JPG ou PNG.",
        )

    extensao = ".jpg" if tipo_real == "image/jpeg" else ".png"
    nome_arquivo = f"{uuid.uuid4()}{extensao}"
    caminho = UPLOAD_DIR / nome_arquivo
    caminho.write_bytes(conteudo)

    documento = Documento(
        pessoa_id=pessoa.id,
        nome_arquivo=nome_arquivo,
        caminho_arquivo=str(caminho),
        content_type=tipo_real,
        tamanho_bytes=len(conteudo),
        tipo_documento="DOCUMENTO_IDENTIFICACAO",
    )
    db.add(documento)
    db.commit()
    db.refresh(documento)

    registrar_auditoria(
        db,
        current_user,
        entidade="documento",
        entidade_id=documento.id,
        acao="upload",
        detalhes=f"Documento {documento.nome_arquivo} anexado à pessoa {pessoa.id}",
    )
    db.commit()

    return {
        "id": documento.id,
        "pessoa_id": pessoa.id,
        "nome_arquivo": documento.nome_arquivo,
        "mime_type": documento.content_type,
        "tamanho_bytes": documento.tamanho_bytes,
    }
