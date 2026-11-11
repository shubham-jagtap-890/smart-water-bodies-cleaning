import os
from pathlib import Path

# Reads backend/.env (KEY=value per line; "# comments" are ignored, also after a value)
_env = Path(__file__).parent / ".env"
if _env.exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            _v = _v.split(" #", 1)[0].strip().strip('"').strip("'")
            os.environ.setdefault(_k.strip(), _v)

from flask import Flask, jsonify, send_from_directory
from models import db
from routes import api
from seed import seed_if_empty


def create_app():
    app = Flask(__name__, static_folder=None)
    uri = os.getenv("DATABASE_URL", "sqlite:///water.db")
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql+psycopg2://", 1)
    elif uri.startswith("postgresql://"):
        uri = uri.replace("postgresql://", "postgresql+psycopg2://", 1)
    elif uri.startswith("postgresql+psycopg://"):
        uri = uri.replace("postgresql+psycopg://", "postgresql+psycopg2://", 1)
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-only-change-me"),
        SQLALCHEMY_DATABASE_URI=uri,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True, "pool_recycle": 280},  # Neon sleeps when idle
        MAX_CONTENT_LENGTH=6 * 1024 * 1024,
        RESPONSE_HOURS=float(os.getenv("RESPONSE_HOURS", "48")),
        GEO_TOLERANCE_M=float(os.getenv("GEO_TOLERANCE_M", "300")),
        COMPLAINT_GEO_TOLERANCE_M=float(os.getenv("COMPLAINT_GEO_TOLERANCE_M", "1000")),
        CRON_KEY=os.getenv("CRON_KEY", "change-me"),
        OPENWEATHER_KEY=os.getenv("OPENWEATHER_API_KEY", ""),
    )
    db.init_app(app)
    app.register_blueprint(api)

    with app.app_context():
        db.create_all()
        if os.getenv("SEED_DEMO", "true").lower() == "true":
            seed_if_empty()

    dist = os.getenv("STATIC_DIR") or os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

    @app.errorhandler(413)
    def too_big(_):
        return jsonify(error="Upload is too large"), 413

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def spa(path):
        if path.startswith("api/"):
            return jsonify(error="Not found"), 404
        full = os.path.join(dist, path)
        if path and os.path.isfile(full):
            return send_from_directory(dist, path)
        if os.path.isfile(os.path.join(dist, "index.html")):
            return send_from_directory(dist, "index.html")
        return jsonify(message="API is running. Build the frontend (cd frontend && npm run build)."), 200

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
