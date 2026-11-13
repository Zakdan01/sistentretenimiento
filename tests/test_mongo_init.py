import subprocess
from pathlib import Path

import pytest
from pymongo import MongoClient

from mongodb.seed.load_seed import load_titles

BASE_DIR = Path(__file__).resolve().parent.parent
COLLECTIONS_JS = BASE_DIR / "mongodb" / "init" / "01_collections.js"
INDEXES_JS = BASE_DIR / "mongodb" / "init" / "02_indexes.js"
SEED_PATH = BASE_DIR / "mongodb" / "seed" / "titles.json"
TEST_URI = "mongodb://localhost:27017/catalogo_test_init"
DB_NAME = "catalogo_test_init"


@pytest.fixture
def initialized_db():
    client = MongoClient(TEST_URI)
    client.drop_database(DB_NAME)

    for script in (COLLECTIONS_JS, INDEXES_JS):
        subprocess.run(
            ["mongosh", TEST_URI, "--quiet", "--file", str(script)],
            check=True,
            capture_output=True,
            text=True,
        )

    load_titles(client[DB_NAME], SEED_PATH)

    yield client[DB_NAME]

    client.drop_database(DB_NAME)


def test_init_scripts_accept_seed_and_create_indexes(initialized_db):
    assert initialized_db.titles.count_documents({}) == 16

    indexes = initialized_db.titles.index_information()
    assert "text_busqueda" in indexes
    assert "uq_fuente_externa" in indexes
    assert indexes["uq_fuente_externa"]["unique"] is True


def test_text_index_matches_spanish_word_stems(initialized_db):
    results = initialized_db.titles.find(
        {"$text": {"$search": "sueño"}}, {"title": 1, "_id": 0}
    )

    assert [document["title"] for document in results] == ["Inception"]


def test_text_index_uses_spanish_stemming(initialized_db):
    initialized_db.titles.update_one(
        {"title": "Inception"},
        {"$set": {"synopsis": "Un hombre sigue corriendo por los sueños."}},
    )

    results = initialized_db.titles.find(
        {"$text": {"$search": "correr"}}, {"title": 1, "_id": 0}
    )

    assert [document["title"] for document in results] == ["Inception"]
