from flask import Flask, g, jsonify

from app.auth.current_user import load_logged_in_user
from app.auth.profile import bp as profile_bp
from app.auth.routes import bp as auth_bp
from app.catalog.routes import bp as catalog_bp
from app.library.routes import bp as library_bp


def create_app(config_overrides: dict | None = None) -> Flask:
    """Application factory for the virtual library."""
    app = Flask(__name__)
    app.config.from_object("app.config.Config")

    if config_overrides:
        app.config.update(config_overrides)

    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(catalog_bp)
    app.register_blueprint(library_bp)
    app.before_request(load_logged_in_user)

    @app.context_processor
    def inject_current_user():
        return {"current_user": g.get("user")}

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    return app

