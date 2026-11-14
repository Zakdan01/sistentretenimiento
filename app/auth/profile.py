from flask import Blueprint, g, render_template

from app.auth.current_user import login_required
from app.extensions import get_mongo_db
from app.library.services import profile_stats, user_top_favorites

bp = Blueprint("profile", __name__)


@bp.get("/profile")
@login_required
def show():
    db = get_mongo_db()
    stats = profile_stats(db, g.user["_id"])
    top_favorites = user_top_favorites(db, g.user["_id"])
    return render_template(
        "profile.html",
        stats=stats,
        top_favorites=top_favorites,
    )
