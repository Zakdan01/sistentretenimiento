from flask import Blueprint, abort, g, redirect, render_template, request, url_for

from app.auth.current_user import login_required
from app.cache import invalidate_titles, sync_favorites_rank, sync_likes
from app.catalog.services import average_rating, get_title
from app.extensions import get_mongo_db, get_redis_client
from app.library.services import (
    STATUSES,
    count_by_status,
    delete_entry,
    get_entry,
    list_entries,
    parse_entry_form,
    upsert_entry,
)

bp = Blueprint("library", __name__, url_prefix="/library")


def _sync_title_likes(db, title_id) -> int:
    total = db.library_entries.count_documents(
        {"title_id": title_id, "favorite": True}
    )
    redis_client = get_redis_client()
    sync_favorites_rank(redis_client, title_id, total)
    return sync_likes(redis_client, title_id, total)


@bp.get("")
@login_required
def index():
    db = get_mongo_db()
    status = request.args.get("status", "")
    if status not in STATUSES:
        status = None

    entries = list_entries(db, g.user["_id"], status)

    return render_template(
        "library/index.html",
        entries=entries,
        active_status=status or "",
        counts=count_by_status(db, g.user["_id"]),
    )


@bp.post("/<title_id>")
@login_required
def save(title_id):
    db = get_mongo_db()
    title = get_title(db, title_id)
    if title is None:
        abort(404)

    entry = get_entry(db, g.user["_id"], title["_id"])
    data, error = parse_entry_form(request.form)
    if error:
        return (
            render_template(
                "detail.html",
                title=title,
                ratings=average_rating(db, title["_id"]),
                entry=entry,
                form_error=error,
            ),
            400,
        )

    upsert_entry(db, g.user["_id"], title["_id"], title["type"], data)
    _sync_title_likes(db, title["_id"])
    invalidate_titles(get_redis_client())
    return redirect(url_for("catalog.detail", title_id=title["_id"], _anchor="library"))


@bp.post("/<title_id>/delete")
@login_required
def delete(title_id):
    db = get_mongo_db()
    title = get_title(db, title_id)
    if title is None:
        abort(404)

    delete_entry(db, g.user["_id"], title["_id"])
    _sync_title_likes(db, title["_id"])
    invalidate_titles(get_redis_client())
    return redirect(url_for("library.index"))
