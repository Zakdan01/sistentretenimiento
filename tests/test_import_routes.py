import pytest

from app.catalog.providers import ProviderError
from tests.support import (
    flush_redis,
    get_database,
    make_app,
    prepare_database,
    teardown,
)

DB_NAME = "catalogo_test_import_routes"

JIKAN_DETAILS = {
    "external": {"source": "jikan", "id": 16498},
    "type": "anime",
    "title": "Shingeki no Kyojin",
    "synopsis": "La humanidad sobrevive tras enormes murallas.",
    "genres": ["Acción", "Fantasía"],
    "year": 2013,
    "poster_url": "https://cdn.example/poster.jpg",
    "external_rating": 8.5,
}


@pytest.fixture
def app():
    client, db = prepare_database(DB_NAME)
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


def register(client, role: str = "admin"):
    res = client.post(
        "/auth/register",
        data={
            "display_name": "Ivan",
            "email": "ivan@example.com",
            "password": "secreto123",
        },
    )
    if role != "user":
        get_database(DB_NAME).users.update_one(
            {"email": "ivan@example.com"},
            {"$set": {"role": role}},
        )
    return res


def test_import_page_requires_login(client):
    response = client.get("/import")

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_import_page_rejects_regular_user(client):
    register(client, role="user")
    response = client.get("/import")
    assert response.status_code == 403


def test_import_page_shows_provider_error(client, monkeypatch):
    register(client)

    def fail(query, source):
        raise ProviderError("Falta TMDB_API_KEY en el archivo .env.")

    monkeypatch.setattr("app.catalog.routes._search_external", fail)

    response = client.get("/import?q=inception&source=tmdb")

    assert response.status_code == 200
    assert "TMDB_API_KEY" in response.get_data(as_text=True)


def test_import_page_shows_external_results(client, monkeypatch):
    register(client)
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


def test_import_post_creates_title_in_the_right_collection(client, db, monkeypatch):
    register(client)
    monkeypatch.setattr(
        "app.catalog.routes._fetch_external",
        lambda source, external_id, media_type: JIKAN_DETAILS,
    )

    response = client.post(
        "/import",
        data={"source": "jikan", "external_id": "16498", "media_type": "movie"},
    )

    assert response.status_code == 302
    assert db.animes.count_documents({}) == 1
    assert db.animes.find_one()["title"] == "Shingeki no Kyojin"
    assert db.movies.count_documents({}) == 0


def test_import_post_reports_provider_errors(client, monkeypatch):
    register(client)

    def fail(source, external_id, media_type):
        raise ProviderError("sin conexión")

    monkeypatch.setattr("app.catalog.routes._fetch_external", fail)

    response = client.post(
        "/import",
        data={"source": "jikan", "external_id": "16498"},
    )

    assert response.status_code == 400
    assert "sin conexión" in response.get_data(as_text=True)
