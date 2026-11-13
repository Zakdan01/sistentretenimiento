from datetime import datetime, timezone

import pytest
from bson import ObjectId

from app.catalog.services import (
    average_rating,
    get_title,
    list_genres,
    recent_titles,
    search_titles,
    titles_by_ids,
    top_rated_titles,
)
from tests.support import find_title, prepare_database, seed_catalog, teardown

DB_NAME = "catalogo_test_catalog"


@pytest.fixture
def db():
    client, database = prepare_database(DB_NAME)
    seed_catalog(database)

    yield database

    teardown(client, DB_NAME)


def search(db, **params):
    return search_titles(db, params)


def test_search_filters_by_type(db):
    documents, total = search(db, type="anime")

    assert total == 6
    assert all(document["type"] == "anime" for document in documents)


def test_search_by_text_finds_title(db):
    documents, total = search(db, q="inception")

    assert total == 1
    assert documents[0]["title"] == "Inception"


def test_search_by_text_uses_spanish_synopsis_stemming(db):
    documents, total = search(db, q="sueño")

    assert total == 1
    assert documents[0]["title"] == "Inception"


def test_search_combines_text_and_type(db):
    documents, total = search(db, q="drama", type="series")

    assert total == 4
    assert all(document["type"] == "series" for document in documents)
    assert all("Drama" in document["genres"] for document in documents)


def test_search_filters_by_genre(db):
    documents, total = search(db, genre="Drama")

    assert total == 7
    assert all("Drama" in document["genres"] for document in documents)


def test_search_filters_by_year_range(db):
    documents, total = search(db, year_from="2010", year_to="2015")

    assert total == 5
    assert all(2010 <= document["year"] <= 2015 for document in documents)


def test_search_filters_by_minimum_rating(db):
    documents, total = search(db, min_rating="9.0")

    assert total == 6
    assert all(document["external_rating"] >= 9.0 for document in documents)


def test_search_sorts_by_rating(db):
    documents, _ = search(db, sort="rating")

    assert documents[0]["title"] == "Breaking Bad"


def test_search_sorts_by_year_and_title(db):
    by_year, _ = search(db, sort="year")
    by_title, _ = search(db, sort="title")

    assert by_year[0]["title"] == "Chernobyl"
    assert by_title[0]["title"] == "Breaking Bad"


def test_search_paginates_without_overlap(db):
    first_page, total = search(db, page="1")
    second_page, _ = search(db, page="2")

    first_ids = {document["_id"] for document in first_page}
    second_ids = {document["_id"] for document in second_page}

    assert total == 16
    assert len(first_page) == 12
    assert len(second_page) == 4
    assert first_ids.isdisjoint(second_ids)


def test_search_ignores_unknown_sort(db):
    documents, _ = search(db, sort="inventado")

    assert documents[0]["title"] == "Breaking Bad"


def test_get_title_resolves_each_collection_or_none(db):
    dark = find_title(db, "Dark")

    assert get_title(db, str(dark["_id"]))["title"] == "Dark"
    assert get_title(db, str(dark["_id"]), "series")["title"] == "Dark"
    assert get_title(db, str(dark["_id"]), "movie") is None
    assert get_title(db, "no-es-un-id") is None


def test_titles_by_ids_combines_the_three_collections(db):
    inception = find_title(db, "Inception")
    dark = find_title(db, "Dark")
    titan = find_title(db, "Shingeki no Kyojin")

    documents = titles_by_ids(db, [inception["_id"], dark["_id"], titan["_id"], "x"])

    assert {document["type"] for document in documents.values()} == {
        "movie",
        "series",
        "anime",
    }


def test_top_rated_and_recent_titles_come_from_all_collections(db):
    top = top_rated_titles(db, limit=3)
    recent = recent_titles(db, limit=3)

    assert [document["title"] for document in top] == [
        "Breaking Bad",
        "Chernobyl",
        "The Wire",
    ]
    assert [document["title"] for document in recent] == [
        "Chernobyl",
        "Dark",
        "Stranger Things",
    ]


def test_list_genres_merges_the_three_collections(db):
    genres = list_genres(db)

    assert "Drama" in genres
    assert "Acción" in genres
    assert genres == sorted(genres)


def test_average_rating_uses_library_entries(db):
    dark = find_title(db, "Dark")
    now = datetime.now(timezone.utc)

    db.library_entries.insert_many(
        [
            {
                "user_id": ObjectId(),
                "title_id": dark["_id"],
                "title_type": "series",
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
                "title_id": dark["_id"],
                "title_type": "series",
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

    assert average_rating(db, dark["_id"]) == {"average": 9.0, "count": 2}
