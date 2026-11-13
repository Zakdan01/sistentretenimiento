from datetime import datetime, timezone

from pymongo.database import Database

from app.catalog.services import title_collection


def _parse_year(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return None


def _external_id(value):
    """IMDb y Wikidata usan strings; Jikan y TMDB usan enteros."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return value
    text = str(value).strip()
    return int(text) if text.isdigit() else text


def build_document(details: dict, now: datetime) -> dict:
    """Convierte el payload de un proveedor en un documento de catálogo."""
    source = str(details["external"]["source"])

    return {
        "external": {
            "source": source,
            "id": _external_id(details["external"]["id"]),
        },
        "type": details["type"],
        "title": details["title"],
        "synopsis": details.get("synopsis") or "",
        "year": _parse_year(details.get("year")),
        "genres": details.get("genres") or [],
        "poster_url": details.get("poster_url"),
        "external_rating": details.get("external_rating"),
        "created_at": now,
        "updated_at": now,
    }


def import_title(db: Database, details: dict) -> tuple[dict, bool]:
    """Inserta o actualiza un título importado. Devuelve (documento, creado)."""
    now = datetime.now(timezone.utc)
    document = build_document(details, now)
    collection = title_collection(db, document["type"])

    query = {
        "external.source": document["external"]["source"],
        "external.id": document["external"]["id"],
    }
    result = collection.update_one(
        query,
        {
            "$set": {k: v for k, v in document.items() if k != "created_at"},
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )

    saved = collection.find_one(query)
    return saved, result.upserted_id is not None
