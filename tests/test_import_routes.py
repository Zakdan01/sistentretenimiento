import subprocess
from pathlib import Path

import pytest
from pymongo import MongoClient

from app import create_app

BASE_DIR = Path(__file__).resolve().parent.parent
INIT_SCRIPTS = [
    BASE_DIR / "mongodb" / "init" / "01_collections.js",
    BASE_DIR / "mongodb" / "init" / "02_indexes.js",
]
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "catalogo_test_import_routes"
REDIS_URL = "redis://localhost:6379/15"

JIKAN_DETAILS = {
    "external": {"source": "jikan", "id": 16498},
    "type": "anime",
    "title": "Shingeki no Kyojin",
    "original_title": "進撃の巨人",
    "synopsis": "La humanidad sobrevive tras enormes murallas.",
    "genres": ["Acción", "Fantasía"],
    "release_date": "2013-04-07",
    "runtime_minutes": None,
    "seasons": [{"number": 1, "episodes": 25}],
    "episodes_total": 25,
    "directors": [],
    "cast": [],
    "studios": ["Wit Studio"],
    "poster_url": "https://cdn.example/poster.jpg",
    "external_rating": 8.5,
    "awards": [],
}


@pytest.fixture
def app():
    from redis import Redis

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


def login(client):
    return client.post(
        "/auth/register",
        data={
            "display_name": "Ivan",
            "email": "ivan@example.com",
            "password": "secreto123",
        },
    )


def test_import_page_requires_login(client):
    response = client.get("/import")

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_import_page_shows_external_results(client, monkeypatch):
    login(client)
    monkeypatch.setattr(
        "app.catalog.routes._search_external",
        lambda query, source: [
            {
                "external": {"source": "jikan", "id": 16498},
                "title": "Shingeki no Kyojin",
                "year": 2013,
                "type": "anime",
                "poster_url": None,
            }
        ],
    )

    response = client.get("/import?q=attack&source=jikan")

    assert response.status_code == 200
    assert "Shingeki no Kyojin" in response.get_data(as_text=True)


def test_import_post_creates_title(client, monkeypatch):
    login(client)
    monkeypatch.setattr(
        "app.catalog.routes._fetch_external",
        lambda source, external_id, media_type: JIKAN_DETAILS,
    )

    response = client.post(
        "/import",
        data={"source": "jikan", "external_id": "16498", "media_type": "movie"},
    )

    assert response.status_code == 302
    database = MongoClient(MONGO_URI)[DB_NAME]
    assert database.titles.count_documents({}) == 1
    assert database.titles.find_one()["title"] == "Shingeki no Kyojin"
