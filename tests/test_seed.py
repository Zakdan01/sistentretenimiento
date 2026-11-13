import json
from pathlib import Path

from pymongo import MongoClient

from mongodb.seed.load_seed import load_titles

SEED_PATH = Path(__file__).resolve().parent.parent / "mongodb" / "seed" / "titles.json"
MONGO_URI = "mongodb://localhost:27017"
TEST_DB = "catalogo_test_seed"


def _db():
    return MongoClient(MONGO_URI)[TEST_DB]


def test_load_titles_inserts_every_seed_document():
    db = _db()
    db.titles.drop()

    count = load_titles(db, SEED_PATH)

    expected = len(json.loads(SEED_PATH.read_text(encoding="utf-8")))
    assert count == expected
    assert db.titles.count_documents({}) == expected

    db.client.drop_database(TEST_DB)


def test_load_titles_is_idempotent():
    db = _db()
    db.titles.drop()

    load_titles(db, SEED_PATH)
    count = load_titles(db, SEED_PATH)

    assert db.titles.count_documents({}) == count

    db.client.drop_database(TEST_DB)
