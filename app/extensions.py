from flask import current_app
from pymongo import MongoClient
from redis import Redis


def get_mongo_client() -> MongoClient:
    if "mongo_client" not in current_app.extensions:
        current_app.extensions["mongo_client"] = MongoClient(
            current_app.config["MONGO_URI"],
            serverSelectionTimeoutMS=2000,
        )
    return current_app.extensions["mongo_client"]


def get_mongo_db():
    return get_mongo_client()[current_app.config["MONGO_DB"]]


def get_redis_client() -> Redis:
    if "redis_client" not in current_app.extensions:
        current_app.extensions["redis_client"] = Redis.from_url(
            current_app.config["REDIS_URL"],
            decode_responses=True,
            socket_connect_timeout=2,
            # Redis 5.0 (build de Windows) no soporta RESP3/HELLO.
            protocol=2,
        )
    return current_app.extensions["redis_client"]
