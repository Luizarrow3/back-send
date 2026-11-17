from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
import jwt
from sqlalchemy.orm import Session

from app.auth import authenticate_user, create_access_token, get_current_user, oauth2_scheme
from app.config import settings
from app.database import get_db
from app.models import User
from app.sessions import encerrar_sessao, registrar_sessao
from app.schemas import LoginRequest, TokenResponse, UserResponse

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if "@" not in payload.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="E-mail inválido",
        )

    user = authenticate_user(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
        )

    token = create_access_token({"id": user.id, "email": user.email, "perfil": user.perfil})
    session_id = jwt.decode(
        token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )["jti"]
    registrar_sessao(str(session_id), user.id)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        nome=current_user.nome,
        perfil=current_user.perfil,
    )


@router.get("/config")
def configuracao_sessao(current_user: User = Depends(get_current_user)) -> dict[str, int | bool]:
    del current_user
    return {
        "session_idle_minutes": settings.SESSION_IDLE_MINUTES,
        "redis_sessions_enabled": bool(settings.REDIS_URL),
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
) -> None:
    del current_user
    if credentials is not None:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        session_id = payload.get("jti")
        if session_id:
            encerrar_sessao(str(session_id))
