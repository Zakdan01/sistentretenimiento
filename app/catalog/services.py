from collections.abc import Mapping

from bson import ObjectId
from bson.errors import InvalidId

PAGE_SIZE = 12
TYPES = {"movie", "series", "anime"}
SORTS = {"relevance", "rating", "year", "title"}


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_filters(params: Mapping) -> dict:
    query = str(params.get("q") or "").strip()
    title_type = params.get("type") or None
    sort = params.get("sort") or ("relevance" if query else "rating")

    return {
        "q": query,
        "type": title_type if title_type in TYPES else None,
        "genre": str(params.get("genre") or "").strip() or None,
        "year_from": _to_int(params.get("year_from")),
        "year_to": _to_int(params.get("year_to")),
        "min_rating": _to_float(params.get("min_rating")),
        "sort": sort if sort in SORTS else "rating",
        "page": max(1, _to_int(params.get("page")) or 1),
    }


def build_filter(filters: dict) -> dict:
    query = {}

    if filters["q"]:
        query["$text"] = {"$search": filters["q"]}
    if filters["type"]:
        query["type"] = filters["type"]
    if filters["genre"]:
        query["genres"] = filters["genre"]
    if filters["year_from"] or filters["year_to"]:
        year = {}
        if filters["year_from"]:
            year["$gte"] = filters["year_from"]
        if filters["year_to"]:
            year["$lte"] = filters["year_to"]
        query["year"] = year
    if filters["min_rating"] is not None:
        query["external_rating"] = {"$gte": filters["min_rating"]}

    return query


def _cursor_sorted(collection, query: dict, filters: dict, page_size: int):
    skip = (filters["page"] - 1) * page_size

    if filters["q"] and filters["sort"] == "relevance":
        projection = {"score": {"$meta": "textScore"}}
        return collection.find(query, projection).sort(
            [("score", {"$meta": "textScore"})]
        ).skip(skip).limit(page_size)

    sort = {
        "rating": [("external_rating", -1), ("title", 1)],
        "year": [("year", -1), ("title", 1)],
        "title": [("title", 1)],
    }.get(filters["sort"], [("external_rating", -1), ("title", 1)])

    return collection.find(query).sort(sort).skip(skip).limit(page_size)


def search_titles(db, params: Mapping, page_size: int = PAGE_SIZE):
    filters = parse_filters(params)
    query = build_filter(filters)

    total = db.titles.count_documents(query)
    documents = list(_cursor_sorted(db.titles, query, filters, page_size))

    return documents, total


def get_title(db, title_id) -> dict | None:
    try:
        object_id = ObjectId(str(title_id))
    except (InvalidId, TypeError):
        return None

    return db.titles.find_one({"_id": object_id})


def average_rating(db, title_id) -> dict:
    pipeline = [
        {"$match": {"title_id": title_id, "rating": {"$ne": None}}},
        {
            "$group": {
                "_id": None,
                "average": {"$avg": "$rating"},
                "count": {"$sum": 1},
            }
        },
    ]

    result = list(db.library_entries.aggregate(pipeline))
    if not result:
        return {"average": None, "count": 0}

    return {"average": round(result[0]["average"], 1), "count": result[0]["count"]}


def list_genres(db) -> list[str]:
    return sorted(genre for genre in db.titles.distinct("genres") if genre)


def serialize_title(document: dict) -> dict:
    return {
        "id": str(document["_id"]),
        "type": document["type"],
        "title": document["title"],
        "original_title": document.get("original_title"),
        "synopsis": document.get("synopsis"),
        "genres": document.get("genres", []),
        "release_date": document["release_date"].date().isoformat(),
        "year": document["year"],
        "runtime_minutes": document.get("runtime_minutes"),
        "seasons": [
            {
                "number": season["number"],
                "episodes": season["episodes"],
                **(
                    {"air_date": season["air_date"].date().isoformat()}
                    if season.get("air_date")
                    else {}
                ),
            }
            for season in document.get("seasons", [])
        ],
        "episodes_total": document.get("episodes_total"),
        "directors": document.get("directors", []),
        "cast": document.get("cast", []),
        "studios": document.get("studios", []),
        "poster_url": document.get("poster_url"),
        "external_rating": document.get("external_rating"),
        "awards": document.get("awards", []),
    }
