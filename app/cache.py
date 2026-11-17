import json
import logging
from typing import Any

from redis import Redis, RedisError

from app.config import settings

_client: Redis | None = Redis.from_url(settings.REDIS_URL, decode_responses=True) if settings.REDIS_URL else None
_SUMMARY_KEY = "censo:cache:resumo"
_logger = logging.getLogger(__name__)


def obter_resumo() -> dict[str, Any] | None:
    if _client is None:
        return None
    try:
        valor = _client.get(_SUMMARY_KEY)
    except RedisError:
        _logger.exception("Não foi possível consultar o cache Redis das estatísticas.")
        return None
    if valor is None:
        return None
    if not isinstance(valor, (str, bytes, bytearray)):
        raise TypeError("Resposta Redis inválida para o cache de estatísticas")
    return json.loads(valor)


def guardar_resumo(resumo: dict[str, Any]) -> None:
    if _client is not None:
        try:
            _client.set(_SUMMARY_KEY, json.dumps(resumo), ex=30)
        except RedisError:
            _logger.exception("Não foi possível atualizar o cache Redis das estatísticas.")


def invalidar_resumo() -> None:
    if _client is not None:
        try:
            _client.delete(_SUMMARY_KEY)
        except RedisError:
            _logger.exception("Não foi possível invalidar o cache Redis das estatísticas.")
