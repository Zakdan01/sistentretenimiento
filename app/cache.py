"""Cache, contadores y rankings sobre Redis.

Mapa de claves:
- `cache:search:<hash>` — resultados serializados de una búsqueda (TTL corto).
- `cache:title:<id>` — ficha serializada de un título (TTL medio).
- `cnt:views:<id>` — visitas acumuladas a la ficha.
- `cnt:likes:<id>` — favoritos actuales del título (sincronizado con Mongo).
- `rank:popular` — ZSET de títulos ordenados por visitas.
"""

import json
from collections.abc import Mapping
from hashlib import sha1

SEARCH_PREFIX = "cache:search:"
TITLE_PREFIX = "cache:title:"
VIEWS_PREFIX = "cnt:views:"
LIKES_PREFIX = "cnt:likes:"
POPULAR_KEY = "rank:popular"

SEARCH_TTL_SECONDS = 60
TITLE_TTL_SECONDS = 300


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
