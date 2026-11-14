from bson import ObjectId
from bson.errors import InvalidId
from flask import abort, g, redirect, request, url_for

from app.auth.session import load_session, touch_session
from app.cache import record_active_user
from app.extensions import get_mongo_db, get_redis_client

COOKIE_NAME = "sid"


def login_required(view):
    """Redirige al login conservando la ruta pedida."""

    def wrapped(*args, **kwargs):
        if not g.get("user"):
            return redirect(url_for("auth.login", next=request.full_path))
        return view(*args, **kwargs)

    wrapped.__name__ = view.__name__
    return wrapped


def admin_required(view):
    """Exige sesión iniciada y rol `admin`."""

    def wrapped(*args, **kwargs):
        if not g.get("user"):
            return redirect(url_for("auth.login", next=request.full_path))
        if g.user.get("role") != "admin":
            abort(403)
        return view(*args, **kwargs)

    wrapped.__name__ = view.__name__
    return wrapped


def load_logged_in_user() -> None:
    sid = request.cookies.get(COOKIE_NAME)
    redis_client = get_redis_client()
    user_id = load_session(redis_client, sid) if sid else None

    if not user_id:
        g.user = None
        record_active_user(redis_client, request.remote_addr or "guest")
        return

    try:
        g.user = get_mongo_db().users.find_one({"_id": ObjectId(user_id)})
        if g.user:
            # Sesión activa: registra presencia en vivo con Redis ZSET
            record_active_user(redis_client, str(g.user["_id"]))
            # Si es usuario común, renueva su tiempo por inactividad (Sliding Window de 30 min)
            if g.user.get("role") == "user":
                touch_session(redis_client, sid, 1800)
    except InvalidId:
        g.user = None
