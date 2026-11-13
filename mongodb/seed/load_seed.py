"""Carga en MongoDB el catálogo y los datos de demostración.

Los JSON viven en `mongodb/seed/data/` y este módulo solo los transforma al
esquema de las cinco colecciones. Es idempotente por `external.source +
external.id` (catálogo) y por email (usuarios).

Uso:
    python -m mongodb.seed.load_seed
    python -m mongodb.seed.load_seed --reset
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient, UpdateOne
from pymongo.database import Database
from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parents[2]
SEED_DIR = Path(__file__).resolve().parent
DATA_DIR = SEED_DIR / "data"

CATALOG_FILES = {
    "movie": "movies.json",
    "series": "series.json",
    "anime": "animes.json",
}
USERS_FILE = "users.json"
LIBRARIES_FILE = "libraries.json"

CATALOG_COLLECTIONS = {
    "movie": "movies",
    "series": "series",
    "anime": "animes",
}


def read_json(path: Path) -> list | dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _catalog_document(raw: dict, title_type: str, now: datetime) -> dict:
    year = raw.get("year")
    return {
        "external": {
            "source": str(raw["source"]),
            "id": raw["external_id"],
        },
        "type": title_type,
        "title": raw["title"],
        "synopsis": raw.get("synopsis") or "",
        "year": int(year) if year is not None else None,
        "genres": raw.get("genres") or [],
        "poster_url": raw.get("image"),
        "external_rating": raw.get("rating"),
        "created_at": now,
        "updated_at": now,
    }


def load_catalog(
    db: Database, data_dir: Path | str = DATA_DIR, reset: bool = False
) -> dict[str, int]:
    """Carga movies/series/animes. Con `reset` reemplaza el catálogo previo."""
    data_dir = Path(data_dir)
    now = datetime.now(timezone.utc)
    counts: dict[str, int] = {}

    for title_type, filename in CATALOG_FILES.items():
        path = data_dir / filename
        if not path.exists():
            raise FileNotFoundError(
                f"Falta {path}. Generá los datos con "
                "`python -m mongodb.seed.fetch_catalog`."
            )

        collection = db[CATALOG_COLLECTIONS[title_type]]
        if reset:
            collection.delete_many({})

        operations = []
        for raw in read_json(path):
            document = _catalog_document(raw, title_type, now)
            operations.append(
                UpdateOne(
                    {
                        "external.source": document["external"]["source"],
                        "external.id": document["external"]["id"],
                    },
                    {
                        "$set": {
                            key: value
                            for key, value in document.items()
                            if key != "created_at"
                        },
                        "$setOnInsert": {"created_at": now},
                    },
                    upsert=True,
                )
            )

        if operations:
            collection.bulk_write(operations, ordered=False)
        counts[title_type] = len(operations)

    return counts


def load_users(
    db: Database, path: Path | str, reset: bool = False
) -> dict[str, dict]:
    """Carga las cuentas demo y devuelve {email: usuario}."""
    if reset:
        db.users.delete_many({})

    now = datetime.now(timezone.utc)
    users = {}
    for raw in read_json(Path(path)):
        document = {
            "email": raw["email"].strip().lower(),
            "password_hash": generate_password_hash(raw["password"]),
            "display_name": raw["display_name"],
            "role": raw["role"],
        }
        db.users.update_one(
            {"email": document["email"]},
            {
                "$set": document,
                "$setOnInsert": {
                    "avatar_url": raw.get("avatar_url"),
                    "created_at": now,
                },
            },
            upsert=True,
        )
        users[document["email"]] = db.users.find_one({"email": document["email"]})

    return users


def _find_title(db: Database, entry: dict):
    for title_type, collection_name in CATALOG_COLLECTIONS.items():
        document = db[collection_name].find_one(
            {
                "external.source": entry["source"],
                "external.id": entry["external_id"],
            }
        )
        if document is not None:
            return title_type, document
    return None, None


def load_libraries(
    db: Database,
    path: Path | str,
    users: dict[str, dict],
    reset: bool = False,
) -> int:
    """Carga las bibliotecas demo resolviendo cada título por identidad externa."""
    if reset:
        db.library_entries.delete_many({})

    now = datetime.now(timezone.utc)
    libraries = read_json(Path(path))
    total = 0
    missing = []

    for email, entries in libraries.items():
        user = users.get(email.strip().lower())
        if user is None:
            raise ValueError(f"La biblioteca referencia un usuario inexistente: {email}")

        for entry in entries:
            title_type, title = _find_title(db, entry)
            if title is None:
                missing.append(f"{entry['source']}:{entry['external_id']}")
                continue

            db.library_entries.update_one(
                {"user_id": user["_id"], "title_id": title["_id"]},
                {
                    "$set": {
                        "title_type": title_type,
                        "status": entry["status"],
                        "favorite": bool(entry.get("favorite")),
                        "rating": entry.get("rating"),
                        "progress": entry.get("progress"),
                        "notes": entry.get("notes"),
                        "updated_at": now,
                    },
                    "$setOnInsert": {
                        "user_id": user["_id"],
                        "title_id": title["_id"],
                        "created_at": now,
                    },
                },
                upsert=True,
            )
            total += 1

    if missing:
        raise ValueError(
            "Bibliotecas con títulos que no están en el catálogo: "
            + ", ".join(sorted(missing))
        )

    return total


def main() -> None:
    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="borra catálogo, usuarios y bibliotecas antes de cargar",
    )
    parser.add_argument("--skip-demo", action="store_true", help="solo catálogo")
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    load_dotenv(BASE_DIR / ".env")
    db = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))[
        os.getenv("MONGO_DB", "catalogo")
    ]

    counts = load_catalog(db, args.data_dir, reset=args.reset)
    print(
        "catálogo: "
        + ", ".join(f"{title_type}={count}" for title_type, count in counts.items())
    )

    if args.skip_demo:
        return

    data_dir = Path(args.data_dir)
    users = load_users(db, data_dir / USERS_FILE, reset=args.reset)
    entries = load_libraries(
        db, data_dir / LIBRARIES_FILE, users, reset=args.reset
    )
    print(f"usuarios demo: {len(users)}; entradas de biblioteca: {entries}")
    print("seed cargado en la base", db.name)


if __name__ == "__main__":
    main()
