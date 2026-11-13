import subprocess
from pathlib import Path

import pytest
from pymongo import MongoClient

from app.catalog.importer import import_title

BASE_DIR = Path(__file__).resolve().parent.parent
INIT_SCRIPTS = [
    BASE_DIR / "mongodb" / "init" / "01_collections.js",
    BASE_DIR / "mongodb" / "init" / "02_indexes.js",
]
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "catalogo_test_import"

JIKAN_DETAILS = {
    "external": {"source": "jikan", "id": 16498},
    "type": "anime",
    "title": "Shingeki no Kyojin",
    "original_title": "進撃の巨人",
    "synopsis": "La humanidad sobrevive tras enormes murallas.",
    "genres": ["Acción", "Fantasía"],
    "release_date": "2013-04-07",
    "runtime_minutes": None,
    "seasons": [{"number": 1, "episodes": 25}],
    "episodes_total": 25,
    "directors": [],
    "cast": [],
    "studios": ["Wit Studio"],
    "poster_url": "https://cdn.example/poster.jpg",
    "external_rating": 8.5,
    "awards": [],
}


@pytest.fixture
def db():
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

    yield client[DB_NAME]

    client.drop_database(DB_NAME)


def test_import_title_inserts_document(db):
    document, created = import_title(db, JIKAN_DETAILS)

    assert created is True
    assert document["year"] == 2013
    assert document["type"] == "anime"
    assert db.titles.count_documents({}) == 1


def test_import_title_updates_instead_of_duplicating(db):
    import_title(db, JIKAN_DETAILS)

    document, created = import_title(
        db, {**JIKAN_DETAILS, "title": "Shingeki no Kyojin (título actualizado)"}
    )

    assert created is False
    assert db.titles.count_documents({}) == 1
    assert document["title"] == "Shingeki no Kyojin (título actualizado)"
