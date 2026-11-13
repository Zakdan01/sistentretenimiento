from datetime import datetime, timezone

import pytest

from tests.support import (
    find_title,
    flush_redis,
    get_database,
    login,
    make_app,
    make_user,
    prepare_database,
    seed_catalog,
    teardown,
)

DB_NAME = "catalogo_test_admin"
ADMIN_EMAIL = "admin@biblioteca.local"
ADMIN_PASSWORD = "Admin12345"
USER_EMAIL = "laura@biblioteca.local"
USER_PASSWORD = "Laura12345"


@pytest.fixture
def app():
    client, db = prepare_database(DB_NAME)
    seed_catalog(db)
    make_user(
        db,
        email=ADMIN_EMAIL,
        password=ADMIN_PASSWORD,
        display_name="Administrador",
        role="admin",
    )
    make_user(
        db,
        email=USER_EMAIL,
        password=USER_PASSWORD,
        display_name="Laura Gómez",
        role="user",
    )
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


@pytest.fixture
def admin_client(client):
    login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    return client


def test_admin_requires_login(client):
    response = client.get("/admin")

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_admin_rejects_common_users(client):
    login(client, USER_EMAIL, USER_PASSWORD)

    response = client.get("/admin")

    assert response.status_code == 403


def test_dashboard_shows_catalog_and_users(admin_client):
    response = admin_client.get("/admin")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Panel de administración" in body
    assert "títulos en el catálogo" in body
    assert "16" in body
    assert "2" in body


def test_titles_list_filters_by_type(admin_client):
    response = admin_client.get("/admin/titles?type=anime")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Shingeki no Kyojin" in body
    assert "Breaking Bad" not in body


def test_admin_can_create_a_manual_title(admin_client, db):
    response = admin_client.post(
        "/admin/titles/new",
        data={
            "type": "movie",
            "title": "Título cargado a mano",
            "synopsis": "Sinopsis inventada para la prueba.",
            "year": "2024",
            "genres": "Drama, Misterio",
            "external_rating": "7.5",
            "poster_url": "https://example.org/manual.jpg",
            "source": "manual",
            "external_id": "",
        },
    )

    assert response.status_code == 302
    assert db.movies.count_documents({}) == 6
    document = db.movies.find_one({"title": "Título cargado a mano"})
    assert document["external"] is None
    assert document["genres"] == ["Drama", "Misterio"]
    assert document["type"] == "movie"


def test_admin_create_rejects_duplicate_external_identity(admin_client, db):
    response = admin_client.post(
        "/admin/titles/new",
        data={
            "type": "movie",
            "title": "Otra Inception",
            "synopsis": "Duplicada.",
            "year": "2010",
            "genres": "Drama",
            "external_rating": "8.0",
            "source": "imdb",
            "external_id": "tt1375666",
        },
    )

    assert response.status_code == 200
    assert "Ya existe un título" in response.get_data(as_text=True)
    assert db.movies.count_documents({}) == 5


def test_admin_can_edit_a_title(admin_client, db):
    inception = find_title(db, "Inception")

    response = admin_client.post(
        f"/admin/titles/{inception['_id']}/edit",
        data={
            "type": "movie",
            "title": "Inception (reeditada)",
            "synopsis": "Sinopsis actualizada.",
            "year": "2010",
            "genres": "Ciencia ficción",
            "external_rating": "9.1",
            "poster_url": "https://example.org/inception.jpg",
            "source": "imdb",
            "external_id": "tt1375666",
        },
    )

    assert response.status_code == 302
    updated = db.movies.find_one({"_id": inception["_id"]})
    assert updated["title"] == "Inception (reeditada)"
    assert updated["external_rating"] == 9.1
    assert updated["type"] == "movie"


def test_admin_delete_title_removes_library_entries(admin_client, db):
    inception = find_title(db, "Inception")
    user = db.users.find_one({"email": USER_EMAIL})
    now = datetime.now(timezone.utc)
    db.library_entries.insert_one(
        {
            "user_id": user["_id"],
            "title_id": inception["_id"],
            "title_type": "movie",
            "status": "watched",
            "favorite": False,
            "rating": 9,
            "progress": None,
            "notes": None,
            "created_at": now,
            "updated_at": now,
        }
    )

    response = admin_client.post(f"/admin/titles/{inception['_id']}/delete")

    assert response.status_code == 302
    assert db.movies.count_documents({"_id": inception["_id"]}) == 0
    assert db.library_entries.count_documents({"title_id": inception["_id"]}) == 0


def test_admin_can_create_and_edit_users(admin_client, db):
    response = admin_client.post(
        "/admin/users/new",
        data={
            "display_name": "Diego Pérez",
            "email": "diego@biblioteca.local",
            "role": "user",
            "password": "Diego12345",
        },
    )

    assert response.status_code == 302
    assert db.users.count_documents({}) == 3
    diego = db.users.find_one({"email": "diego@biblioteca.local"})
    assert diego["role"] == "user"

    response = admin_client.post(
        f"/admin/users/{diego['_id']}/edit",
        data={
            "display_name": "Diego P.",
            "email": "diego@biblioteca.local",
            "role": "admin",
            "password": "",
        },
    )

    assert response.status_code == 302
    updated = db.users.find_one({"_id": diego["_id"]})
    assert updated["display_name"] == "Diego P."
    assert updated["role"] == "admin"


def test_admin_create_user_rejects_duplicate_email(admin_client, db):
    response = admin_client.post(
        "/admin/users/new",
        data={
            "display_name": "Otra Laura",
            "email": USER_EMAIL,
            "role": "user",
            "password": "Otra12345",
        },
    )

    assert response.status_code == 200
    assert "ya está registrado" in response.get_data(as_text=True)
    assert db.users.count_documents({}) == 2


def test_admin_cannot_demote_the_last_admin(admin_client, db):
    admin = db.users.find_one({"email": ADMIN_EMAIL})

    response = admin_client.post(
        f"/admin/users/{admin['_id']}/edit",
        data={
            "display_name": "Administrador",
            "email": ADMIN_EMAIL,
            "role": "user",
            "password": "",
        },
    )

    assert response.status_code == 200
    assert "último administrador" in response.get_data(as_text=True)
    assert db.users.find_one({"_id": admin["_id"]})["role"] == "admin"


def test_admin_cannot_delete_own_account(admin_client, db):
    admin = db.users.find_one({"email": ADMIN_EMAIL})

    response = admin_client.post(f"/admin/users/{admin['_id']}/delete")

    assert response.status_code == 400
    assert db.users.count_documents({}) == 2


def test_admin_can_delete_another_user(admin_client, db):
    laura = db.users.find_one({"email": USER_EMAIL})

    response = admin_client.post(f"/admin/users/{laura['_id']}/delete")

    assert response.status_code == 302
    assert db.users.count_documents({}) == 1


def test_reports_page_shows_every_section(admin_client):
    response = admin_client.get("/admin/reports")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Salud del catálogo" in body
    assert "Géneros más presentes" in body
    assert "Bibliotecas por usuario y estado" in body
    assert "Actividad por usuario" in body
    assert "Drama" in body
