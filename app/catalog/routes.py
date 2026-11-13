from math import ceil

from bson import ObjectId
from bson.errors import InvalidId
from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from app.auth.current_user import login_required
from app.cache import (
    SEARCH_TTL_SECONDS,
    TITLE_TTL_SECONDS,
    get_json,
    invalidate_search,
    invalidate_titles,
    like_count,
    popular_title_ids,
    register_view,
    search_cache_key,
    set_json,
    title_cache_key,
)
from app.catalog.importer import import_title
from app.catalog.providers import (
    ProviderError,
    fetch_jikan,
    fetch_tmdb,
    search_jikan,
    search_tmdb,
)
from app.catalog.services import (
    PAGE_SIZE,
    average_rating,
    get_title,
    list_genres,
    parse_filters,
    search_titles,
    serialize_title,
)
from app.extensions import get_mongo_db, get_redis_client

bp = Blueprint("catalog", __name__)


def _namespace() -> str:
    return current_app.config["MONGO_DB"]


def _search_payload(db, params) -> dict:
    """Cache-aside de búsquedas: Redis primero, Mongo si no hay entrada."""
    redis_client = get_redis_client()
    key = search_cache_key(params, namespace=_namespace())

    cached = get_json(redis_client, key)
    if cached is not None:
        return cached

    documents, total = search_titles(db, params)
    payload = {
        "total": total,
        "page": parse_filters(params)["page"],
        "results": [serialize_title(document) for document in documents],
    }
    set_json(redis_client, key, payload, SEARCH_TTL_SECONDS)
    return payload


def _trending_titles(db) -> list[dict]:
    object_ids = []
    for raw_id in popular_title_ids(get_redis_client()):
        try:
            object_ids.append(ObjectId(raw_id))
        except (InvalidId, TypeError):
            continue

    if not object_ids:
        return []

    documents = {
        document["_id"]: document
        for document in db.titles.find({"_id": {"$in": object_ids}})
    }
    return [documents[object_id] for object_id in object_ids if object_id in documents]


@bp.get("/")
def index():
    db = get_mongo_db()
    top_rated = list(
        db.titles.find().sort([("external_rating", -1), ("title", 1)]).limit(8)
    )
    recent = list(db.titles.find().sort([("year", -1), ("title", 1)]).limit(8))

    return render_template(
        "index.html",
        top_rated=top_rated,
        recent=recent,
        trending=_trending_titles(db),
    )


@bp.get("/search")
def search():
    db = get_mongo_db()
    payload = _search_payload(db, request.args)
    filters = parse_filters(request.args)
    total_pages = max(1, ceil(payload["total"] / PAGE_SIZE))

    def page_url(page: int) -> str:
        args = request.args.to_dict(flat=True)
        args["page"] = page
        return url_for("catalog.search", **args)

    return render_template(
        "search.html",
        titles=payload["results"],
        total=payload["total"],
        filters=filters,
        genres=list_genres(db),
        total_pages=total_pages,
        previous_url=page_url(filters["page"] - 1) if filters["page"] > 1 else None,
        next_url=page_url(filters["page"] + 1)
        if filters["page"] < total_pages
        else None,
    )


@bp.get("/titles/<title_id>")
def detail(title_id):
    db = get_mongo_db()
    document = get_title(db, title_id)
    if document is None:
        abort(404)

    register_view(get_redis_client(), document["_id"])

    entry = None
    if g.get("user"):
        entry = db.library_entries.find_one(
            {"user_id": g.user["_id"], "title_id": document["_id"]}
        )

    return render_template(
        "detail.html",
        title=document,
        ratings=average_rating(db, document["_id"]),
        entry=entry,
        likes=like_count(get_redis_client(), document["_id"]),
    )


@bp.get("/api/search")
def api_search():
    return jsonify(_search_payload(get_mongo_db(), request.args))


@bp.get("/api/titles/<title_id>")
def api_title(title_id):
    db = get_mongo_db()
    document = get_title(db, title_id)
    if document is None:
        abort(404)

    redis_client = get_redis_client()
    key = title_cache_key(document["_id"], namespace=_namespace())
    cached = get_json(redis_client, key)
    if cached is not None:
        return jsonify(cached)

    payload = serialize_title(document)
    payload["average_rating"] = average_rating(db, document["_id"])
    set_json(redis_client, key, payload, TITLE_TTL_SECONDS)
    return jsonify(payload)


def _search_external(query: str, source: str) -> list[dict]:
    """Busca en la API externa elegida. El resultado no se guarda todavía."""
    if source == "tmdb":
        return search_tmdb(
            query,
            api_key=current_app.config["TMDB_API_KEY"],
            base_url=current_app.config["TMDB_BASE_URL"],
        )
    return search_jikan(query, base_url=current_app.config["JIKAN_BASE_URL"])


def _fetch_external(source: str, external_id: str, media_type: str) -> dict:
    if source == "tmdb":
        return fetch_tmdb(
            media_type if media_type in ("movie", "tv") else "movie",
            int(external_id),
            api_key=current_app.config["TMDB_API_KEY"],
            base_url=current_app.config["TMDB_BASE_URL"],
        )
    return fetch_jikan(int(external_id), base_url=current_app.config["JIKAN_BASE_URL"])


@bp.get("/import")
@login_required
def import_search():
    query = request.args.get("q", "").strip()
    source = request.args.get("source", "jikan")
    if source not in ("jikan", "tmdb"):
        source = "jikan"

    results = []
    error = None
    if query:
        try:
            results = _search_external(query, source)
        except ProviderError as exc:
            error = str(exc)

    return render_template(
        "import.html",
        query=query,
        source=source,
        results=results,
        error=error,
    )


@bp.post("/import")
@login_required
def import_create():
    source = request.form.get("source", "jikan")
    external_id = request.form.get("external_id", "")
    media_type = request.form.get("media_type", "movie")

    try:
        details = _fetch_external(source, external_id, media_type)
        document, _created = import_title(get_mongo_db(), details)
    except (ProviderError, ValueError, KeyError) as exc:
        return (
            render_template(
                "import.html",
                query="",
                source=source,
                results=[],
                error=f"No se pudo importar el título: {exc}",
            ),
            400,
        )

    redis_client = get_redis_client()
    invalidate_titles(redis_client)
    invalidate_search(redis_client)

    return redirect(url_for("catalog.detail", title_id=document["_id"]))
