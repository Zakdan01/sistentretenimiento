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

from app.auth.current_user import admin_required, login_required
from app.cache import (
    EXTERNAL_TTL_SECONDS,
    SEARCH_TTL_SECONDS,
    TITLE_TTL_SECONDS,
    add_recent_view,
    api_cache_key,
    get_json,
    get_recent_views,
    invalidate_api,
    invalidate_search,
    invalidate_titles,
    is_rate_limited,
    like_count,
    popular_favorites_ids,
    popular_title_ids,
    popular_with_scores,
    register_view,
    search_cache_key,
    set_json,
    title_cache_key,
    view_count,
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
    recent_titles,
    search_titles,
    serialize_title,
    titles_by_ids,
    top_rated_titles,
)
from app.extensions import get_mongo_db, get_redis_client

bp = Blueprint("catalog", __name__)


def _namespace() -> str:
    return current_app.config["MONGO_DB"]


CATALOG_PAGE_SIZE = 20


def _search_payload(db, params) -> dict:
    """Cache-aside de búsquedas: Redis primero, Mongo si no hay entrada."""
    redis_client = get_redis_client()
    key = search_cache_key(params, namespace=_namespace())

    cached = get_json(redis_client, key)
    if cached is not None:
        return cached

    documents, total = search_titles(db, params, page_size=CATALOG_PAGE_SIZE)
    payload = {
        "total": total,
        "page": parse_filters(params)["page"],
        "results": [serialize_title(document) for document in documents],
    }
    set_json(redis_client, key, payload, SEARCH_TTL_SECONDS)
    return payload


def _trending_titles(db) -> list[dict]:
    raw_ids = popular_title_ids(get_redis_client())
    if not raw_ids:
        return []

    documents = titles_by_ids(db, raw_ids)
    ordered = []
    for raw_id in raw_ids:
        try:
            object_id = ObjectId(raw_id)
        except (InvalidId, TypeError):
            continue
        document = documents.get(object_id)
        if document is not None:
            ordered.append(document)
    return ordered


def _top_favorites_titles(db) -> list[dict]:
    raw_ids = popular_favorites_ids(get_redis_client())
    if not raw_ids:
        return []

    documents = titles_by_ids(db, raw_ids)
    ordered = []
    for raw_id in raw_ids:
        try:
            object_id = ObjectId(raw_id)
        except (InvalidId, TypeError):
            continue
        document = documents.get(object_id)
        if document is not None:
            ordered.append(document)
    return ordered


@bp.get("/")
def index():
    db = get_mongo_db()
    recent_viewed = []
    if g.get("user"):
        recent_ids = get_recent_views(get_redis_client(), g.user["_id"])
        if recent_ids:
            docs_map = titles_by_ids(db, recent_ids)
            for raw_id in recent_ids:
                try:
                    oid = ObjectId(raw_id)
                except (InvalidId, TypeError):
                    continue
                doc = docs_map.get(oid)
                if doc is not None:
                    recent_viewed.append(doc)

    return render_template(
        "index.html",
        top_rated=top_rated_titles(db),
        recent=recent_titles(db),
        trending=_trending_titles(db),
        favorites_ranking=_top_favorites_titles(db),
        recent_viewed=recent_viewed,
    )


@bp.get("/search")
def search():
    db = get_mongo_db()
    # Rate Limiting con Redis para proteger el motor de búsqueda
    if not current_app.config.get("TESTING"):
        client_ip = request.remote_addr or "127.0.0.1"
        if is_rate_limited(get_redis_client(), f"search:{client_ip}", limit=40, window=60):
            return render_template(
                "search.html",
                titles=[],
                total=0,
                filters=parse_filters(request.args),
                genres=list_genres(db),
                total_pages=1,
                error="⚡ Límite de búsquedas por minuto alcanzado (Protección anti-spam con Redis). Espera un minuto.",
            ), 429

    payload = _search_payload(db, request.args)
    filters = parse_filters(request.args)
    total_pages = max(1, ceil(payload["total"] / CATALOG_PAGE_SIZE))

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

    views = register_view(get_redis_client(), document["_id"])

    entry = None
    if g.get("user"):
        add_recent_view(get_redis_client(), g.user["_id"], document["_id"])
        entry = db.library_entries.find_one(
            {"user_id": g.user["_id"], "title_id": document["_id"]}
        )

    return render_template(
        "detail.html",
        title=document,
        ratings=average_rating(db, document["_id"]),
        entry=entry,
        likes=like_count(get_redis_client(), document["_id"]),
        views=views,
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


@bp.get("/api/popular")
def api_popular():
    """Ranking de títulos más vistos, alimentado por `rank:popular` en Redis."""
    db = get_mongo_db()
    entries = popular_with_scores(get_redis_client())

    object_ids = []
    scores = {}
    for raw_id, score in entries:
        try:
            object_id = ObjectId(raw_id)
        except (InvalidId, TypeError):
            continue
        object_ids.append(object_id)
        scores[object_id] = int(score)

    documents = titles_by_ids(db, object_ids)

    results = []
    for object_id in object_ids:
        document = documents.get(object_id)
        if document is None:
            continue
        payload = serialize_title(document)
        payload["views"] = scores[object_id]
        results.append(payload)

    return jsonify(results=results)


def _search_external_uncached(query: str, source: str) -> list[dict]:
    """Busca en la API externa elegida. El resultado no se guarda todavía."""
    if source == "tmdb":
        return search_tmdb(
            query,
            api_key=current_app.config["TMDB_API_KEY"],
            base_url=current_app.config["TMDB_BASE_URL"],
        )
    return search_jikan(query, base_url=current_app.config["JIKAN_BASE_URL"])


def _search_external(query: str, source: str) -> list[dict]:
    """Cache-aside de búsquedas externas para no repetir llamadas a la API."""
    redis_client = get_redis_client()
    key = api_cache_key(source, query, namespace=_namespace())
    cached = get_json(redis_client, key)
    if cached is not None:
        return cached

    results = _search_external_uncached(query, source)
    set_json(redis_client, key, results, EXTERNAL_TTL_SECONDS)
    return results


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
@admin_required
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
@admin_required
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
    invalidate_api(redis_client)

    return redirect(url_for("catalog.detail", title_id=document["_id"]))
