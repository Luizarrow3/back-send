from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User
from app.sessions import renovar_sessao

oauth2_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(subject: dict[str, Any]) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "sub": str(subject["id"]),
        "user_id": subject["id"],
        "email": subject["email"],
        "perfil": subject["perfil"],
        "jti": uuid4().hex,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None

    if not user.ativo:
        return None

    if not verify_password(password, user.senha_hash):
        user.tentativas_login += 1
        if user.tentativas_login >= 5:
            user.ativo = False
        db.commit()
        return None

    user.tentativas_login = 0
    user.ultima_tentativa = datetime.now(timezone.utc)
    db.commit()
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.scheme.lower() == "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token ausente ou inválido")

    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload.get("user_id") or payload.get("sub")
        if user_id is None:
            raise ValueError("id ausente")
    except (jwt.PyJWTError, ValueError, TypeError) as exc:  # pragma: no cover
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido") from exc

    session_id = payload.get("jti")
    if session_id is not None and not renovar_sessao(str(session_id), int(user_id)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão expirada por inatividade",
        )

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.ativo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não autorizado")

    return user


def ensure_admin_user(db: Session) -> User:
    admin = db.query(User).filter(User.email == settings.ADMIN_EMAIL).first()
    if admin is None:
        admin = User(
            email=settings.ADMIN_EMAIL,
            nome="Administrador",
            senha_hash=hash_password(settings.ADMIN_PASSWORD),
            perfil="ADMIN",
            ativo=True,
            tentativas_login=0,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
    return admin
