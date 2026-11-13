import secrets

SESSION_PREFIX = "sess:"


def _key(sid: str) -> str:
    return f"{SESSION_PREFIX}{sid}"


def create_session(redis_client, user_id, ttl_seconds: int) -> str:
    sid = secrets.token_urlsafe(32)
    redis_client.hset(_key(sid), mapping={"user_id": str(user_id)})
    redis_client.expire(_key(sid), ttl_seconds)
    return sid


def load_session(redis_client, sid: str | None) -> str | None:
    if not sid:
        return None
    return redis_client.hget(_key(sid), "user_id")


def destroy_session(redis_client, sid: str | None) -> None:
    if sid:
        redis_client.delete(_key(sid))
