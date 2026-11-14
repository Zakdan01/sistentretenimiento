from datetime import datetime, timezone

from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
)
from pymongo.errors import DuplicateKeyError
from werkzeug.security import check_password_hash, generate_password_hash

from app.auth.current_user import COOKIE_NAME
from app.auth.session import create_session, destroy_session
from app.extensions import get_mongo_db, get_redis_client

bp = Blueprint("auth", __name__, url_prefix="/auth")


def _session_ttl(role: str) -> int:
    base_ttl = current_app.config.get("SESSION_TTL_SECONDS")
    if current_app.config.get("TESTING") and base_ttl:
        return base_ttl
    if role == "admin":
        return 60 * 60 * 24 * 7  # 7 días para administradores
    return 60 * 30  # 30 minutos para usuarios comunes por inactividad


def _start_session(response, user_id, role: str = "user"):
    ttl = _session_ttl(role)
    sid = create_session(get_redis_client(), user_id, ttl, role=role)
    response.set_cookie(
        COOKIE_NAME,
        sid,
        max_age=ttl,
        httponly=True,
        samesite="Lax",
    )
    return response


@bp.get("/register")
def register_form():
    return render_template("auth/register.html")


@bp.post("/register")
def register():
    display_name = request.form.get("display_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    error = None
    if not display_name or not email or not password:
        error = "Completá todos los campos."
    elif len(password) < 8:
        error = "La contraseña debe tener al menos 8 caracteres."
    elif get_mongo_db().users.find_one({"email": email}):
        error = "Ese email ya está registrado."

    if error:
        return render_template("auth/register.html", error=error, form=request.form)

    document = {
        "email": email,
        "password_hash": generate_password_hash(password),
        "display_name": display_name,
        "role": "user",
        "avatar_url": None,
        "created_at": datetime.now(timezone.utc),
    }

    try:
        user_id = get_mongo_db().users.insert_one(document).inserted_id
    except DuplicateKeyError:
        return render_template(
            "auth/register.html",
            error="Ese email ya está registrado.",
            form=request.form,
        )

    return _start_session(redirect("/"), user_id, role="user")


@bp.get("/login")
def login_form():
    return render_template("auth/login.html", next=request.args.get("next", ""))


@bp.post("/login")
def login():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    user = get_mongo_db().users.find_one({"email": email})
    if not user or not check_password_hash(user["password_hash"], password):
        return render_template(
            "auth/login.html",
            error="Email o contraseña incorrectos.",
            form=request.form,
            next=request.args.get("next", ""),
        )

    return _start_session(
        redirect(request.args.get("next") or "/"),
        user["_id"],
        role=user.get("role", "user"),
    )


@bp.post("/logout")
def logout():
    destroy_session(get_redis_client(), request.cookies.get(COOKIE_NAME))
    response = redirect("/")
    response.delete_cookie(COOKIE_NAME)
    return response
