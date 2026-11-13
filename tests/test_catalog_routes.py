import subprocess
from pathlib import Path

import pytest
from pymongo import MongoClient

from app import create_app
from mongodb.seed.load_seed import load_titles

BASE_DIR = Path(__file__).resolve().parent.parent
INIT_SCRIPTS = [
    BASE_DIR / "mongodb" / "init" / "01_collections.js",
    BASE_DIR / "mongodb" / "init" / "02_indexes.js",
]
SEED_PATH = BASE_DIR / "mongodb" / "seed" / "titles.json"
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "catalogo_test_routes"


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

    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "MONGO_DB": DB_NAME,
            "REDIS_URL": "redis://localhost:6379/15",
        }
    )

    yield application

    client.drop_database(DB_NAME)


@pytest.fixture
def client(app):
    return app.test_client()


def test_home_page_lists_top_rated_titles(client):
    response = client.get("/")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Mejor valoradas" in body
    assert "Fullmetal Alchemist: Brotherhood" in body


def test_search_page_filters_by_type(client):
    response = client.get("/search?type=anime")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Shingeki no Kyojin" in body
    assert "Breaking Bad" not in body


def test_detail_page_shows_title_information(client):
    title = MongoClient(MONGO_URI)[DB_NAME].titles.find_one({"title": "Inception"})

    response = client.get(f"/titles/{title['_id']}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Christopher Nolan" in body
    assert "Leonardo DiCaprio" in body


def test_detail_page_returns_404_for_unknown_title(client):
    response = client.get("/titles/000000000000000000000000")

    assert response.status_code == 404


def test_api_search_returns_json(client):
    response = client.get("/api/search?q=nolan")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total"] == 2
    assert {item["title"] for item in payload["results"]} == {
        "Inception",
        "Interstellar",
    }
    assert payload["results"][0]["id"]


def test_api_title_returns_json(client):
    response = client.get("/api/search?q=dark")
    title_id = response.get_json()["results"][0]["id"]

    response = client.get(f"/api/titles/{title_id}")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["title"] == "Dark"
    assert payload["average_rating"] == {"average": None, "count": 0}
