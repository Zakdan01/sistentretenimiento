from math import ceil

from flask import (
    Blueprint,
    abort,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from pymongo.errors import DuplicateKeyError

from app.admin.services import (
    PAGE_SIZE,
    catalog_health_report,
    create_title,
    create_user,
    dashboard_stats,
    delete_title,
    delete_user,
    library_by_status_report,
    list_users,
    parse_title_form,
    parse_user_form,
    top_genres_report,
    top_rated_by_type_report,
    update_title,
    update_user,
    user_activity_report,
)
from app.auth.current_user import admin_required
from app.cache import invalidate_api, invalidate_search, invalidate_titles
from app.catalog.services import (
    TYPE_COLLECTIONS,
    get_title,
    list_genres,
    parse_filters,
    search_titles,
)
from app.extensions import get_mongo_db, get_redis_client

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _invalidate() -> None:
    redis_client = get_redis_client()
    invalidate_search(redis_client)
    invalidate_titles(redis_client)
    invalidate_api(redis_client)


def _page_url(page: int) -> str:
    args = request.args.to_dict(flat=True)
    args["page"] = page
    return url_for("admin.titles", **args)


@bp.get("")
@admin_required
def dashboard():
    db = get_mongo_db()
    return render_template(
        "admin/dashboard.html",
        stats=dashboard_stats(db),
        genres=top_genres_report(db, limit=6),
        recent_users=list_users(db)[0][:5],
    )


@bp.get("/titles")
@admin_required
def titles():
    db = get_mongo_db()
    documents, total = search_titles(db, request.args, page_size=PAGE_SIZE)
    filters = parse_filters(request.args)
    total_pages = max(1, ceil(total / PAGE_SIZE))

    return render_template(
        "admin/titles.html",
        titles=documents,
        total=total,
        filters=filters,
        genres=list_genres(db),
        total_pages=total_pages,
        previous_url=_page_url(filters["page"] - 1) if filters["page"] > 1 else None,
        next_url=(
            _page_url(filters["page"] + 1)
            if filters["page"] < total_pages
            else None
        ),
    )


@bp.route("/titles/new", methods=["GET", "POST"])
@admin_required
def title_create():
    error = None
    if request.method == "POST":
        data, error = parse_title_form(request.form)
        if data and not error:
            try:
                create_title(get_mongo_db(), data)
            except DuplicateKeyError:
                error = "Ya existe un título con esa fuente e id externo."
            else:
                _invalidate()
                return redirect(url_for("admin.titles"))

    return render_template(
        "admin/title_form.html",
        title=None,
        data=request.form if request.method == "POST" else {},
        error=error,
        action_url=url_for("admin.title_create"),
        title_types=TYPE_COLLECTIONS,
        genres=list_genres(get_mongo_db()),
    )


@bp.route("/titles/<title_id>/edit", methods=["GET", "POST"])
@admin_required
def title_edit(title_id):
    db = get_mongo_db()
    document = get_title(db, title_id)
    if document is None:
        abort(404)

    error = None
    if request.method == "POST":
        data, error = parse_title_form(request.form)
        if data and not error:
            data["type"] = document["type"]
            try:
                update_title(db, document["type"], document["_id"], data)
            except DuplicateKeyError:
                error = "Ya existe un título con esa fuente e id externo."
            else:
                _invalidate()
                return redirect(url_for("admin.titles"))
        form_data = request.form
    else:
        form_data = {
            "type": document["type"],
            "title": document["title"],
            "synopsis": document.get("synopsis", ""),
            "year": document.get("year"),
            "genres": ", ".join(document.get("genres", [])),
            "poster_url": document.get("poster_url"),
            "external_rating": document.get("external_rating"),
            "source": (document.get("external") or {}).get("source", "manual"),
            "external_id": (document.get("external") or {}).get("id", ""),
        }

    return render_template(
        "admin/title_form.html",
        title=document,
        data=form_data,
        error=error,
        action_url=url_for("admin.title_edit", title_id=document["_id"]),
        title_types=TYPE_COLLECTIONS,
        genres=list_genres(db),
    )


@bp.post("/titles/<title_id>/delete")
@admin_required
def title_delete(title_id):
    db = get_mongo_db()
    document = get_title(db, title_id)
    if document is None:
        abort(404)

    delete_title(db, document["type"], document["_id"])
    _invalidate()
    return redirect(url_for("admin.titles"))


@bp.get("/users")
@admin_required
def users():
    page = max(1, int(request.args.get("page", 1) or 1))
    documents, total = list_users(get_mongo_db(), page)
    total_pages = max(1, ceil(total / PAGE_SIZE))

    return render_template(
        "admin/users.html",
        users=documents,
        total=total,
        page=page,
        total_pages=total_pages,
        previous_url=url_for("admin.users", page=page - 1) if page > 1 else None,
        next_url=url_for("admin.users", page=page + 1) if page < total_pages else None,
    )


@bp.route("/users/new", methods=["GET", "POST"])
@admin_required
def user_create():
    error = None
    if request.method == "POST":
        data, error = parse_user_form(request.form, require_password=True)
        if data and not error:
            try:
                create_user(get_mongo_db(), data)
            except DuplicateKeyError:
                error = "Ese email ya está registrado."
            else:
                return redirect(url_for("admin.users"))

    return render_template(
        "admin/user_form.html",
        user=None,
        data=request.form if request.method == "POST" else {},
        error=error,
        action_url=url_for("admin.user_create"),
    )


@bp.route("/users/<user_id>/edit", methods=["GET", "POST"])
@admin_required
def user_edit(user_id):
    db = get_mongo_db()
    from bson import ObjectId
    from bson.errors import InvalidId

    try:
        user = db.users.find_one({"_id": ObjectId(str(user_id))})
    except (InvalidId, TypeError):
        user = None
    if user is None:
        abort(404)

    error = None
    if request.method == "POST":
        data, error = parse_user_form(request.form, require_password=False)
        if data and not error:
            if user["role"] == "admin" and data["role"] != "admin":
                if db.users.count_documents({"role": "admin"}) <= 1:
                    error = "No podés quitar el rol al último administrador."
            if not error:
                try:
                    update_user(db, user["_id"], data)
                except DuplicateKeyError:
                    error = "Ese email ya está registrado."
                else:
                    return redirect(url_for("admin.users"))
        form_data = request.form
    else:
        form_data = user

    return render_template(
        "admin/user_form.html",
        user=user,
        data=form_data,
        error=error,
        action_url=url_for("admin.user_edit", user_id=user["_id"]),
    )


@bp.post("/users/<user_id>/delete")
@admin_required
def user_delete(user_id):
    db = get_mongo_db()
    from bson import ObjectId
    from bson.errors import InvalidId

    try:
        user = db.users.find_one({"_id": ObjectId(str(user_id))})
    except (InvalidId, TypeError):
        user = None
    if user is None:
        abort(404)

    if user["_id"] == g.user["_id"]:
        abort(400)

    if user["role"] == "admin" and db.users.count_documents({"role": "admin"}) <= 1:
        abort(400)

    delete_user(db, user["_id"])
    return redirect(url_for("admin.users"))


@bp.get("/reports")
@admin_required
def reports():
    db = get_mongo_db()
    return render_template(
        "admin/reports.html",
        genres=top_genres_report(db, limit=15),
        library=library_by_status_report(db),
        health=catalog_health_report(db),
        top_rated=top_rated_by_type_report(db, per_type=5),
        activity=user_activity_report(db),
    )
