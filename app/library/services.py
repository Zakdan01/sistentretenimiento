from datetime import datetime, timezone

from bson import ObjectId
from pymongo.database import Database

STATUSES = ("watching", "watched", "planned", "dropped")


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
    db: Database, user_id: ObjectId, title_id: ObjectId, data: dict
) -> dict:
    now = datetime.now(timezone.utc)
    db.library_entries.update_one(
        {"user_id": user_id, "title_id": title_id},
        {
            "$set": {**data, "updated_at": now},
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
    match = {"user_id": user_id}
    if status in STATUSES:
        match["status"] = status

    pipeline = [
        {"$match": match},
        {"$sort": {"updated_at": -1}},
        {
            "$lookup": {
                "from": "titles",
                "localField": "title_id",
                "foreignField": "_id",
                "as": "title",
            }
        },
        {"$unwind": "$title"},
    ]
    return list(db.library_entries.aggregate(pipeline))


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
