from fastapi import APIRouter, Request

from archimaid.adapters.web.render import Lookups, present_rows, render
from archimaid.application.services import Services


def pages_router(services: Services) -> APIRouter:
    """Full-page routes. Each page embeds the shared resource tables."""
    router = APIRouter()

    @router.get("/ui/teams")
    def teams_page(request: Request):
        rows = present_rows(services.teams, services.teams.list())
        return render(request, "teams.html", rows=rows, lookups=Lookups(services))

    @router.get("/ui/personas")
    def personas_page(request: Request):
        rows = present_rows(services.personas, services.personas.list())
        return render(request, "personas.html", rows=rows, lookups=Lookups(services))

    return router
