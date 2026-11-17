from fastapi import HTTPException, status
from redis import Redis
from redis.exceptions import RedisError

from app.config import settings

_client: Redis | None = Redis.from_url(settings.REDIS_URL, decode_responses=True) if settings.REDIS_URL else None


def _unavailable(exc: RedisError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Serviço de sessões indisponível",
    )


def registrar_sessao(session_id: str, user_id: int) -> None:
    if _client is not None:
        try:
            _client.set(
                f"censo:session:{session_id}",
                str(user_id),
                ex=settings.SESSION_IDLE_MINUTES * 60,
            )
        except RedisError as exc:
            raise _unavailable(exc) from exc


def renovar_sessao(session_id: str, user_id: int) -> bool:
    if _client is None:
        return True

    chave = f"censo:session:{session_id}"
    try:
        if _client.get(chave) != str(user_id):
            return False
        return bool(_client.expire(chave, settings.SESSION_IDLE_MINUTES * 60))
    except RedisError as exc:
        raise _unavailable(exc) from exc


def encerrar_sessao(session_id: str) -> None:
    if _client is not None:
        try:
            _client.delete(f"censo:session:{session_id}")
        except RedisError as exc:
            raise _unavailable(exc) from exc
