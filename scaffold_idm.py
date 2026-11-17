#!/usr/bin/env python3
"""Generate a modular, runnable FastAPI identity-management portal."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from textwrap import dedent

BACKEND_FILES = {
    "app/__init__.py": "",
    "app/config.py": r'''
        import os
        from pathlib import Path

        from dotenv import load_dotenv

        ROOT = Path(__file__).resolve().parent.parent
        load_dotenv(ROOT / ".env")

        class Settings:
            app_env = os.getenv("APP_ENV", "development")
            database_url = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'censo.db'}")
            jwt_secret = os.getenv("JWT_SECRET_KEY", "change-this-development-secret")
            jwt_expire_minutes = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
            idle_minutes = int(os.getenv("SESSION_IDLE_MINUTES", "15"))
            redis_url = os.getenv("REDIS_URL", "")
            admin_email = os.getenv("ADMIN_EMAIL", "admin@local.test")
            admin_password = os.getenv("ADMIN_PASSWORD", "change-me-now")
            upload_dir = Path(os.getenv("UPLOAD_DIR", str(ROOT / "data" / "uploads")))

            def validate(self) -> None:
                if self.idle_minutes < 1:
                    raise ValueError("SESSION_IDLE_MINUTES deve ser maior que zero")
                if self.app_env == "production":
                    if self.jwt_secret == "change-this-development-secret":
                        raise ValueError("Configure JWT_SECRET_KEY em produção")
                    if not self.redis_url:
                        raise ValueError("Configure REDIS_URL em produção")

        settings = Settings()
    ''',
    "app/database.py": r'''
        from collections.abc import Generator

        from sqlalchemy import create_engine
        from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

        from app.config import settings

        if settings.database_url.startswith("sqlite"):
            engine = create_engine(
                settings.database_url,
                connect_args={"check_same_thread": False},
            )
        else:
            engine = create_engine(settings.database_url, pool_pre_ping=True)

        SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        class Base(DeclarativeBase):
            pass

        def get_db() -> Generator[Session, None, None]:
            db = SessionLocal()
            try:
                yield db
            finally:
                db.close()
    ''',
    "app/models.py": r'''
        from datetime import datetime, timezone

        from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, UniqueConstraint
        from sqlalchemy.orm import Mapped, mapped_column, relationship

        from app.database import Base

        def utcnow() -> datetime:
            return datetime.now(timezone.utc)

        class User(Base):
            __tablename__ = "users"

            id: Mapped[int] = mapped_column(primary_key=True)
            email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
            name: Mapped[str] = mapped_column(String(150))
            password_hash: Mapped[str] = mapped_column(String(255))
            active: Mapped[bool] = mapped_column(Boolean, default=True)

        class Recenseado(Base):
            __tablename__ = "recenseados"
            __table_args__ = (UniqueConstraint("cpf_hash", name="uq_recenseado_cpf_hash"),)

            id: Mapped[int] = mapped_column(primary_key=True)
            nome: Mapped[str] = mapped_column(String(150), index=True)
            cpf_hash: Mapped[str] = mapped_column(String(64), index=True)
            cpf_mascarado: Mapped[str] = mapped_column(String(20))
            sexo: Mapped[str] = mapped_column(String(20))
            data_nascimento: Mapped[str] = mapped_column(String(10))
            status: Mapped[str] = mapped_column(String(20), default="PENDENTE", index=True)
            foto_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
            criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
            atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
            validacoes: Mapped[list["Biometria"]] = relationship(
                back_populates="recenseado", cascade="all, delete-orphan"
            )

        class Biometria(Base):
            __tablename__ = "validacoes_biometricas"

            id: Mapped[int] = mapped_column(primary_key=True)
            recenseado_id: Mapped[int] = mapped_column(ForeignKey("recenseados.id", ondelete="CASCADE"))
            resultado: Mapped[str] = mapped_column(String(20))
            assertividade_simulada: Mapped[float] = mapped_column(Float)
            criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
            recenseado: Mapped[Recenseado] = relationship(back_populates="validacoes")
    ''',
    "app/schemas.py": r'''
        import re
        from datetime import date, datetime
        from typing import Literal

        from pydantic import BaseModel, ConfigDict, Field, field_validator

        def limpar_cpf(value: str) -> str:
            return re.sub(r"\D", "", value)

        def cpf_valido(value: str) -> bool:
            digits = limpar_cpf(value)
            if len(digits) != 11 or len(set(digits)) == 1:
                return False
            numbers = [int(digit) for digit in digits]
            for length in (9, 10):
                total = sum(numbers[index] * (length + 1 - index) for index in range(length))
                check = (total * 10) % 11
                if check == 10:
                    check = 0
                if numbers[length] != check:
                    return False
            return True

        def mascarar_cpf(value: str) -> str:
            return f"***.{value[3:6]}.{value[6:9]}-**"

        class LoginInput(BaseModel):
            email: str = Field(min_length=5, max_length=255)
            password: str = Field(min_length=10, max_length=128)

            @field_validator("email")
            @classmethod
            def normalize_email(cls, value: str) -> str:
                email = value.strip().lower()
                if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                    raise ValueError("E-mail inválido")
                return email

        class RecenseadoCreate(BaseModel):
            model_config = ConfigDict(str_strip_whitespace=True)

            nome: str = Field(min_length=2, max_length=150)
            cpf: str = Field(min_length=11, max_length=14)
            sexo: Literal["FEMININO", "MASCULINO", "OUTRO"]
            data_nascimento: date

            @field_validator("nome")
            @classmethod
            def normalize_name(cls, value: str) -> str:
                name = re.sub(r"\s+", " ", value).strip()
                if len(name) < 2:
                    raise ValueError("Nome deve ter ao menos 2 caracteres")
                return name

            @field_validator("cpf")
            @classmethod
            def validate_cpf(cls, value: str) -> str:
                if not re.fullmatch(r"[\d.\-\s]+", value) or not cpf_valido(value):
                    raise ValueError("CPF inválido")
                return limpar_cpf(value)

            @field_validator("data_nascimento")
            @classmethod
            def validate_birth_date(cls, value: date) -> date:
                if value > date.today():
                    raise ValueError("Data de nascimento não pode estar no futuro")
                return value

        class RecenseadoUpdate(BaseModel):
            model_config = ConfigDict(str_strip_whitespace=True)

            nome: str | None = Field(default=None, min_length=2, max_length=150)
            sexo: Literal["FEMININO", "MASCULINO", "OUTRO"] | None = None
            data_nascimento: date | None = None

            @field_validator("nome")
            @classmethod
            def normalize_name(cls, value: str | None) -> str | None:
                if value is None:
                    return None
                name = re.sub(r"\s+", " ", value).strip()
                if len(name) < 2:
                    raise ValueError("Nome deve ter ao menos 2 caracteres")
                return name

            @field_validator("data_nascimento")
            @classmethod
            def validate_birth_date(cls, value: date | None) -> date | None:
                if value is not None and value > date.today():
                    raise ValueError("Data de nascimento não pode estar no futuro")
                return value

        class RecenseadoOut(BaseModel):
            model_config = ConfigDict(from_attributes=True)

            id: int
            nome: str
            cpf_mascarado: str
            sexo: str
            data_nascimento: str
            status: str
            foto_disponivel: bool = False

        class PageOut(BaseModel):
            items: list[RecenseadoOut]
            total: int
            page: int
            page_size: int
            pages: int

        class BiometriaOut(BaseModel):
            resultado: str
            assertividade_simulada: float
            modo_simulacao: Literal[True] = True
            aviso: str = "Resultado ilustrativo; não representa reconhecimento biométrico real."

        class UserOut(BaseModel):
            id: int
            email: str
            nome: str

        class TokenOut(BaseModel):
            access_token: str
            token_type: str = "bearer"

        class SessionConfig(BaseModel):
            session_idle_minutes: int
            redis_enabled: bool
    ''',
    "app/security.py": r'''
        from datetime import datetime, timedelta, timezone
        from uuid import uuid4

        import bcrypt
        import jwt
        from fastapi import Depends, HTTPException, status
        from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
        from redis import Redis
        from redis.exceptions import RedisError
        from sqlalchemy.orm import Session

        from app.config import settings
        from app.database import get_db
        from app.models import User

        bearer = HTTPBearer(auto_error=False)
        redis_client = Redis.from_url(settings.redis_url, decode_responses=True) if settings.redis_url else None

        def password_hash(password: str) -> str:
            return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        def verify_password(password: str, hashed: str) -> bool:
            return bcrypt.checkpw(password.encode(), hashed.encode())

        def _session_error(exc: RedisError) -> HTTPException:
            return HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Serviço de sessão temporariamente indisponível",
            )

        def create_token(user: User) -> str:
            session_id = uuid4().hex
            expires = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
            token = jwt.encode(
                {"sub": str(user.id), "jti": session_id, "exp": expires},
                settings.jwt_secret,
                algorithm="HS256",
            )
            if redis_client is not None:
                try:
                    redis_client.setex(
                        f"idm:session:{session_id}",
                        settings.idle_minutes * 60,
                        str(user.id),
                    )
                except RedisError as exc:
                    raise _session_error(exc) from exc
            return token

        def current_user(
            credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
            db: Session = Depends(get_db),
        ) -> User:
            if credentials is None or credentials.scheme.lower() != "bearer":
                raise HTTPException(status_code=401, detail="Autenticação necessária")
            try:
                claims = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=["HS256"])
                user_id = int(claims["sub"])
                session_id = str(claims["jti"])
            except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
                raise HTTPException(status_code=401, detail="Token inválido ou expirado") from exc
            if redis_client is not None:
                try:
                    key = f"idm:session:{session_id}"
                    if redis_client.get(key) != str(user_id):
                        raise HTTPException(status_code=401, detail="Sessão encerrada ou expirada")
                    redis_client.expire(key, settings.idle_minutes * 60)
                except RedisError as exc:
                    raise _session_error(exc) from exc
            user = db.get(User, user_id)
            if user is None or not user.active:
                raise HTTPException(status_code=401, detail="Usuário não autorizado")
            return user

        def invalidate_session(token: str) -> None:
            if redis_client is None:
                return
            try:
                claims = jwt.decode(
                    token,
                    settings.jwt_secret,
                    algorithms=["HS256"],
                    options={"verify_exp": False},
                )
                redis_client.delete(f"idm:session:{claims['jti']}")
            except (jwt.PyJWTError, KeyError) as exc:
                raise HTTPException(status_code=401, detail="Token inválido") from exc
            except RedisError as exc:
                raise _session_error(exc) from exc
    ''',
    "app/repositories/__init__.py": "",
    "app/repositories/recenseados.py": r'''
        from sqlalchemy import and_, func, select
        from sqlalchemy.orm import Session

        from app.models import Recenseado

        def listar(
            db: Session,
            *,
            page: int,
            page_size: int,
            query: str | None,
            cpf_hash: str | None,
            status: str | None,
        ) -> tuple[list[Recenseado], int]:
            statement = select(Recenseado)
            count_statement = select(func.count()).select_from(Recenseado)
            filters = []
            if query:
                pattern = f"%{query.strip().lower()}%"
                filters.append(func.lower(Recenseado.nome).like(pattern))
            if cpf_hash:
                filters.append(Recenseado.cpf_hash == cpf_hash)
            if status:
                filters.append(Recenseado.status == status)
            if filters:
                combined = and_(*filters)
                statement = statement.where(combined)
                count_statement = count_statement.where(combined)
            total = db.scalar(count_statement) or 0
            items = db.scalars(
                statement.order_by(Recenseado.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            return list(items), total

        def buscar(db: Session, recenseado_id: int) -> Recenseado | None:
            return db.get(Recenseado, recenseado_id)
    ''',
    "app/services/__init__.py": "",
    "app/services/recenseados.py": r'''
        import hashlib
        import hmac
        from datetime import datetime, time, timezone

        from fastapi import HTTPException
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm import Session

        from app.config import settings
        from app.models import Biometria, Recenseado
        from app.repositories import recenseados as repository
        from app.schemas import RecenseadoCreate, RecenseadoUpdate, mascarar_cpf

        STATUSES = {"PENDENTE", "EM_ANALISE", "RECENSEADO", "REJEITADO"}
        TRANSITIONS = {
            "PENDENTE": {"EM_ANALISE"},
            "EM_ANALISE": {"RECENSEADO", "REJEITADO"},
            "RECENSEADO": set(),
            "REJEITADO": set(),
        }

        def _cpf_hash(cpf: str) -> str:
            return hmac.new(settings.jwt_secret.encode(), cpf.encode(), hashlib.sha256).hexdigest()

        def _get_or_404(db: Session, recenseado_id: int) -> Recenseado:
            person = repository.buscar(db, recenseado_id)
            if person is None:
                raise HTTPException(status_code=404, detail="Recenseado não encontrado")
            return person

        def criar(db: Session, payload: RecenseadoCreate) -> Recenseado:
            person = Recenseado(
                nome=payload.nome,
                cpf_hash=_cpf_hash(payload.cpf),
                cpf_mascarado=mascarar_cpf(payload.cpf),
                sexo=payload.sexo,
                data_nascimento=payload.data_nascimento.isoformat(),
            )
            db.add(person)
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise HTTPException(status_code=409, detail="CPF já cadastrado") from exc
            db.refresh(person)
            return person

        def atualizar(db: Session, recenseado_id: int, payload: RecenseadoUpdate) -> Recenseado:
            person = _get_or_404(db, recenseado_id)
            changes = payload.model_dump(exclude_unset=True)
            if not changes:
                raise HTTPException(status_code=400, detail="Informe ao menos um campo")
            for key, value in changes.items():
                if key == "data_nascimento" and value is not None:
                    value = value.isoformat()
                setattr(person, key, value)
            db.commit()
            db.refresh(person)
            return person

        def excluir(db: Session, recenseado_id: int) -> Recenseado:
            person = _get_or_404(db, recenseado_id)
            db.delete(person)
            db.commit()
            return person

        def alterar_status(db: Session, recenseado_id: int, novo_status: str, motivo: str | None) -> Recenseado:
            person = _get_or_404(db, recenseado_id)
            if novo_status not in TRANSITIONS.get(person.status, set()):
                raise HTTPException(status_code=409, detail=f"Transição inválida: {person.status} -> {novo_status}")
            if novo_status == "REJEITADO" and not (motivo and motivo.strip()):
                raise HTTPException(status_code=400, detail="Informe o motivo da rejeição")
            if novo_status == "RECENSEADO" and not person.foto_path:
                raise HTTPException(status_code=409, detail="Adicione uma foto/documento antes de concluir")
            person.status = novo_status
            db.commit()
            db.refresh(person)
            return person

        def simular_biometria(db: Session, recenseado_id: int, corresponde: bool) -> Biometria:
            person = _get_or_404(db, recenseado_id)
            result = Biometria(
                recenseado_id=person.id,
                resultado="CORRESPONDENTE" if corresponde else "DIVERGENTE",
                assertividade_simulada=96.4 if corresponde else 18.7,
            )
            db.add(result)
            db.commit()
            db.refresh(result)
            return result
    ''',
    "app/routers/__init__.py": "",
    "app/routers/auth.py": r'''
        from fastapi import APIRouter, Depends, HTTPException, status
        from fastapi.security import HTTPAuthorizationCredentials
        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from app.config import settings
        from app.database import get_db
        from app.models import User
        from app.schemas import LoginInput, SessionConfig, TokenOut, UserOut
        from app.security import bearer, current_user, create_token, invalidate_session, password_hash, verify_password

        router = APIRouter(prefix="/api/auth", tags=["autenticação"])

        def ensure_admin(db: Session) -> None:
            if db.scalar(select(User).where(User.email == settings.admin_email)) is None:
                db.add(User(
                    email=settings.admin_email,
                    name="Administrador",
                    password_hash=password_hash(settings.admin_password),
                    active=True,
                ))
                db.commit()

        @router.post("/login", response_model=TokenOut)
        def login(payload: LoginInput, db: Session = Depends(get_db)) -> TokenOut:
            user = db.scalar(select(User).where(User.email == payload.email))
            if user is None or not user.active or not verify_password(payload.password, user.password_hash):
                raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")
            return TokenOut(access_token=create_token(user))

        @router.get("/me", response_model=UserOut)
        def me(user: User = Depends(current_user)) -> UserOut:
            return UserOut(id=user.id, email=user.email, nome=user.name)

        @router.get("/config", response_model=SessionConfig)
        def session_config(user: User = Depends(current_user)) -> SessionConfig:
            return SessionConfig(session_idle_minutes=settings.idle_minutes, redis_enabled=bool(settings.redis_url))

        @router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
        def logout(
            credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
            user: User = Depends(current_user),
        ) -> None:
            if credentials is not None:
                invalidate_session(credentials.credentials)
    ''',
    "app/routers/recenseados.py": r'''
        import hashlib
        import hmac
        import math
        import re
        import uuid
        from pathlib import Path

        from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
        from fastapi.responses import FileResponse
        from sqlalchemy import func, select
        from sqlalchemy.orm import Session

        from app.config import settings
        from app.database import get_db
        from app.models import Biometria, Recenseado, User
        from app.repositories import recenseados as repository
        from app.schemas import PageOut, RecenseadoCreate, RecenseadoOut, RecenseadoUpdate, BiometriaOut, cpf_valido, limpar_cpf
        from app.security import current_user
        from app.services import recenseados as service

        router = APIRouter(prefix="/api/recenseados", tags=["recenseados"])
        ALLOWED_IMAGES = {
            "image/jpeg": (b"\xff\xd8\xff", ".jpg"),
            "image/png": (b"\x89PNG\r\n\x1a\n", ".png"),
        }
        MAX_IMAGE_SIZE = 5 * 1024 * 1024

        def _out(person: Recenseado) -> RecenseadoOut:
            return RecenseadoOut(
                id=person.id,
                nome=person.nome,
                cpf_mascarado=person.cpf_mascarado,
                sexo=person.sexo,
                data_nascimento=person.data_nascimento,
                status=person.status,
                foto_disponivel=bool(person.foto_path),
            )

        @router.get("", response_model=PageOut)
        def listar(
            q: str | None = None,
            status_filtro: str | None = Query(default=None, pattern="^(PENDENTE|EM_ANALISE|RECENSEADO|REJEITADO)$"),
            page: int = Query(default=1, ge=1),
            page_size: int = Query(default=12, ge=1, le=100),
            db: Session = Depends(get_db),
            user: User = Depends(current_user),
        ) -> PageOut:
            cpf_digest = None
            query = q.strip() if q and q.strip() else None
            if query and re.fullmatch(r"[\d.\-\s]+", query):
                digits = limpar_cpf(query)
                if len(digits) == 11:
                    if not cpf_valido(digits):
                        raise HTTPException(status_code=400, detail="CPF inválido")
                    cpf_digest = hmac.new(settings.jwt_secret.encode(), digits.encode(), hashlib.sha256).hexdigest()
                    query = None
            items, total = repository.listar(
                db, page=page, page_size=page_size, query=query,
                cpf_hash=cpf_digest, status=status_filtro,
            )
            return PageOut(
                items=[_out(item) for item in items],
                total=total,
                page=page,
                page_size=page_size,
                pages=math.ceil(total / page_size) if total else 0,
            )

        @router.post("", response_model=RecenseadoOut, status_code=status.HTTP_201_CREATED)
        def criar(
            payload: RecenseadoCreate,
            db: Session = Depends(get_db),
            user: User = Depends(current_user),
        ) -> RecenseadoOut:
            return _out(service.criar(db, payload))

        @router.get("/{recenseado_id}", response_model=RecenseadoOut)
        def obter(
            recenseado_id: int,
            db: Session = Depends(get_db),
            user: User = Depends(current_user),
        ) -> RecenseadoOut:
            person = repository.buscar(db, recenseado_id)
            if person is None:
                raise HTTPException(status_code=404, detail="Recenseado não encontrado")
            return _out(person)

        @router.put("/{recenseado_id}", response_model=RecenseadoOut)
        def atualizar(
            recenseado_id: int,
            payload: RecenseadoUpdate,
            db: Session = Depends(get_db),
            user: User = Depends(current_user),
        ) -> RecenseadoOut:
            return _out(service.atualizar(db, recenseado_id, payload))

        @router.delete("/{recenseado_id}", status_code=status.HTTP_204_NO_CONTENT)
        def excluir(
            recenseado_id: int,
            db: Session = Depends(get_db),
            user: User = Depends(current_user),
        ) -> None:
            person = service.excluir(db, recenseado_id)
            if person.foto_path:
                Path(person.foto_path).unlink(missing_ok=True)

        @router.post("/{recenseado_id}/foto", response_model=RecenseadoOut)
        async def upload_foto(
            recenseado_id: int,
            arquivo: UploadFile = File(...),
            db: Session = Depends(get_db),
            user: User = Depends(current_user),
        ) -> RecenseadoOut:
            person = repository.buscar(db, recenseado_id)
            if person is None:
                raise HTTPException(status_code=404, detail="Recenseado não encontrado")
            content = await arquivo.read(MAX_IMAGE_SIZE + 1)
            if not content or len(content) > MAX_IMAGE_SIZE:
                raise HTTPException(status_code=413, detail="A imagem deve ter até 5 MB")
            image = ALLOWED_IMAGES.get(arquivo.content_type or "")
            if image is None or not content.startswith(image[0]):
                raise HTTPException(status_code=400, detail="Envie uma imagem JPG ou PNG válida")
            settings.upload_dir.mkdir(parents=True, exist_ok=True)
            path = settings.upload_dir / f"{uuid.uuid4().hex}{image[1]}"
            path.write_bytes(content)
            previous = person.foto_path
            person.foto_path = str(path)
            db.commit()
            db.refresh(person)
            if previous:
                Path(previous).unlink(missing_ok=True)
            return _out(person)

        @router.get("/{recenseado_id}/foto")
        def foto(
            recenseado_id: int,
            db: Session = Depends(get_db),
            user: User = Depends(current_user),
        ) -> FileResponse:
            person = repository.buscar(db, recenseado_id)
            if person is None or not person.foto_path or not Path(person.foto_path).is_file():
                raise HTTPException(status_code=404, detail="Foto não encontrada")
            return FileResponse(person.foto_path)

        @router.post("/{recenseado_id}/biometria-simulada", response_model=BiometriaOut)
        def biometria(
            recenseado_id: int,
            corresponde: bool = Query(...),
            db: Session = Depends(get_db),
            user: User = Depends(current_user),
        ) -> BiometriaOut:
            result = service.simular_biometria(db, recenseado_id, corresponde)
            return BiometriaOut(
                resultado=result.resultado,
                assertividade_simulada=result.assertividade_simulada,
            )

        @router.post("/{recenseado_id}/status", response_model=RecenseadoOut)
        def status(
            recenseado_id: int,
            novo_status: str = Query(..., pattern="^(EM_ANALISE|RECENSEADO|REJEITADO)$"),
            motivo: str | None = None,
            db: Session = Depends(get_db),
            user: User = Depends(current_user),
        ) -> RecenseadoOut:
            return _out(service.alterar_status(db, recenseado_id, novo_status, motivo))
    ''',
    "app/routers/dashboard.py": r'''
        import csv
        from io import StringIO
        import re

        from fastapi import APIRouter, Depends
        from fastapi.responses import Response
        from sqlalchemy import func, select
        from sqlalchemy.orm import Session

        from app.database import get_db
        from app.models import Biometria, Recenseado, User
        from app.security import current_user

        router = APIRouter(prefix="/api", tags=["painel e relatórios"])

        @router.get("/dashboard")
        def dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict[str, object]:
            total = db.scalar(select(func.count()).select_from(Recenseado)) or 0
            rows = db.execute(select(Recenseado.status, func.count()).group_by(Recenseado.status)).all()
            validated = db.scalar(
                select(func.count(func.distinct(Biometria.recenseado_id)))
                .where(Biometria.resultado == "CORRESPONDENTE")
            ) or 0
            return {
                "total": total,
                "pendentes": next((count for key, count in rows if key == "PENDENTE"), 0),
                "biometrias_simuladas": validated,
                "por_status": dict(rows),
            }

        @router.get("/relatorios/recenseados.csv")
        def csv_report(db: Session = Depends(get_db), user: User = Depends(current_user)) -> Response:
            people = db.scalars(select(Recenseado).order_by(Recenseado.id)).all()
            output = StringIO()
            writer = csv.writer(output)
            writer.writerow(["ID", "Nome", "CPF", "Sexo", "Nascimento", "Status"])
            for person in people:
                name = person.nome
                if re.match(r"^\s*[=+\-@]", name):
                    name = "'" + name
                writer.writerow([
                    person.id, name, person.cpf_mascarado, person.sexo,
                    person.data_nascimento, person.status,
                ])
            return Response(
                "\\ufeff" + output.getvalue(),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": 'attachment; filename="relatorio-recenseados.csv"'},
            )
    ''',
    "app/main.py": r'''
        from contextlib import asynccontextmanager
        from pathlib import Path

        from fastapi import FastAPI
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        from app.config import settings
        from app.database import Base, SessionLocal, engine
        from app.models import Biometria, Recenseado, User  # noqa: F401
        from app.routers import auth, dashboard, recenseados
        from app.routers.auth import ensure_admin

        FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            settings.validate()
            settings.upload_dir.mkdir(parents=True, exist_ok=True)
            Base.metadata.create_all(bind=engine)
            db = SessionLocal()
            try:
                ensure_admin(db)
            finally:
                db.close()
            yield

        app = FastAPI(
            title="Portal IDM - Censo Previdenciário",
            version="1.0.0",
            lifespan=lifespan,
        )
        app.include_router(auth.router)
        app.include_router(recenseados.router)
        app.include_router(dashboard.router)
        app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(FRONTEND / "index.html")

        @app.get("/health")
        def health() -> dict[str, str]:
            return {"status": "ok"}
    ''',
}

FRONTEND_FILES = {
    "frontend/index.html": r'''
        <!doctype html>
        <html lang="pt-BR">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <meta name="theme-color" content="#153a6b">
            <title>Portal IDM | Censo Previdenciário</title>
            <link rel="stylesheet" href="/static/styles.css">
            <link rel="stylesheet" href="/static/tailwind.generated.css">
        </head>
        <body>
            <section id="login-view" class="login-view" hidden>
                <form id="login-form" class="login-card">
                    <div class="brand-lockup"><span class="brand-symbol">IDM</span><div><strong>Portal de Identidade</strong><small>Censo Previdenciário</small></div></div>
                    <h1>Acessar o sistema</h1>
                    <p class="muted">Entre com suas credenciais institucionais.</p>
                    <label for="login-email">E-mail</label><input id="login-email" type="email" required autocomplete="username">
                    <label for="login-password">Senha</label><input id="login-password" type="password" required autocomplete="current-password">
                    <p id="login-error" class="form-error" role="alert" hidden></p>
                    <button class="button button-primary full-width" type="submit">Entrar</button>
                    <small class="login-footnote">Credenciais iniciais definidas no arquivo .env.</small>
                </form>
            </section>

            <div id="application" hidden>
                <header class="topbar">
                    <a class="brand-lockup" href="/" aria-label="Portal IDM, início">
                        <span class="brand-symbol">IDM</span><span class="brand-copy"><strong>Identity Management</strong><small>Censo Previdenciário</small></span>
                    </a>
                    <nav id="main-nav" class="main-nav" aria-label="Navegação principal">
                        <button class="nav-tab active" data-view="painel" aria-current="page">Painel</button>
                        <button class="nav-tab" data-view="aplicativos">Aplicativos</button>
                        <button class="nav-tab" data-view="tarefas">Tarefas</button>
                        <button class="nav-tab" data-view="acessar">Acessar</button>
                        <button class="nav-tab" data-view="pessoas">Pessoas</button>
                        <button class="nav-tab" data-view="administracao">Administração</button>
                    </nav>
                    <div class="account-actions">
                        <span class="user-name" id="user-name">Operador</span>
                        <button id="settings-open" class="icon-action" type="button" aria-label="Abrir configurações" title="Configurações">
                            <svg aria-hidden="true" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="m19.4 15 .1.1 1.4 1.1-1.4 2.4-1.7-.7a8 8 0 0 1-1.4.8l-.3 1.8h-2.8l-.3-1.8a8 8 0 0 1-1.4-.8l-1.7.7-1.4-2.4 1.4-1.1a7 7 0 0 1 0-1.8l-1.4-1.1 1.4-2.4 1.7.7a8 8 0 0 1 1.4-.8l.3-1.8h2.8l.3 1.8a8 8 0 0 1 1.4.8l1.7-.7 1.4 2.4-1.4 1.1a7 7 0 0 1 0 1.8z"/></svg>
                        </button>
                        <button id="logout-button" class="button button-light" type="button">Sair</button>
                    </div>
                </header>

                <main class="workspace">
                    <div id="notice" class="notice" role="status" hidden></div>
                    <div class="page-heading">
                        <div><p class="eyebrow">Portal IDM</p><h1 id="page-title">Painel</h1><p id="page-description">Visão geral do Censo Previdenciário.</p></div>
                        <button id="refresh-button" class="button button-outline" type="button">
                            <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M20 7v5h-5M4 17v-5h5"/><path d="M5.6 9a7 7 0 0 1 11.6-2L20 12M4 12l2.8 5a7 7 0 0 0 11.6-2"/></svg>Atualizar
                        </button>
                    </div>

                    <section class="view" id="view-painel">
                        <div class="metric-grid">
                            <article class="metric-card"><span>Recenseados</span><strong id="metric-total">0</strong><small>Total de cadastros</small></article>
                            <article class="metric-card"><span>Pendentes</span><strong id="metric-pending">0</strong><small>Aguardando análise</small></article>
                            <article class="metric-card"><span>Biometria simulada</span><strong id="metric-biometric">0</strong><small>Correspondências registradas</small></article>
                            <article class="metric-card"><span>Atendimento</span><strong id="metric-complete">0%</strong><small>Cadastros concluídos</small></article>
                        </div>
                        <div class="content-grid">
                            <section class="surface chart-surface"><div class="section-title"><div><p class="eyebrow">Indicadores</p><h2>Status dos recenseados</h2></div><span class="subtle">Atualização automática</span></div><div id="status-chart" class="status-chart"></div></section>
                            <section class="surface quick-panel"><div class="section-title"><div><p class="eyebrow">Acesso rápido</p><h2>Atalhos operacionais</h2></div></div>
                                <button class="quick-link" data-go="pessoas">Gerenciar recenseados <span>›</span></button>
                                <button class="quick-link" data-go="tarefas">Consultar tarefas <span>›</span></button>
                                <button class="quick-link" data-go="aplicativos">Abrir aplicativos <span>›</span></button>
                            </section>
                        </div>
                        <section class="surface terminal-surface">
                            <div class="section-title"><div><p class="eyebrow">Ferramentas</p><h2>Terminal do operador</h2></div><span class="subtle">Execução restrita a comandos permitidos</span></div>
                            <div id="terminal-output" class="terminal-output" aria-live="polite"></div>
                            <form id="terminal-form" class="terminal-form"><label for="terminal-input">operador@idm:</label><input id="terminal-input" autocomplete="off" spellcheck="false" placeholder="Digite ajuda para listar comandos"><button class="button button-light" type="submit">Executar</button></form>
                        </section>
                        <p class="disclaimer">A validação facial é simulada e não realiza reconhecimento biométrico real.</p>
                    </section>

                    <section class="view" id="view-aplicativos" hidden>
                        <section class="surface"><div class="section-title"><div><p class="eyebrow">Catálogo institucional</p><h2>Aplicativos</h2></div><label class="search-box"><span class="visually-hidden">Pesquisar aplicativos</span><svg aria-hidden="true" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg><input id="app-search" type="search" placeholder="Pesquisar por nome ou descrição"></label></div>
                            <h3 class="group-title">Aplicativos da página inicial</h3><div id="application-cards" class="application-grid"></div>
                        </section>
                    </section>

                    <section class="view" id="view-tarefas" hidden>
                        <section class="surface"><div class="section-title"><div><p class="eyebrow">Fluxo de trabalho</p><h2>Tarefas</h2></div></div>
                            <div class="task-list"><article class="task-row"><span class="task-marker"></span><div><strong>Recenseamentos pendentes</strong><p>Cadastros que aguardam análise documental.</p></div><strong id="task-pending">0</strong></article>
                            <article class="task-row"><span class="task-marker marker-blue"></span><div><strong>Cadastros em análise</strong><p>Processos em revisão pelo operador.</p></div><strong id="task-review">0</strong></article></div>
                        </section>
                    </section>

                    <section class="view" id="view-acessar" hidden>
                        <section class="surface"><div class="section-title"><div><p class="eyebrow">Solicitações e permissões</p><h2>Acessar</h2></div></div><div class="application-grid">
                            <button class="application-card" data-go="pessoas"><span class="card-icon" data-icon="person"></span><strong>Consultar pessoa</strong><small>Pesquisar e consultar cadastro previdenciário.</small></button>
                            <button class="application-card" data-go="administracao"><span class="card-icon" data-icon="access"></span><strong>Solicitar acesso</strong><small>Consultar acessos e recursos administrativos.</small></button>
                            <button class="application-card" data-go="tarefas"><span class="card-icon" data-icon="task"></span><strong>Minhas tarefas</strong><small>Acompanhar atividades pendentes.</small></button>
                        </div></section>
                    </section>

                    <section class="view" id="view-pessoas" hidden>
                        <section class="surface people-surface"><div class="section-title"><div><p class="eyebrow">Base cadastral</p><h2>Recenseados</h2></div><button id="add-person" class="button button-primary" type="button"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>Novo recenseado</button></div>
                            <form id="people-filter" class="filter-row"><label class="search-box"><span class="visually-hidden">Buscar por nome ou CPF</span><svg aria-hidden="true" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg><input id="people-query" type="search" placeholder="Buscar por nome ou CPF"></label>
                            <select id="people-status" aria-label="Filtrar por status"><option value="">Todos os status</option><option>PENDENTE</option><option>EM_ANALISE</option><option>RECENSEADO</option><option>REJEITADO</option></select><button class="button button-outline" type="submit">Filtrar</button></form>
                            <div class="table-wrap"><table><thead><tr><th>Nome e CPF</th><th>Sexo</th><th>Nascimento</th><th>Status</th><th>Ações</th></tr></thead><tbody id="people-rows"><tr><td colspan="5" class="empty-state">Carregando dados...</td></tr></tbody></table></div>
                            <div class="pagination"><button id="previous-page" class="button button-outline" type="button">Anterior</button><span id="page-label"></span><button id="next-page" class="button button-outline" type="button">Próxima</button></div>
                        </section>
                    </section>

                    <section class="view" id="view-administracao" hidden>
                        <section class="surface"><div class="section-title"><div><p class="eyebrow">Governança</p><h2>Administração</h2></div></div>
                            <div class="application-grid admin-grid">
                                <button class="application-card" data-go="pessoas"><span class="card-icon" data-icon="team"></span><strong>Gerenciar equipes</strong><small>Organizar filas de atendimento.</small></button>
                                <button class="application-card" data-go="pessoas"><span class="card-icon" data-icon="resource"></span><strong>Atribuir recursos</strong><small>Distribuir recursos para análise.</small></button>
                                <button class="application-card" data-go="tarefas"><span class="card-icon" data-icon="user"></span><strong>Identidades e tarefas</strong><small>Acompanhar atividade operacional.</small></button>
                                <button class="application-card" data-go="relatorios"><span class="card-icon" data-icon="report"></span><strong>Relatórios de identidade</strong><small>Gerar relatório consolidado do censo.</small></button>
                            </div>
                        </section>
                        <section class="surface report-surface"><div class="section-title"><div><p class="eyebrow">Dados consolidados</p><h2>Relatórios</h2></div></div><p class="muted">Exportação CSV com CPF mascarado ou impressão do relatório final em PDF.</p><div class="button-row"><button id="export-csv" class="button button-primary" type="button">Exportar CSV</button><button id="export-pdf" class="button button-outline" type="button">Gerar PDF</button></div></section>
                    </section>
                </main>
            </div>

            <dialog id="person-dialog" class="dialog"><form id="person-form"><div class="dialog-heading"><div><p class="eyebrow">Cadastro previdenciário</p><h2 id="person-dialog-title">Novo recenseado</h2></div><button class="icon-action" type="button" data-close="person-dialog" aria-label="Fechar"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="m18 6-12 12M6 6l12 12"/></svg></button></div>
                <input id="person-id" type="hidden"><label for="person-name">Nome completo</label><input id="person-name" required minlength="2" maxlength="150"><div id="cpf-field"><label for="person-cpf">CPF</label><input id="person-cpf" inputmode="numeric" required placeholder="000.000.000-00"></div>
                <div class="form-grid"><div><label for="person-sex">Sexo</label><select id="person-sex"><option>FEMININO</option><option>MASCULINO</option><option>OUTRO</option></select></div><div><label for="person-birth">Nascimento</label><input id="person-birth" type="date" required></div></div>
                <label for="person-photo">Foto de rosto ou documento (JPG/PNG, até 5 MB)</label><input id="person-photo" type="file" accept="image/png,image/jpeg" capture="user"><img id="photo-preview" class="photo-preview" alt="Pré-visualização da imagem" hidden>
                <div class="dialog-actions"><button class="button button-outline" type="button" data-close="person-dialog">Cancelar</button><button class="button button-primary" type="submit">Salvar</button></div></form></dialog>

            <dialog id="settings-dialog" class="dialog settings-dialog"><div class="dialog-heading"><div><p class="eyebrow">Preferências pessoais</p><h2>Configurações</h2></div><button class="icon-action" type="button" data-close="settings-dialog" aria-label="Fechar"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="m18 6-12 12M6 6l12 12"/></svg></button></div>
                <label for="theme-select">Tema da interface</label><select id="theme-select"><option value="light">Claro</option><option value="dark">Escuro</option></select><label for="idle-select">Bloquear após inatividade</label><select id="idle-select"><option value="1">1 minuto</option><option value="5">5 minutos</option><option value="10">10 minutos</option><option value="15">15 minutos</option></select><p class="muted">O desbloqueio requer nova autenticação.</p></dialog>
            <dialog id="photo-dialog" class="dialog photo-dialog"><button class="icon-action" type="button" data-close="photo-dialog" aria-label="Fechar"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="m18 6-12 12M6 6l12 12"/></svg></button><img id="photo-full" alt="Foto ou documento do recenseado"></dialog>
            <dialog id="confirm-dialog" class="dialog"><form id="confirm-form"><div class="dialog-heading"><div><p class="eyebrow">Confirmação</p><h2 id="confirm-title">Confirmar ação</h2></div><button class="icon-action" type="button" data-close="confirm-dialog" aria-label="Fechar"><svg aria-hidden="true" viewBox="0 0 24 24"><path d="m18 6-12 12M6 6l12 12"/></svg></button></div><p id="confirm-copy" class="muted"></p><label id="reason-label" for="confirm-reason" hidden>Motivo da rejeição</label><textarea id="confirm-reason" rows="3" maxlength="500" hidden></textarea><div class="dialog-actions"><button id="confirm-cancel" class="button button-outline" type="button">Cancelar</button><button id="confirm-submit" class="button button-primary" type="submit">Confirmar</button></div></form></dialog>
            <section id="lock-screen" class="lock-screen" hidden><form id="unlock-form" class="login-card"><div class="brand-lockup"><span class="brand-symbol">IDM</span><div><strong>Sessão bloqueada</strong><small>Reautentique para continuar</small></div></div><label for="unlock-email">E-mail</label><input id="unlock-email" type="email" required autocomplete="username"><label for="unlock-password">Senha</label><input id="unlock-password" type="password" required autocomplete="current-password"><p id="unlock-error" class="form-error" hidden></p><button class="button button-primary full-width" type="submit">Desbloquear</button></form></section>
            <script type="module" src="/static/app.js"></script>
        </body></html>
    ''',
    "frontend/styles.css": r'''
        :root{font-family:Inter,"Segoe UI",Arial,sans-serif;color:#1f2937;background:#f5f7f8;font-synthesis:none;text-rendering:optimizeLegibility;--bg:#f5f7f8;--surface:#fff;--tile:#edf2f2;--text:#202b36;--muted:#6b7785;--border:#d8e0e5;--blue:#007ab8;--blue-dark:#155278;--danger:#b42318}
        *{box-sizing:border-box}body{margin:0;min-height:100vh;background:var(--bg);color:var(--text);font-size:14px}button,input,select,textarea{font:inherit}button{cursor:pointer}[hidden]{display:none!important}
        .topbar{height:58px;background:#edf2f2;border-bottom:1px solid #dce3e5;display:flex;align-items:stretch;padding:0 24px;gap:26px;position:sticky;top:0;z-index:5}
        .brand-lockup{display:flex;align-items:center;gap:10px;color:inherit;text-decoration:none;flex:none}.brand-symbol{display:grid;place-items:center;width:34px;height:34px;background:#fff;color:var(--blue-dark);border:1px solid #d7e2e8;border-radius:5px;font-size:12px;font-weight:800;letter-spacing:.04em}.brand-copy,.brand-lockup>div{display:grid;gap:2px}.brand-lockup strong{font-size:12px}.brand-lockup small{font-size:10px;color:var(--muted)}
        .main-nav{display:flex;align-items:stretch;gap:3px;overflow-x:auto}.nav-tab{position:relative;white-space:nowrap;border:0;background:transparent;color:#4b5563;padding:0 13px;font-size:13px}.nav-tab:hover,.nav-tab.active{color:#172b3a}.nav-tab.active{font-weight:650}.nav-tab.active:after{position:absolute;content:"";height:2px;bottom:0;left:8px;right:8px;background:var(--blue)}
        .account-actions{margin-left:auto;display:flex;align-items:center;gap:10px}.user-name{font-size:12px;color:#475569}.icon-action{display:grid;place-items:center;width:36px;height:36px;background:transparent;color:#526575;border:0;border-radius:6px}.icon-action:hover{background:#dfe8eb}.icon-action svg,.button svg,.search-box svg{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
        .workspace{max-width:1500px;margin:0 auto;padding:26px 28px 56px}.page-heading{display:flex;align-items:center;justify-content:space-between;margin-bottom:22px;gap:18px}.eyebrow{margin:0 0 5px;text-transform:uppercase;letter-spacing:.1em;font-size:10px;font-weight:700;color:var(--blue)}.page-heading h1{font-size:25px;margin:0 0 4px;font-weight:600}.page-heading p:not(.eyebrow){margin:0;color:var(--muted);font-size:12px}
        .button{min-height:38px;padding:8px 13px;border:1px solid transparent;border-radius:5px;display:inline-flex;align-items:center;justify-content:center;gap:8px;font-size:12px;font-weight:600}.button-primary{background:var(--blue);color:#fff}.button-primary:hover{background:#00689e}.button-outline{background:var(--surface);border-color:#cdd7de;color:#334155}.button-outline:hover{background:#f8fafc}.button-light{background:#fff;color:#334155;border-color:#d6e0e5}.full-width{width:100%}
        .metric-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.metric-card,.surface{background:var(--surface);border:1px solid #e0e5e8;border-radius:6px}.metric-card{padding:18px 20px;display:grid;gap:8px;min-height:116px}.metric-card span{font-size:12px;color:#4b5966;font-weight:600}.metric-card strong{font-size:27px;font-weight:650;letter-spacing:-.03em;font-variant-numeric:tabular-nums}.metric-card small{font-size:11px;color:var(--muted)}
        .content-grid{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(250px,1fr);gap:14px;margin-top:16px}.surface{padding:20px}.section-title{display:flex;justify-content:space-between;align-items:center;gap:14px;margin-bottom:18px}.section-title h2{font-size:16px;font-weight:600;margin:0}.subtle,.muted{color:var(--muted);font-size:11px}.status-chart{display:grid;gap:14px}.chart-row{display:grid;grid-template-columns:125px 1fr 30px;align-items:center;gap:12px;font-size:11px}.chart-track{height:8px;background:#e8eef1;border-radius:10px;overflow:hidden}.chart-track span{height:100%;display:block;background:var(--blue);border-radius:inherit}.quick-panel{display:flex;flex-direction:column}.quick-link{background:transparent;border:0;border-top:1px solid #edf0f2;padding:13px 2px;text-align:left;color:#334155;font-size:12px;display:flex;justify-content:space-between}.quick-link span{font-size:20px;color:var(--blue);line-height:12px}
        .terminal-surface{margin-top:16px;background:#142230;color:#d9e3eb;border-color:#243748}.terminal-surface .section-title h2{color:#f8fafc}.terminal-surface .eyebrow{color:#72c6ed}.terminal-output{height:112px;overflow:auto;background:#0d1822;border:1px solid #263a4b;border-radius:4px;padding:10px 12px;font:11px/1.6 ui-monospace,Menlo,monospace}.terminal-output p{margin:0 0 3px}.terminal-command{color:#9edbff}.terminal-error{color:#ffb4a9}.terminal-form{margin-top:9px;display:flex;align-items:center;gap:8px}.terminal-form label{color:#8ed6ac;font:11px ui-monospace,Menlo,monospace;white-space:nowrap}.terminal-form input{flex:1;min-width:80px;background:#0d1822;border:1px solid #34495a;border-radius:4px;color:#fff;padding:9px}.disclaimer{text-align:right;font-size:10px;color:var(--muted);margin:10px 0}
        .application-grid{display:grid;grid-template-columns:repeat(7,minmax(120px,1fr));gap:8px}.application-card{min-height:145px;background:var(--tile);border:1px solid transparent;border-radius:3px;padding:14px 10px 11px;text-align:center;display:flex;align-items:center;flex-direction:column;gap:6px;color:#17212b}.application-card:hover{border-color:#8ec9e7;background:#e5f1f5}.card-icon{height:52px;width:58px;color:#008bd0;display:grid;place-items:center}.card-icon svg{height:48px;width:48px;fill:none;stroke:currentColor;stroke-width:1.45;stroke-linecap:round;stroke-linejoin:round}.application-card strong{font-size:12px;line-height:1.35}.application-card small{font-size:10px;color:#687789;line-height:1.4}.group-title{font-size:13px;font-weight:500;margin:20px 0 9px}.search-box{position:relative;display:flex;align-items:center;min-width:235px}.search-box svg{position:absolute;left:10px;color:#8292a0;width:15px;height:15px}.search-box input{width:100%;padding-left:33px}.filter-row{display:flex;gap:9px;margin:12px 0 16px}.filter-row .search-box{flex:1}
        input,select,textarea{background:var(--surface);color:var(--text);border:1px solid #cbd5dc;border-radius:4px;padding:9px 10px;min-height:38px}input:focus,select:focus,textarea:focus{outline:2px solid #8bc7e4;outline-offset:1px}select{min-width:170px}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;min-width:720px;text-align:left}th,td{border-bottom:1px solid #e8edef;padding:11px 9px;font-size:11px;vertical-align:middle}th{font-size:10px;color:#667482;text-transform:uppercase;letter-spacing:.05em;font-weight:650}td small{display:block;color:var(--muted);margin-top:3px}.badge{display:inline-block;padding:4px 8px;border-radius:12px;background:#e8f4fa;color:#12638c;font-size:9px;font-weight:700}.actions{display:flex;flex-wrap:wrap;gap:3px 7px}.text-button{border:0;background:transparent;color:#006fa8;font-size:10px;padding:3px}.text-button.danger{color:var(--danger)}.pagination{display:flex;justify-content:space-between;align-items:center;padding-top:13px;color:var(--muted);font-size:11px}.empty-state{text-align:center;color:var(--muted);padding:26px}.task-list{display:grid}.task-row{display:flex;align-items:center;gap:12px;padding:14px 2px;border-top:1px solid #edf0f2}.task-row div{flex:1}.task-row strong{font-size:12px}.task-row p{margin:4px 0 0;font-size:10px;color:var(--muted)}.task-row>strong{font-variant-numeric:tabular-nums}.task-marker{width:8px;height:8px;border-radius:50%;background:#c58c21}.marker-blue{background:#1689be}
        .report-surface{margin-top:16px}.button-row{display:flex;gap:9px}.notice{padding:11px 14px;border:1px solid #a7d8b8;border-radius:5px;background:#edf9f0;color:#176737;font-size:12px;margin-bottom:14px}.notice.error,.form-error{color:#a12720;background:#fff1f0;border-color:#f1c0bc}.form-error{padding:9px;border-radius:4px;font-size:11px}.dialog{width:min(520px,calc(100% - 24px));max-height:90vh;overflow:auto;border:1px solid var(--border);border-radius:7px;padding:22px;background:var(--surface);color:var(--text);box-shadow:0 20px 70px #0f172a44}.dialog::backdrop{background:#16243388}.dialog form{display:grid;gap:9px}.dialog-heading{display:flex;align-items:center;justify-content:space-between;margin-bottom:7px}.dialog-heading h2{font-size:19px;margin:0}.dialog label,.login-card label{font-size:11px;font-weight:650}.dialog-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:8px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.form-grid>div{display:grid;gap:7px}.photo-preview{width:100%;max-height:160px;object-fit:contain;background:var(--tile);border-radius:4px}.photo-dialog{width:min(800px,calc(100% - 24px))}.photo-dialog>.icon-action{margin-left:auto}.photo-dialog img{display:block;max-width:100%;max-height:72vh;margin:auto;object-fit:contain}.settings-dialog{width:min(400px,calc(100% - 24px));display:grid;gap:10px}.settings-dialog .dialog-heading{margin-bottom:6px}
        .login-view,.lock-screen{position:fixed;inset:0;z-index:10;display:grid;place-items:center;background:#eff3f5;padding:20px}.lock-screen{background:#142230ed;z-index:20}.login-card{display:grid;gap:10px;width:min(390px,100%);background:var(--surface);border:1px solid var(--border);border-radius:7px;padding:28px;box-shadow:0 16px 50px #12283b18}.login-card h1{font-size:21px;margin:8px 0 0}.login-card>.muted{margin:0 0 8px}.login-footnote{font-size:10px;color:var(--muted);text-align:center;margin-top:6px}.visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}.full-width{width:100%}
        body.dark{color-scheme:dark;--bg:#111a24;--surface:#1b2733;--tile:#243440;--text:#e3eaf0;--muted:#a3b2bf;--border:#344452;background:var(--bg);color:var(--text)}body.dark .topbar{background:#172530;border-color:#334554}body.dark .nav-tab{color:#b4c2cd}body.dark .nav-tab.active{color:#fff}body.dark .metric-card,body.dark .surface{border-color:#344452}body.dark .quick-link{color:#dce5eb;border-color:#334452}body.dark .application-card{color:#e5edf2}body.dark .application-card small{color:#b3c1cb}body.dark th,body.dark td{border-color:#344452}body.dark .button-outline{background:#1b2733;color:#e3eaf0;border-color:#435363}body.dark .badge{background:#173b50;color:#b5e5f7}body.dark .login-view{background:#111a24}
        @media(max-width:1050px){.topbar{gap:10px;padding:0 14px}.nav-tab{padding:0 9px;font-size:11px}.brand-copy{display:none}.application-grid{grid-template-columns:repeat(4,minmax(120px,1fr))}}
        @media(max-width:720px){.topbar{height:auto;min-height:58px;flex-wrap:wrap;gap:0;padding:0 10px}.brand-lockup{height:52px}.main-nav{order:3;width:100%;height:43px}.account-actions{height:52px}.user-name{display:none}.workspace{padding:20px 14px 40px}.page-heading{align-items:flex-start}.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.metric-card{padding:14px;min-height:100px}.metric-card strong{font-size:23px}.content-grid{grid-template-columns:1fr}.application-grid{grid-template-columns:repeat(3,minmax(90px,1fr))}.section-title{align-items:flex-start;flex-wrap:wrap}.filter-row{flex-wrap:wrap}.filter-row .search-box{flex-basis:100%}.filter-row select{flex:1}.subtle{display:none}}
        @media(max-width:420px){.application-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.terminal-form{flex-wrap:wrap}.terminal-form input{order:2;flex-basis:100%}.terminal-form label{order:1}.terminal-form button{order:3}.form-grid{grid-template-columns:1fr}.page-heading h1{font-size:21px}}
        @media print{.topbar,.page-heading button,.main-nav,.account-actions,.terminal-surface,.quick-panel,.button,.disclaimer{display:none!important}.workspace{padding:0}.view[hidden]{display:none!important}.surface,.metric-card{box-shadow:none;background:#fff;color:#111;border-color:#ccc}}
    ''',
    "frontend/app.js": r'''
        import { api, json, downloadCsv } from "./modules/api.js";
        import { mountTerminal } from "./modules/terminal.js";

        const $ = (selector) => document.querySelector(selector);
        const state = { user: null, view: "painel", page: 1, pageSize: 12, query: "", status: "", timer: null, resolveConfirm: null };
        let idleListenersBound = false;
        const descriptions = {
            painel: ["Painel", "Visão geral do Censo Previdenciário."],
            aplicativos: ["Aplicativos", "Acesse os recursos e serviços institucionais."],
            tarefas: ["Tarefas", "Acompanhe os processos pendentes de análise."],
            acessar: ["Acessar", "Consulte recursos e solicite acesso."],
            pessoas: ["Pessoas", "Consulte e gerencie os cadastros previdenciários."],
            administracao: ["Administração", "Gerencie recursos e relatórios do sistema."],
        };
        const iconPaths = {
            user: '<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2z"/>',
            dashboard: '<rect x="3" y="3" width="8" height="8" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="11" width="7" height="10" rx="1"/><rect x="3" y="14" width="8" height="7" rx="1"/>',
            task: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
            access: '<path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11z"/><path d="m9 12 2 2 4-4"/>',
            history: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>',
            person: '<path d="M16 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="10" cy="7" r="4"/><path d="M20 21v-2a4 4 0 0 0-3-3.8"/>',
            team: '<circle cx="9" cy="8" r="4"/><path d="M2 21v-2a7 7 0 0 1 14 0v2M17 4a4 4 0 0 1 0 8m5 9v-2a7 7 0 0 0-4-6"/>',
            resource: '<path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
            report: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 13h8M8 17h8"/>',
            applications: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
            profile: '<rect x="4" y="3" width="16" height="18" rx="2"/><circle cx="12" cy="9" r="3"/><path d="M8 17a4 4 0 0 1 8 0"/>',
        };
        const catalog = [
            ["Role Manager", "Delegar e gerenciar funções de acesso.", "team", "administracao"],
            ["Painel", "Navegar para o painel do Censo.", "dashboard", "painel"],
            ["Minhas Aprovações", "Revisar tarefas aguardando aprovação.", "task", "tarefas"],
            ["Solicitar Acesso", "Consultar solicitações e recursos.", "access", "acessar"],
            ["Meu Histórico", "Consultar atividades recentes.", "history", "tarefas"],
            ["Meu Acesso", "Visualizar recursos associados.", "access", "acessar"],
            ["Meu Perfil", "Consultar perfil da conta.", "profile", "administracao"],
            ["Mudar Minha Senha", "Acessar preferências de segurança.", "history", "administracao"],
            ["Organograma", "Consultar estrutura de atendimento.", "team", "administracao"],
            ["Laptop", "Recurso institucional.", "applications", "acessar"],
            ["Headset", "Recurso institucional.", "applications", "acessar"],
            ["Access Review", "Revisar permissões e solicitações.", "report", "administracao"],
        ];
        function escapeHtml(value) { return String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
        function icon(name) { return `<svg viewBox="0 0 24 24" aria-hidden="true">${iconPaths[name] || iconPaths.applications}</svg>`; }
        function notice(message, error = false) { const el = $("#notice"); el.textContent = message; el.classList.toggle("error", error); el.hidden = false; setTimeout(() => { el.hidden = true; }, 5000); }
        function setTheme(theme) { document.body.classList.toggle("dark", theme === "dark"); localStorage.setItem("idm-theme", theme); $("#theme-select").value = theme; }
        function showView(name) {
            if (name === "relatorios") name = "administracao";
            if (!descriptions[name]) return;
            state.view = name;
            document.querySelectorAll(".view").forEach((view) => { view.hidden = view.id !== `view-${name}`; });
            document.querySelectorAll(".nav-tab").forEach((tab) => {
                const active = tab.dataset.view === name; tab.classList.toggle("active", active);
                active ? tab.setAttribute("aria-current", "page") : tab.removeAttribute("aria-current");
            });
            $("#page-title").textContent = descriptions[name][0];
            $("#page-description").textContent = descriptions[name][1];
            if (name === "painel") loadDashboard().catch(showError);
            if (name === "pessoas") loadPeople().catch(showError);
            if (name === "tarefas") loadDashboard().catch(showError);
        }
        function showError(error) { notice(error.message || "Falha na operação.", true); }
        async function loadDashboard() {
            const data = await json("/api/dashboard");
            $("#metric-total").textContent = data.total;
            $("#metric-pending").textContent = data.pendentes;
            $("#metric-biometric").textContent = data.biometrias_simuladas;
            const completed = data.total - data.pendentes - (data.por_status.EM_ANALISE || 0);
            $("#metric-complete").textContent = `${data.total ? Math.round(completed / data.total * 100) : 0}%`;
            $("#task-pending").textContent = data.pendentes;
            $("#task-review").textContent = data.por_status.EM_ANALISE || 0;
            const rows = Object.entries(data.por_status);
            const max = Math.max(1, ...rows.map(([, count]) => count));
            $("#status-chart").innerHTML = rows.length ? rows.map(([status, count]) => `<div class="chart-row"><span>${escapeHtml(status.replaceAll("_", " "))}</span><div class="chart-track"><span style="width:${Math.round(count / max * 100)}%"></span></div><strong>${count}</strong></div>`).join("") : '<p class="muted">Sem registros cadastrados.</p>';
        }
        async function loadPeople() {
            const params = new URLSearchParams({ page: String(state.page), page_size: String(state.pageSize) });
            if (state.query) params.set("q", state.query);
            if (state.status) params.set("status_filtro", state.status);
            const data = await json(`/api/recenseados?${params}`);
            $("#people-rows").innerHTML = data.items.length ? data.items.map((person) => `<tr>
                <td><strong>${escapeHtml(person.nome)}</strong><small>${escapeHtml(person.cpf_mascarado)}</small></td>
                <td>${escapeHtml(person.sexo)}</td><td>${escapeHtml(person.data_nascimento)}</td>
                <td><span class="badge">${escapeHtml(person.status.replaceAll("_", " "))}</span></td>
                <td class="actions"><button class="text-button" data-action="edit" data-id="${person.id}">Editar</button>
                ${person.status === "PENDENTE" ? `<button class="text-button" data-action="review" data-id="${person.id}">Iniciar análise</button>` : ""}
                ${person.status === "EM_ANALISE" ? `<button class="text-button" data-action="approve" data-id="${person.id}">Concluir</button><button class="text-button danger" data-action="reject" data-id="${person.id}">Rejeitar</button>` : ""}
                <button class="text-button" data-action="photo" data-id="${person.id}">Foto</button><button class="text-button" data-action="biometry-match" data-id="${person.id}">Simular correspondência</button><button class="text-button" data-action="biometry-mismatch" data-id="${person.id}">Simular divergência</button><button class="text-button danger" data-action="delete" data-id="${person.id}">Excluir</button></td></tr>`).join("") : '<tr><td colspan="5" class="empty-state">Nenhum recenseado encontrado.</td></tr>';
            $("#page-label").textContent = `Página ${data.page} de ${Math.max(1, data.pages)} · ${data.total} registros`;
            $("#previous-page").disabled = data.page <= 1; $("#next-page").disabled = data.page >= data.pages;
        }
        function openPerson(person = null) {
            $("#person-form").reset(); $("#person-id").value = person?.id || "";
            $("#person-name").value = person?.nome || ""; $("#person-sex").value = person?.sexo || "FEMININO";
            $("#person-birth").value = person?.data_nascimento || ""; $("#person-cpf").required = !person;
            $("#cpf-field").hidden = Boolean(person); $("#person-dialog-title").textContent = person ? "Editar recenseado" : "Novo recenseado";
            $("#photo-preview").hidden = true; $("#person-dialog").showModal();
        }
        function confirmAction({title, copy, label, reason = false}) {
            $("#confirm-title").textContent = title; $("#confirm-copy").textContent = copy;
            $("#confirm-submit").textContent = label; $("#confirm-reason").hidden = !reason;
            $("#reason-label").hidden = !reason; $("#confirm-reason").required = reason; $("#confirm-reason").value = "";
            $("#confirm-dialog").showModal();
            return new Promise((resolve) => { state.resolveConfirm = resolve; });
        }
        async function tableAction(event) {
            const button = event.target.closest("[data-action]"); if (!button) return;
            const id = button.dataset.id; const action = button.dataset.action;
            if (action === "edit") { openPerson(await json(`/api/recenseados/${id}`)); return; }
            if (action === "delete") {
                const answer = await confirmAction({title:"Excluir recenseado",copy:"O cadastro e a imagem associados serão removidos permanentemente.",label:"Excluir"});
                if (!answer?.confirmed) return;
                await json(`/api/recenseados/${id}`, {method:"DELETE"}); notice("Cadastro excluído."); await loadPeople(); await loadDashboard(); return;
            }
            if (action === "photo") {
                const response = await api(`/api/recenseados/${id}/foto`);
                $("#photo-full").src = URL.createObjectURL(await response.blob()); $("#photo-dialog").showModal(); return;
            }
            if (action === "biometry-match" || action === "biometry-mismatch") {
                const match = action === "biometry-match";
                const answer = await confirmAction({title:"Simulação biométrica",copy:"Este recurso demonstra apenas um resultado ilustrativo. Nenhuma característica biométrica será analisada.",label:match ? "Simular correspondência" : "Simular divergência"});
                if (!answer?.confirmed) return;
                const result = await json(`/api/recenseados/${id}/biometria-simulada?corresponde=${match}`, {method:"POST"});
                notice(`${result.resultado}: assertividade ilustrativa de ${result.assertividade_simulada}%. Não é uma medição real.`);
                await loadDashboard(); return;
            }
            let nextStatus = {review:"EM_ANALISE",approve:"RECENSEADO",reject:"REJEITADO"}[action];
            if (!nextStatus) return;
            let reason = "";
            if (action === "reject") {
                const answer = await confirmAction({title:"Rejeitar cadastro",copy:"Informe o motivo da rejeição. A justificativa ficará registrada.",label:"Rejeitar",reason:true});
                if (!answer?.confirmed) return; reason = answer.reason;
            }
            const params = new URLSearchParams({novo_status:nextStatus}); if (reason) params.set("motivo", reason);
            await json(`/api/recenseados/${id}/status?${params}`, {method:"POST"});
            notice(`Status alterado para ${nextStatus.replaceAll("_"," ")}.`); await loadPeople(); await loadDashboard();
        }
        async function savePerson(event) {
            event.preventDefault(); const id = $("#person-id").value;
            const payload = {nome:$("#person-name").value,sexo:$("#person-sex").value,data_nascimento:$("#person-birth").value};
            if (!id) payload.cpf = $("#person-cpf").value;
            const person = await json(id ? `/api/recenseados/${id}` : "/api/recenseados", {method:id ? "PUT" : "POST",body:JSON.stringify(payload)});
            const image = $("#person-photo").files[0];
            if (image) { const form = new FormData(); form.append("arquivo", image); await json(`/api/recenseados/${person.id}/foto`,{method:"POST",body:form}); }
            $("#person-dialog").close(); notice(id ? "Cadastro atualizado." : "Recenseado cadastrado."); await loadPeople(); await loadDashboard();
        }
        function startIdleTimer() {
            const reset = () => { if (!$("#lock-screen").hidden) return; clearTimeout(state.timer); const mins = Number(localStorage.getItem("idm-idle-minutes") || 15); state.timer = setTimeout(lock, mins * 60000); };
            if (!idleListenersBound) {
                ["pointerdown","keydown","touchstart","scroll","pointermove"].forEach((event) => document.addEventListener(event, reset, {passive:true}));
                idleListenersBound = true;
            }
            reset();
        }
        async function lock() {
            $("#lock-screen").hidden = false; $("#unlock-email").value = state.user.email; $("#unlock-password").focus();
            const token = localStorage.getItem("idm-token");
            if (token) { try { await fetch("/api/auth/logout",{method:"POST",headers:{Authorization:`Bearer ${token}`}}); } catch (error) { notice("Sessão local bloqueada; não foi possível notificar o servidor.",true); } }
            localStorage.removeItem("idm-token"); localStorage.setItem("idm-locked","true");
        }
        async function unlock(event) {
            event.preventDefault(); $("#unlock-error").hidden = true;
            const response = await fetch("/api/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:$("#unlock-email").value,password:$("#unlock-password").value})});
            const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Falha de autenticação");
            localStorage.setItem("idm-token",data.access_token); localStorage.removeItem("idm-locked"); location.reload();
        }
        function renderCatalog(filter = "") {
            const items = catalog.filter((item) => item[0].toLowerCase().includes(filter.toLowerCase()) || item[1].toLowerCase().includes(filter.toLowerCase()));
            $("#application-cards").innerHTML = items.map(([name,description,iconName,view]) => `<button class="application-card" data-go="${view}"><span class="card-icon">${icon(iconName)}</span><strong>${escapeHtml(name)}</strong><small>${escapeHtml(description)}</small></button>`).join("");
        }
        async function printReport() {
            const report = window.open("", "_blank");
            if (!report) throw new Error("Permita pop-ups para gerar o relatório PDF.");
            try {
                const all = [];
                let page = 1;
                let pages = 1;
                do {
                    const data = await json(`/api/recenseados?page=${page}&page_size=100`);
                    all.push(...data.items);
                    pages = data.pages;
                    page += 1;
                } while (page <= pages);
                const rows = all.map((person) => `<tr><td>${escapeHtml(person.id)}</td><td>${escapeHtml(person.nome)}</td><td>${escapeHtml(person.cpf_mascarado)}</td><td>${escapeHtml(person.sexo)}</td><td>${escapeHtml(person.data_nascimento)}</td><td>${escapeHtml(person.status)}</td></tr>`).join("");
                report.document.write(`<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Relatório do Censo</title><style>body{font:12px Arial,sans-serif;color:#17212b;margin:28px}h1{font-size:20px}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:8px;border:1px solid #cbd5dc}th{background:#edf2f2}p{color:#64748b}@media print{body{margin:12mm}}</style><h1>Relatório de recenseados</h1><p>Gerado em ${escapeHtml(new Date().toLocaleString("pt-BR"))} · ${all.length} registros · CPF mascarado</p><table><thead><tr><th>ID</th><th>Nome</th><th>CPF</th><th>Sexo</th><th>Nascimento</th><th>Status</th></tr></thead><tbody>${rows || '<tr><td colspan="6">Nenhum registro.</td></tr>'}</tbody></table></html>`);
                report.document.close();
                report.focus();
                setTimeout(() => report.print(), 250);
            } catch (error) {
                report.close();
                throw error;
            }
        }
        const terminal = mountTerminal(async (command) => {
            if (command === "ajuda") return "Comandos: ajuda | status | tema claro | tema escuro | relatorio csv | pessoa adicionar NOME | CPF | AAAA-MM-DD";
            if (command === "status") { const data = await json("/api/dashboard"); return `Cadastros: ${data.total} · Pendentes: ${data.pendentes}`; }
            if (command === "tema claro" || command === "tema escuro") { setTheme(command.endsWith("escuro") ? "dark" : "light"); return "Tema atualizado."; }
            if (command === "relatorio csv") { await downloadCsv("/api/relatorios/recenseados.csv"); return "Relatório CSV gerado."; }
            if (command.startsWith("pessoa adicionar ")) {
                const fields = command.slice("pessoa adicionar ".length).split("|").map((part) => part.trim());
                if (fields.length !== 3) throw new Error("Formato: pessoa adicionar NOME | CPF | AAAA-MM-DD");
                await json("/api/recenseados",{method:"POST",body:JSON.stringify({nome:fields[0],cpf:fields[1],sexo:"OUTRO",data_nascimento:fields[2]})});
                await loadDashboard(); return "Cadastro criado.";
            }
            throw new Error("Comando desconhecido. Digite ajuda.");
        });
        async function showApplication() {
            const saved = localStorage.getItem("idm-theme") || "light"; setTheme(saved);
            $("#theme-select").value = saved;
            const config = await json("/api/auth/config");
            const idle = $("#idle-select");
            const options = [1,5,10,15].filter((minutes) => minutes <= config.session_idle_minutes);
            if (!options.length) options.push(config.session_idle_minutes);
            idle.replaceChildren(...options.map((minutes) => {
                const option = document.createElement("option");
                option.value = String(minutes);
                option.textContent = `${minutes} minuto${minutes === 1 ? "" : "s"}`;
                return option;
            }));
            const preferred = localStorage.getItem("idm-idle-minutes") || idle.options[idle.options.length - 1].value;
            idle.value = Array.from(idle.options).some((option) => option.value === preferred)
                ? preferred
                : idle.options[idle.options.length - 1].value;
            localStorage.setItem("idm-idle-minutes", idle.value);
            $("#login-view").hidden = true; $("#application").hidden = false;
            renderCatalog(); showView("painel"); startIdleTimer();
        }
        async function init() {
            $("#login-form").addEventListener("submit", async (event) => {
                event.preventDefault(); $("#login-error").hidden = true;
                try {
                    const data = await json("/api/auth/login",{method:"POST",body:JSON.stringify({email:$("#login-email").value,password:$("#login-password").value})});
                    localStorage.setItem("idm-token",data.access_token);
                    localStorage.removeItem("idm-locked");
                    state.user = await json("/api/auth/me");
                    $("#user-name").textContent = state.user.nome;
                    localStorage.setItem("idm-email",state.user.email);
                    await showApplication();
                } catch (error) { localStorage.removeItem("idm-token"); $("#login-error").textContent = error.message; $("#login-error").hidden = false; }
            });
            if (localStorage.getItem("idm-locked") === "true") {
                $("#application").hidden = false; $("#lock-screen").hidden = false;
                $("#unlock-email").value = localStorage.getItem("idm-email") || "";
            } else if (localStorage.getItem("idm-token")) {
                try {
                    state.user = await json("/api/auth/me");
                    $("#user-name").textContent = state.user.nome;
                    localStorage.setItem("idm-email",state.user.email);
                    await showApplication();
                }
                catch { localStorage.removeItem("idm-token"); $("#login-view").hidden = false; }
            } else $("#login-view").hidden = false;
            $("#unlock-form").addEventListener("submit",(event) => unlock(event).catch((error) => {$("#unlock-error").textContent=error.message;$("#unlock-error").hidden=false;}));
            window.addEventListener("idm:locked",() => {
                $("#application").hidden = false;
                $("#lock-screen").hidden = false;
                $("#unlock-email").value = state.user?.email || localStorage.getItem("idm-email") || "";
            });
            $("#main-nav").addEventListener("click",(event) => { const tab=event.target.closest("[data-view]"); if(tab) showView(tab.dataset.view); });
            document.addEventListener("click",(event) => { const target=event.target.closest("[data-go]"); if(target) showView(target.dataset.go); });
            $("#settings-open").addEventListener("click",() => $("#settings-dialog").showModal());
            $("#theme-select").addEventListener("change",(event) => setTheme(event.target.value));
            $("#idle-select").addEventListener("change",(event) => {localStorage.setItem("idm-idle-minutes",event.target.value);startIdleTimer();});
            $("#logout-button").addEventListener("click",async() => {try{await json("/api/auth/logout",{method:"POST"});}finally{localStorage.removeItem("idm-token");localStorage.removeItem("idm-locked");location.reload();}});
            $("#refresh-button").addEventListener("click",() => { if(state.view==="pessoas") loadPeople().catch(showError); else loadDashboard().catch(showError); });
            $("#people-filter").addEventListener("submit",(event) => {event.preventDefault();state.page=1;state.query=$("#people-query").value.trim();state.status=$("#people-status").value;loadPeople().catch(showError);});
            $("#people-status").addEventListener("change",() => $("#people-filter").requestSubmit());
            $("#previous-page").addEventListener("click",() => {state.page--;loadPeople().catch(showError);});
            $("#next-page").addEventListener("click",() => {state.page++;loadPeople().catch(showError);});
            $("#people-rows").addEventListener("click",(event) => tableAction(event).catch(showError));
            $("#add-person").addEventListener("click",() => openPerson());
            $("#person-form").addEventListener("submit",(event) => savePerson(event).catch(showError));
            $("#person-photo").addEventListener("change",() => {const file=$("#person-photo").files[0];if(file){if(!["image/jpeg","image/png"].includes(file.type)){notice("Selecione uma imagem JPG ou PNG.",true);return;}$("#photo-preview").src=URL.createObjectURL(file);$("#photo-preview").hidden=false;}});
            $("#confirm-form").addEventListener("submit",(event) => {event.preventDefault();state.resolveConfirm?.({confirmed:true,reason:$("#confirm-reason").value.trim()});state.resolveConfirm=null;$("#confirm-dialog").close();});
            $("#confirm-cancel").addEventListener("click",() => {state.resolveConfirm?.({confirmed:false});state.resolveConfirm=null;$("#confirm-dialog").close();});
            $("#confirm-dialog").addEventListener("close",() => {state.resolveConfirm?.({confirmed:false});state.resolveConfirm=null;});
            document.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click",() => document.getElementById(button.dataset.close).close()));
            $("#app-search").addEventListener("input",(event) => renderCatalog(event.target.value));
            $("#export-csv").addEventListener("click",() => downloadCsv("/api/relatorios/recenseados.csv").catch(showError));
            $("#export-pdf").addEventListener("click",() => printReport().catch(showError));
            if(terminal) terminal.write("Console disponível. Digite ajuda para consultar os comandos.");
            setInterval(() => {if(!$("#application").hidden&&$("#lock-screen").hidden)loadDashboard().catch(showError);},30000);
        }
        init();
    ''',
    "frontend/modules/api.js": r'''
        export async function api(path, options = {}) {
            const headers = new Headers(options.headers || {});
            const token = localStorage.getItem("idm-token");
            if (token) headers.set("Authorization", `Bearer ${token}`);
            if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
            const response = await fetch(path, {...options, headers});
            if (response.status === 401) {
                localStorage.setItem("idm-locked", "true");
                localStorage.removeItem("idm-token");
                window.dispatchEvent(new Event("idm:locked"));
            }
            if (!response.ok) {
                const payload = await response.json().catch(() => ({}));
                const detail = Array.isArray(payload.detail)
                    ? payload.detail.map((item) => item.msg).join("; ")
                    : payload.detail;
                throw new Error(detail || `Erro HTTP ${response.status}`);
            }
            return response;
        }
        export async function json(path, options) {
            const response = await api(path, options);
            return response.status === 204 ? null : response.json();
        }
        export async function downloadCsv(path) {
            const response = await api(path);
            const url = URL.createObjectURL(await response.blob());
            const link = document.createElement("a");
            link.href = url; link.download = "relatorio-recenseados.csv"; link.click();
            URL.revokeObjectURL(url);
        }
    ''',
    "frontend/modules/terminal.js": r'''
        export function mountTerminal(onCommand) {
            const form = document.querySelector("#terminal-form");
            const input = document.querySelector("#terminal-input");
            const output = document.querySelector("#terminal-output");
            const write = (value, type = "result") => {
                const line = document.createElement("p");
                line.className = `terminal-${type}`;
                line.textContent = value;
                output.append(line);
                output.scrollTop = output.scrollHeight;
            };
            form.addEventListener("submit", async (event) => {
                event.preventDefault();
                const command = input.value.trim();
                if (!command) return;
                write(`operador@idm: ${command}`, "command");
                input.value = "";
                try { const result = await onCommand(command); if (result) write(result); }
                catch (error) { write(error.message || "Falha ao executar comando.", "error"); }
            });
            return {write};
        }
    ''',
    "frontend/tailwind.css": r'''
        @tailwind base;
        @tailwind components;
        @tailwind utilities;
    ''',
    "frontend/tailwind.generated.css": r'''
        /* Execute npm run build:css to generate the Tailwind utility stylesheet. */
    ''',
    "tailwind.config.js": r'''
        module.exports = {
          content: ["./frontend/**/*.{html,js}"],
          darkMode: "class",
          theme: { extend: {} },
          plugins: [],
        };
    ''',
    "package.json": r'''
        {
          "name": "idm-censo-frontend",
          "private": true,
          "scripts": {
            "build:css": "tailwindcss -i ./frontend/tailwind.css -o ./frontend/tailwind.generated.css --minify"
          },
          "devDependencies": {
            "tailwindcss": "^3.4.17"
          }
        }
    ''',
}

PROJECT_FILES = {
    ".env.example": r'''
        APP_ENV=development
        DATABASE_URL=sqlite:///./data/censo.db
        JWT_SECRET_KEY=change-this-to-a-long-random-secret
        JWT_EXPIRE_MINUTES=60
        SESSION_IDLE_MINUTES=15
        REDIS_URL=redis://localhost:6379/0
        ADMIN_EMAIL=admin@local.test
        ADMIN_PASSWORD=change-me-now
        UPLOAD_DIR=./data/uploads
    ''',
    "requirements.txt": r'''
        fastapi>=0.115,<1.0
        uvicorn[standard]>=0.30,<1.0
        sqlalchemy>=2.0,<3.0
        pydantic>=2.8,<3.0
        python-multipart>=0.0.20
        python-dotenv>=1.0,<2.0
        redis>=5.0,<7.0
        PyJWT>=2.8,<3.0
        bcrypt>=4.1,<6.0
        pytest>=8.0,<9.0
        httpx>=0.27,<1.0
    ''',
    "tests/__init__.py": "",
    "tests/test_api.py": r'''
        import uuid

        import pytest
        from fastapi.testclient import TestClient

        from app.main import app

        @pytest.fixture
        def client():
            with TestClient(app) as test_client:
                yield test_client

        def valid_cpf() -> str:
            digits = [int(value) for value in str(uuid.uuid4().int % 10**9).zfill(9)]
            for length in (9, 10):
                total = sum(digits[index] * (length + 1 - index) for index in range(length))
                check = (total * 10) % 11
                digits.append(0 if check == 10 else check)
            return "".join(map(str, digits))

        def auth_headers(client: TestClient) -> dict[str, str]:
            response = client.post(
                "/api/auth/login",
                json={"email": "admin@local.test", "password": "change-me-now"},
            )
            assert response.status_code == 200
            return {"Authorization": f"Bearer {response.json()['access_token']}"}

        def person_payload(name: str = "Pessoa de Teste") -> dict[str, str]:
            return {
                "nome": name,
                "cpf": valid_cpf(),
                "sexo": "OUTRO",
                "data_nascimento": "1980-04-15",
            }

        def test_api_requires_authentication(client: TestClient) -> None:
            assert client.get("/api/recenseados").status_code == 401

        def test_create_and_list_recenseado(client: TestClient) -> None:
            headers = auth_headers(client)
            name = f"Pessoa {uuid.uuid4().hex}"
            created = client.post("/api/recenseados", headers=headers, json=person_payload(name))
            assert created.status_code == 201
            assert created.json()["nome"] == name
            assert created.json()["cpf_mascarado"].startswith("***.")
            listed = client.get("/api/recenseados", headers=headers, params={"q": name})
            assert listed.status_code == 200
            assert listed.json()["total"] == 1

        def test_invalid_cpf_and_duplicate_cpf(client: TestClient) -> None:
            headers = auth_headers(client)
            payload = person_payload()
            payload["cpf"] = "111.111.111-11"
            assert client.post("/api/recenseados", headers=headers, json=payload).status_code == 422
            payload = person_payload()
            assert client.post("/api/recenseados", headers=headers, json=payload).status_code == 201
            duplicate = client.post("/api/recenseados", headers=headers, json=payload)
            assert duplicate.status_code == 409

        def test_face_validation_is_explicitly_a_simulation(client: TestClient) -> None:
            headers = auth_headers(client)
            person = client.post(
                "/api/recenseados", headers=headers, json=person_payload()
            ).json()
            result = client.post(
                f"/api/recenseados/{person['id']}/biometria-simulada?corresponde=true",
                headers=headers,
            )
            assert result.status_code == 200
            assert result.json()["modo_simulacao"] is True
            assert "não representa" in result.json()["aviso"]
    ''',
    "tailwind.config.js": FRONTEND_FILES["tailwind.config.js"],
    "package.json": FRONTEND_FILES["package.json"],
    "README.md": r'''
        # Portal IDM — Censo Previdenciário

        SPA corporativa com API FastAPI modular, SQLAlchemy, validação Pydantic v2, JWT e sessões Redis opcionais.

        ## Executar

        ```bash
        python -m venv .venv
        source .venv/bin/activate  # Windows: .venv\Scripts\activate
        pip install -r requirements.txt
        cp .env.example .env
        uvicorn app.main:app --reload
        ```

        Acesse `http://127.0.0.1:8000`. A conta inicial vem de `ADMIN_EMAIL` e `ADMIN_PASSWORD`.
        Altere essas credenciais antes de disponibilizar o sistema.

        Para sessões distribuídas e expiração por inatividade, execute Redis e configure `REDIS_URL`.
        Em `APP_ENV=production`, `JWT_SECRET_KEY` e `REDIS_URL` são obrigatórios. O bloqueio visual
        exige novo login e o Redis invalida o token no servidor quando configurado.

        O CSS institucional funciona sem build. Para compilar as classes utilitárias Tailwind:

        ```bash
        npm install
        npm run build:css
        ```

        ## API

        - `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout`
        - `GET/POST /api/recenseados`, `GET/PUT/DELETE /api/recenseados/{id}`
        - `POST /api/recenseados/{id}/foto`, `GET /api/recenseados/{id}/foto`
        - `POST /api/recenseados/{id}/biometria-simulada?corresponde=true|false`
        - `POST /api/recenseados/{id}/status?novo_status=...`
        - `GET /api/dashboard`, `GET /api/relatorios/recenseados.csv`

        A simulação biométrica é apenas demonstrativa e não deve fundamentar decisões. Dados de CPF
        são armazenados como hash HMAC e exibidos mascarados. Imagens são armazenadas no diretório
        configurado por `UPLOAD_DIR`.

        ## Testes

        ```bash
        pytest -q
        ```
    ''',
    ".gitignore": r'''
        .env
        .venv/
        __pycache__/
        .pytest_cache/
        node_modules/
        data/
        frontend/tailwind.generated.css
    ''',
}

FILES = {**BACKEND_FILES, **FRONTEND_FILES, **PROJECT_FILES}


def write_project(destination: Path, force: bool) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    conflicts = [relative for relative in FILES if (destination / relative).exists()]
    if conflicts and not force:
        names = ", ".join(conflicts[:5])
        raise FileExistsError(
            f"Destino contém arquivos gerados ({names}). Use --force para atualizar."
        )
    for relative, content in FILES.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(dedent(content).lstrip("\n"), encoding="utf-8")
    (destination / "data").mkdir(exist_ok=True)
    print(f"Portal IDM criado em: {destination.resolve()}")
    print("Próximos passos: pip install -r requirements.txt && uvicorn app.main:app --reload")


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera o portal IDM de Censo Previdenciário.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("idm_portal"),
        help="Diretório de destino (padrão: ./idm_portal)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Atualiza arquivos já gerados sem remover outros arquivos.",
    )
    args = parser.parse_args()
    try:
        write_project(args.output, args.force)
    except (OSError, ValueError) as exc:
        print(f"Erro ao gerar o projeto: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
