from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    perfil: Mapped[str] = mapped_column(String(20), nullable=False, default="OPERADOR")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tentativas_login: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ultima_tentativa: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    auditorias: Mapped[list["Auditoria"]] = relationship(back_populates="usuario")
    historicos: Mapped[list["StatusHistorico"]] = relationship(back_populates="usuario")
    pessoas: Mapped[list["Pessoa"]] = relationship(back_populates="usuario")


class Pessoa(Base):
    __tablename__ = "pessoas"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    cpf_cifrado: Mapped[str] = mapped_column(String(255), nullable=False)
    cpf_hash: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    sexo: Mapped[str] = mapped_column(String(20), nullable=False)
    data_nascimento: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="PENDENTE", nullable=False)
    motivo_rejeicao: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    usuario_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    usuario: Mapped[Optional[User]] = relationship(back_populates="pessoas")
    documentos: Mapped[list["Documento"]] = relationship(
        back_populates="pessoa", cascade="all, delete-orphan"
    )
    historicos: Mapped[list["StatusHistorico"]] = relationship(
        back_populates="pessoa", cascade="all, delete-orphan"
    )
    validacoes_faciais: Mapped[list["ValidacaoFacial"]] = relationship(
        back_populates="pessoa", cascade="all, delete-orphan"
    )


class StatusHistorico(Base):
    __tablename__ = "status_historico"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    pessoa_id: Mapped[int] = mapped_column(ForeignKey("pessoas.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    motivo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    usuario_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    pessoa: Mapped[Pessoa] = relationship(back_populates="historicos")
    usuario: Mapped[Optional[User]] = relationship(back_populates="historicos")


class Documento(Base):
    __tablename__ = "documentos"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    pessoa_id: Mapped[int] = mapped_column(ForeignKey("pessoas.id"), nullable=False)
    nome_arquivo: Mapped[str] = mapped_column(String(255), nullable=False)
    caminho_arquivo: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    tamanho_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo_documento: Mapped[str] = mapped_column(String(50), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    pessoa: Mapped[Pessoa] = relationship(back_populates="documentos")


class Auditoria(Base):
    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    usuario_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    entidade: Mapped[str] = mapped_column(String(100), nullable=False)
    entidade_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    acao: Mapped[str] = mapped_column(String(50), nullable=False)
    detalhes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    usuario: Mapped[Optional[User]] = relationship(back_populates="auditorias")


class ValidacaoFacial(Base):
    __tablename__ = "validacoes_faciais"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    pessoa_id: Mapped[int] = mapped_column(ForeignKey("pessoas.id"), nullable=False, index=True)
    usuario_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    resultado: Mapped[str] = mapped_column(String(20), nullable=False)
    modo_simulacao: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    pessoa: Mapped[Pessoa] = relationship(back_populates="validacoes_faciais")
