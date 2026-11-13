from redis import Redis

from app.auth.session import create_session, destroy_session, load_session

REDIS_URL = "redis://localhost:6379/15"


def _redis() -> Redis:
    return Redis.from_url(REDIS_URL, decode_responses=True, protocol=2)


def test_create_session_stores_user_with_ttl():
    redis_client = _redis()
    redis_client.flushdb()

    sid = create_session(redis_client, "user-123", ttl_seconds=60)

    assert redis_client.hget(f"sess:{sid}", "user_id") == "user-123"
    assert 0 < redis_client.ttl(f"sess:{sid}") <= 60

    redis_client.flushdb()


def test_load_session_returns_user_id():
    redis_client = _redis()
    redis_client.flushdb()
    sid = create_session(redis_client, "user-123", ttl_seconds=60)

    assert load_session(redis_client, sid) == "user-123"

    redis_client.flushdb()


def test_load_session_returns_none_when_missing():
    redis_client = _redis()
    redis_client.flushdb()

    assert load_session(redis_client, "no-existe") is None


def test_destroy_session_removes_key():
    redis_client = _redis()
    redis_client.flushdb()
    sid = create_session(redis_client, "user-123", ttl_seconds=60)

    destroy_session(redis_client, sid)

    assert redis_client.exists(f"sess:{sid}") == 0
