import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
from bson import ObjectId
from pymongo import MongoClient

from mongodb.seed.load_seed import load_titles

BASE_DIR = Path(__file__).resolve().parent.parent
INIT_SCRIPTS = [
    BASE_DIR / "mongodb" / "init" / "01_collections.js",
    BASE_DIR / "mongodb" / "init" / "02_indexes.js",
]
SEED_PATH = BASE_DIR / "mongodb" / "seed" / "titles.json"
AGGREGATIONS_DIR = BASE_DIR / "mongodb" / "aggregations"
QUERIES_DIR = BASE_DIR / "mongodb" / "queries"
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "catalogo_test_reports"
URI = f"{MONGO_URI}/{DB_NAME}"


@pytest.fixture(scope="module")
def reported_db():
    client = MongoClient(MONGO_URI)
    client.drop_database(DB_NAME)

    for script in INIT_SCRIPTS:
        subprocess.run(
            ["mongosh", URI, "--quiet", "--file", str(script)],
            check=True,
            capture_output=True,
            text=True,
        )

    db = client[DB_NAME]
    load_titles(db, SEED_PATH)

    now = datetime.now(timezone.utc)
    user_id = db.users.insert_one(
        {
            "email": "laura@example.com",
            "password_hash": "x",
            "display_name": "Laura",
            "avatar_url": None,
            "created_at": now,
        }
    ).inserted_id

    dark = db.titles.find_one({"title": "Dark"})
    inception = db.titles.find_one({"title": "Inception"})

    db.library_entries.insert_many(
        [
            {
                "user_id": user_id,
                "title_id": dark["_id"],
                "status": "watching",
                "favorite": True,
                "rating": 9,
                "progress": {"season": 1, "episode": 3},
                "notes": None,
                "created_at": now,
                "updated_at": now,
            },
            {
                "user_id": user_id,
                "title_id": inception["_id"],
                "status": "watched",
                "favorite": False,
                "rating": 8,
                "progress": None,
                "notes": None,
                "created_at": now,
                "updated_at": now,
            },
        ]
    )

    yield db

    client.drop_database(DB_NAME)


def run_js(path: Path) -> str:
    result = subprocess.run(
        ["mongosh", URI, "--quiet", "--file", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def test_every_aggregation_is_valid_and_returns_data(reported_db):
    scripts = sorted(AGGREGATIONS_DIR.glob("*.js"))
    assert scripts, "faltan las agregaciones del informe"

    for script in scripts:
        output = run_js(script)
        assert output.strip(), f"{script.name} no imprimió resultados"
        assert "Error" not in output, f"{script.name} falló: {output}"


def test_top_genres_reports_drama_first(reported_db):
    output = run_js(AGGREGATIONS_DIR / "01_top_genres.js")
    payload = json.loads(output)

    assert payload[0]["genre"] == "Drama"
    assert payload[0]["titles"] >= 8


def test_library_by_status_groups_user_entries(reported_db):
    output = run_js(AGGREGATIONS_DIR / "02_library_by_status.js")
    payload = json.loads(output)

    assert payload[0]["user"] == "Laura"
    assert payload[0]["total"] == 2
    statuses = {row["status"]: row["total"] for row in payload[0]["statuses"]}
    assert statuses == {"watching": 1, "watched": 1}


def test_catalog_health_counts_types(reported_db):
    output = run_js(AGGREGATIONS_DIR / "03_catalog_health.js")
    payload = {row["type"]: row for row in json.loads(output)}

    assert payload["movie"]["titles"] == 4
    assert payload["series"]["titles"] == 5
    assert payload["anime"]["titles"] == 7
    assert payload["anime"]["episodes"] == 285


def test_top_rated_by_type_returns_three_per_type(reported_db):
    output = run_js(AGGREGATIONS_DIR / "05_top_rated_by_type.js")
    payload = json.loads(output)

    positions = {(row["type"], row["position"]) for row in payload}
    assert ("anime", 1) in positions
    assert all(position <= 3 for _type, position in positions)
    per_type = {}
    for row in payload:
        per_type[row["type"]] = per_type.get(row["type"], 0) + 1
    assert all(total <= 4 for total in per_type.values())


def test_report_queries_produce_explain_stats(reported_db):
    output = run_js(QUERIES_DIR / "report_queries.js")

    assert "texto_libre" in output
    assert "totalDocsExamined" in output
    assert "executionTimeMillis" in output


def test_sizing_reports_storage_for_each_collection(reported_db):
    output = run_js(QUERIES_DIR / "sizing.js")
    payload = {row["collection"]: row for row in json.loads(output)}

    assert payload["titles"]["documents"] == 16
    assert payload["titles"]["storageSize"] > 0
    assert "library_entries" in payload
    assert "users" in payload
