import secrets

SESSION_PREFIX = "sess:"


def _key(sid: str) -> str:
    return f"{SESSION_PREFIX}{sid}"


def create_session(redis_client, user_id, ttl_seconds: int, role: str = "user") -> str:
    sid = secrets.token_urlsafe(32)
    redis_client.hset(
        _key(sid),
        mapping={
            "user_id": str(user_id),
            "role": role,
        },
    )
    redis_client.expire(_key(sid), ttl_seconds)
    return sid


def load_session(redis_client, sid: str | None) -> str | None:
    if not sid:
        return None
    return redis_client.hget(_key(sid), "user_id")


def touch_session(redis_client, sid: str | None, ttl_seconds: int) -> None:
    """Renueva el TTL de la sesión por actividad (Sliding Expiration)."""
    if sid:
        redis_client.expire(_key(sid), ttl_seconds)


def destroy_session(redis_client, sid: str | None) -> None:
    if sid:
        redis_client.delete(_key(sid))
