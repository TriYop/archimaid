from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from archimaid.application.services import Services

STATIC_DIR = Path(__file__).parent / "static"


def install_web(app: FastAPI, services: Services) -> None:
    """Mount the server-rendered web UI (HTMX + Jinja2) under /ui."""
    app.mount("/ui/static", StaticFiles(directory=str(STATIC_DIR)), name="ui-static")

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/ui/")

    @app.get("/ui/", include_in_schema=False)
    def ui_index() -> RedirectResponse:
        return RedirectResponse("/ui/teams")
