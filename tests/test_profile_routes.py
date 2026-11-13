import subprocess
from pathlib import Path

import pytest
from pymongo import MongoClient
from redis import Redis

from app import create_app
from mongodb.seed.load_seed import load_titles

BASE_DIR = Path(__file__).resolve().parent.parent
INIT_SCRIPTS = [
    BASE_DIR / "mongodb" / "init" / "01_collections.js",
    BASE_DIR / "mongodb" / "init" / "02_indexes.js",
]
SEED_PATH = BASE_DIR / "mongodb" / "seed" / "titles.json"
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "catalogo_test_profile"
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
def db(app):
    return MongoClient(MONGO_URI)[DB_NAME]


def login(client):
    return client.post(
        "/auth/register",
        data={
            "display_name": "Laura",
            "email": "laura@example.com",
            "password": "secreto123",
        },
    )


def test_profile_page_requires_login(client):
    response = client.get("/profile")

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_profile_page_shows_account_and_stats(client, db):
    login(client)
    dark = db.titles.find_one({"title": "Dark"})
    inception = db.titles.find_one({"title": "Inception"})
    client.post(f"/library/{dark['_id']}", data={"status": "watching", "favorite": "on", "rating": "9"})
    client.post(f"/library/{inception['_id']}", data={"status": "watched", "rating": "7"})

    response = client.get("/profile")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Laura" in body
    assert "laura@example.com" in body
    assert "Viendo" in body
    assert "Vistas" in body


def test_profile_average_rating_uses_only_rated_entries(client, db):
    login(client)
    dark = db.titles.find_one({"title": "Dark"})
    inception = db.titles.find_one({"title": "Inception"})
    client.post(f"/library/{dark['_id']}", data={"status": "watched", "rating": "9"})
    client.post(f"/library/{inception['_id']}", data={"status": "planned"})

    body = client.get("/profile").get_data(as_text=True)

    assert "9.0" in body
