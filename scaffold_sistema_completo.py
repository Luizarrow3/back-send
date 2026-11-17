#!/usr/bin/env python3
"""Gera um portal corporativo de Censo Previdenciário pronto para executar."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from textwrap import dedent


FILES = {
    "requirements.txt": r'''
        fastapi>=0.115,<1
        uvicorn[standard]>=0.30,<1
        sqlalchemy>=2.0,<3
        pydantic>=2.8,<3
        python-multipart>=0.0.9
        python-dotenv>=1.0
        redis>=5.0
        PyJWT>=2.8
        bcrypt>=4.0
    ''',
    ".env.example": r'''
        APP_ENV=development
        JWT_SECRET_KEY=change-this-to-a-long-random-secret
        ADMIN_EMAIL=admin@local.test
        ADMIN_PASSWORD=change-me-now
        REDIS_URL=redis://localhost:6379/0
        SESSION_IDLE_MINUTES=15
        DATABASE_URL=sqlite:///./data/censo.db
        UPLOAD_DIR=./data/uploads
    ''',
    ".gitignore": r'''
        .venv/
        __pycache__/
        .env
        data/
        *.py[cod]
    ''',
    "app/__init__.py": "",
    "app/config.py": r'''
        import os
        from pathlib import Path

        from dotenv import load_dotenv

        ROOT = Path(__file__).resolve().parent.parent
        load_dotenv(ROOT / ".env")

        class Settings:
            app_env = os.getenv("APP_ENV", "development")
            jwt_secret = os.getenv("JWT_SECRET_KEY", "development-only-change-me")
            admin_email = os.getenv("ADMIN_EMAIL", "admin@local.test").strip().lower()
            admin_password = os.getenv("ADMIN_PASSWORD", "change-me-now")
            redis_url = os.getenv("REDIS_URL", "")
            idle_minutes = int(os.getenv("SESSION_IDLE_MINUTES", "15"))
            database_url = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'censo.db'}")
            upload_dir = Path(os.getenv("UPLOAD_DIR", str(ROOT / "data" / "uploads")))

            def validate(self):
                if self.idle_minutes < 1:
                    raise ValueError("SESSION_IDLE_MINUTES deve ser positivo")
                if self.app_env == "production" and self.jwt_secret == "development-only-change-me":
                    raise ValueError("Configure JWT_SECRET_KEY em produção")

        settings = Settings()
    ''',
    "app/database.py": r'''
        from collections.abc import Generator
        from pathlib import Path

        from sqlalchemy import create_engine
        from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

        from app.config import settings

        if settings.database_url.startswith("sqlite:///"):
            db_path = settings.database_url.removeprefix("sqlite:///")
            if db_path != ":memory:" and not db_path.startswith("/"):
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
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

        from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
        from sqlalchemy.orm import Mapped, mapped_column

        from app.database import Base

        def now_utc() -> datetime:
            return datetime.now(timezone.utc)

        class Recenseado(Base):
            __tablename__ = "recenseados"
            id: Mapped[int] = mapped_column(primary_key=True)
            nome: Mapped[str] = mapped_column(String(150), index=True)
            cpf: Mapped[str] = mapped_column(String(64), unique=True, index=True)
            cpf_mascarado: Mapped[str] = mapped_column(String(20))
            estado: Mapped[str] = mapped_column(String(2), index=True)
            regiao: Mapped[str] = mapped_column(String(30), index=True)
            canal_acesso: Mapped[str] = mapped_column(String(20), index=True)
            status: Mapped[str] = mapped_column(String(20), default="PENDENTE", index=True)
            foto_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
            biometria_validada: Mapped[bool] = mapped_column(Boolean, default=False)
            data_cadastro: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)

        class AccessEvent(Base):
            __tablename__ = "access_events"
            id: Mapped[int] = mapped_column(primary_key=True)
            channel: Mapped[str] = mapped_column(String(20), default="Desktop")
            occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)

        class BiometricEvent(Base):
            __tablename__ = "biometric_events"
            id: Mapped[int] = mapped_column(primary_key=True)
            recenseado_id: Mapped[int] = mapped_column(ForeignKey("recenseados.id", ondelete="CASCADE"))
            score: Mapped[float] = mapped_column(Float)
            matched: Mapped[bool] = mapped_column(Boolean)
            occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    ''',
    "app/schemas.py": r'''
        import re
        from datetime import datetime
        from typing import Literal

        from pydantic import BaseModel, ConfigDict, Field, field_validator

        def digits_only(value: str) -> str:
            return re.sub(r"\D", "", value)

        def valid_cpf(value: str) -> bool:
            cpf = digits_only(value)
            if len(cpf) != 11 or len(set(cpf)) == 1:
                return False
            values = [int(x) for x in cpf]
            for size in (9, 10):
                check = (sum(values[i] * (size + 1 - i) for i in range(size)) * 10) % 11
                if values[size] != (0 if check == 10 else check):
                    return False
            return True

        def cpf_mask(cpf: str) -> str:
            return f"***.{cpf[3:6]}.{cpf[6:9]}-**"

        class LoginInput(BaseModel):
            email: str = Field(min_length=5, max_length=254)
            password: str = Field(min_length=10, max_length=128)

            @field_validator("email")
            @classmethod
            def normalize_email(cls, value: str) -> str:
                value = value.strip().lower()
                if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
                    raise ValueError("E-mail inválido")
                return value

        class RecenseadoInput(BaseModel):
            model_config = ConfigDict(str_strip_whitespace=True)
            nome: str = Field(min_length=2, max_length=150)
            cpf: str = Field(min_length=11, max_length=14)
            estado: str = Field(min_length=2, max_length=2)
            regiao: str = Field(min_length=2, max_length=30)
            canal_acesso: Literal["Presencial", "Desktop", "Mobile"]

            @field_validator("nome")
            @classmethod
            def clean_name(cls, value: str) -> str:
                value = re.sub(r"\s+", " ", value).strip()
                if not re.fullmatch(r"[^\W\d_][\wÀ-ÿ .'-]{1,149}", value, re.UNICODE):
                    raise ValueError("Nome contém caracteres inválidos")
                return value

            @field_validator("cpf")
            @classmethod
            def check_cpf(cls, value: str) -> str:
                if not re.fullmatch(r"[\d.\-\s]+", value) or not valid_cpf(value):
                    raise ValueError("CPF inválido")
                return digits_only(value)

            @field_validator("estado")
            @classmethod
            def normalize_state(cls, value: str) -> str:
                value = value.strip().upper()
                if not re.fullmatch(r"[A-Z]{2}", value):
                    raise ValueError("Informe a sigla de estado com duas letras")
                return value

            @field_validator("regiao")
            @classmethod
            def clean_region(cls, value: str) -> str:
                value = re.sub(r"\s+", " ", value).strip().title()
                if not re.fullmatch(r"[A-Za-zÀ-ÿ ]{2,30}", value):
                    raise ValueError("Região inválida")
                return value

        class RecenseadoUpdate(BaseModel):
            model_config = ConfigDict(str_strip_whitespace=True)
            nome: str | None = Field(default=None, min_length=2, max_length=150)
            estado: str | None = Field(default=None, min_length=2, max_length=2)
            regiao: str | None = Field(default=None, min_length=2, max_length=30)
            canal_acesso: Literal["Presencial", "Desktop", "Mobile"] | None = None
            status: Literal["PENDENTE", "EM_ANALISE", "VALIDADO", "REJEITADO"] | None = None

            @field_validator("nome")
            @classmethod
            def clean_name(cls, value: str | None) -> str | None:
                return re.sub(r"\s+", " ", value).strip() if value else value

            @field_validator("estado")
            @classmethod
            def normalize_state(cls, value: str | None) -> str | None:
                return value.strip().upper() if value else value

        class RecenseadoOut(BaseModel):
            model_config = ConfigDict(from_attributes=True)
            id: int
            nome: str
            cpf_mascarado: str
            estado: str
            regiao: str
            canal_acesso: str
            status: str
            foto_url: str | None
            biometria_validada: bool
            data_cadastro: datetime

        class TokenOut(BaseModel):
            access_token: str
            token_type: str = "bearer"
            idle_minutes: int

        class BiometricInput(BaseModel):
            matched: bool = True
    ''',
    "app/cache.py": r'''
        import json
        import time
        from threading import RLock

        from redis import Redis
        from redis.exceptions import RedisError

        from app.config import settings

        class TTLStore:
            def __init__(self):
                self.redis = Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=0.25) if settings.redis_url else None
                self._memory: dict[str, tuple[float, str]] = {}
                self._lock = RLock()
                self.redis_available = False

            def set(self, key: str, value: str, ttl: int) -> None:
                if self.redis:
                    try:
                        self.redis.setex(key, ttl, value)
                        self.redis_available = True
                        return
                    except RedisError:
                        self.redis_available = False
                with self._lock:
                    self._memory[key] = (time.monotonic() + ttl, value)

            def get(self, key: str) -> str | None:
                if self.redis:
                    try:
                        value = self.redis.get(key)
                        self.redis_available = True
                        if value is not None:
                            return value
                    except RedisError:
                        self.redis_available = False
                with self._lock:
                    item = self._memory.get(key)
                    if item is None:
                        return None
                    expires, value = item
                    if expires <= time.monotonic():
                        self._memory.pop(key, None)
                        return None
                    return value

            def delete(self, key: str) -> None:
                if self.redis:
                    try:
                        self.redis.delete(key)
                        self.redis_available = True
                    except RedisError:
                        self.redis_available = False
                with self._lock:
                    self._memory.pop(key, None)

            def touch(self, key: str, ttl: int) -> None:
                if self.redis:
                    try:
                        if self.redis.expire(key, ttl):
                            self.redis_available = True
                            return
                    except RedisError:
                        self.redis_available = False
                with self._lock:
                    item = self._memory.get(key)
                    if item:
                        self._memory[key] = (time.monotonic() + ttl, item[1])

            def get_json(self, key: str):
                value = self.get(key)
                return json.loads(value) if value else None

            def set_json(self, key: str, value, ttl: int) -> None:
                self.set(key, json.dumps(value, default=str), ttl)

        store = TTLStore()
    ''',
    "app/security.py": r'''
        from datetime import datetime, timedelta, timezone
        from uuid import uuid4

        import bcrypt
        import jwt
        from fastapi import Depends, HTTPException
        from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
        from sqlalchemy.orm import Session

        from app.cache import store
        from app.config import settings
        from app.database import get_db

        bearer = HTTPBearer(auto_error=False)

        def hash_password(value: str) -> str:
            return bcrypt.hashpw(value.encode(), bcrypt.gensalt()).decode()

        def verify_password(value: str, hashed: str) -> bool:
            return bcrypt.checkpw(value.encode(), hashed.encode())

        def make_token(user_id: int) -> str:
            sid = uuid4().hex
            expiry = datetime.now(timezone.utc) + timedelta(days=1)
            token = jwt.encode({"sub": str(user_id), "sid": sid, "exp": expiry}, settings.jwt_secret, algorithm="HS256")
            store.set(f"session:{sid}", str(user_id), settings.idle_minutes * 60)
            return token

        def current_user(
            credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
            db: Session = Depends(get_db),
        ) -> int:
            if credentials is None:
                raise HTTPException(status_code=401, detail="Autenticação necessária")
            try:
                claims = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=["HS256"])
                user_id, sid = int(claims["sub"]), claims["sid"]
            except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
                raise HTTPException(status_code=401, detail="Token inválido ou expirado") from exc
            if store.get(f"session:{sid}") != str(user_id):
                raise HTTPException(status_code=401, detail="Sessão expirada; autentique-se novamente")
            store.touch(f"session:{sid}", settings.idle_minutes * 60)
            return user_id

        def logout_token(credentials: HTTPAuthorizationCredentials | None) -> None:
            if credentials:
                try:
                    claims = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=["HS256"], options={"verify_exp": False})
                    store.delete(f"session:{claims['sid']}")
                except (jwt.PyJWTError, KeyError) as exc:
                    raise HTTPException(status_code=401, detail="Token inválido") from exc
    ''',
    "app/repositories/__init__.py": "",
    "app/repositories/recenseados.py": r'''
        from sqlalchemy import func, or_, select
        from sqlalchemy.orm import Session

        from app.models import Recenseado

        def list_people(db: Session, page: int, page_size: int, q: str | None, status: str | None):
            query = select(Recenseado)
            count = select(func.count()).select_from(Recenseado)
            filters = []
            if q:
                term = f"%{q.strip().lower()}%"
                filters.append(or_(func.lower(Recenseado.nome).like(term), func.lower(Recenseado.estado).like(term), func.lower(Recenseado.regiao).like(term)))
            if status:
                filters.append(Recenseado.status == status)
            if filters:
                query, count = query.where(*filters), count.where(*filters)
            total = db.scalar(count) or 0
            records = db.scalars(query.order_by(Recenseado.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
            return records, total
    ''',
    "app/services/__init__.py": "",
    "app/services/recenseados.py": r'''
        import hashlib
        import hmac
        from datetime import datetime, timezone

        from fastapi import HTTPException
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm import Session

        from app.config import settings
        from app.models import AccessEvent, BiometricEvent, Recenseado
        from app.repositories.recenseados import list_people
        from app.schemas import RecenseadoInput, RecenseadoUpdate, cpf_mask

        def cpf_digest(cpf: str) -> str:
            return hmac.new(settings.jwt_secret.encode(), cpf.encode(), hashlib.sha256).hexdigest()

        def create(db: Session, data: RecenseadoInput) -> Recenseado:
            record = Recenseado(
                nome=data.nome, cpf=cpf_digest(data.cpf), cpf_mascarado=cpf_mask(data.cpf),
                estado=data.estado, regiao=data.regiao, canal_acesso=data.canal_acesso,
            )
            db.add(record)
            db.add(AccessEvent(channel=data.canal_acesso))
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise HTTPException(status_code=409, detail="CPF já cadastrado") from exc
            db.refresh(record)
            return record

        def update(db: Session, record: Recenseado, data: RecenseadoUpdate) -> Recenseado:
            for key, value in data.model_dump(exclude_unset=True).items():
                if value is not None:
                    setattr(record, key, value)
            db.commit()
            db.refresh(record)
            return record

        def delete(db: Session, record: Recenseado) -> None:
            db.delete(record)
            db.commit()

        def biometric(db: Session, record: Recenseado, matched: bool) -> dict:
            score = 96.4 if matched else 18.7
            record.biometria_validada = matched
            record.status = "VALIDADO" if matched else "EM_ANALISE"
            db.add(BiometricEvent(recenseado_id=record.id, score=score, matched=matched))
            db.commit()
            return {"resultado": "CORRESPONDENTE" if matched else "DIVERGENTE", "assertividade": score, "simulado": True}

        def find_or_404(db: Session, record_id: int) -> Recenseado:
            record = db.get(Recenseado, record_id)
            if record is None:
                raise HTTPException(status_code=404, detail="Recenseado não encontrado")
            return record
    ''',
    "app/routers/__init__.py": "",
    "app/routers/auth.py": r'''
        from fastapi import APIRouter, Depends, HTTPException, Response
        from sqlalchemy.orm import Session

        from app.cache import store
        from app.config import settings
        from app.database import get_db
        from app.models import AccessEvent
        from app.schemas import LoginInput, TokenOut
        from app.security import current_user, hash_password, make_token, logout_token, verify_password
        from app.routers.setup import get_admin_hash

        router = APIRouter(prefix="/api/auth", tags=["Autenticação"])

        @router.post("/login", response_model=TokenOut)
        def login(payload: LoginInput, db: Session = Depends(get_db)):
            if payload.email != settings.admin_email or not verify_password(payload.password, get_admin_hash()):
                raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")
            db.add(AccessEvent(channel="Desktop"))
            db.commit()
            return TokenOut(access_token=make_token(1), idle_minutes=settings.idle_minutes)

        @router.get("/me")
        def me(user_id: int = Depends(current_user)):
            return {"id": user_id, "email": settings.admin_email}

        @router.post("/logout", status_code=204)
        def logout(response: Response, authorization=Depends(__import__("app.security", fromlist=["bearer"]).bearer)):
            logout_token(authorization)
            return response
    ''',
    "app/routers/setup.py": r'''
        from app.config import settings
        from app.security import hash_password

        _admin_hash: str | None = None

        def initialize_admin() -> None:
            global _admin_hash
            _admin_hash = hash_password(settings.admin_password)

        def get_admin_hash() -> str:
            if _admin_hash is None:
                initialize_admin()
            return _admin_hash
    ''',
    "app/routers/recenseados.py": r'''
        import math
        import uuid
        from pathlib import Path

        from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
        from fastapi.responses import FileResponse
        from sqlalchemy.orm import Session

        from app.config import settings
        from app.database import get_db
        from app.models import Recenseado
        from app.repositories.recenseados import list_people
        from app.schemas import BiometricInput, RecenseadoInput, RecenseadoOut, RecenseadoUpdate
        from app.security import current_user
        from app.services import recenseados as service

        router = APIRouter(prefix="/api/recenseados", tags=["Recenseados"])
        MAX_SIZE = 5 * 1024 * 1024
        FILE_TYPES = {"image/jpeg": (b"\\xff\\xd8\\xff", ".jpg"), "image/png": (b"\\x89PNG\\r\\n\\x1a\\n", ".png")}

        @router.get("")
        def listing(q: str | None = None, status: str | None = Query(None, pattern="^(PENDENTE|EM_ANALISE|VALIDADO|REJEITADO)$"),
                    page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100),
                    db: Session = Depends(get_db), user_id: int = Depends(current_user)):
            records, total = list_people(db, page, page_size, q, status)
            return {"items": [RecenseadoOut.model_validate(x) for x in records], "total": total, "page": page,
                    "page_size": page_size, "pages": math.ceil(total / page_size) if total else 0}

        @router.post("", response_model=RecenseadoOut, status_code=201)
        def create(payload: RecenseadoInput, db: Session = Depends(get_db), user_id: int = Depends(current_user)):
            return service.create(db, payload)

        @router.put("/{record_id}", response_model=RecenseadoOut)
        def update(record_id: int, payload: RecenseadoUpdate, db: Session = Depends(get_db), user_id: int = Depends(current_user)):
            return service.update(db, service.find_or_404(db, record_id), payload)

        @router.delete("/{record_id}", status_code=204)
        def delete(record_id: int, db: Session = Depends(get_db), user_id: int = Depends(current_user)):
            record = service.find_or_404(db, record_id)
            if record.foto_url:
                (settings.upload_dir / Path(record.foto_url).name).unlink(missing_ok=True)
            service.delete(db, record)

        @router.post("/{record_id}/foto")
        async def upload_photo(record_id: int, arquivo: UploadFile = File(...),
                               db: Session = Depends(get_db), user_id: int = Depends(current_user)):
            record = service.find_or_404(db, record_id)
            specification = FILE_TYPES.get(arquivo.content_type or "")
            data = await arquivo.read(MAX_SIZE + 1)
            if not specification or not data.startswith(specification[0]) or len(data) > MAX_SIZE:
                raise HTTPException(status_code=400, detail="Envie imagem JPEG/PNG válida de até 5 MB")
            settings.upload_dir.mkdir(parents=True, exist_ok=True)
            filename = uuid.uuid4().hex + specification[1]
            (settings.upload_dir / filename).write_bytes(data)
            record.foto_url = f"/uploads/{filename}"
            db.commit()
            return {"foto_url": record.foto_url}

        @router.post("/{record_id}/biometria")
        def validate_face(record_id: int, payload: BiometricInput,
                          db: Session = Depends(get_db), user_id: int = Depends(current_user)):
            return service.biometric(db, service.find_or_404(db, record_id), payload.matched)

        @router.get("/{record_id}/foto")
        def photo(record_id: int, db: Session = Depends(get_db), user_id: int = Depends(current_user)):
            record = service.find_or_404(db, record_id)
            if not record.foto_url:
                raise HTTPException(status_code=404, detail="Imagem não cadastrada")
            path = settings.upload_dir / Path(record.foto_url).name
            if not path.is_file():
                raise HTTPException(status_code=404, detail="Arquivo de imagem não encontrado")
            return FileResponse(path)
    ''',
    "app/routers/analytics.py": r'''
        import csv
        import io
        from datetime import date, datetime, time, timedelta, timezone

        from fastapi import APIRouter, Depends, Query
        from fastapi.responses import StreamingResponse
        from sqlalchemy import func, select
        from sqlalchemy.orm import Session

        from app.cache import store
        from app.database import get_db
        from app.models import AccessEvent, Recenseado
        from app.security import current_user

        router = APIRouter(prefix="/api", tags=["Dashboard e relatórios"])
        VALID_DAYS = {"7": 7, "30": 30, "all": None}

        @router.get("/dashboard")
        def dashboard(period: str = Query("7"), db: Session = Depends(get_db), user_id: int = Depends(current_user)):
            if period not in VALID_DAYS:
                period = "7"
            cache_key = f"analytics:{period}"
            cached = store.get_json(cache_key)
            if cached:
                return cached
            days = VALID_DAYS[period]
            since = datetime.combine(date.today() - timedelta(days=days - 1), time.min, tzinfo=timezone.utc) if days else None
            query = select(Recenseado)
            access_query = select(AccessEvent)
            if since:
                query = query.where(Recenseado.data_cadastro >= since)
                access_query = access_query.where(AccessEvent.occurred_at >= since)
            rows = list(db.scalars(query.order_by(Recenseado.data_cadastro.desc())).all())
            total = db.scalar(select(func.count()).select_from(Recenseado)) or 0
            registrations, validations, regions, channels = {}, {}, {}, {}
            for row in rows:
                day = row.data_cadastro.date().isoformat()
                registrations[day] = registrations.get(day, 0) + 1
                if row.biometria_validada:
                    validations[day] = validations.get(day, 0) + 1
                regions[row.estado] = regions.get(row.estado, 0) + 1
                channels[row.canal_acesso] = channels.get(row.canal_acesso, 0) + 1
            start = date.today() - timedelta(days=(days - 1 if days else 6))
            labels = [(start + timedelta(days=i)).isoformat() for i in range((days or 7))]
            weekly_labels = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
            week_now, week_before = [0] * 7, [0] * 7
            for row in rows:
                delta = (date.today() - row.data_cadastro.date()).days
                if delta < 7:
                    week_now[row.data_cadastro.weekday()] += 1
                elif delta < 14:
                    week_before[row.data_cadastro.weekday()] += 1
            access_rows = db.scalars(access_query).all()
            hourly = [0] * 24
            for event in access_rows:
                hourly[event.occurred_at.hour] += 1
            result = {
                "total": total,
                "pendentes": db.scalar(select(func.count()).select_from(Recenseado).where(Recenseado.status == "PENDENTE")) or 0,
                "validados": db.scalar(select(func.count()).select_from(Recenseado).where(Recenseado.biometria_validada.is_(True))) or 0,
                "novos": len(rows),
                "daily": {"labels": labels, "cadastros": [registrations.get(x, 0) for x in labels],
                          "validados": [validations.get(x, 0) for x in labels]},
                "regions": dict(sorted(regions.items(), key=lambda item: -item[1])[:10]),
                "weekly": {"labels": weekly_labels, "atual": week_now, "anterior": week_before},
                "hourly": {"labels": [f"{i:02}:00" for i in range(24)], "acessos": hourly},
                "channels": channels,
                "recentes": [{"id": x.id, "nome": x.nome, "data": x.data_cadastro.isoformat(), "status": x.status}
                             for x in rows[:8]],
            }
            store.set_json(cache_key, result, 30)
            return result

        @router.get("/reports/recenseados.csv")
        def csv_report(db: Session = Depends(get_db), user_id: int = Depends(current_user)):
            records = db.scalars(select(Recenseado).order_by(Recenseado.id)).all()
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["ID", "Nome", "CPF", "Estado", "Região", "Canal", "Status", "Biometria", "Data de cadastro"])
            for x in records:
                writer.writerow([x.id, x.nome, x.cpf_mascarado, x.estado, x.regiao, x.canal_acesso, x.status,
                                 "Validada" if x.biometria_validada else "Pendente", x.data_cadastro.isoformat()])
            return StreamingResponse(iter([output.getvalue()]), media_type="text/csv; charset=utf-8",
                                     headers={"Content-Disposition": "attachment; filename=relatorio-censo.csv"})

        @router.get("/reports/recenseados.json")
        def json_report(db: Session = Depends(get_db), user_id: int = Depends(current_user)):
            records = db.scalars(select(Recenseado).order_by(Recenseado.id)).all()
            return {"generated_at": datetime.now(timezone.utc), "total": len(records), "items": [
                {"id": x.id, "nome": x.nome, "cpf": x.cpf_mascarado, "estado": x.estado, "regiao": x.regiao,
                 "canal_acesso": x.canal_acesso, "status": x.status, "biometria_validada": x.biometria_validada,
                 "data_cadastro": x.data_cadastro} for x in records]}
    ''',
    "app/main.py": r'''
        from contextlib import asynccontextmanager
        from pathlib import Path

        from fastapi import FastAPI
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        from app.config import settings
        from app.database import Base, SessionLocal, engine
        from app.models import Recenseado
        from app.routers import analytics, auth, recenseados
        from app.routers.setup import initialize_admin

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            settings.validate()
            Base.metadata.create_all(bind=engine)
            initialize_admin()
            yield

        app = FastAPI(title="Censo Previdenciário", version="1.0.0", lifespan=lifespan)
        app.include_router(auth.router)
        app.include_router(recenseados.router)
        app.include_router(analytics.router)
        frontend = Path(__file__).resolve().parent.parent / "frontend"
        app.mount("/static", StaticFiles(directory=frontend), name="static")
        app.mount("/uploads", StaticFiles(directory=settings.upload_dir, check_dir=False), name="uploads")

        @app.get("/")
        def index():
            return FileResponse(frontend / "index.html")

        @app.get("/health")
        def health():
            return {"status": "ok", "service": "censo-previdenciario"}
    ''',
    "frontend/index.html": r'''
        <!doctype html>
        <html lang="pt-BR">
        <head>
          <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
          <meta name="theme-color" content="#13578d"><title>Painel Institucional | Censo Previdenciário</title>
          <link rel="stylesheet" href="/static/styles.css">
          <script src="https://cdn.tailwindcss.com"></script>
          <script>tailwind.config={darkMode:"class",theme:{extend:{colors:{institutional:"#13578d"}}}};</script>
          <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js" defer></script>
          <script type="module" src="/static/app.js"></script>
        </head>
        <body>
          <div id="login-screen" class="login-screen">
            <form id="login-form" class="login-card"><div class="brand-mark">CP</div><p class="eyebrow">PORTAL INSTITUCIONAL</p>
              <h1>Censo Previdenciário</h1><p class="muted">Acesse o ambiente administrativo seguro.</p>
              <label>E-mail<input id="login-email" type="email" value="admin@local.test" required></label>
              <label>Senha<input id="login-password" type="password" value="change-me-now" required></label>
              <p id="login-error" class="error" hidden></p><button class="primary-button">Entrar</button>
            </form>
          </div>
          <div id="application" hidden>
            <header class="topbar"><a class="wordmark" href="#" data-page="dashboard"><span class="brand-mark small">CP</span><span>CENSO<br><b>PREVIDENCIÁRIO</b></span></a>
              <label class="global-search"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m16 16 4 4"/></svg><input id="quick-search" placeholder="Buscar recenseados..." aria-label="Busca rápida"></label>
              <div class="header-links"><button data-page="reports">Relatórios</button><button data-page="apps">Utilitários</button><button data-page="people">Arquivos</button><button id="settings-open" title="Configurações" aria-label="Configurações"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="m19.4 15 .1.1 1.4 1.1-1.4 2.4-1.7-.7a8 8 0 0 1-1.7 1l-.3 1.8h-2.8l-.3-1.8a8 8 0 0 1-1.7-1l-1.7.7-1.4-2.4L7.3 15a8 8 0 0 1 0-2l-1.4-1.1 1.4-2.4 1.7.7a8 8 0 0 1 1.7-1L11 7.4h2.8l.3 1.8a8 8 0 0 1 1.7 1l1.7-.7 1.4 2.4-1.4 1.1a8 8 0 0 1-.1 2Z"/></svg></button><button id="logout-button">Sair</button></div>
            </header>
            <div class="shell"><aside class="sidebar"><div class="side-label">GESTÃO</div>
              <button class="nav-button active" data-page="dashboard"><span class="nav-icon">▦</span>Painel Analítico</button>
              <button class="nav-button" data-page="apps"><span class="nav-icon">▧</span>Aplicativos &amp; Módulos</button>
              <button class="nav-button" data-page="people"><span class="nav-icon">♙</span>Gestão de Recenseados</button>
              <button class="nav-button" data-page="reports"><span class="nav-icon">▤</span>Relatórios Finais</button>
              <button class="nav-button" data-page="terminal"><span class="nav-icon">⌘</span>Terminal CLI</button>
              <div class="side-bottom"><span class="online-dot"></span>Serviços operacionais</div></aside>
              <main class="content">
                <section id="page-dashboard" class="page">
                  <div class="page-heading"><div><p class="eyebrow">VISÃO GERAL</p><h1>Painel Analítico</h1><p class="muted">Indicadores operacionais do Censo Previdenciário.</p></div>
                    <label class="filter-label">Período<select id="period-filter"><option value="7">Últimos 7 dias</option><option value="30">Últimos 30 dias</option><option value="all">Todos</option></select></label></div>
                  <div class="metric-grid"><article class="metric-card"><span>Total de recenseados</span><strong id="metric-total">—</strong><small>Base consolidada</small></article><article class="metric-card"><span>Pendentes</span><strong id="metric-pending">—</strong><small>Aguardando análise</small></article><article class="metric-card"><span>Validados por biometria</span><strong id="metric-validated">—</strong><small>Validação simulada</small></article><article class="metric-card"><span>Cadastros no período</span><strong id="metric-new">—</strong><small id="range-label">Período selecionado</small></article></div>
                  <div class="dashboard-grid">
                    <article class="widget"><div class="widget-title"><div><span class="widget-kicker">EVOLUÇÃO</span><h2>Cadastros diários vs. validados</h2></div></div><div class="chart-box"><canvas id="daily-chart"></canvas></div></article>
                    <article class="widget"><div class="widget-title"><div><span class="widget-kicker">DISTRIBUIÇÃO</span><h2>Recenseados por estado</h2></div></div><div id="region-ranking" class="ranking"></div></article>
                    <article class="widget recent-widget"><div class="widget-title"><div><span class="widget-kicker">ATIVIDADE</span><h2>Registros recentes</h2></div><button class="text-button" data-page="people">Ver todos</button></div><div class="table-wrap"><table><thead><tr><th>ID</th><th>Data/hora</th><th>Status</th><th>Ações</th></tr></thead><tbody id="recent-rows"></tbody></table></div></article>
                    <article class="widget"><div class="widget-title"><div><span class="widget-kicker">TENDÊNCIA</span><h2>Comparativo semanal de atendimentos</h2></div></div><div class="chart-box"><canvas id="weekly-chart"></canvas></div></article>
                    <article class="widget"><div class="widget-title"><div><span class="widget-kicker">MOVIMENTO</span><h2>Acessos por hora</h2></div></div><div class="chart-box"><canvas id="hourly-chart"></canvas></div></article>
                    <article class="widget"><div class="widget-title"><div><span class="widget-kicker">ORIGEM</span><h2>Cadastros por tipo de acesso</h2></div></div><div class="chart-box"><canvas id="channel-chart"></canvas></div></article>
                  </div>
                </section>
                <section id="page-apps" class="page" hidden><div class="page-heading"><div><p class="eyebrow">FERRAMENTAS</p><h1>Aplicativos &amp; Módulos</h1><p class="muted">Acesso rápido aos módulos operacionais.</p></div></div><div class="apps-grid">
                  <button class="app-tile" data-page="people"><span class="tile-icon">01</span><b>Gestão de Recenseados</b><small>Cadastro, consulta e validação.</small></button><button class="app-tile" data-page="reports"><span class="tile-icon">02</span><b>Relatórios Finais</b><small>Exportação e impressão de dados.</small></button><button class="app-tile" data-page="terminal"><span class="tile-icon">03</span><b>Terminal CLI</b><small>Comandos de operação rápida.</small></button><button class="app-tile" data-page="dashboard"><span class="tile-icon">04</span><b>Painel Analítico</b><small>Indicadores do censo.</small></button></div></section>
                <section id="page-people" class="page" hidden><div class="page-heading"><div><p class="eyebrow">CADASTRO E ACOMPANHAMENTO</p><h1>Gestão de Recenseados</h1><p class="muted">Consulte e mantenha os registros do censo.</p></div><button id="new-person" class="primary-button">Novo recenseado</button></div>
                  <div class="toolbar"><input id="people-search" placeholder="Nome, estado ou região"><select id="status-filter"><option value="">Todos os status</option><option>PENDENTE</option><option>EM_ANALISE</option><option>VALIDADO</option><option>REJEITADO</option></select><span id="people-total" class="muted"></span></div>
                  <div class="widget table-widget"><div class="table-wrap"><table><thead><tr><th>Recenseado</th><th>CPF</th><th>Localidade</th><th>Canal</th><th>Status</th><th>Biometria</th><th>Ações</th></tr></thead><tbody id="people-rows"></tbody></table></div><div class="pagination"><button id="prev-page">Anterior</button><span id="page-label"></span><button id="next-page">Próxima</button></div></div></section>
                <section id="page-reports" class="page" hidden><div class="page-heading"><div><p class="eyebrow">DADOS CONSOLIDADOS</p><h1>Relatórios Finais</h1><p class="muted">Gere relatórios institucionais para análise e arquivo.</p></div></div><div class="report-panel"><div class="report-symbol">PDF</div><div><h2>Relatório Final Consolidado</h2><p>Relação de recenseados com CPF mascarado, região, canal e status.</p><span>Impressão/PDF · CSV · JSON</span></div><div class="report-actions"><button id="download-csv" class="primary-button">Exportar CSV</button><button id="download-json" class="secondary-button">Baixar JSON</button><button id="print-report" class="secondary-button">Imprimir / PDF</button></div></div></section>
                <section id="page-terminal" class="page" hidden><div class="page-heading"><div><p class="eyebrow">FERRAMENTA ADMINISTRATIVA</p><h1>Terminal CLI</h1><p class="muted">Comandos operacionais para tarefas frequentes.</p></div></div><div class="terminal-panel"><div class="terminal-bar"><span></span><span></span><span></span><b>censo-admin — console seguro</b></div><div id="terminal-output" class="terminal-output"></div><form id="terminal-form" class="terminal-form"><label>operador@censo:~$</label><input id="terminal-input" autocomplete="off" placeholder="Digite ajuda para listar comandos"><button>Executar</button></form></div><div class="command-help"><b>Comandos disponíveis</b><code>status</code><code>relatorio</code><code>cadastrar --nome "Nome" --cpf 00000000000 --estado SP --regiao Sudeste --canal Desktop</code><code>tema escuro | tema claro</code></div></section>
              </main>
            </div>
          </div>
          <dialog id="person-dialog" class="dialog"><form id="person-form"><div class="dialog-head"><div><p class="eyebrow">DADOS CADASTRAIS</p><h2 id="person-dialog-title">Novo recenseado</h2></div><button type="button" class="close-button" data-close="person-dialog" aria-label="Fechar">×</button></div><input id="person-id" type="hidden"><label>Nome completo<input id="person-name" required minlength="2" maxlength="150"></label><label>CPF<input id="person-cpf" required maxlength="14" placeholder="000.000.000-00"></label><div class="form-row"><label>Estado (UF)<input id="person-state" required maxlength="2" placeholder="SP"></label><label>Região<input id="person-region" required maxlength="30" placeholder="Sudeste"></label></div><label>Canal de acesso<select id="person-channel"><option>Presencial</option><option>Desktop</option><option>Mobile</option></select></label><label>Foto do documento/rosto<input id="person-photo" type="file" accept="image/png,image/jpeg"></label><img id="photo-preview" class="photo-preview" hidden alt="Pré-visualização da imagem"><p id="person-error" class="error" hidden></p><div class="dialog-actions"><button type="button" class="secondary-button" data-close="person-dialog">Cancelar</button><button class="primary-button">Salvar registro</button></div></form></dialog>
          <dialog id="settings-dialog" class="dialog settings-dialog"><div class="dialog-head"><div><p class="eyebrow">PREFERÊNCIAS</p><h2>Configurações</h2></div><button class="close-button" data-close="settings-dialog" aria-label="Fechar">×</button></div><label>Tema da interface<select id="theme-select"><option value="light">Claro</option><option value="dark">Escuro</option></select></label><label>Bloqueio por inatividade<select id="idle-select"><option value="1">1 minuto (teste)</option><option value="5">5 minutos</option><option value="10">10 minutos</option><option value="15">15 minutos</option></select></label><p class="muted">A sessão também expira no servidor conforme o limite configurado.</p></dialog>
          <div id="lock-screen" class="lock-screen" hidden><div class="lock-card"><div class="brand-mark">CP</div><h2>Sessão bloqueada</h2><p>Por segurança, sua sessão foi bloqueada por inatividade.</p><button id="unlock-button" class="primary-button">Voltar ao acesso</button></div></div>
          <div id="toast" class="toast" role="status" hidden></div>
        </body></html>
    ''',
    "frontend/styles.css": r'''
        :root{font-family:Inter,"Segoe UI",Arial,sans-serif;color:#243447;background:#f2f5f8;font-synthesis:none;--blue:#13578d;--blue2:#2177b7;--line:#dce4eb;--muted:#758494;--surface:#fff;--body:#f2f5f8;--text:#243447}
        *{box-sizing:border-box}body{margin:0;background:var(--body);color:var(--text);font-size:13px}body.dark{--body:#111b26;--surface:#192735;--text:#e2eaf1;--line:#304251;--muted:#9aabba;background:var(--body)}button,input,select{font:inherit}button{cursor:pointer}button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid #65a9dc;outline-offset:1px}.topbar{height:56px;background:#13578d;color:#fff;display:flex;align-items:center;padding:0 24px;gap:26px;box-shadow:0 2px 6px #0e345422}.wordmark{display:flex;align-items:center;gap:10px;color:#fff;text-decoration:none;font-size:10px;line-height:1.2;letter-spacing:.07em;min-width:220px}.wordmark b{font-size:12px}.brand-mark{width:44px;height:44px;border:1px solid #c5d9e8;border-radius:4px;display:grid;place-items:center;color:#13578d;font-size:14px;font-weight:750;background:#fff}.brand-mark.small{width:34px;height:34px;color:#13578d;font-size:11px}.global-search{display:flex;align-items:center;gap:8px;max-width:380px;flex:1;background:#ffffff20;border:1px solid #ffffff3a;padding:7px 10px;border-radius:3px}.global-search svg{width:16px;fill:none;stroke:currentColor;stroke-width:1.8}.global-search input{border:0;outline:0;background:transparent;color:#fff;width:100%}.global-search input::placeholder{color:#d8e6f0}.header-links{display:flex;align-items:center;gap:5px;margin-left:auto}.header-links button{border:0;background:transparent;color:#eaf3f9;padding:8px 9px;border-radius:3px}.header-links button:hover{background:#ffffff1a}.header-links svg{width:19px;height:19px;fill:none;stroke:currentColor;stroke-width:1.6;vertical-align:middle}.shell{min-height:calc(100vh - 56px);display:flex}.sidebar{width:226px;background:var(--surface);border-right:1px solid var(--line);padding:22px 12px;display:flex;flex-direction:column;flex-shrink:0}.side-label,.eyebrow,.widget-kicker{font-size:10px;letter-spacing:.09em;color:#3b84b5;font-weight:700}.side-label{padding:0 12px 12px;color:#8191a0}.nav-button{display:flex;align-items:center;gap:12px;border:0;text-align:left;background:transparent;color:var(--muted);padding:12px;border-radius:3px;margin:2px 0}.nav-button:hover,.nav-button.active{background:#eaf3f9;color:#13578d}.dark .nav-button:hover,.dark .nav-button.active{background:#233b4d;color:#9dd0f1}.nav-icon{font-size:17px;width:20px;text-align:center}.side-bottom{margin-top:auto;border-top:1px solid var(--line);padding:16px 9px 0;color:var(--muted);font-size:11px}.online-dot{display:inline-block;width:7px;height:7px;background:#34a56a;border-radius:50%;margin-right:7px}.content{max-width:1600px;min-width:0;width:100%;margin:0 auto;padding:24px 28px 42px}.page-heading{display:flex;align-items:center;justify-content:space-between;margin:0 0 17px}.page-heading h1{font-size:24px;letter-spacing:-.03em;margin:4px 0}.muted{color:var(--muted);margin:5px 0 0}.filter-label{display:flex;align-items:center;gap:9px;color:var(--muted)}input,select{border:1px solid var(--line);border-radius:3px;padding:9px 10px;background:var(--surface);color:var(--text)}.filter-label select{min-width:140px}.metric-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px;margin:18px 0 14px}.metric-card{background:var(--surface);border:1px solid var(--line);border-top:2px solid #428bb9;border-radius:3px;padding:15px 17px;box-shadow:0 2px 5px #1a34400a}.metric-card span,.metric-card small{display:block;color:var(--muted);font-size:11px}.metric-card strong{display:block;font-size:25px;line-height:1.5;color:var(--text)}.metric-card small{font-size:10px}.dashboard-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px}.widget{background:var(--surface);border:1px solid var(--line);border-radius:3px;min-width:0;padding:13px 14px;box-shadow:0 2px 5px #1a344008}.widget-title{display:flex;justify-content:space-between;align-items:center;min-height:35px;border-bottom:1px solid var(--line);padding:0 0 9px}.widget-title h2{font-size:13px;margin:4px 0 0;font-weight:650}.widget-kicker{font-size:9px;color:#8292a0}.chart-box{position:relative;height:205px;padding-top:12px}.recent-widget{grid-column:span 1}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;text-align:left;white-space:nowrap}th{font-size:10px;font-weight:650;color:var(--muted);background:#f7f9fb}.dark th{background:#1d2b38}th,td{border-bottom:1px solid var(--line);padding:10px 8px}td{font-size:11px}.badge{display:inline-block;padding:4px 7px;border-radius:3px;font-size:9px;font-weight:700;background:#edf2f7;color:#526476}.badge-VALIDADO{background:#e4f4eb;color:#23744b}.badge-PENDENTE{background:#fff4dc;color:#946500}.badge-EM_ANALISE{background:#e7f2fc;color:#216b9b}.badge-REJEITADO{background:#fde9e8;color:#ad3932}.ranking{padding:12px 1px}.rank-row{display:grid;grid-template-columns:30px 1fr 24px;align-items:center;gap:8px;margin:11px 0;font-size:11px}.rank-row>span:first-child{color:var(--muted)}.rank-bar{height:7px;background:#edf1f4;border-radius:5px;overflow:hidden;margin-top:4px}.rank-bar i{display:block;height:100%;background:#287db4;border-radius:5px}.text-button{border:0;background:none;color:#2576a9;font-size:11px}.primary-button,.secondary-button{border:1px solid transparent;border-radius:3px;padding:9px 13px;font-weight:650;font-size:11px}.primary-button{background:#176da5;color:#fff}.primary-button:hover{background:#105982}.secondary-button{background:var(--surface);border-color:var(--line);color:var(--text)}.toolbar{display:flex;align-items:center;gap:9px;margin:13px 0}.toolbar input{width:min(380px,45vw)}.toolbar select{min-width:150px}.table-widget{padding:0}.table-widget .table-wrap{min-height:230px}.pagination{display:flex;justify-content:center;align-items:center;gap:15px;padding:12px}.pagination button{border:1px solid var(--line);background:var(--surface);color:var(--text);padding:6px 12px;border-radius:3px}.row-actions{display:flex;gap:5px}.row-actions button{border:1px solid var(--line);background:var(--surface);border-radius:3px;color:#3478a1;padding:5px 7px;font-size:10px}.apps-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.app-tile{background:var(--surface);border:1px solid var(--line);border-radius:3px;text-align:left;padding:18px;display:flex;flex-direction:column;gap:9px;color:var(--text)}.app-tile:hover{border-color:#4d95be;box-shadow:0 5px 15px #1a344012}.tile-icon{width:34px;height:34px;display:grid;place-items:center;background:#e8f2f8;color:#176999;border-radius:3px;font-weight:700}.app-tile small{color:var(--muted)}.report-panel{display:flex;align-items:center;gap:20px;padding:23px;background:var(--surface);border:1px solid var(--line);border-left:3px solid #2877a6}.report-symbol{width:55px;height:60px;border:1px solid #d5e0e8;color:#246f9c;display:grid;place-items:center;font-size:13px;font-weight:750}.report-panel h2{margin:0 0 7px;font-size:17px}.report-panel p{margin:0 0 7px;color:var(--muted)}.report-panel span{font-size:10px;color:#4684a8}.report-actions{margin-left:auto;display:flex;gap:7px;flex-wrap:wrap}.terminal-panel{background:#111e29;border:1px solid #243b4d;border-radius:4px;overflow:hidden;color:#e2ebf2}.terminal-bar{height:38px;background:#1a2c3b;padding:0 13px;display:flex;align-items:center;gap:5px}.terminal-bar>span{width:8px;height:8px;border-radius:50%;background:#708391}.terminal-bar>span:first-child{background:#db7164}.terminal-bar>span:nth-child(2){background:#d9b45e}.terminal-bar>span:nth-child(3){background:#63a879}.terminal-bar b{margin:auto;font-size:10px;font-weight:500;color:#bdcbd5}.terminal-output{height:270px;padding:16px;font:12px/1.7 ui-monospace,Menlo,monospace;overflow:auto}.terminal-line{margin:0;color:#d1e4ee}.terminal-line .prompt{color:#70c794}.terminal-line.error{color:#f18a7e}.terminal-form{display:flex;align-items:center;gap:9px;border-top:1px solid #324552;padding:12px}.terminal-form label{font:11px ui-monospace,Menlo,monospace;color:#7acb96;white-space:nowrap}.terminal-form input{flex:1;background:#172a38;color:#fff;border-color:#354c5c;font:12px ui-monospace,Menlo,monospace}.terminal-form button{background:#2375a4;color:white;border:0;border-radius:3px;padding:9px 14px}.command-help{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:13px;color:var(--muted);font-size:11px}.command-help code{background:var(--surface);border:1px solid var(--line);padding:5px 7px;border-radius:3px;font-size:10px}.dialog{width:min(520px,calc(100% - 25px));border:1px solid var(--line);border-radius:5px;padding:22px;background:var(--surface);color:var(--text);box-shadow:0 20px 70px #12253855}.dialog::backdrop{background:#11253688}.dialog form,.settings-dialog{display:grid;gap:12px}.dialog-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:2px}.dialog-head h2{margin:4px 0;font-size:18px}.close-button{border:0;background:transparent;font-size:23px;color:var(--muted)}.dialog label,.login-card label{display:grid;gap:6px;font-size:11px;font-weight:650}.dialog input,.dialog select{width:100%}.form-row{display:grid;grid-template-columns:1fr 1fr;gap:10px}.dialog-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:5px}.photo-preview{max-width:100%;max-height:160px;object-fit:contain}.error{color:#b3342f;font-size:11px}.login-screen{min-height:100vh;display:grid;place-items:center;background:linear-gradient(130deg,#103e65,#1d6e9e)}.login-card{width:min(390px,calc(100% - 30px));display:grid;gap:12px;background:#fff;padding:30px;border-radius:5px;box-shadow:0 18px 55px #082a4445;color:#233648}.login-card .brand-mark{margin-bottom:4px}.login-card h1{font-size:22px;margin:0}.login-card .muted{font-size:12px;margin:0 0 5px}.login-card label{color:#485a68}.login-card input{width:100%;margin-top:5px}.login-card .primary-button{margin-top:5px;padding:11px}.lock-screen{position:fixed;inset:0;background:#112536eF;display:grid;place-items:center;z-index:10}.lock-card{width:min(360px,calc(100% - 30px));background:var(--surface);color:var(--text);padding:27px;border-radius:5px;text-align:center}.lock-card .brand-mark{margin:auto}.lock-card h2{margin-bottom:5px}.lock-card p{color:var(--muted)}.toast{position:fixed;right:20px;bottom:20px;background:#153e5e;color:#fff;padding:12px 16px;border-radius:4px;z-index:20;box-shadow:0 5px 20px #0003}.dark .metric-card,.dark .widget,.dark .app-tile,.dark .report-panel{box-shadow:none}@media(max-width:1100px){.sidebar{width:190px}.dashboard-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.metric-grid{grid-template-columns:repeat(2,1fr)}.apps-grid{grid-template-columns:repeat(2,1fr)}.wordmark{min-width:auto}.header-links button:nth-child(2),.header-links button:nth-child(3){display:none}}@media(max-width:700px){.topbar{padding:0 12px;gap:10px;height:52px}.wordmark{font-size:8px}.wordmark b{font-size:9px}.global-search{max-width:none}.header-links button{padding:6px}.header-links button:first-child{display:none}.shell{display:block}.sidebar{width:100%;height:auto;position:sticky;top:0;z-index:4;padding:5px;flex-direction:row;overflow:auto;border-right:0;border-bottom:1px solid var(--line)}.side-label,.side-bottom{display:none}.nav-button{flex:0 0 auto;gap:6px;padding:9px;font-size:10px}.nav-icon{font-size:13px;width:auto}.content{padding:17px 12px 28px}.page-heading h1{font-size:21px}.metric-grid{gap:8px}.metric-card{padding:11px}.metric-card strong{font-size:21px}.dashboard-grid{grid-template-columns:1fr}.chart-box{height:190px}.toolbar{flex-wrap:wrap}.toolbar input{width:100%}.report-panel{align-items:flex-start;flex-wrap:wrap;padding:16px}.report-actions{margin-left:0;width:100%}.apps-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.app-tile{padding:13px}.terminal-form{flex-wrap:wrap}.terminal-form input{min-width:0}.form-row{grid-template-columns:1fr}.filter-label{font-size:10px}.filter-label select{min-width:110px}.page-heading>.primary-button{padding:8px}.header-links button:last-child{font-size:10px}}@media print{.topbar,.sidebar,.page-heading button,.report-actions,.toolbar,.pagination{display:none!important}.content{padding:0}.page[hidden]{display:none!important}.widget,.metric-card{box-shadow:none;border:1px solid #aaa;color:#111;background:#fff}}
    ''',
    "frontend/app.js": r'''
        const $ = (selector, root = document) => root.querySelector(selector);
        const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
        const state = {token: localStorage.getItem("censo_token"), page: "dashboard", peoplePage: 1, totalPages: 1, charts: {}, idleMinutes: 15, timer: null, toastTimer: null};
        const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
        async function api(path, options = {}) {
          const headers = new Headers(options.headers || {});
          if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
          if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
          const response = await fetch(path, {...options, headers});
          if (response.status === 401 && state.token) { lockSession(); throw new Error("Sessão expirada"); }
          if (!response.ok) {
            let message = `Falha HTTP ${response.status}`;
            try { const data = await response.json(); message = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data); } catch {}
            throw new Error(message);
          }
          return response.status === 204 ? null : response.json();
        }
        function toast(message) { const el=$("#toast"); el.textContent=message; el.hidden=false; clearTimeout(state.toastTimer); state.toastTimer=setTimeout(()=>el.hidden=true,3200); }
        function applyTheme(theme) { document.body.classList.toggle("dark", theme==="dark"); localStorage.setItem("censo_theme",theme); $("#theme-select").value=theme; }
        function setPage(name) { state.page=name; $$(".page").forEach((el)=>el.hidden=el.id!==`page-${name}`); $$(".nav-button").forEach((el)=>el.classList.toggle("active",el.dataset.page===name)); if(name==="people") loadPeople(); if(name==="dashboard") loadDashboard(); }
        function lockSession() { if(!state.token)return; $("#lock-screen").hidden=false; }
        function resetIdle() {
          if(!state.token || $("#settings-dialog").open || $("#person-dialog").open || !$("#lock-screen").hidden)return;
          clearTimeout(state.timer); const chosen=Number(localStorage.getItem("censo_idle")||state.idleMinutes);
          state.timer=setTimeout(lockSession,chosen*60*1000);
        }
        function startSession(token,idle) { state.token=token;state.idleMinutes=idle;localStorage.setItem("censo_token",token);$("#login-screen").hidden=true;$("#application").hidden=false;$("#lock-screen").hidden=true;resetIdle();loadDashboard().catch(showError); }
        function showError(error) { toast(error.message||"Erro inesperado"); }
        function statusBadge(status) { return `<span class="badge badge-${escapeHTML(status)}">${escapeHTML(status.replace("_"," "))}</span>`; }
        function formatDate(value) { return new Date(value).toLocaleString("pt-BR",{dateStyle:"short",timeStyle:"short"}); }
        function chart(id,type,data,options={}) {
          if(!window.Chart)return;
          if(state.charts[id])state.charts[id].destroy();
          state.charts[id]=new Chart($(`#${id}`),{type,data,options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:"bottom",labels:{boxWidth:9,font:{size:10},color:getComputedStyle(document.body).getPropertyValue("--muted")}}},scales:type==="doughnut"?{}:{x:{grid:{display:false},ticks:{font:{size:9},color:"#80909d"},border:{display:false}},y:{beginAtZero:true,grid:{color:"#e9eef2"},ticks:{font:{size:9},color:"#80909d"},border:{display:false}}},...options}});
        }
        async function loadDashboard() {
          const data=await api(`/api/dashboard?period=${$("#period-filter").value}`);
          $("#metric-total").textContent=data.total;$("#metric-pending").textContent=data.pendentes;$("#metric-validated").textContent=data.validados;$("#metric-new").textContent=data.novos;
          const labels=data.daily.labels.map((x)=>new Date(`${x}T12:00:00`).toLocaleDateString("pt-BR",{day:"2-digit",month:"2-digit"}));
          chart("daily-chart","bar",{labels,datasets:[{label:"Cadastros",data:data.daily.cadastros,backgroundColor:"#2c78b4",borderRadius:2},{label:"Validados",data:data.daily.validados,backgroundColor:"#e44920",borderRadius:2}]});
          const regions=Object.entries(data.regions);const max=Math.max(1,...regions.map(([,v])=>v));
          $("#region-ranking").innerHTML=regions.length?regions.map(([name,value],i)=>`<div class="rank-row"><span>${String(i+1).padStart(2,"0")}</span><div><b>${escapeHTML(name)}</b><div class="rank-bar"><i style="width:${Math.max(3,value/max*100)}%"></i></div></div><b>${value}</b></div>`).join(""):'<p class="muted">Sem registros no período.</p>';
          $("#recent-rows").innerHTML=data.recentes.length?data.recentes.map((x)=>`<tr><td>#${x.id}</td><td>${formatDate(x.data)}</td><td>${statusBadge(x.status)}</td><td><button class="text-button" data-open-person="${x.id}">Abrir</button></td></tr>`).join(""):'<tr><td colspan="4">Sem registros recentes.</td></tr>';
          chart("weekly-chart","line",{labels:data.weekly.labels,datasets:[{label:"Semana atual",data:data.weekly.atual,borderColor:"#2779b5",backgroundColor:"#2779b5",tension:.25},{label:"Semana anterior",data:data.weekly.anterior,borderColor:"#e44720",backgroundColor:"#e44720",tension:.25}]});
          chart("hourly-chart","bar",{labels:data.hourly.labels,datasets:[{label:"Acessos",data:data.hourly.acessos,backgroundColor:"#347bb4",borderRadius:1}]},{plugins:{legend:{display:false}}});
          const ch=data.channels;chart("channel-chart","doughnut",{labels:["Presencial","Desktop","Mobile"],datasets:[{data:[ch.Presencial||0,ch.Desktop||0,ch.Mobile||0],backgroundColor:["#e6411d","#2b69c8","#abb5c0"],borderWidth:2,borderColor:getComputedStyle(document.body).getPropertyValue("--surface"),hoverOffset:5}]},{cutout:"62%"});
        }
        async function loadPeople() {
          const params=new URLSearchParams({page:String(state.peoplePage),page_size:"10"});if($("#people-search").value.trim())params.set("q",$("#people-search").value.trim());if($("#status-filter").value)params.set("status",$("#status-filter").value);
          const data=await api(`/api/recenseados?${params}`);state.totalPages=Math.max(1,data.pages);
          $("#people-total").textContent=`${data.total} registros`;$("#page-label").textContent=`Página ${state.peoplePage} de ${state.totalPages}`;
          $("#prev-page").disabled=state.peoplePage<=1;$("#next-page").disabled=state.peoplePage>=state.totalPages;
          $("#people-rows").innerHTML=data.items.length?data.items.map((x)=>`<tr><td><b>${escapeHTML(x.nome)}</b><br><small>#${x.id}</small></td><td>${escapeHTML(x.cpf_mascarado)}</td><td>${escapeHTML(x.estado)} · ${escapeHTML(x.regiao)}</td><td>${escapeHTML(x.canal_acesso)}</td><td>${statusBadge(x.status)}</td><td>${x.biometria_validada?'<span class="badge badge-VALIDADO">Validada</span>':'<span class="badge">Pendente</span>'}</td><td><div class="row-actions"><button data-action="edit" data-id="${x.id}">Editar</button><button data-action="photo" data-id="${x.id}">Foto</button><button data-action="face" data-id="${x.id}">Biometria</button><button data-action="delete" data-id="${x.id}">Excluir</button></div></td></tr>`).join(""):'<tr><td colspan="7">Nenhum recenseado encontrado.</td></tr>';
        }
        function openPerson(record=null) {
          $("#person-form").reset();$("#person-id").value=record?.id||"";$("#person-dialog-title").textContent=record?"Editar recenseado":"Novo recenseado";$("#person-error").hidden=true;$("#person-cpf").disabled=!!record;$("#photo-preview").hidden=true;$("#person-dialog").showModal();
          if(record){$("#person-name").value=record.nome;$("#person-state").value=record.estado;$("#person-region").value=record.regiao;$("#person-channel").value=record.canal_acesso;}
        }
        async function savePerson(event) {
          event.preventDefault();const id=$("#person-id").value;const payload={nome:$("#person-name").value,estado:$("#person-state").value,regiao:$("#person-region").value,canal_acesso:$("#person-channel").value};
          if(!id)payload.cpf=$("#person-cpf").value;
          try{
            const record=await api(id?`/api/recenseados/${id}`:"/api/recenseados",{method:id?"PUT":"POST",body:JSON.stringify(payload)});
            const photo=$("#person-photo").files[0];if(photo){const form=new FormData();form.append("arquivo",photo);await api(`/api/recenseados/${record.id}/foto`,{method:"POST",body:form});}
            $("#person-dialog").close();toast("Registro salvo.");await loadPeople();await loadDashboard();
          }catch(error){$("#person-error").textContent=error.message;$("#person-error").hidden=false;}
        }
        async function rowAction(event) {
          const button=event.target.closest("[data-action]");if(!button)return;const id=Number(button.dataset.id);
          try {
            if(button.dataset.action==="edit"){const page=await api(`/api/recenseados?page=1&page_size=100`);openPerson(page.items.find((x)=>x.id===id));return;}
            if(button.dataset.action==="delete"){if(!confirm("Excluir este registro permanentemente?"))return;await api(`/api/recenseados/${id}`,{method:"DELETE"});toast("Registro excluído.");}
            if(button.dataset.action==="photo"){const file=document.createElement("input");file.type="file";file.accept="image/png,image/jpeg";file.onchange=async()=>{if(!file.files[0])return;const form=new FormData();form.append("arquivo",file.files[0]);await api(`/api/recenseados/${id}/foto`,{method:"POST",body:form});toast("Imagem atualizada.");};file.click();return;}
            if(button.dataset.action==="face"){const result=await api(`/api/recenseados/${id}/biometria`,{method:"POST",body:JSON.stringify({matched:true})});toast(`Simulação biométrica: ${result.assertividade}% de assertividade ilustrativa.`);}
            await loadPeople();await loadDashboard();
          }catch(error){showError(error);}
        }
        async function reportPrint() {
          const data=await api("/api/reports/recenseados.json");const rows=data.items.map((x)=>`<tr><td>${x.id}</td><td>${escapeHTML(x.nome)}</td><td>${escapeHTML(x.cpf)}</td><td>${escapeHTML(x.estado)} / ${escapeHTML(x.regiao)}</td><td>${escapeHTML(x.canal_acesso)}</td><td>${escapeHTML(x.status)}</td><td>${new Date(x.data_cadastro).toLocaleString("pt-BR")}</td></tr>`).join("");
          const win=window.open("","_blank");if(!win)throw new Error("Permita a abertura de pop-ups para gerar o PDF.");
          win.document.write(`<!doctype html><meta charset="utf-8"><title>Relatório Final do Censo</title><style>body{font:12px Arial;margin:24px;color:#243447}h1{color:#13578d}table{border-collapse:collapse;width:100%}td,th{border:1px solid #d3dce4;padding:7px;text-align:left}th{background:#edf3f7}@media print{body{margin:12mm}}</style><h1>Relatório Final Consolidado</h1><p>Gerado em ${new Date().toLocaleString("pt-BR")} · ${data.total} registros · CPF mascarado.</p><table><thead><tr><th>ID</th><th>Nome</th><th>CPF</th><th>Localidade</th><th>Canal</th><th>Status</th><th>Data</th></tr></thead><tbody>${rows||'<tr><td colspan="7">Sem registros.</td></tr>'}</tbody></table>`);
          win.document.close();win.focus();setTimeout(()=>win.print(),250);
        }
        function parseArgs(line) {
          const result={};for(const match of line.matchAll(/--([\w-]+)\s+(?:"([^"]*)"|'([^']*)'|([^\s]+))/g))result[match[1]]=match[2]??match[3]??match[4];return result;
        }
        async function terminalCommand(command) {
          const args=command.trim();if(!args)return "";
          if(args==="ajuda"||args==="help")return "Comandos: status | relatorio | cadastrar --nome \"Nome\" --cpf ... --estado SP --regiao Sudeste --canal Desktop | tema escuro | tema claro";
          if(args==="status"){const d=await api("/api/dashboard?period=all");return `Serviço ativo · ${d.total} recenseados · ${d.pendentes} pendentes · ${d.validados} biometria(s) validada(s).`;}
          if(args==="relatorio"){const d=await api("/api/reports/recenseados.json");return `Relatório consolidado pronto: ${d.total} registro(s). Acesse Relatórios Finais para exportar.`;}
          if(args==="tema escuro"||args==="tema claro"){applyTheme(args.endsWith("escuro")?"dark":"light");return "Preferência de tema atualizada.";}
          if(args.startsWith("cadastrar ")){const a=parseArgs(args);const item=await api("/api/recenseados",{method:"POST",body:JSON.stringify({nome:a.nome,cpf:a.cpf,estado:a.estado,regiao:a.regiao,canal_acesso:a.canal||"Desktop"})});await loadDashboard();return `Cadastro #${item.id} criado para ${item.nome}.`;}
          throw new Error("Comando desconhecido. Digite ajuda para consultar os comandos.");
        }
        function terminalLine(text,type="normal",command=false) {const p=document.createElement("p");p.className=`terminal-line ${type}`;if(command){const prompt=document.createElement("span");prompt.className="prompt";prompt.textContent="operador@censo:~$ ";p.append(prompt);}p.append(document.createTextNode(text));$("#terminal-output").append(p);$("#terminal-output").scrollTop=$("#terminal-output").scrollHeight;}
        async function runTerminal(event){event.preventDefault();const input=$("#terminal-input"),command=input.value.trim();input.value="";terminalLine(command,"normal",true);try{const output=await terminalCommand(command);if(output)terminalLine(output);}catch(error){terminalLine(error.message,"error");}}
        async function init() {
          applyTheme(localStorage.getItem("censo_theme")||"light");
          $("#theme-select").addEventListener("change",()=>applyTheme($("#theme-select").value));
          $("#idle-select").value=localStorage.getItem("censo_idle")||"15";$("#idle-select").addEventListener("change",()=>{localStorage.setItem("censo_idle",$("#idle-select").value);resetIdle();});
          if(state.token){$("#login-screen").hidden=true;$("#application").hidden=false;try{const user=await api("/api/auth/me");if(user)startSession(state.token,state.idleMinutes);}catch{state.token=null;localStorage.removeItem("censo_token");$("#login-screen").hidden=false;$("#application").hidden=true;}}
          $("#login-form").addEventListener("submit",async(event)=>{event.preventDefault();const error=$("#login-error");error.hidden=true;try{const data=await api("/api/auth/login",{method:"POST",body:JSON.stringify({email:$("#login-email").value,password:$("#login-password").value})});startSession(data.access_token,data.idle_minutes);}catch(e){error.textContent=e.message;error.hidden=false;}});
          $$(".nav-button,[data-page]").forEach((button)=>button.addEventListener("click",()=>{if(button.dataset.page)setPage(button.dataset.page);}));
          $("#settings-open").addEventListener("click",()=>$("#settings-dialog").showModal());
          $$("[data-close]").forEach((button)=>button.addEventListener("click",()=>$( `#${button.dataset.close}`).close()));
          $("#period-filter").addEventListener("change",()=>loadDashboard().catch(showError));
          $("#new-person").addEventListener("click",()=>openPerson());
          $("#person-form").addEventListener("submit",savePerson);
          $("#people-rows").addEventListener("click",rowAction);
          $("#prev-page").addEventListener("click",()=>{state.peoplePage=Math.max(1,state.peoplePage-1);loadPeople().catch(showError);});
          $("#next-page").addEventListener("click",()=>{state.peoplePage=Math.min(state.totalPages,state.peoplePage+1);loadPeople().catch(showError);});
          let searchTimer;$("#people-search").addEventListener("input",()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{state.peoplePage=1;loadPeople().catch(showError);},250);});
          $("#status-filter").addEventListener("change",()=>{state.peoplePage=1;loadPeople().catch(showError);});
          $("#quick-search").addEventListener("keydown",(event)=>{if(event.key==="Enter"){setPage("people");$("#people-search").value=event.target.value;loadPeople().catch(showError);}});
          $("#recent-rows").addEventListener("click",(event)=>{const button=event.target.closest("[data-open-person]");if(button){setPage("people");}});
          $("#person-photo").addEventListener("change",(event)=>{const file=event.target.files[0];if(!file)return;const preview=$("#photo-preview");preview.src=URL.createObjectURL(file);preview.hidden=false;});
          $("#download-csv").addEventListener("click",()=>download("/api/reports/recenseados.csv"));
          $("#download-json").addEventListener("click",()=>download("/api/reports/recenseados.json"));
          $("#print-report").addEventListener("click",()=>reportPrint().catch(showError));
          $("#terminal-form").addEventListener("submit",runTerminal);
          $("#logout-button").addEventListener("click",async()=>{try{await api("/api/auth/logout",{method:"POST"});}catch{}finally{localStorage.removeItem("censo_token");state.token=null;location.reload();}});
          $("#unlock-button").addEventListener("click",()=>{localStorage.removeItem("censo_token");state.token=null;location.reload();});
          ["pointerdown","keydown","touchstart"].forEach((name)=>document.addEventListener(name,resetIdle,{passive:true}));
          $("#terminal-output").innerHTML='<p class="terminal-line"><span class="prompt">censo-cli</span> Console administrativa disponível. Digite <b>ajuda</b>.</p>';
        }
        async function download(path){try{const response=await fetch(path,{headers:{Authorization:`Bearer ${state.token}`}});if(!response.ok)throw new Error("Não foi possível gerar o arquivo.");const blob=await response.blob();const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=path.endsWith("csv")?"relatorio-censo.csv":"relatorio-censo.json";a.click();URL.revokeObjectURL(a.href);}catch(e){showError(e);}}
        init().catch(showError);
    ''',
    "README.md": r'''
        # Portal Censo Previdenciário

        ## Executar

        ```bash
        python -m venv .venv
        source .venv/bin/activate  # Windows: .venv\Scripts\activate
        pip install -r requirements.txt
        cp .env.example .env       # Windows: copy .env.example .env
        uvicorn app.main:app --reload
        ```

        Abra http://127.0.0.1:8000. Credenciais locais iniciais: `admin@local.test` / `change-me-now`.
        Configure `ADMIN_PASSWORD` e `JWT_SECRET_KEY` antes de qualquer implantação. Sem Redis,
        sessões e cache funcionam com TTL em memória, compartilhados apenas no processo atual.

        ## Recursos

        CRUD paginado, validação matemática de CPF, unicidade, upload JPEG/PNG (5 MB), biometria
        explicitamente simulada, dashboard com período, CSV/JSON e impressão para PDF pelo navegador.
        O SQLite fica em `data/censo.db`; arquivos enviados ficam em `data/uploads/`.

        ## API

        A documentação interativa está em `/docs`. O frontend usa Chart.js e Tailwind CDN.
    ''',
    "tests/test_api.py": r'''
        import os
        from pathlib import Path

        os.environ.setdefault("DATABASE_URL", "sqlite:///./data/test.db")
        os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-long-enough")

        from fastapi.testclient import TestClient

        from app.main import app

        def test_health():
            with TestClient(app) as client:
                assert client.get("/health").json()["status"] == "ok"

        def test_login_and_cpf_validation():
            with TestClient(app) as client:
                token = client.post("/api/auth/login", json={"email": "admin@local.test", "password": "change-me-now"})
                assert token.status_code == 200
                headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
                invalid = client.post("/api/recenseados", headers=headers, json={
                    "nome": "Pessoa Teste", "cpf": "11111111111", "estado": "SP",
                    "regiao": "Sudeste", "canal_acesso": "Desktop",
                })
                assert invalid.status_code == 422

        def test_create_and_duplicate_cpf():
            with TestClient(app) as client:
                token = client.post("/api/auth/login", json={"email": "admin@local.test", "password": "change-me-now"}).json()
                headers = {"Authorization": f"Bearer {token['access_token']}"}
                payload = {"nome": "Pessoa Teste", "cpf": "529.982.247-25", "estado": "SP",
                           "regiao": "Sudeste", "canal_acesso": "Desktop"}
                first = client.post("/api/recenseados", headers=headers, json=payload)
                assert first.status_code == 201
                assert first.json()["cpf_mascarado"] == "***.982.247-**"
                assert client.post("/api/recenseados", headers=headers, json=payload).status_code == 409
    ''',
}


def write_project(destination: Path, force: bool) -> None:
    destination = destination.resolve()
    existing = [destination / name for name in FILES if (destination / name).exists()]
    if existing and not force:
        names = ", ".join(str(path.relative_to(destination)) for path in existing)
        raise FileExistsError(f"Arquivos existentes: {names}. Use --force para sobrescrever.")
    for relative, content in FILES.items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized = dedent(content).lstrip("\n")
        path.write_text(normalized, encoding="utf-8")
    (destination / "data").mkdir(parents=True, exist_ok=True)
    print(f"Projeto gerado em: {destination}")
    print("Próximos passos: pip install -r requirements.txt && cp .env.example .env && uvicorn app.main:app --reload")


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera uma aplicação institucional de Censo Previdenciário.")
    parser.add_argument("--output", "-o", type=Path, default=Path("sistema_completo"), help="Diretório de saída")
    parser.add_argument("--force", action="store_true", help="Sobrescreve apenas os arquivos que este gerador cria")
    args = parser.parse_args()
    try:
        write_project(args.output, args.force)
    except (OSError, FileExistsError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
