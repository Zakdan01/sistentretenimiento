from app import create_app
from app.extensions import get_mongo_db, get_redis_client


def test_mongo_and_redis_are_reachable():
    app = create_app(
        {
            "TESTING": True,
            "MONGO_DB": "catalogo_test",
            "REDIS_URL": "redis://localhost:6379/15",
        }
    )

    with app.app_context():
        assert get_mongo_db().command("ping")["ok"] == 1
        assert get_redis_client().ping() is True
