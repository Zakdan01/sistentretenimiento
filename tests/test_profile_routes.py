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

DB_NAME = "catalogo_test_profile"


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


def register(client):
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
    register(client)
    dark = find_title(db, "Dark")
    inception = find_title(db, "Inception")
    client.post(
        f"/library/{dark['_id']}",
        data={"status": "watching", "favorite": "on", "rating": "9"},
    )
    client.post(f"/library/{inception['_id']}", data={"status": "watched", "rating": "7"})

    response = client.get("/profile")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Laura" in body
    assert "laura@example.com" in body
    assert "Viendo" in body
    assert "Vistas" in body


def test_profile_average_rating_uses_only_rated_entries(client, db):
    register(client)
    dark = find_title(db, "Dark")
    inception = find_title(db, "Inception")
    client.post(f"/library/{dark['_id']}", data={"status": "watched", "rating": "9"})
    client.post(f"/library/{inception['_id']}", data={"status": "planned"})

    body = client.get("/profile").get_data(as_text=True)

    assert "9.0" in body
