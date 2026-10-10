"""The Flask application: JSON API plus the built web client."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from flask import Flask, Response, abort, g, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from . import __version__
from .config import Settings
from .security import FONT_CSS, RateLimiter, security_headers
from .service import Platform, ServiceError

log = logging.getLogger("joinery.http")
FONT_LINK = (f'<link rel="preconnect" href="{FONT_CSS}">\n    <link rel="stylesheet" href="{FONT_CSS}/css2?'
             'family=Atkinson+Hyperlegible+Mono:wght@400;600&family=Atkinson+Hyperlegible+Next:ital,wght@0,400;'
             '0,600;0,750;1,400&display=swap">')
MISSING_CLIENT = """<!doctype html><html lang="en"><meta charset="utf-8"><title>Joinery</title>
<body style="font-family:system-ui;max-width:40rem;margin:4rem auto;line-height:1.5">
<h1>The web client has not been built yet</h1><p>Run <code>npm install</code> and <code>npm run build</code>,
then reload this page. The API is already available under <code>/api</code>.</p></body></html>"""


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or Settings.from_env()
    platform = Platform(settings)
    limiter = RateLimiter(settings.rate_limit)
    headers = security_headers(settings.web_fonts)
    web_dir = Path(settings.web_dir)

    app = Flask(__name__, static_folder=None)
    app.config.update(MAX_CONTENT_LENGTH=256 * 1024)
    app.json.sort_keys = False  # type: ignore[attr-defined]
    app.extensions["joinery"] = platform
    if settings.trust_proxy:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)  # type: ignore[method-assign]

    def body() -> dict:
        if not request.is_json:
            raise ServiceError("Send a JSON body with Content-Type: application/json.", 415)
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ServiceError("The request body must be a JSON object.")
        return data

    def sql_field(data: dict, name: str = "sql", required: bool = True) -> str | None:
        value = data.get(name)
        if value is None and not required:
            return None
        if not isinstance(value, str):
            raise ServiceError(f"'{name}' must be a string.")
        if len(value) > settings.max_sql_chars:
            raise ServiceError(f"'{name}' is longer than the {settings.max_sql_chars:,} character limit.", 413)
        return value

    def text_field(data: dict, name: str, default: str | None = None) -> str | None:
        value = data.get(name, default)
        if value is not None and not isinstance(value, str):
            raise ServiceError(f"'{name}' must be a string.")
        return value

    @app.before_request
    def before() -> Response | None:
        g.started = time.perf_counter()
        if request.method == "POST" and request.path.startswith("/api/"):
            allowed, retry = limiter.allow(request.remote_addr or "unknown")
            if not allowed:
                response = jsonify(error={"type": "RateLimited",
                                          "message": f"Too many requests. Try again in {retry} seconds."})
                response.status_code = 429
                response.headers["Retry-After"] = str(retry)
                return response
        return None

    @app.after_request
    def after(response: Response) -> Response:
        response.headers.update(headers)
        if request.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
            log.info("%s %s %s %.1fms", request.method, request.path, response.status_code,
                     (time.perf_counter() - g.get("started", time.perf_counter())) * 1000)
        return response

    @app.errorhandler(ServiceError)
    def service_error(exc: ServiceError):
        return jsonify(error={"type": "RequestError", "message": exc.message}), exc.status

    @app.errorhandler(HTTPException)
    def http_error(exc: HTTPException):
        if request.path.startswith("/api/"):
            return jsonify(error={"type": exc.name.replace(" ", ""), "message": exc.description}), exc.code
        return exc

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__, "engines": list(platform.engines)}

    @app.get("/api/meta")
    def meta():
        return {"version": __version__, **platform.meta()}

    @app.get("/api/curriculum")
    def curriculum():
        return {"modules": platform.content.curriculum()}

    @app.get("/api/lessons/<lesson_id>")
    def lesson(lesson_id: str):
        found = platform.content.lessons.get(lesson_id)
        if found is None:
            raise ServiceError(f"There is no lesson called '{lesson_id}'.", 404)
        return found

    @app.get("/api/explore")
    def explore():
        return platform.explore

    @app.post("/api/visualize")
    def visualize():
        data = body()
        return platform.visualize(sql_field(data) or "", text_field(data, "dataset", "shop") or "",
                                  text_field(data, "engine"))

    @app.get("/api/dialects")
    def dialects():
        return platform.content.dialects

    @app.get("/api/datasets/<dataset_id>")
    def dataset(dataset_id: str):
        return platform.dataset_detail(dataset_id)

    @app.get("/api/datasets/<dataset_id>/export")
    def export(dataset_id: str):
        dialect = request.args.get("dialect", "sqlite")
        script = platform.export(dataset_id, dialect)
        return Response(script, mimetype="application/sql",
                        headers={"Content-Disposition": f'attachment; filename="{dataset_id}.{dialect}.sql"'})

    @app.post("/api/run")
    def run():
        data = body()
        return platform.run(sql_field(data) or "", text_field(data, "dataset", "shop") or "",
                            text_field(data, "engine"))

    @app.post("/api/explain")
    def explain():
        data = body()
        return platform.explain(sql_field(data) or "", text_field(data, "dataset", "shop") or "",
                                text_field(data, "engine"), sql_field(data, "setup", required=False))

    @app.post("/api/steps")
    def steps():
        data = body()
        return platform.steps(sql_field(data) or "", text_field(data, "dataset", "shop") or "",
                              text_field(data, "engine"))

    @app.post("/api/exercises/<exercise_id>/check")
    def check(exercise_id: str):
        data = body()
        return platform.check(exercise_id, sql_field(data) or "", text_field(data, "engine"))

    @app.get("/api/exercises/<exercise_id>/solution")
    def solution(exercise_id: str):
        return platform.solution(exercise_id)

    @app.get("/")
    def index():
        page = web_dir / "index.html"
        if not page.exists():
            return Response(MISSING_CLIENT, mimetype="text/html", status=503)
        html = page.read_text(encoding="utf-8").replace("<!-- web-fonts -->", FONT_LINK if settings.web_fonts else "")
        return Response(html, mimetype="text/html", headers={"Cache-Control": "no-cache"})

    @app.get("/assets/<path:filename>")
    def assets(filename: str):
        if not (web_dir / "assets").is_dir():
            abort(404)
        response = send_from_directory(web_dir / "assets", filename, max_age=31_536_000)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    @app.get("/favicon.svg")
    def favicon():
        return send_from_directory(web_dir, "favicon.svg", max_age=86_400)

    return app
