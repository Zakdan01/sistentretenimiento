from datetime import datetime, timezone

from bson import ObjectId
from pymongo.database import Database

from app.catalog.services import title_collection

STATUSES = ("watching", "watched", "planned", "dropped")
TITLE_TYPES = ("movie", "series", "anime")


def parse_entry_form(form) -> tuple[dict | None, str | None]:
    """Valida el formulario de biblioteca. Devuelve (datos, error)."""
    status = form.get("status", "")
    if status not in STATUSES:
        return None, "Elegí un estado válido."

    raw_rating = (form.get("rating") or "").strip()
    rating = None
    if raw_rating:
        try:
            rating = int(raw_rating)
        except ValueError:
            return None, "La nota debe ser un número entero."
        if not 1 <= rating <= 10:
            return None, "La nota debe estar entre 1 y 10."

    raw_season = (form.get("progress_season") or "").strip()
    raw_episode = (form.get("progress_episode") or "").strip()
    progress = None
    if raw_season or raw_episode:
        if not raw_season or not raw_episode:
            return None, "Para el progreso indicá temporada y episodio."
        try:
            progress = {"season": int(raw_season), "episode": int(raw_episode)}
        except ValueError:
            return None, "La temporada y el episodio deben ser números."
        if progress["season"] < 1 or progress["episode"] < 1:
            return None, "La temporada y el episodio deben ser mayores a cero."

    notes = (form.get("notes") or "").strip() or None
    if notes and len(notes) > 500:
        return None, "Las notas no pueden superar los 500 caracteres."

    return {
        "status": status,
        "favorite": form.get("favorite") == "on",
        "rating": rating,
        "progress": progress,
        "notes": notes,
    }, None


def upsert_entry(
    db: Database,
    user_id: ObjectId,
    title_id: ObjectId,
    title_type: str,
    data: dict,
) -> dict:
    if title_type not in TITLE_TYPES:
        raise ValueError(f"Tipo de título inválido: {title_type}")

    now = datetime.now(timezone.utc)
    db.library_entries.update_one(
        {"user_id": user_id, "title_id": title_id},
        {
            "$set": {**data, "title_type": title_type, "updated_at": now},
            "$setOnInsert": {
                "user_id": user_id,
                "title_id": title_id,
                "created_at": now,
            },
        },
        upsert=True,
    )
    return db.library_entries.find_one({"user_id": user_id, "title_id": title_id})


def delete_entry(db: Database, user_id: ObjectId, title_id: ObjectId) -> None:
    db.library_entries.delete_one({"user_id": user_id, "title_id": title_id})


def get_entry(
    db: Database, user_id: ObjectId, title_id: ObjectId
) -> dict | None:
    return db.library_entries.find_one({"user_id": user_id, "title_id": title_id})


def list_entries(db: Database, user_id: ObjectId, status: str | None = None) -> list[dict]:
    """Entradas del usuario con su ficha, resolviendo el tipo de cada título."""
    match = {"user_id": user_id}
    if status in STATUSES:
        match["status"] = status

    entries = list(
        db.library_entries.find(match).sort([("updated_at", -1)])
    )

    ids_by_type: dict[str, list[ObjectId]] = {}
    for entry in entries:
        title_type = entry.get("title_type")
        if title_type in TITLE_TYPES:
            ids_by_type.setdefault(title_type, []).append(entry["title_id"])

    titles: dict[ObjectId, dict] = {}
    for title_type, title_ids in ids_by_type.items():
        collection = title_collection(db, title_type)
        for document in collection.find({"_id": {"$in": title_ids}}):
            titles[document["_id"]] = document

    result = []
    for entry in entries:
        document = titles.get(entry["title_id"])
        if document is None:
            continue
        entry["title"] = document
        result.append(entry)
    return result


def count_by_status(db: Database, user_id: ObjectId) -> dict:
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": "$status", "total": {"$sum": 1}}},
    ]
    counts = {status: 0 for status in STATUSES}
    for row in db.library_entries.aggregate(pipeline):
        counts[row["_id"]] = row["total"]
    return counts


def profile_stats(db: Database, user_id: ObjectId) -> dict:
    counts = count_by_status(db, user_id)
    favorites = db.library_entries.count_documents(
        {"user_id": user_id, "favorite": True}
    )
    average = list(
        db.library_entries.aggregate(
            [
                {"$match": {"user_id": user_id, "rating": {"$ne": None}}},
                {"$group": {"_id": None, "average": {"$avg": "$rating"}}},
            ]
        )
    )

    return {
        "counts": counts,
        "total": sum(counts.values()),
        "favorites": favorites,
        "avg_rating": round(average[0]["average"], 1) if average else None,
    }


def user_top_favorites(db: Database, user_id: ObjectId) -> dict:
    """Devuelve la entrada y ficha del título favorito destacado por categoría (movie, series, anime)."""
    top = {"movie": None, "series": None, "anime": None}
    for title_type in TITLE_TYPES:
        cursor = (
            db.library_entries.find(
                {"user_id": user_id, "title_type": title_type, "favorite": True}
            )
            .sort([("rating", -1), ("updated_at", -1)])
            .limit(1)
        )
        entries = list(cursor)
        if entries:
            entry = entries[0]
            col = title_collection(db, title_type)
            doc = col.find_one({"_id": entry["title_id"]})
            if doc:
                entry["title"] = doc
                top[title_type] = entry
    return top
