"""Lógica del panel de administración: títulos, usuarios, reportes."""

import re
from collections import defaultdict
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from werkzeug.security import generate_password_hash

from app.catalog.services import TYPES, title_collection, title_collections

ROLES = ("admin", "user")
SOURCES = ("manual", "imdb", "tmdb", "jikan", "anilist")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PAGE_SIZE = 20


def _to_object_id(raw):
    try:
        return ObjectId(str(raw))
    except (InvalidId, TypeError):
        return None


def parse_title_form(form) -> tuple[dict | None, str | None]:
    """Valida el formulario de alta/edición de un título."""
    title_type = (form.get("type") or "").strip()
    title = (form.get("title") or "").strip()
    synopsis = (form.get("synopsis") or "").strip()
    genres = [
        genre.strip()
        for genre in re.split(r"[,;]", form.get("genres") or "")
        if genre.strip()
    ]
    poster_url = (form.get("poster_url") or "").strip() or None

    if title_type not in TYPES:
        return None, "Elegí un tipo de título válido."

    if not title:
        return None, "El título es obligatorio."

    raw_year = (form.get("year") or "").strip()
    year = None
    if raw_year:
        try:
            year = int(raw_year)
        except ValueError:
            return None, "El año debe ser un número."
        if not 1900 <= year <= 2100:
            return None, "El año debe estar entre 1900 y 2100."

    raw_rating = (form.get("external_rating") or "").strip()
    rating = None
    if raw_rating:
        try:
            rating = round(float(raw_rating), 1)
        except ValueError:
            return None, "La valoración debe ser un número."
        if not 0 <= rating <= 10:
            return None, "La valoración debe estar entre 0 y 10."

    source = (form.get("source") or "manual").strip()
    if source not in SOURCES:
        return None, "Elegí una fuente válida."

    external_id = (form.get("external_id") or "").strip()
    external = None
    if source != "manual":
        if not external_id:
            return None, "Indicá el id externo o elegí la fuente manual."
        external = {
            "source": source,
            "id": int(external_id) if external_id.isdigit() else external_id,
        }

    if poster_url and not poster_url.startswith(("http://", "https://")):
        return None, "La imagen debe ser una URL http(s)."

    return {
        "type": title_type,
        "title": title,
        "synopsis": synopsis,
        "year": year,
        "genres": genres,
        "poster_url": poster_url,
        "external_rating": rating,
        "external": external,
    }, None


def create_title(db, data: dict):
    now = datetime.now(timezone.utc)
    document = {
        **data,
        "created_at": now,
        "updated_at": now,
    }
    return title_collection(db, document["type"]).insert_one(document).inserted_id


def update_title(db, title_type: str, title_id, data: dict) -> None:
    # El tipo no se cambia en edición: mover el documento de colección no aporta
    # y rompería la identidad de la entrada en las bibliotecas.
    payload = {k: v for k, v in data.items() if k != "type"}
    payload["updated_at"] = datetime.now(timezone.utc)
    title_collection(db, title_type).update_one(
        {"_id": _to_object_id(title_id)}, {"$set": payload}
    )


def delete_title(db, title_type: str, title_id) -> int:
    """Elimina la ficha y sus entradas de biblioteca. Devuelve entradas borradas."""
    object_id = _to_object_id(title_id)
    if object_id is None:
        return 0

    title_collection(db, title_type).delete_one({"_id": object_id})
    return db.library_entries.delete_many({"title_id": object_id}).deleted_count


def parse_user_form(form, require_password: bool) -> tuple[dict | None, str | None]:
    display_name = (form.get("display_name") or "").strip()
    email = (form.get("email") or "").strip().lower()
    role = (form.get("role") or "user").strip()
    password = form.get("password") or ""

    if not display_name:
        return None, "El nombre es obligatorio."
    if len(display_name) > 60:
        return None, "El nombre no puede superar los 60 caracteres."
    if not EMAIL_RE.match(email):
        return None, "Ingresá un email válido."
    if role not in ROLES:
        return None, "Elegí un rol válido."
    if require_password or password:
        if len(password) < 8:
            return None, "La contraseña debe tener al menos 8 caracteres."

    return {
        "display_name": display_name,
        "email": email,
        "role": role,
        "password": password,
    }, None


def create_user(db, data: dict):
    document = {
        "email": data["email"],
        "password_hash": generate_password_hash(data["password"]),
        "display_name": data["display_name"],
        "role": data["role"],
        "avatar_url": None,
        "created_at": datetime.now(timezone.utc),
    }
    return db.users.insert_one(document).inserted_id


def update_user(db, user_id, data: dict) -> None:
    payload = {
        "email": data["email"],
        "display_name": data["display_name"],
        "role": data["role"],
    }
    if data["password"]:
        payload["password_hash"] = generate_password_hash(data["password"])
    db.users.update_one({"_id": _to_object_id(user_id)}, {"$set": payload})


def delete_user(db, user_id) -> int:
    """Elimina la cuenta y su biblioteca. Devuelve entradas borradas."""
    object_id = _to_object_id(user_id)
    if object_id is None:
        return 0

    db.users.delete_one({"_id": object_id})
    return db.library_entries.delete_many({"user_id": object_id}).deleted_count


def list_users(db, page: int = 1) -> tuple[list[dict], int]:
    total = db.users.count_documents({})
    cursor = (
        db.users.find()
        .sort([("role", 1), ("display_name", 1)])
        .skip((max(1, page) - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
    )
    return list(cursor), total


def dashboard_stats(db) -> dict:
    catalog = {
        title_type: collection.count_documents({})
        for title_type, collection in title_collections(db)
    }

    status_counts = {row["_id"]: row["total"] for row in db.library_entries.aggregate([
        {"$group": {"_id": "$status", "total": {"$sum": 1}}},
    ])}
    for status in ("watching", "watched", "planned", "dropped"):
        status_counts.setdefault(status, 0)

    ratings = list(
        db.library_entries.aggregate(
            [
                {"$match": {"rating": {"$ne": None}}},
                {"$group": {"_id": None, "average": {"$avg": "$rating"}}},
            ]
        )
    )

    return {
        "catalog": catalog,
        "catalog_total": sum(catalog.values()),
        "users_total": db.users.count_documents({}),
        "admins": db.users.count_documents({"role": "admin"}),
        "common_users": db.users.count_documents({"role": "user"}),
        "entries_total": db.library_entries.count_documents({}),
        "favorites": db.library_entries.count_documents({"favorite": True}),
        "status_counts": status_counts,
        "avg_rating": (
            round(ratings[0]["average"], 1) if ratings else None
        ),
    }


def top_genres_report(db, limit: int = 10) -> list[dict]:
    totals = defaultdict(lambda: {"titles": 0, "ratings": [], "types": set()})
    for title_type, collection in title_collections(db):
        for document in collection.find({"genres": {"$exists": True, "$ne": []}}):
            for genre in document.get("genres", []):
                bucket = totals[genre]
                bucket["titles"] += 1
                bucket["types"].add(title_type)
                if document.get("external_rating") is not None:
                    bucket["ratings"].append(document["external_rating"])

    rows = []
    for genre, bucket in totals.items():
        average = (
            round(sum(bucket["ratings"]) / len(bucket["ratings"]), 2)
            if bucket["ratings"]
            else None
        )
        rows.append(
            {
                "genre": genre,
                "titles": bucket["titles"],
                "avg_rating": average,
                "types": sorted(bucket["types"]),
            }
        )
    rows.sort(key=lambda row: (-row["titles"], row["genre"]))
    return rows[:limit]


def library_by_status_report(db) -> list[dict]:
    users = {
        user["_id"]: user
        for user in db.users.find({}, {"display_name": 1, "email": 1, "role": 1})
    }
    grouped = defaultdict(lambda: defaultdict(int))
    for entry in db.library_entries.find({"status": {"$exists": True}}):
        grouped[entry["user_id"]][entry["status"]] += 1

    rows = []
    for user_id, statuses in grouped.items():
        user = users.get(user_id)
        if user is None:
            continue
        rows.append(
            {
                "user": user["display_name"],
                "email": user["email"],
                "role": user["role"],
                "total": sum(statuses.values()),
                "statuses": [
                    {"status": status, "total": total}
                    for status, total in sorted(statuses.items())
                ],
            }
        )
    rows.sort(key=lambda row: (-row["total"], row["user"]))
    return rows


def catalog_health_report(db) -> list[dict]:
    rows = []
    for title_type, collection in title_collections(db):
        documents = list(collection.find())
        ratings = [
            document["external_rating"]
            for document in documents
            if document.get("external_rating") is not None
        ]
        years = [document["year"] for document in documents if document.get("year")]
        rows.append(
            {
                "type": title_type,
                "titles": len(documents),
                "avg_external_rating": (
                    round(sum(ratings) / len(ratings), 2) if ratings else None
                ),
                "avg_year": round(sum(years) / len(years)) if years else None,
                "with_image": sum(1 for document in documents if document.get("poster_url")),
            }
        )
    return rows


def top_rated_by_type_report(db, per_type: int = 3) -> list[dict]:
    rows = []
    for title_type, collection in title_collections(db):
        documents = [
            document
            for document in collection.find({"external_rating": {"$ne": None}})
        ]
        documents.sort(
            key=lambda document: (
                -(document.get("external_rating") or 0),
                document.get("title", "").casefold(),
            )
        )
        for position, document in enumerate(documents[:per_type], start=1):
            rows.append(
                {
                    "type": title_type,
                    "position": position,
                    "title": document["title"],
                    "external_rating": document["external_rating"],
                }
            )
    return rows


def user_activity_report(db) -> list[dict]:
    users = {
        user["_id"]: user
        for user in db.users.find({}, {"display_name": 1, "email": 1, "role": 1})
    }
    grouped = defaultdict(lambda: {"entries": 0, "favorites": 0, "ratings": []})
    for entry in db.library_entries.find():
        bucket = grouped[entry["user_id"]]
        bucket["entries"] += 1
        if entry.get("favorite"):
            bucket["favorites"] += 1
        if entry.get("rating") is not None:
            bucket["ratings"].append(entry["rating"])

    rows = []
    for user_id, bucket in grouped.items():
        user = users.get(user_id)
        if user is None:
            continue
        rows.append(
            {
                "user": user["display_name"],
                "email": user["email"],
                "role": user["role"],
                "entries": bucket["entries"],
                "favorites": bucket["favorites"],
                "avg_rating": (
                    round(sum(bucket["ratings"]) / len(bucket["ratings"]), 2)
                    if bucket["ratings"]
                    else None
                ),
            }
        )
    rows.sort(key=lambda row: (-row["entries"], row["user"]))
    return rows
