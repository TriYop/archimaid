from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request

from archimaid.adapters.web.errors import UiError
from archimaid.adapters.web.render import Lookups, present_rows, render
from archimaid.application.services import Services
from archimaid.domain.errors import NotFound


def _fetch(service: Any, entity_id: UUID) -> Any:
    try:
        return service.get(entity_id)
    except NotFound as exc:
        raise UiError(exc) from exc


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

    @router.get("/ui/teams/{team_id}")
    def team_page(request: Request, team_id: UUID):
        team = _fetch(services.teams, team_id)
        return render(
            request,
            "team.html",
            team=team,
            team_rows=present_rows(services.teams, [team]),
            member_rows=present_rows(services.members, services.members.list(team_id=team_id)),
            app_rows=present_rows(
                services.applications, services.applications.list(team_id=team_id)
            ),
            lookups=Lookups(services),
        )

    return router
