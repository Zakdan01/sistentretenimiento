import subprocess
from pathlib import Path

import pytest
from pymongo import MongoClient
from redis import Redis

from app import create_app
from app.cache import (
    POPULAR_KEY,
    like_count,
    search_cache_key,
    title_cache_key,
    view_count,
)
from mongodb.seed.load_seed import load_titles

BASE_DIR = Path(__file__).resolve().parent.parent
INIT_SCRIPTS = [
    BASE_DIR / "mongodb" / "init" / "01_collections.js",
    BASE_DIR / "mongodb" / "init" / "02_indexes.js",
]
SEED_PATH = BASE_DIR / "mongodb" / "seed" / "titles.json"
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "catalogo_test_cache"
REDIS_URL = "redis://localhost:6379/15"


@pytest.fixture
def app():
    client = MongoClient(MONGO_URI)
    client.drop_database(DB_NAME)

    uri = f"{MONGO_URI}/{DB_NAME}"
    for script in INIT_SCRIPTS:
        subprocess.run(
            ["mongosh", uri, "--quiet", "--file", str(script)],
            check=True,
            capture_output=True,
            text=True,
        )

    load_titles(client[DB_NAME], SEED_PATH)

    redis_client = Redis.from_url(REDIS_URL, decode_responses=True, protocol=2)
    redis_client.flushdb()

    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "MONGO_DB": DB_NAME,
            "REDIS_URL": REDIS_URL,
            "SESSION_TTL_SECONDS": 60,
        }
    )

    yield application

    client.drop_database(DB_NAME)
    redis_client.flushdb()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def redis_client(app):
    return Redis.from_url(REDIS_URL, decode_responses=True, protocol=2)


@pytest.fixture
def dark_id(app):
    db = MongoClient(MONGO_URI)[DB_NAME]
    return db.titles.find_one({"title": "Dark"})["_id"]


def login(client):
    return client.post(
        "/auth/register",
        data={
            "display_name": "Ivan",
            "email": "ivan@example.com",
            "password": "secreto123",
        },
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
    login(client)

    client.post(f"/library/{dark_id}", data={"status": "watched", "favorite": "on"})
    assert like_count(redis_client, dark_id) == 1

    client.post(f"/library/{dark_id}", data={"status": "watched"})
    assert like_count(redis_client, dark_id) == 0
