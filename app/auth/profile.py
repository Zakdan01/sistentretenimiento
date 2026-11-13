from flask import Blueprint, g, render_template

from app.auth.current_user import login_required
from app.extensions import get_mongo_db
from app.library.services import profile_stats

bp = Blueprint("profile", __name__)


@bp.get("/profile")
@login_required
def show():
    stats = profile_stats(get_mongo_db(), g.user["_id"])
    return render_template("profile.html", stats=stats)
