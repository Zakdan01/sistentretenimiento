from datetime import datetime, timezone

from pymongo.database import Database


def _parse_date(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(str(value)).replace(tzinfo=timezone.utc)


def _parse_seasons(raw_seasons) -> list[dict]:
    seasons = []
    for season in raw_seasons or []:
        parsed = {
            "number": int(season["number"]),
            "episodes": int(season["episodes"]),
        }
        if season.get("air_date"):
            parsed["air_date"] = _parse_date(season["air_date"])
        seasons.append(parsed)
    return seasons


def build_document(details: dict, now: datetime) -> dict:
    """Convierte el payload de un proveedor en un documento de `titles`."""
    release_date = _parse_date(details.get("release_date"))
    year = details.get("year") or release_date.year

    return {
        "external": {
            "source": details["external"]["source"],
            "id": int(details["external"]["id"]),
        },
        "type": details["type"],
        "title": details["title"],
        "original_title": details.get("original_title") or details["title"],
        "synopsis": details.get("synopsis") or "",
        "genres": details.get("genres", []),
        "release_date": release_date,
        "year": int(year),
        "runtime_minutes": details.get("runtime_minutes"),
        "seasons": _parse_seasons(details.get("seasons")),
        "episodes_total": details.get("episodes_total"),
        "directors": details.get("directors", []),
        "cast": details.get("cast", []),
        "studios": details.get("studios", []),
        "poster_url": details.get("poster_url"),
        "external_rating": details.get("external_rating"),
        "awards": details.get("awards", []),
        "created_at": now,
        "updated_at": now,
    }


def import_title(db: Database, details: dict) -> tuple[dict, bool]:
    """Inserta o actualiza un título importado. Devuelve (documento, creado)."""
    now = datetime.now(timezone.utc)
    document = build_document(details, now)

    result = db.titles.update_one(
        {
            "external.source": document["external"]["source"],
            "external.id": document["external"]["id"],
        },
        {
            "$set": {k: v for k, v in document.items() if k != "created_at"},
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )

    saved = db.titles.find_one(
        {
            "external.source": document["external"]["source"],
            "external.id": document["external"]["id"],
        }
    )
    return saved, result.upserted_id is not None
