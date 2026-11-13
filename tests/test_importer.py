import pytest

from app.catalog.importer import import_title
from tests.support import prepare_database, teardown

DB_NAME = "catalogo_test_import"

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
def db():
    client, database = prepare_database(DB_NAME)

    yield database

    teardown(client, DB_NAME)


def test_import_title_inserts_document(db):
    document, created = import_title(db, JIKAN_DETAILS)

    assert created is True
    assert document["year"] == 2013
    assert document["type"] == "anime"
    assert document["external"] == {"source": "jikan", "id": 16498}
    assert db.animes.count_documents({}) == 1
    assert db.movies.count_documents({}) == 0


def test_import_title_updates_instead_of_duplicating(db):
    import_title(db, JIKAN_DETAILS)

    document, created = import_title(
        db, {**JIKAN_DETAILS, "title": "Shingeki no Kyojin (título actualizado)"}
    )

    assert created is False
    assert db.animes.count_documents({}) == 1
    assert document["title"] == "Shingeki no Kyojin (título actualizado)"


def test_import_title_keeps_string_external_ids(db):
    details = {
        "external": {"source": "imdb", "id": "tt1375666"},
        "type": "movie",
        "title": "Inception",
        "synopsis": "Dom Cobb roba secretos dentro de los sueños.",
        "genres": ["Ciencia ficción"],
        "year": 2010,
        "poster_url": None,
        "external_rating": 8.8,
    }

    document, created = import_title(db, details)

    assert created is True
    assert document["external"] == {"source": "imdb", "id": "tt1375666"}
    assert db.movies.count_documents({}) == 1


def test_import_title_converts_numeric_strings_to_int(db):
    details = {
        **JIKAN_DETAILS,
        "external": {"source": "jikan", "id": "16498"},
    }

    document, _created = import_title(db, details)

    assert document["external"]["id"] == 16498
