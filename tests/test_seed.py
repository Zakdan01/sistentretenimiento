import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from werkzeug.security import check_password_hash

from mongodb.seed.load_seed import load_catalog, load_libraries, load_users
from tests.support import (
    CATALOG,
    prepare_database,
    write_catalog_files,
    teardown,
)

DB_NAME = "catalogo_test_seed"


@pytest.fixture
def db():
    client, database = prepare_database(DB_NAME)

    yield database

    teardown(client, DB_NAME)


def _catalog_entry(title: str) -> dict:
    for raw in CATALOG:
        if raw["title"] == title:
            return raw
    raise AssertionError(f"falta {title} en el catálogo de prueba")


def _write_users(path: Path) -> None:
    path.write_text(
        json.dumps(
            [
                {
                    "display_name": "Administrador",
                    "email": "admin@biblioteca.local",
                    "password": "Admin12345",
                    "role": "admin",
                },
                {
                    "display_name": "Laura Gómez",
                    "email": "laura@biblioteca.local",
                    "password": "Laura12345",
                    "role": "user",
                },
                {
                    "display_name": "Diego Pérez",
                    "email": "diego@biblioteca.local",
                    "password": "Diego12345",
                    "role": "user",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_libraries(path: Path) -> None:
    inception = _catalog_entry("Inception")
    dark = _catalog_entry("Dark")
    titan = _catalog_entry("Shingeki no Kyojin")

    def reference(raw: dict) -> dict:
        return {"source": raw["source"], "external_id": raw["external_id"]}

    path.write_text(
        json.dumps(
            {
                "laura@biblioteca.local": [
                    {
                        **reference(inception),
                        "status": "watched",
                        "favorite": True,
                        "rating": 9,
                        "progress": None,
                        "notes": "Impecable.",
                    },
                    {
                        **reference(dark),
                        "status": "watching",
                        "favorite": False,
                        "rating": None,
                        "progress": {"season": 2, "episode": 5},
                        "notes": None,
                    },
                ],
                "diego@biblioteca.local": [
                    {
                        **reference(titan),
                        "status": "watching",
                        "favorite": True,
                        "rating": 9,
                        "progress": {"season": 3, "episode": 10},
                        "notes": "La animación es espectacular.",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_load_catalog_inserts_snapshots(db, tmp_path):
    write_catalog_files(tmp_path)

    counts = load_catalog(db, tmp_path)

    assert counts == {"movie": 5, "series": 5, "anime": 6}
    assert db.movies.count_documents({}) == 5
    assert db.series.count_documents({}) == 5
    assert db.animes.count_documents({}) == 6

    inception = db.movies.find_one({"title": "Inception"})
    assert inception["external"] == {"source": "imdb", "id": "tt1375666"}
    assert inception["poster_url"] == "https://example.org/inception.jpg"
    assert inception["external_rating"] == 8.8
    assert inception["type"] == "movie"
    assert inception["created_at"] is not None


def test_load_catalog_is_idempotent_by_external_identity(db, tmp_path):
    write_catalog_files(tmp_path)
    load_catalog(db, tmp_path)

    db.movies.update_one({"title": "Inception"}, {"$set": {"title": "Cambiado"}})
    load_catalog(db, tmp_path)

    assert db.movies.count_documents({}) == 5
    assert db.movies.count_documents({"title": "Inception"}) == 1
    assert db.movies.count_documents({"title": "Cambiado"}) == 0


def test_load_catalog_reset_replaces_previous_documents(db, tmp_path):
    write_catalog_files(tmp_path)
    db.movies.insert_one(
        {
            "external": None,
            "type": "movie",
            "title": "Anterior",
            "poster_url": None,
            "synopsis": "Vieja.",
            "year": 1990,
            "genres": [],
            "external_rating": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    load_catalog(db, tmp_path, reset=True)

    assert db.movies.count_documents({}) == 5
    assert db.movies.count_documents({"title": "Anterior"}) == 0


def test_load_catalog_requires_every_snapshot(db, tmp_path):
    write_catalog_files(tmp_path)
    (tmp_path / "series.json").unlink()

    with pytest.raises(FileNotFoundError, match="series.json"):
        load_catalog(db, tmp_path)


def test_load_users_creates_hashed_accounts(db, tmp_path):
    users_file = tmp_path / "users.json"
    _write_users(users_file)

    users = load_users(db, users_file)

    assert set(users) == {
        "admin@biblioteca.local",
        "laura@biblioteca.local",
        "diego@biblioteca.local",
    }
    assert db.users.count_documents({"role": "admin"}) == 1
    assert db.users.count_documents({"role": "user"}) == 2
    laura = users["laura@biblioteca.local"]
    assert laura["display_name"] == "Laura Gómez"
    assert laura["password_hash"] != "Laura12345"
    assert check_password_hash(laura["password_hash"], "Laura12345")


def test_load_users_is_idempotent_by_email(db, tmp_path):
    users_file = tmp_path / "users.json"
    _write_users(users_file)

    load_users(db, users_file)
    load_users(db, users_file)

    assert db.users.count_documents({}) == 3


def test_load_libraries_resolves_titles_by_external_identity(db, tmp_path):
    write_catalog_files(tmp_path)
    load_catalog(db, tmp_path)
    users_file = tmp_path / "users.json"
    _write_users(users_file)
    users = load_users(db, users_file)
    libraries_file = tmp_path / "libraries.json"
    _write_libraries(libraries_file)

    total = load_libraries(db, libraries_file, users)

    assert total == 3
    assert db.library_entries.count_documents({}) == 3
    assert db.library_entries.count_documents({"title_type": "series"}) == 1
    assert db.library_entries.count_documents({"favorite": True}) == 2

    dark = db.series.find_one({"title": "Dark"})
    entry = db.library_entries.find_one({"title_id": dark["_id"]})
    assert entry["status"] == "watching"
    assert entry["progress"] == {"season": 2, "episode": 5}


def test_load_libraries_is_idempotent(db, tmp_path):
    write_catalog_files(tmp_path)
    load_catalog(db, tmp_path)
    users_file = tmp_path / "users.json"
    _write_users(users_file)
    users = load_users(db, users_file)
    libraries_file = tmp_path / "libraries.json"
    _write_libraries(libraries_file)

    load_libraries(db, libraries_file, users)
    load_libraries(db, libraries_file, users)

    assert db.library_entries.count_documents({}) == 3


def test_load_libraries_reports_missing_titles(db, tmp_path):
    write_catalog_files(tmp_path)
    load_catalog(db, tmp_path)
    users_file = tmp_path / "users.json"
    _write_users(users_file)
    users = load_users(db, users_file)
    libraries_file = tmp_path / "libraries.json"
    libraries_file.write_text(
        json.dumps(
            {
                "laura@biblioteca.local": [
                    {
                        "source": "imdb",
                        "external_id": "tt0000000",
                        "status": "planned",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="tt0000000"):
        load_libraries(db, libraries_file, users)
