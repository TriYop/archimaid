from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from archimaid.adapters.web.diagram import build_diagram, draw
from archimaid.adapters.web.diagram.files import filename_slug
from archimaid.adapters.web.errors import UiError, inline_problem
from archimaid.adapters.web.forms import form_data, parse_form
from archimaid.adapters.web.render import Lookups, present_rows, render
from archimaid.adapters.web.resources import APPLICATION, DATA_FLOW, TABS
from archimaid.application.services import Services
from archimaid.domain.errors import DomainError, NotFound


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

    def tab_context(app: Any, tab: str, lookups: Lookups) -> dict[str, Any]:
        if tab not in dict(TABS):
            raise UiError(NotFound(f"unknown tab {tab!r}"))
        app_values = present_rows(services.applications, [app])[0]
        context: dict[str, Any] = {
            "app": app,
            "tab": tab,
            "lookups": lookups,
            "app_values": app_values,
            "values": app_values,
            "messages": [],
            "saved": False,
        }
        if tab == "functions":
            context["rows"] = present_rows(
                services.functions, services.functions.list(application_id=app.id)
            )
        elif tab == "data-types":
            context["rows"] = present_rows(
                services.data_types, services.data_types.list(application_id=app.id)
            )
        elif tab == "technologies":
            context["rows"] = present_rows(
                services.technologies, services.technologies.list(application_id=app.id)
            )
        elif tab == "data-flows":
            context["outgoing_rows"] = present_rows(
                services.data_flows, services.data_flows.list(source_application_id=app.id)
            )
            context["incoming_rows"] = present_rows(
                services.data_flows, services.data_flows.list(target_application_id=app.id)
            )
        elif tab == "diagram":
            context["diagram"] = draw(build_diagram(services, app.id))
        return context

    @router.get("/ui/applications/{application_id}")
    def application_page(request: Request, application_id: UUID, tab: str = "details"):
        app = _fetch(services.applications, application_id)
        team = _fetch(services.teams, app.team_id)
        context = tab_context(app, tab, Lookups(services))
        return render(request, "application.html", team=team, **context)

    @router.get("/ui/applications/{application_id}/tabs/{tab}")
    def application_tab(request: Request, application_id: UUID, tab: str):
        app = _fetch(services.applications, application_id)
        context = tab_context(app, tab, Lookups(services))
        return render(request, "_tab_panel.html", **context)

    @router.put("/ui/applications/{application_id}/details")
    def save_details(
        request: Request,
        application_id: UUID,
        form: dict[str, str] = Depends(form_data),
    ):
        app = _fetch(services.applications, application_id)
        data, problems = parse_form(form, APPLICATION.editable())
        status = 422
        if not problems:
            try:
                app = services.applications.update(application_id, data)
                status = 200
            except DomainError as exc:
                problems, status = inline_problem(exc)
        context = tab_context(app, "details", Lookups(services))
        if problems:
            context.update(values={**form, "id": str(app.id)}, messages=problems)
        else:
            context.update(saved=True)
        return render(request, "_tab_panel.html", status_code=status, **context)

    @router.get("/ui/data-flows")
    def data_flows_page(request: Request):
        lookups = Lookups(services)
        apps = {a.id: a.name for a in services.applications.list()}
        usage = DATA_FLOW.field("usage_mode")
        flows = [
            {
                "id": f.id,
                "source_id": f.source_application_id,
                "source_name": apps.get(f.source_application_id, "?"),
                "target_id": f.target_application_id,
                "target_name": apps.get(f.target_application_id, "?"),
                "data_type": lookups.display(DATA_FLOW.field("data_type_id"), vars(f)),
                "usage_mode": lookups.display(usage, vars(f)),
                "explanation": f.usage_explanation or "—",
            }
            for f in services.data_flows.list()
        ]
        return render(request, "data_flows.html", flows=flows)

    @router.get("/ui/applications/{application_id}/diagram.svg")
    def application_diagram(application_id: UUID, download: int = 0):
        app = _fetch(services.applications, application_id)
        diagram = draw(build_diagram(services, application_id))
        headers = {
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        }
        if download:
            headers["Content-Disposition"] = (
                f'attachment; filename="{filename_slug(app.name)}-interactions.svg"'
            )
        return Response(
            content=diagram.svg,
            media_type="image/svg+xml; charset=utf-8",
            headers=headers,
        )

    return router
