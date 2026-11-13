"""Utilidades compartidas por la suite.

Cada módulo de pruebas sigue definiendo sus propias fixtures, pero la
inicialización de MongoDB/Redis y el catálogo mínimo viven acá para no repetir
el esquema de las cinco colecciones en cada archivo.

Requisitos: `mongosh` en el PATH, MongoDB en localhost:27017 y Redis en
localhost:6379 (se usa la base 15, exclusiva de pruebas).
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient
from redis import Redis
from werkzeug.security import generate_password_hash

from app import create_app
from mongodb.seed.load_seed import load_catalog

BASE_DIR = Path(__file__).resolve().parent.parent
INIT_SCRIPTS = [
    BASE_DIR / "mongodb" / "init" / "01_collections.js",
    BASE_DIR / "mongodb" / "init" / "02_indexes.js",
]
MONGO_URI = "mongodb://localhost:27017"
REDIS_URL = "redis://localhost:6379/15"

CATALOG_FILES = {
    "movie": "movies.json",
    "series": "series.json",
    "anime": "animes.json",
}

# Catálogo mínimo pero suficiente: 16 títulos (5 películas, 5 series, 6 animes).
# Las sinopsis y géneros están en español para ejercitar el índice de texto.
CATALOG = [
    {
        "type": "movie",
        "source": "imdb",
        "external_id": "tt1375666",
        "title": "Inception",
        "image": "https://example.org/inception.jpg",
        "synopsis": "Dom Cobb roba secretos dentro de los sueños de otras personas.",
        "year": 2010,
        "genres": ["Ciencia ficción", "Acción"],
        "rating": 8.8,
    },
    {
        "type": "movie",
        "source": "imdb",
        "external_id": "tt0816692",
        "title": "Interstellar",
        "image": "https://example.org/interstellar.jpg",
        "synopsis": "Un grupo de astronautas busca un nuevo hogar para la humanidad.",
        "year": 2014,
        "genres": ["Ciencia ficción", "Drama"],
        "rating": 8.6,
    },
    {
        "type": "movie",
        "source": "imdb",
        "external_id": "tt0068646",
        "title": "El padrino",
        "image": "https://example.org/padrino.jpg",
        "synopsis": "El patriarca de una familia mafiosa prepara a su hijo para el mando.",
        "year": 1972,
        "genres": ["Drama", "Crimen"],
        "rating": 9.2,
    },
    {
        "type": "movie",
        "source": "imdb",
        "external_id": "tt0110912",
        "title": "Pulp Fiction",
        "image": "https://example.org/pulp.jpg",
        "synopsis": "Historias entrelazadas de gánsteres, boxeadores y ladrones.",
        "year": 1994,
        "genres": ["Crimen", "Drama"],
        "rating": 8.9,
    },
    {
        "type": "movie",
        "source": "imdb",
        "external_id": "tt0167260",
        "title": "El señor de los anillos: El retorno del rey",
        "image": "https://example.org/retorno.jpg",
        "synopsis": "La batalla final por la Tierra Media decide el destino de la comunidad.",
        "year": 2003,
        "genres": ["Fantasía", "Aventura"],
        "rating": 9.0,
    },
    {
        "type": "series",
        "source": "imdb",
        "external_id": "tt5753856",
        "title": "Dark",
        "image": "https://example.org/dark.jpg",
        "synopsis": "Cuatro familias buscan a un niño desaparecido en un pueblo alemán.",
        "year": 2017,
        "genres": ["Misterio", "Drama"],
        "rating": 8.7,
    },
    {
        "type": "series",
        "source": "imdb",
        "external_id": "tt0903747",
        "title": "Breaking Bad",
        "image": "https://example.org/breaking.jpg",
        "synopsis": "Un profesor de química con cáncer terminal se vuelve narcotraficante.",
        "year": 2008,
        "genres": ["Drama", "Crimen"],
        "rating": 9.5,
    },
    {
        "type": "series",
        "source": "imdb",
        "external_id": "tt0306414",
        "title": "The Wire",
        "image": "https://example.org/wire.jpg",
        "synopsis": "La vida en Baltimore a través de policías, traficantes y periodistas.",
        "year": 2002,
        "genres": ["Drama", "Crimen"],
        "rating": 9.3,
    },
    {
        "type": "series",
        "source": "imdb",
        "external_id": "tt7366338",
        "title": "Chernobyl",
        "image": "https://example.org/chernobyl.jpg",
        "synopsis": "La reconstrucción del accidente nuclear de 1986.",
        "year": 2019,
        "genres": ["Drama", "Historia"],
        "rating": 9.4,
    },
    {
        "type": "series",
        "source": "imdb",
        "external_id": "tt4574334",
        "title": "Stranger Things",
        "image": "https://example.org/stranger.jpg",
        "synopsis": "Un pueblo descubre experimentos secretos y una niña con poderes.",
        "year": 2016,
        "genres": ["Ciencia ficción", "Terror"],
        "rating": 8.6,
    },
    {
        "type": "anime",
        "source": "jikan",
        "external_id": 16498,
        "title": "Shingeki no Kyojin",
        "image": "https://example.org/titan.jpg",
        "synopsis": "La humanidad sobrevive tras enormes murallas.",
        "year": 2013,
        "genres": ["Acción", "Fantasía"],
        "rating": 8.5,
    },
    {
        "type": "anime",
        "source": "jikan",
        "external_id": 5114,
        "title": "Fullmetal Alchemist: Brotherhood",
        "image": "https://example.org/fma.jpg",
        "synopsis": "Dos hermanos alquimistas buscan la piedra filosofal.",
        "year": 2009,
        "genres": ["Acción", "Aventura"],
        "rating": 9.1,
    },
    {
        "type": "anime",
        "source": "jikan",
        "external_id": 1535,
        "title": "Death Note",
        "image": "https://example.org/deathnote.jpg",
        "synopsis": "Un estudiante encuentra un cuaderno que mata a quien nombre.",
        "year": 2006,
        "genres": ["Misterio", "Suspenso"],
        "rating": 8.6,
    },
    {
        "type": "anime",
        "source": "jikan",
        "external_id": 1,
        "title": "Cowboy Bebop",
        "image": "https://example.org/bebop.jpg",
        "synopsis": "Cazarrecompensas viajan por el sistema solar.",
        "year": 1998,
        "genres": ["Ciencia ficción", "Acción"],
        "rating": 8.8,
    },
    {
        "type": "anime",
        "source": "jikan",
        "external_id": 9253,
        "title": "Steins;Gate",
        "image": "https://example.org/steins.jpg",
        "synopsis": "Un científico descubre cómo enviar mensajes al pasado.",
        "year": 2011,
        "genres": ["Ciencia ficción", "Suspenso"],
        "rating": 8.9,
    },
    {
        "type": "anime",
        "source": "jikan",
        "external_id": 30276,
        "title": "One Punch Man",
        "image": "https://example.org/onepunch.jpg",
        "synopsis": "Un héroe tan fuerte que derrota a todos con un solo golpe.",
        "year": 2015,
        "genres": ["Acción", "Comedia"],
        "rating": 8.5,
    },
]


def prepare_database(db_name: str):
    """Crea una base de pruebas limpia con colecciones, validadores e índices."""
    client = MongoClient(MONGO_URI)
    client.drop_database(db_name)

    uri = f"{MONGO_URI}/{db_name}"
    for script in INIT_SCRIPTS:
        subprocess.run(
            ["mongosh", uri, "--quiet", "--file", str(script)],
            check=True,
            capture_output=True,
            text=True,
        )

    return client, client[db_name]


def catalog_snapshots() -> dict[str, list[dict]]:
    """Agrupa `CATALOG` por tipo, con la forma de los JSON del seed."""
    grouped = {title_type: [] for title_type in CATALOG_FILES}
    for raw in CATALOG:
        grouped[raw["type"]].append(
            {key: value for key, value in raw.items() if key != "type"}
        )
    return grouped


def write_catalog_files(directory: Path) -> None:
    """Escribe `movies.json`, `series.json` y `animes.json` en `directory`."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for title_type, filename in CATALOG_FILES.items():
        (directory / filename).write_text(
            json.dumps(catalog_snapshots()[title_type], ensure_ascii=False),
            encoding="utf-8",
        )


def seed_catalog(db) -> dict[str, int]:
    """Carga `CATALOG` usando el loader real de `mongodb.seed.load_seed`."""
    with tempfile.TemporaryDirectory() as temp:
        directory = Path(temp)
        write_catalog_files(directory)
        return load_catalog(db, directory)


def get_database(db_name: str):
    """Conexión directa a la base de pruebas (sin depender del contexto Flask)."""
    return MongoClient(MONGO_URI)[db_name]


def flush_redis() -> Redis:
    redis_client = Redis.from_url(REDIS_URL, decode_responses=True, protocol=2)
    redis_client.flushdb()
    return redis_client


def make_app(db_name: str):
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "MONGO_DB": db_name,
            "REDIS_URL": REDIS_URL,
            "SESSION_TTL_SECONDS": 60,
        }
    )


def make_user(
    db,
    email: str = "laura@example.com",
    password: str = "secreto123",
    display_name: str = "Laura",
    role: str = "user",
):
    """Inserta una cuenta válida para el validador de `users`."""
    db.users.insert_one(
        {
            "email": email.strip().lower(),
            "password_hash": generate_password_hash(password),
            "display_name": display_name,
            "role": role,
            "avatar_url": None,
            "created_at": datetime.now(timezone.utc),
        }
    )
    return db.users.find_one({"email": email.strip().lower()})


def login(client, email: str = "laura@example.com", password: str = "secreto123"):
    return client.post(
        "/auth/login", data={"email": email, "password": password}
    )


def find_title(db, title: str) -> dict:
    """Busca un título en las tres colecciones del catálogo."""
    for name in ("movies", "series", "animes"):
        document = db[name].find_one({"title": title})
        if document is not None:
            return document
    raise AssertionError(f"no existe el título {title!r} en el catálogo de prueba")


def teardown(client, db_name: str, redis_client: Redis | None = None) -> None:
    client.drop_database(db_name)
    if redis_client is not None:
        redis_client.flushdb()
