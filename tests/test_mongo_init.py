import subprocess
from datetime import datetime, timezone

import pytest
from pymongo.errors import DuplicateKeyError, WriteError

from tests.support import BASE_DIR, MONGO_URI, prepare_database, seed_catalog, teardown

DB_NAME = "catalogo_test_init"
DROP_LEGACY_JS = BASE_DIR / "mongodb" / "init" / "03_drop_legacy.js"
CATALOG_COLLECTIONS = ("movies", "series", "animes")


@pytest.fixture
def initialized_db():
    client, db = prepare_database(DB_NAME)
    seed_catalog(db)

    yield db

    teardown(client, DB_NAME)


def _valid_title(**overrides):
    now = datetime.now(timezone.utc)
    document = {
        "external": None,
        "type": "movie",
        "title": "Título manual",
        "poster_url": None,
        "synopsis": "Sinopsis de prueba.",
        "year": 2020,
        "genres": ["Drama"],
        "external_rating": 7.0,
        "created_at": now,
        "updated_at": now,
    }
    document.update(overrides)
    return document


def test_init_scripts_accept_catalog_and_create_indexes(initialized_db):
    assert initialized_db.movies.count_documents({}) == 5
    assert initialized_db.series.count_documents({}) == 5
    assert initialized_db.animes.count_documents({}) == 6

    for name in CATALOG_COLLECTIONS:
        indexes = initialized_db[name].index_information()
        assert "text_busqueda" in indexes
        assert "anio" in indexes
        assert "genero_anio" in indexes
        assert "uq_fuente_externa" in indexes
        assert indexes["uq_fuente_externa"]["unique"] is True


def test_text_index_matches_spanish_word_stems(initialized_db):
    results = initialized_db.movies.find(
        {"$text": {"$search": "sueño"}}, {"title": 1, "_id": 0}
    )

    assert [document["title"] for document in results] == ["Inception"]


def test_text_index_uses_spanish_stemming(initialized_db):
    initialized_db.movies.update_one(
        {"title": "Inception"},
        {"$set": {"synopsis": "Un hombre sigue corriendo por los sueños."}},
    )

    results = initialized_db.movies.find(
        {"$text": {"$search": "correr"}}, {"title": 1, "_id": 0}
    )

    assert [document["title"] for document in results] == ["Inception"]


def test_collection_validator_rejects_wrong_type(initialized_db):
    with pytest.raises(WriteError):
        initialized_db.movies.insert_one(_valid_title(type="series"))


def test_collection_validator_rejects_unknown_fields(initialized_db):
    with pytest.raises(WriteError):
        initialized_db.movies.insert_one(_valid_title(cast=["Alguien"]))


def test_user_validator_rejects_invalid_role(initialized_db):
    with pytest.raises(WriteError):
        initialized_db.users.insert_one(
            {
                "email": "invalido@example.com",
                "password_hash": "x",
                "display_name": "Inválido",
                "role": "superadmin",
                "created_at": datetime.now(timezone.utc),
            }
        )


def test_library_validator_requires_title_type(initialized_db):
    now = datetime.now(timezone.utc)
    with pytest.raises(WriteError):
        initialized_db.library_entries.insert_one(
            {
                "user_id": initialized_db.users.insert_one(
                    {
                        "email": "validador@example.com",
                        "password_hash": "x",
                        "display_name": "Validador",
                        "role": "user",
                        "created_at": now,
                    }
                ).inserted_id,
                "title_id": initialized_db.movies.find_one()["_id"],
                "status": "watching",
                "favorite": False,
                "created_at": now,
                "updated_at": now,
            }
        )


def test_email_index_is_unique(initialized_db):
    now = datetime.now(timezone.utc)
    user = {
        "email": "unico@example.com",
        "password_hash": "x",
        "display_name": "Único",
        "role": "user",
        "created_at": now,
    }
    initialized_db.users.insert_one(dict(user))

    with pytest.raises(DuplicateKeyError):
        initialized_db.users.insert_one(dict(user))


def test_external_identity_is_unique_but_manual_titles_are_not(initialized_db):
    initialized_db.movies.insert_one(_valid_title())
    initialized_db.movies.insert_one(_valid_title(title="Otro manual"))

    duplicated = _valid_title()
    duplicated["external"] = {"source": "imdb", "id": "tt1375666"}
    with pytest.raises(DuplicateKeyError):
        initialized_db.movies.insert_one(duplicated)


def test_drop_legacy_removes_titles_collection(initialized_db):
    initialized_db.titles.insert_one({"_id": "legacy"})

    subprocess.run(
        ["mongosh", f"{MONGO_URI}/{DB_NAME}", "--quiet", "--file", str(DROP_LEGACY_JS)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "titles" not in initialized_db.list_collection_names()
