import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")

    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB = os.getenv("MONGO_DB", "catalogo")

    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", 60 * 60 * 24 * 7))

    TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
    TMDB_BASE_URL = os.getenv("TMDB_BASE_URL", "https://api.themoviedb.org/3")
    JIKAN_BASE_URL = os.getenv("JIKAN_BASE_URL", "https://api.jikan.moe/v4")
