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

DB_NAME = "catalogo_test_library"


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


def register(client, email="laura@example.com"):
    return client.post(
        "/auth/register",
        data={"display_name": "Laura", "email": email, "password": "secreto123"},
    )


def title_id(db, title="Dark"):
    return find_title(db, title)["_id"]


def test_library_page_requires_login(client):
    response = client.get("/library")

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_add_entry_creates_document_with_title_type(client, db):
    register(client)

    response = client.post(
        f"/library/{title_id(db)}",
        data={"status": "watching", "rating": "9", "favorite": "on"},
    )

    assert response.status_code == 302
    entry = db.library_entries.find_one({"title_id": title_id(db)})
    assert entry["status"] == "watching"
    assert entry["rating"] == 9
    assert entry["favorite"] is True
    assert entry["title_type"] == "series"


def test_add_entry_works_for_each_catalog_collection(client, db):
    register(client)

    for title, expected_type in (
        ("Inception", "movie"),
        ("Dark", "series"),
        ("Cowboy Bebop", "anime"),
    ):
        client.post(f"/library/{title_id(db, title)}", data={"status": "planned"})

    stored = {entry["title_type"] for entry in db.library_entries.find()}
    assert stored == {"movie", "series", "anime"}


def test_add_entry_rejects_invalid_rating(client, db):
    register(client)

    response = client.post(
        f"/library/{title_id(db)}",
        data={"status": "watched", "rating": "11"},
    )

    assert response.status_code == 400
    assert db.library_entries.count_documents({}) == 0


def test_update_entry_keeps_a_single_document(client, db):
    register(client)
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
    register(client)
    client.post(f"/library/{title_id(db)}", data={"status": "watched", "favorite": "on"})

    client.post(f"/library/{title_id(db)}", data={"status": "watched"})

    assert db.library_entries.find_one({})["favorite"] is False


def test_delete_entry_removes_document(client, db):
    register(client)
    client.post(f"/library/{title_id(db)}", data={"status": "watched"})

    response = client.post(f"/library/{title_id(db)}/delete")

    assert response.status_code == 302
    assert db.library_entries.count_documents({}) == 0


def test_library_page_lists_only_my_entries(client, db):
    register(client)
    client.post(f"/library/{title_id(db)}", data={"status": "watching"})

    response = client.get("/library")

    body = response.get_data(as_text=True)
    assert "Dark" in body
    assert "Breaking Bad" not in body


def test_library_page_filters_by_status(client, db):
    register(client)
    client.post(f"/library/{title_id(db)}", data={"status": "watching"})
    client.post(f"/library/{title_id(db, 'Inception')}", data={"status": "watched"})

    response = client.get("/library?status=watched")

    body = response.get_data(as_text=True)
    assert "Inception" in body
    assert "Dark" not in body


def test_progress_requires_season_and_episode(client, db):
    register(client)

    response = client.post(
        f"/library/{title_id(db)}",
        data={"status": "watching", "progress_season": "2"},
    )

    assert response.status_code == 400
    assert db.library_entries.count_documents({}) == 0


def test_progress_is_stored_as_nested_object(client, db):
    register(client)

    client.post(
        f"/library/{title_id(db)}",
        data={"status": "watching", "progress_season": "2", "progress_episode": "4"},
    )

    assert db.library_entries.find_one({})["progress"] == {"season": 2, "episode": 4}


def test_entries_of_another_user_are_not_visible(client, db):
    register(client)
    client.post(f"/library/{title_id(db)}", data={"status": "watching"})
    client.post("/auth/logout")

    register(client, email="diego@example.com")

    response = client.get("/library")

    assert response.status_code == 200
    assert db.library_entries.count_documents({}) == 1
    assert "Dark" not in response.get_data(as_text=True)
