"""Cache, contadores y rankings sobre Redis.

Mapa de claves:
- `cache:search:<hash>` — resultados serializados de una búsqueda (TTL corto).
- `cache:title:<id>` — ficha serializada de un título (TTL medio).
- `cnt:views:<id>` — visitas acumuladas a la ficha.
- `cnt:likes:<id>` — favoritos actuales del título (sincronizado con Mongo).
- `rank:popular` — ZSET de títulos ordenados por visitas.
"""

import json
import time
from collections.abc import Mapping
from hashlib import sha1

SEARCH_PREFIX = "cache:search:"
TITLE_PREFIX = "cache:title:"
API_PREFIX = "cache:api:"
VIEWS_PREFIX = "cnt:views:"
LIKES_PREFIX = "cnt:likes:"
RECENT_PREFIX = "recent:views:"
POPULAR_KEY = "rank:popular"
FAVORITES_KEY = "rank:favorites"
ACTIVE_USERS_KEY = "online:active"
RATE_LIMIT_PREFIX = "ratelimit:"

SEARCH_TTL_SECONDS = 60
TITLE_TTL_SECONDS = 300
EXTERNAL_TTL_SECONDS = 600
ACTIVE_WINDOW_SECONDS = 300  # 5 minutos para considerar activo a un usuario


def search_cache_key(params: Mapping, namespace: str = "") -> str:
    items = sorted(
        (key, str(value)) for key, value in params.items() if str(value).strip()
    )
    canonical = "&".join(f"{key}={value}" for key, value in items)
    digest = sha1(canonical.encode("utf-8")).hexdigest()[:16]
    prefix = f"{namespace}:" if namespace else ""
    return f"{SEARCH_PREFIX}{prefix}{digest}"


def title_cache_key(title_id, namespace: str = "") -> str:
    prefix = f"{namespace}:" if namespace else ""
    return f"{TITLE_PREFIX}{prefix}{title_id}"


def api_cache_key(source: str, query: str, namespace: str = "") -> str:
    digest = sha1(f"{source}:{query.strip().lower()}".encode("utf-8")).hexdigest()[:16]
    prefix = f"{namespace}:" if namespace else ""
    return f"{API_PREFIX}{prefix}{digest}"


def get_json(redis_client, key: str):
    value = redis_client.get(key)
    return json.loads(value) if value else None


def set_json(redis_client, key: str, value, ttl: int) -> None:
    redis_client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)


def _delete_by_prefix(redis_client, prefix: str) -> int:
    keys = list(redis_client.scan_iter(match=f"{prefix}*"))
    if not keys:
        return 0
    return redis_client.delete(*keys)


def invalidate_search(redis_client) -> int:
    return _delete_by_prefix(redis_client, SEARCH_PREFIX)


def invalidate_titles(redis_client) -> int:
    return _delete_by_prefix(redis_client, TITLE_PREFIX)


def invalidate_api(redis_client) -> int:
    return _delete_by_prefix(redis_client, API_PREFIX)


def register_view(redis_client, title_id) -> int:
    """Suma una visita y actualiza el ranking de popularidad."""
    views = redis_client.incr(f"{VIEWS_PREFIX}{title_id}")
    redis_client.zincrby(POPULAR_KEY, 1, str(title_id))
    return views


def view_count(redis_client, title_id) -> int:
    return int(redis_client.get(f"{VIEWS_PREFIX}{title_id}") or 0)


def sync_likes(redis_client, title_id, total: int) -> int:
    redis_client.set(f"{LIKES_PREFIX}{title_id}", total)
    return total


def like_count(redis_client, title_id) -> int:
    return int(redis_client.get(f"{LIKES_PREFIX}{title_id}") or 0)


def popular_title_ids(redis_client, limit: int = 8) -> list[str]:
    return redis_client.zrevrange(POPULAR_KEY, 0, limit - 1)


def popular_with_scores(redis_client, limit: int = 8) -> list[tuple[str, float]]:
    return redis_client.zrevrange(POPULAR_KEY, 0, limit - 1, withscores=True)


def add_recent_view(redis_client, user_id, title_id, max_items: int = 6) -> None:
    """Registra un título en el historial reciente del usuario usando una LIST en Redis."""
    key = f"{RECENT_PREFIX}{user_id}"
    raw_id = str(title_id)
    # Evita duplicados contiguos o en la lista
    redis_client.lrem(key, 0, raw_id)
    # Inserta al principio de la lista FIFO/LIFO
    redis_client.lpush(key, raw_id)
    # Mantiene un tamaño acotado
    redis_client.ltrim(key, 0, max_items - 1)


def get_recent_views(redis_client, user_id, limit: int = 6) -> list[str]:
    """Obtiene los últimos títulos vistos por el usuario desde la LIST en Redis."""
    key = f"{RECENT_PREFIX}{user_id}"
    raw_list = redis_client.lrange(key, 0, limit - 1)
    return [
        item.decode("utf-8") if isinstance(item, bytes) else str(item)
        for item in raw_list
    ]


def record_active_user(redis_client, identifier: str) -> None:
    """Registra un usuario activo en el ZSET con su timestamp actual."""
    now = time.time()
    redis_client.zadd(ACTIVE_USERS_KEY, {str(identifier): now})
    # Elimina entradas con más de ACTIVE_WINDOW_SECONDS de antigüedad
    redis_client.zremrangebyscore(ACTIVE_USERS_KEY, 0, now - ACTIVE_WINDOW_SECONDS)


def count_active_users(redis_client) -> int:
    """Retorna la cantidad de usuarios únicos activos en los últimos minutos."""
    now = time.time()
    redis_client.zremrangebyscore(ACTIVE_USERS_KEY, 0, now - ACTIVE_WINDOW_SECONDS)
    count = redis_client.zcard(ACTIVE_USERS_KEY)
    return max(1, count)


def sync_favorites_rank(redis_client, title_id, total: int) -> None:
    """Mantiene el ranking de títulos con más favoritos de la comunidad (ZSET)."""
    redis_client.zadd(FAVORITES_KEY, {str(title_id): total})


def popular_favorites_ids(redis_client, limit: int = 8) -> list[str]:
    """Obtiene los títulos con mayor cantidad de favoritos desde Redis (ZSET)."""
    return redis_client.zrevrange(FAVORITES_KEY, 0, limit - 1)


def is_rate_limited(redis_client, identifier: str, limit: int = 30, window: int = 60) -> bool:
    """Control de concurrencia y protección anti-spam con clave efímera (STRING + INCR + EXPIRE)."""
    key = f"{RATE_LIMIT_PREFIX}{identifier}"
    current = redis_client.incr(key)
    if current == 1:
        redis_client.expire(key, window)
    return current > limit
