from redis import Redis

from app.cache import (
    get_json,
    invalidate_search,
    invalidate_titles,
    like_count,
    popular_title_ids,
    register_view,
    search_cache_key,
    set_json,
    sync_likes,
    title_cache_key,
    view_count,
)

REDIS_URL = "redis://localhost:6379/15"


def _redis() -> Redis:
    redis_client = Redis.from_url(REDIS_URL, decode_responses=True, protocol=2)
    redis_client.flushdb()
    return redis_client


def test_search_cache_key_is_order_independent():
    first = search_cache_key({"q": "nolan", "type": "movie"})
    second = search_cache_key({"type": "movie", "q": "nolan"})

    assert first == second
    assert first.startswith("cache:search:")


def test_search_cache_key_ignores_empty_values_and_changes_with_params():
    assert search_cache_key({"q": "nolan", "type": ""}) == search_cache_key({"q": "nolan"})
    assert search_cache_key({"q": "nolan"}) != search_cache_key({"q": "dark"})


def test_json_roundtrip_and_ttl():
    redis_client = _redis()

    set_json(redis_client, "cache:search:test", {"total": 2}, ttl=60)

    assert get_json(redis_client, "cache:search:test") == {"total": 2}
    assert 0 < redis_client.ttl("cache:search:test") <= 60
    assert get_json(redis_client, "cache:search:missing") is None

    redis_client.flushdb()


def test_register_view_counts_and_ranks_popularity():
    redis_client = _redis()

    register_view(redis_client, "title-a")
    register_view(redis_client, "title-b")
    register_view(redis_client, "title-b")

    assert view_count(redis_client, "title-b") == 2
    assert popular_title_ids(redis_client) == ["title-b", "title-a"]

    redis_client.flushdb()


def test_sync_likes_sets_absolute_counter():
    redis_client = _redis()

    sync_likes(redis_client, "title-a", 3)
    assert like_count(redis_client, "title-a") == 3

    sync_likes(redis_client, "title-a", 0)
    assert like_count(redis_client, "title-a") == 0

    redis_client.flushdb()


def test_invalidations_remove_only_their_keyspace():
    redis_client = _redis()
    set_json(redis_client, title_cache_key("a"), {"id": "a"}, ttl=60)
    set_json(redis_client, title_cache_key("b"), {"id": "b"}, ttl=60)
    set_json(redis_client, search_cache_key({"q": "x"}), {"total": 0}, ttl=60)

    assert invalidate_titles(redis_client) == 2
    assert invalidate_search(redis_client) == 1
    assert redis_client.dbsize() == 0

    redis_client.flushdb()
