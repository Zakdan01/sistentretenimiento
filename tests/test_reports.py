import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.support import (
    BASE_DIR,
    MONGO_URI,
    find_title,
    make_user,
    prepare_database,
    seed_catalog,
    teardown,
)

DB_NAME = "catalogo_test_reports"
URI = f"{MONGO_URI}/{DB_NAME}"
AGGREGATIONS_DIR = BASE_DIR / "mongodb" / "aggregations"
QUERIES_DIR = BASE_DIR / "mongodb" / "queries"


@pytest.fixture(scope="module")
def reported_db():
    client, db = prepare_database(DB_NAME)
    seed_catalog(db)

    now = datetime.now(timezone.utc)
    user = make_user(db, display_name="Laura")
    dark = find_title(db, "Dark")
    inception = find_title(db, "Inception")

    db.library_entries.insert_many(
        [
            {
                "user_id": user["_id"],
                "title_id": dark["_id"],
                "title_type": "series",
                "status": "watching",
                "favorite": True,
                "rating": 9,
                "progress": {"season": 1, "episode": 3},
                "notes": None,
                "created_at": now,
                "updated_at": now,
            },
            {
                "user_id": user["_id"],
                "title_id": inception["_id"],
                "title_type": "movie",
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

    teardown(client, DB_NAME)


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
    assert payload[0]["titles"] == 7
    assert payload[0]["avg_rating"] > 8


def test_library_by_status_groups_user_entries(reported_db):
    output = run_js(AGGREGATIONS_DIR / "02_library_by_status.js")
    payload = json.loads(output)

    assert payload[0]["user"] == "Laura"
    assert payload[0]["total"] == 2
    statuses = {row["status"]: row["total"] for row in payload[0]["statuses"]}
    assert statuses == {"watching": 1, "watched": 1}


def test_catalog_health_counts_the_three_collections(reported_db):
    output = run_js(AGGREGATIONS_DIR / "03_catalog_health.js")
    payload = {row["type"]: row for row in json.loads(output)}

    assert payload["movie"]["titles"] == 5
    assert payload["series"]["titles"] == 5
    assert payload["anime"]["titles"] == 6
    assert payload["movie"]["with_image"] == 5
    assert payload["anime"]["avg_year"] == 2009


def test_user_activity_summarizes_entries(reported_db):
    output = run_js(AGGREGATIONS_DIR / "04_user_activity.js")
    payload = json.loads(output)

    assert payload[0]["user"] == "Laura"
    assert payload[0]["entries"] == 2
    assert payload[0]["favorites"] == 1
    assert payload[0]["avg_rating"] == 8.5


def test_top_rated_by_type_returns_three_per_type(reported_db):
    output = run_js(AGGREGATIONS_DIR / "05_top_rated_by_type.js")
    payload = json.loads(output)

    positions = {(row["type"], row["position"]) for row in payload}
    assert positions == {
        (title_type, position)
        for title_type in ("movie", "series", "anime")
        for position in (1, 2, 3)
    }
    top_anime = next(
        row for row in payload if row["type"] == "anime" and row["position"] == 1
    )
    assert top_anime["title"] == "Fullmetal Alchemist: Brotherhood"


def test_report_queries_produce_explain_stats(reported_db):
    output = run_js(QUERIES_DIR / "report_queries.js")

    assert "texto_libre" in output
    assert "filtro_anio" in output
    assert "biblioteca_usuario" in output
    assert "totalDocsExamined" in output
    assert "executionTimeMillis" in output


def test_sizing_reports_storage_for_each_collection(reported_db):
    output = run_js(QUERIES_DIR / "sizing.js")
    payload = {row["collection"]: row for row in json.loads(output)}

    assert payload["movies"]["documents"] == 5
    assert payload["series"]["documents"] == 5
    assert payload["animes"]["documents"] == 6
    assert payload["users"]["documents"] == 1
    assert payload["library_entries"]["documents"] == 2
    assert payload["movies"]["storageSize"] > 0
