from collections.abc import Callable
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from archimaid.adapters.web.errors import UiError, ui_error_handler
from archimaid.adapters.web.pages import pages_router
from archimaid.adapters.web.resource_router import resource_router
from archimaid.adapters.web.resources import PERSONA, TEAM, Resource
from archimaid.application.services import Services

STATIC_DIR = Path(__file__).parent / "static"


def install_web(app: FastAPI, services: Services) -> None:
    """Mount the server-rendered web UI (HTMX + Jinja2) under /ui."""
    app.mount("/ui/static", StaticFiles(directory=str(STATIC_DIR)), name="ui-static")
    app.add_exception_handler(UiError, ui_error_handler)  # type: ignore[arg-type]

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/ui/")

    @app.get("/ui/", include_in_schema=False)
    def ui_index() -> RedirectResponse:
        return RedirectResponse("/ui/teams")

    app.include_router(pages_router(services), include_in_schema=False)

    routed: list[tuple[Resource, Callable[..., UUID] | None]] = [
        (TEAM, None),
        (PERSONA, None),
    ]
    for resource, parent in routed:
        app.include_router(
            resource_router(resource, services, parent_dependency=parent),
            prefix=resource.base,
            include_in_schema=False,
        )
