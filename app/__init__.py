from flask import Flask, jsonify


def create_app(config_overrides: dict | None = None) -> Flask:
    """Application factory for the virtual library."""
    app = Flask(__name__)
    app.config.from_object("app.config.Config")

    if config_overrides:
        app.config.update(config_overrides)

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    return app
