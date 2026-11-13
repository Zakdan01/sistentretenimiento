import subprocess
from pathlib import Path

import pytest
from pymongo import MongoClient
from redis import Redis

from app import create_app

BASE_DIR = Path(__file__).resolve().parent.parent
INIT_SCRIPTS = [
    BASE_DIR / "mongodb" / "init" / "01_collections.js",
    BASE_DIR / "mongodb" / "init" / "02_indexes.js",
]
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "catalogo_test_auth"
REDIS_URL = "redis://localhost:6379/15"


@pytest.fixture
def app():
    client = MongoClient(MONGO_URI)
    client.drop_database(DB_NAME)

    uri = f"{MONGO_URI}/{DB_NAME}"
    for script in INIT_SCRIPTS:
        subprocess.run(
            ["mongosh", uri, "--quiet", "--file", str(script)],
            check=True,
            capture_output=True,
            text=True,
        )

    redis_client = Redis.from_url(REDIS_URL, decode_responses=True, protocol=2)
    redis_client.flushdb()

    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "MONGO_DB": DB_NAME,
            "REDIS_URL": REDIS_URL,
            "SESSION_TTL_SECONDS": 60,
        }
    )

    yield application

    client.drop_database(DB_NAME)
    redis_client.flushdb()


@pytest.fixture
def client(app):
    return app.test_client()


def register(client, email="laura@example.com", password="secreto123"):
    return client.post(
        "/auth/register",
        data={"display_name": "Laura", "email": email, "password": password},
    )


def test_register_creates_user_and_session(app, client):
    response = register(client)

    assert response.status_code == 302

    user = app.extensions["mongo_client"][DB_NAME].users.find_one({"email": "laura@example.com"})
    assert user["display_name"] == "Laura"
    assert user["password_hash"] != "secreto123"

    sid = client.get_cookie("sid").value
    redis_client = Redis.from_url(REDIS_URL, decode_responses=True, protocol=2)
    assert redis_client.hget(f"sess:{sid}", "user_id") == str(user["_id"])


def test_register_rejects_duplicate_email(app, client):
    register(client)

    response = register(client)

    assert response.status_code == 200
    assert "ya está registrado" in response.get_data(as_text=True)
    assert app.extensions["mongo_client"][DB_NAME].users.count_documents({}) == 1


def test_login_with_wrong_password_does_not_open_session(client):
    register(client)
    client.post("/auth/logout")

    response = client.post(
        "/auth/login", data={"email": "laura@example.com", "password": "incorrecta"}
    )

    assert response.status_code == 200
    assert "incorrectos" in response.get_data(as_text=True)
    assert client.get_cookie("sid") is None


def test_logout_destroys_session(client):
    register(client)
    sid = client.get_cookie("sid").value

    response = client.post("/auth/logout")

    assert response.status_code == 302
    redis_client = Redis.from_url(REDIS_URL, decode_responses=True, protocol=2)
    assert redis_client.exists(f"sess:{sid}") == 0
    assert client.get_cookie("sid") is None


def test_login_redirects_to_next_parameter(client):
    register(client)
    client.post("/auth/logout")

    response = client.post(
        "/auth/login?next=/import",
        data={"email": "laura@example.com", "password": "secreto123"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/import"
