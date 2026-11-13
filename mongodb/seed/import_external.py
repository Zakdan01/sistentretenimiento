"""Importa títulos desde una API externa a MongoDB.

Uso:
    python -m mongodb.seed.import_external jikan 21 38000 31964
    python -m mongodb.seed.import_external tmdb 27205 --media-type movie
"""

import argparse
import os
import time

from dotenv import load_dotenv
from pymongo import MongoClient

from app.catalog.importer import import_title
from app.catalog.providers import fetch_jikan, fetch_tmdb

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=["jikan", "tmdb"])
    parser.add_argument("ids", nargs="+", type=int)
    parser.add_argument("--media-type", default="movie", choices=["movie", "tv"])
    args = parser.parse_args()

    load_dotenv(os.path.join(BASE_DIR, ".env"))
    db = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))[
        os.getenv("MONGO_DB", "catalogo")
    ]

    imported = 0
    for external_id in args.ids:
        if args.source == "jikan":
            details = fetch_jikan(external_id)
            time.sleep(1)  # Jikan limita a 3 pedidos por segundo.
        else:
            details = fetch_tmdb(
                args.media_type,
                external_id,
                api_key=os.getenv("TMDB_API_KEY", ""),
            )

        document, created = import_title(db, details)
        status = "creado" if created else "actualizado"
        print(f"{status}: {document['title']} ({document['_id']})")
        imported += 1

    print(f"{imported} títulos procesados en {db.name} (movies/series/animes)")


if __name__ == "__main__":
    main()
