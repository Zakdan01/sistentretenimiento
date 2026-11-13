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
DB_NAME = "catalogo_test_library"
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


def login(client, email="laura@example.com"):
    return client.post(
        "/auth/register",
        data={"display_name": "Laura", "email": email, "password": "secreto123"},
    )


def title_id(db, title="Dark"):
    return db.titles.find_one({"title": title})["_id"]


def test_library_page_requires_login(client):
    response = client.get("/library")

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_add_entry_creates_document(client, db):
    login(client)

    response = client.post(
        f"/library/{title_id(db)}",
        data={"status": "watching", "rating": "9", "favorite": "on"},
    )

    assert response.status_code == 302
    entry = db.library_entries.find_one({"title_id": title_id(db)})
    assert entry["status"] == "watching"
    assert entry["rating"] == 9
    assert entry["favorite"] is True


def test_add_entry_rejects_invalid_rating(client, db):
    login(client)

    response = client.post(
        f"/library/{title_id(db)}",
        data={"status": "watched", "rating": "11"},
    )

    assert response.status_code == 400
    assert db.library_entries.count_documents({}) == 0


def test_update_entry_keeps_a_single_document(client, db):
    login(client)
    client.post(f"/library/{title_id(db)}", data={"status": "planned"})

    client.post(
        f"/library/{title_id(db)}",
        data={"status": "watched", "rating": "8", "favorite": "on"},
    )

    assert db.library_entries.count_documents({}) == 1
    entry = db.library_entries.find_one({})
    assert entry["status"] == "watched"
    assert entry["rating"] == 8
    assert entry["favorite"] is True


def test_update_entry_clears_favorite_when_unchecked(client, db):
    login(client)
    client.post(f"/library/{title_id(db)}", data={"status": "watched", "favorite": "on"})

    client.post(f"/library/{title_id(db)}", data={"status": "watched"})

    assert db.library_entries.find_one({})["favorite"] is False


def test_delete_entry_removes_document(client, db):
    login(client)
    client.post(f"/library/{title_id(db)}", data={"status": "watched"})

    response = client.post(f"/library/{title_id(db)}/delete")

    assert response.status_code == 302
    assert db.library_entries.count_documents({}) == 0


def test_library_page_lists_only_my_entries(client, db):
    login(client)
    client.post(f"/library/{title_id(db)}", data={"status": "watching"})

    response = client.get("/library")

    body = response.get_data(as_text=True)
    assert "Dark" in body
    assert "Breaking Bad" not in body


def test_library_page_filters_by_status(client, db):
    login(client)
    client.post(f"/library/{title_id(db)}", data={"status": "watching"})
    client.post(f"/library/{title_id(db, 'Inception')}", data={"status": "watched"})

    response = client.get("/library?status=watched")

    body = response.get_data(as_text=True)
    assert "Inception" in body
    assert "Dark" not in body


def test_progress_requires_season_and_episode(client, db):
    login(client)

    response = client.post(
        f"/library/{title_id(db)}",
        data={"status": "watching", "progress_season": "2"},
    )

    assert response.status_code == 400
    assert db.library_entries.count_documents({}) == 0


def test_progress_is_stored_as_nested_object(client, db):
    login(client)

    client.post(
        f"/library/{title_id(db)}",
        data={"status": "watching", "progress_season": "2", "progress_episode": "4"},
    )

    assert db.library_entries.find_one({})["progress"] == {"season": 2, "episode": 4}
