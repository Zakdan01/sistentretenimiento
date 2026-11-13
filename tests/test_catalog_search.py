import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
from bson import ObjectId
from pymongo import MongoClient

from app.catalog.services import average_rating, get_title, search_titles
from mongodb.seed.load_seed import load_titles

BASE_DIR = Path(__file__).resolve().parent.parent
INIT_SCRIPTS = [
    BASE_DIR / "mongodb" / "init" / "01_collections.js",
    BASE_DIR / "mongodb" / "init" / "02_indexes.js",
]
SEED_PATH = BASE_DIR / "mongodb" / "seed" / "titles.json"
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "catalogo_test_catalog"


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

    database = client[DB_NAME]
    load_titles(database, SEED_PATH)

    yield database

    client.drop_database(DB_NAME)


def search(db, **params):
    documents, total = search_titles(db, params)
    return documents, total


def test_search_filters_by_type(db):
    documents, total = search(db, type="anime")

    assert total == 7
    assert all(document["type"] == "anime" for document in documents)


def test_search_by_text_finds_director(db):
    documents, total = search(db, q="nolan")

    assert total == 2
    assert {document["title"] for document in documents} == {"Inception", "Interstellar"}


def test_search_combines_text_and_type(db):
    documents, total = search(db, q="drama", type="series")

    assert total >= 1
    assert all(document["type"] == "series" for document in documents)
    assert all("Drama" in document["genres"] for document in documents)


def test_search_filters_by_year_range(db):
    documents, total = search(db, year_from="2010", year_to="2015")

    assert total >= 1
    assert all(2010 <= document["year"] <= 2015 for document in documents)


def test_search_filters_by_minimum_rating(db):
    documents, total = search(db, min_rating="8.8")

    assert total >= 1
    assert all(document["external_rating"] >= 8.8 for document in documents)


def test_search_sorts_by_rating(db):
    documents, _ = search(db, sort="rating")

    assert documents[0]["title"] == "Fullmetal Alchemist: Brotherhood"


def test_search_paginates_without_overlap(db):
    first_page, total = search(db, page="1")
    second_page, _ = search(db, page="2")

    first_ids = {document["_id"] for document in first_page}
    second_ids = {document["_id"] for document in second_page}

    assert total == 16
    assert len(first_page) == 12
    assert len(second_page) == 4
    assert first_ids.isdisjoint(second_ids)


def test_get_title_returns_document_or_none(db):
    document = db.titles.find_one({"title": "Dark"})

    assert get_title(db, str(document["_id"]))["title"] == "Dark"
    assert get_title(db, "no-es-un-id") is None


def test_average_rating_uses_library_entries(db):
    title = db.titles.find_one({"title": "Dark"})
    now = datetime.now(timezone.utc)

    db.library_entries.insert_many(
        [
            {
                "user_id": ObjectId(),
                "title_id": title["_id"],
                "status": "watched",
                "favorite": False,
                "rating": 8,
                "progress": None,
                "notes": None,
                "created_at": now,
                "updated_at": now,
            },
            {
                "user_id": ObjectId(),
                "title_id": title["_id"],
                "status": "watched",
                "favorite": True,
                "rating": 10,
                "progress": None,
                "notes": None,
                "created_at": now,
                "updated_at": now,
            },
        ]
    )

    assert average_rating(db, title["_id"]) == {"average": 9.0, "count": 2}
