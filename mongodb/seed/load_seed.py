"""Carga el catálogo de demo en MongoDB.

Uso:
    python -m mongodb.seed.load_seed
    python -m mongodb.seed.load_seed ruta/al/archivo.json
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient, UpdateOne
from pymongo.database import Database

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SEED = Path(__file__).resolve().parent / "titles.json"


def _parse_date(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _to_document(raw: dict, now: datetime) -> dict:
    release_date = _parse_date(raw["release_date"])
    seasons = []
    for season in raw.get("seasons", []):
        parsed = {"number": int(season["number"]), "episodes": int(season["episodes"])}
        if season.get("air_date"):
            parsed["air_date"] = _parse_date(season["air_date"])
        seasons.append(parsed)

    return {
        "external": {
            "source": raw["external"]["source"],
            "id": int(raw["external"]["id"]),
        },
        "type": raw["type"],
        "title": raw["title"],
        "original_title": raw.get("original_title", raw["title"]),
        "synopsis": raw.get("synopsis", ""),
        "genres": raw.get("genres", []),
        "release_date": release_date,
        "year": release_date.year,
        "runtime_minutes": raw.get("runtime_minutes"),
        "seasons": seasons,
        "episodes_total": raw.get("episodes_total"),
        "directors": raw.get("directors", []),
        "cast": raw.get("cast", []),
        "studios": raw.get("studios", []),
        "poster_url": raw.get("poster_url"),
        "external_rating": raw.get("external_rating"),
        "awards": raw.get("awards", []),
        "created_at": now,
        "updated_at": now,
    }


def load_titles(db: Database, path: Path | str = DEFAULT_SEED) -> int:
    """Inserta o actualiza los títulos del seed. Devuelve cuántos procesó."""
    raw_titles = json.loads(Path(path).read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)

    operations = []
    for raw in raw_titles:
        document = _to_document(raw, now)
        set_document = {k: v for k, v in document.items() if k != "created_at"}
        operations.append(
            UpdateOne(
                {
                    "external.source": document["external"]["source"],
                    "external.id": document["external"]["id"],
                },
                {"$set": set_document, "$setOnInsert": {"created_at": now}},
                upsert=True,
            )
        )

    if not operations:
        return 0

    db.titles.bulk_write(operations, ordered=False)
    return len(operations)


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SEED
    db = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))[
        os.getenv("MONGO_DB", "catalogo")
    ]

    count = load_titles(db, path)
    print(f"seed cargado: {count} títulos en {db.name}.titles")


if __name__ == "__main__":
    main()
