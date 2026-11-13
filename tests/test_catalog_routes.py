import pytest

from tests.support import (
    find_title,
    flush_redis,
    get_database,
    make_app,
    prepare_database,
    seed_catalog,
    teardown,
)

DB_NAME = "catalogo_test_routes"


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
def db(app):
    return get_database(DB_NAME)


def test_home_page_lists_top_rated_titles(client):
    response = client.get("/")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Mejor valoradas" in body
    assert "Breaking Bad" in body


def test_search_page_filters_by_type(client):
    response = client.get("/search?type=anime")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Shingeki no Kyojin" in body
    assert "Breaking Bad" not in body


def test_detail_page_shows_title_information(client, db):
    title = find_title(db, "Inception")

    response = client.get(f"/titles/{title['_id']}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Dom Cobb roba secretos" in body
    assert "Ciencia ficción" in body
    assert "imdb · tt1375666" in body


def test_detail_page_returns_404_for_unknown_title(client):
    response = client.get("/titles/000000000000000000000000")

    assert response.status_code == 404


def test_api_search_returns_json(client):
    response = client.get("/api/search?q=inception")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total"] == 1
    assert payload["results"][0]["title"] == "Inception"
    assert payload["results"][0]["type"] == "movie"
    assert payload["results"][0]["id"]


def test_api_search_filters_by_type(client):
    payload = client.get("/api/search?type=series").get_json()

    assert payload["total"] == 5
    assert {item["type"] for item in payload["results"]} == {"series"}


def test_api_title_returns_json(client):
    search = client.get("/api/search?q=dark").get_json()
    title_id = search["results"][0]["id"]

    response = client.get(f"/api/titles/{title_id}")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["title"] == "Dark"
    assert payload["average_rating"] == {"average": None, "count": 0}


def test_api_title_returns_404_for_unknown_id(client):
    assert client.get("/api/titles/000000000000000000000000").status_code == 404
