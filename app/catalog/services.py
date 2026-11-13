from collections.abc import Mapping

from bson import ObjectId
from bson.errors import InvalidId

PAGE_SIZE = 12
TYPES = ("movie", "series", "anime")
TYPE_COLLECTIONS = {
    "movie": "movies",
    "series": "series",
    "anime": "animes",
}
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


def title_collection(db, title_type: str):
    """Devuelve la colección concreta de un tipo de título."""
    return db[TYPE_COLLECTIONS[title_type]]


def title_collections(db, title_type: str | None = None):
    """Pares (tipo, colección) a consultar; todos si no se filtra."""
    types = (title_type,) if title_type in TYPE_COLLECTIONS else TYPES
    return [(item, db[TYPE_COLLECTIONS[item]]) for item in types]


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


def _matching_titles(db, filters: dict) -> list[tuple[float | None, dict]]:
    """Consulta las colecciones necesarias y devuelve (score, documento)."""
    query = build_filter(filters)
    matching: list[tuple[float | None, dict]] = []

    for _title_type, collection in title_collections(db, filters["type"]):
        if filters["q"] and filters["sort"] == "relevance":
            cursor = collection.find(query, {"score": {"$meta": "textScore"}})
            for document in cursor:
                matching.append((document.get("score"), document))
        else:
            for document in collection.find(query):
                matching.append((None, document))

    return matching


def _sort_matching(matching, sort: str):
    if sort == "relevance":
        return sorted(
            matching,
            key=lambda item: (-(item[0] or 0), item[1].get("title", "").casefold()),
        )

    if sort == "year":
        return sorted(
            matching,
            key=lambda item: (
                item[1].get("year") is None,
                -(item[1].get("year") or 0),
                item[1].get("title", "").casefold(),
            ),
        )

    if sort == "title":
        return sorted(matching, key=lambda item: item[1].get("title", "").casefold())

    return sorted(
        matching,
        key=lambda item: (
            item[1].get("external_rating") is None,
            -(item[1].get("external_rating") or 0),
            item[1].get("title", "").casefold(),
        ),
    )


def search_titles(db, params: Mapping, page_size: int = PAGE_SIZE):
    """Busca en las tres colecciones y pagina el resultado combinado."""
    filters = parse_filters(params)
    matching = _sort_matching(_matching_titles(db, filters), filters["sort"])

    total = len(matching)
    start = (filters["page"] - 1) * page_size
    documents = [document for _score, document in matching[start : start + page_size]]
    return documents, total


def get_title(db, title_id, title_type: str | None = None) -> dict | None:
    """Busca una ficha por id; si no se conoce el tipo, recorre las tres."""
    try:
        object_id = ObjectId(str(title_id))
    except (InvalidId, TypeError):
        return None

    for _title_type, collection in title_collections(db, title_type):
        document = collection.find_one({"_id": object_id})
        if document is not None:
            return document
    return None


def titles_by_ids(db, title_ids) -> dict:
    """Resuelve ids de las tres colecciones en un solo mapa."""
    object_ids = []
    for raw_id in title_ids:
        try:
            object_ids.append(ObjectId(str(raw_id)))
        except (InvalidId, TypeError):
            continue
    if not object_ids:
        return {}

    documents = {}
    for _title_type, collection in title_collections(db):
        for document in collection.find({"_id": {"$in": object_ids}}):
            documents[document["_id"]] = document
    return documents


def top_rated_titles(db, limit: int = 8) -> list[dict]:
    documents = [
        document
        for _title_type, collection in title_collections(db)
        for document in collection.find()
    ]
    documents.sort(
        key=lambda document: (
            document.get("external_rating") is None,
            -(document.get("external_rating") or 0),
            document.get("title", "").casefold(),
        )
    )
    return documents[:limit]


def recent_titles(db, limit: int = 8) -> list[dict]:
    documents = [
        document
        for _title_type, collection in title_collections(db)
        for document in collection.find()
    ]
    documents.sort(
        key=lambda document: (
            document.get("year") is None,
            -(document.get("year") or 0),
            document.get("title", "").casefold(),
        )
    )
    return documents[:limit]


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
    genres = set()
    for _title_type, collection in title_collections(db):
        genres.update(genre for genre in collection.distinct("genres") if genre)
    return sorted(genres)


def serialize_title(document: dict) -> dict:
    return {
        "id": str(document["_id"]),
        "type": document["type"],
        "title": document["title"],
        "synopsis": document.get("synopsis") or "",
        "genres": document.get("genres", []),
        "year": document.get("year"),
        "poster_url": document.get("poster_url"),
        "external_rating": document.get("external_rating"),
    }
