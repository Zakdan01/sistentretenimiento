from math import ceil

from flask import Blueprint, abort, g, jsonify, render_template, request, url_for

from app.catalog.services import (
    PAGE_SIZE,
    average_rating,
    get_title,
    list_genres,
    parse_filters,
    search_titles,
    serialize_title,
)
from app.extensions import get_mongo_db

bp = Blueprint("catalog", __name__)


@bp.get("/")
def index():
    db = get_mongo_db()
    top_rated = list(
        db.titles.find().sort([("external_rating", -1), ("title", 1)]).limit(8)
    )
    recent = list(db.titles.find().sort([("year", -1), ("title", 1)]).limit(8))

    return render_template("index.html", top_rated=top_rated, recent=recent)


@bp.get("/search")
def search():
    db = get_mongo_db()
    documents, total = search_titles(db, request.args)
    filters = parse_filters(request.args)
    total_pages = max(1, ceil(total / PAGE_SIZE))

    def page_url(page: int) -> str:
        args = request.args.to_dict(flat=True)
        args["page"] = page
        return url_for("catalog.search", **args)

    return render_template(
        "search.html",
        titles=documents,
        total=total,
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
    )


@bp.get("/api/search")
def api_search():
    documents, total = search_titles(get_mongo_db(), request.args)
    filters = parse_filters(request.args)

    return jsonify(
        {
            "total": total,
            "page": filters["page"],
            "results": [serialize_title(document) for document in documents],
        }
    )


@bp.get("/api/titles/<title_id>")
def api_title(title_id):
    db = get_mongo_db()
    document = get_title(db, title_id)
    if document is None:
        abort(404)

    payload = serialize_title(document)
    payload["average_rating"] = average_rating(db, document["_id"])
    return jsonify(payload)
