import pytest
from redis import Redis

from app.cache import (
    POPULAR_KEY,
    like_count,
    search_cache_key,
    title_cache_key,
    view_count,
)
from tests.support import (
    REDIS_URL,
    find_title,
    flush_redis,
    get_database,
    make_app,
    prepare_database,
    seed_catalog,
    teardown,
)

DB_NAME = "catalogo_test_cache"


@pytest.fixture
def app():
    client, db = prepare_database(DB_NAME)
    seed_catalog(db)
    redis_client = flush_redis()

    application = make_app(DB_NAME)

    yield application

    teardown(client, DB_NAME, redis_client)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def redis_client(app):
    return Redis.from_url(REDIS_URL, decode_responses=True, protocol=2)


@pytest.fixture
def dark_id(app):
    return find_title(get_database(DB_NAME), "Dark")["_id"]


def register(client, email="ivan@example.com"):
    return client.post(
        "/auth/register",
        data={"display_name": "Ivan", "email": email, "password": "secreto123"},
    )


def test_api_search_populates_redis_cache(client, redis_client):
    client.get("/api/search?q=dark")

    key = search_cache_key({"q": "dark"}, namespace=DB_NAME)
    assert redis_client.exists(key) == 1
    assert 0 < redis_client.ttl(key) <= 60


def test_api_title_populates_redis_cache(client, redis_client, dark_id):
    client.get(f"/api/titles/{dark_id}")

    key = title_cache_key(dark_id, namespace=DB_NAME)
    assert redis_client.exists(key) == 1


def test_detail_page_registers_view_and_ranking(client, redis_client, dark_id):
    client.get(f"/titles/{dark_id}")
    client.get(f"/titles/{dark_id}")

    assert view_count(redis_client, dark_id) == 2
    assert redis_client.zscore(POPULAR_KEY, str(dark_id)) == 2


def test_home_page_shows_trending_from_redis(client, redis_client, dark_id):
    client.get(f"/titles/{dark_id}")
    client.get(f"/titles/{dark_id}")

    body = client.get("/").get_data(as_text=True)

    assert "Tendencias" in body
    assert "Dark" in body


def test_favorite_syncs_likes_counter(client, redis_client, dark_id):
    register(client)

    client.post(f"/library/{dark_id}", data={"status": "watched", "favorite": "on"})
    assert like_count(redis_client, dark_id) == 1

    client.post(f"/library/{dark_id}", data={"status": "watched"})
    assert like_count(redis_client, dark_id) == 0


def test_external_search_is_cached(client, redis_client, monkeypatch):
    calls = {"total": 0}

    def fake_search(query, source):
        calls["total"] += 1
        return [
            {
                "external": {"source": "jikan", "id": 16498},
                "title": "Shingeki no Kyojin",
                "year": 2013,
                "type": "anime",
                "poster_url": None,
            }
        ]

    monkeypatch.setattr("app.catalog.routes._search_external_uncached", fake_search)
    register(client)

    client.get("/import?q=attack&source=jikan")
    client.get("/import?q=attack&source=jikan")

    assert calls["total"] == 1
    keys = list(redis_client.scan_iter(match="cache:api:*"))
    assert len(keys) == 1


def test_api_popular_lists_viewed_titles(client, dark_id):
    client.get(f"/titles/{dark_id}")
    client.get(f"/titles/{dark_id}")

    payload = client.get("/api/popular").get_json()

    assert payload["results"][0]["title"] == "Dark"
    assert payload["results"][0]["views"] == 2
