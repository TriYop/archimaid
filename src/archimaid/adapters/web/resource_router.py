from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse

from archimaid.adapters.web.errors import UiError, inline_problem
from archimaid.adapters.web.forms import form_data, parse_form
from archimaid.adapters.web.render import Lookups, present_rows, render
from archimaid.adapters.web.resources import Resource
from archimaid.application.services import Services
from archimaid.domain.errors import DomainError, NotFound


def _no_parent() -> None:
    return None


def resource_router(
    resource: Resource,
    services: Services,
    *,
    parent_dependency: Callable[..., UUID] | None = None,
) -> APIRouter:
    """add / row / edit / save / delete routes for one resource, rendering HTML fragments."""
    router = APIRouter()
    service = getattr(services, resource.service_name)
    parent_dep = parent_dependency or _no_parent

    def view(entity: Any) -> dict[str, Any]:
        return present_rows(service, [entity])[0]

    def scoped(entity_id: UUID, parent: UUID | None) -> Any:
        try:
            entity = service.get(entity_id)
        except NotFound as exc:
            raise UiError(exc) from exc
        if resource.parent_field and getattr(entity, resource.parent_field) != parent:
            raise UiError(NotFound(f"{resource.title} {entity_id} not found"))
        return entity

    def row_page(request: Request, template: str, values: dict[str, Any], **extra: Any):
        return render(
            request,
            template,
            resource=resource,
            values=values,
            ctx=dict(request.path_params),
            lookups=Lookups(services),
            **extra,
        )

    @router.post("")
    def add(
        request: Request,
        form: dict[str, str] = Depends(form_data),
        parent: UUID | None = Depends(parent_dep),
        table: str | None = None,
    ):
        table_id = table or resource.slug
        data, problems = parse_form(form, resource.form(), uuid_fields=resource.hidden_uuid)
        status = 422
        if resource.parent_field:
            data[resource.parent_field] = parent
        if not problems:
            try:
                entity = service.create(data)
            except DomainError as exc:
                problems, status = inline_problem(exc)
            else:
                return row_page(
                    request, "_row_added.html", view(entity), status_code=201, table_id=table_id
                )
        return render(
            request,
            "_add_errors.html",
            status_code=status,
            headers={"HX-Retarget": f"#add-errors-{table_id}", "HX-Reswap": "innerHTML"},
            messages=problems,
        )

    @router.get("/{entity_id}/row")
    def display_row(
        request: Request, entity_id: UUID, parent: UUID | None = Depends(parent_dep)
    ):
        return row_page(request, "_row.html", view(scoped(entity_id, parent)))

    @router.get("/{entity_id}/edit")
    def edit_row(request: Request, entity_id: UUID, parent: UUID | None = Depends(parent_dep)):
        return row_page(request, "_edit_row.html", view(scoped(entity_id, parent)), messages=[])

    @router.put("/{entity_id}")
    def save(
        request: Request,
        entity_id: UUID,
        form: dict[str, str] = Depends(form_data),
        parent: UUID | None = Depends(parent_dep),
    ):
        scoped(entity_id, parent)
        data, problems = parse_form(form, resource.form())
        status = 422
        if not problems:
            try:
                entity = service.update(entity_id, data)
            except DomainError as exc:
                problems, status = inline_problem(exc)
            else:
                return row_page(request, "_row.html", view(entity))
        values = {**form, "id": str(entity_id)}
        return row_page(request, "_edit_row.html", values, status_code=status, messages=problems)

    @router.delete("/{entity_id}")
    def delete(request: Request, entity_id: UUID, parent: UUID | None = Depends(parent_dep)):
        entity = scoped(entity_id, parent)
        try:
            service.delete(entity_id)
        except DomainError as exc:
            raise UiError(exc) from exc
        if resource.page and resource.after_delete:
            current = urlparse(request.headers.get("HX-Current-URL", "")).path
            if current == resource.page.format(id=entity_id):
                target = resource.after_delete.format(**vars(entity))
                return Response(status_code=200, headers={"HX-Redirect": target})
        return HTMLResponse("")

    return router
