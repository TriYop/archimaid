import re
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from archimaid.adapters.web.errors import UiError, inline_problem
from archimaid.adapters.web.forms import form_data, parse_form
from archimaid.adapters.web.render import Lookups, render
from archimaid.adapters.web.resources import Resource, reference_resource
from archimaid.application.services import Services
from archimaid.domain.errors import DomainError, NotFound
from archimaid.domain.reference import REFERENCE_KINDS


def _title(kind: str) -> str:
    return kind.replace("_", " ").capitalize()


def reference_router(services: Services) -> APIRouter:
    """Pages and inline-editing routes for the configuration catalogs (keyed by code)."""
    router = APIRouter()

    def resource_for(kind: str) -> Resource:
        if kind not in REFERENCE_KINDS:
            raise UiError(NotFound(f"unknown reference kind {kind!r}"))
        return reference_resource(kind)

    def view(value: Any) -> dict[str, Any]:
        return {**vars(value), "id": value.code}

    def fetch(kind: str, code: str) -> Any:
        try:
            return services.reference.get(kind, code)
        except NotFound as exc:
            raise UiError(exc) from exc

    def row_page(request: Request, template: str, resource: Resource, values: dict[str, Any], **extra: Any):
        return render(
            request, template, resource=resource, values=values, ctx={},
            lookups=Lookups(services), **extra,
        )

    @router.get("/ui/reference")
    def index(request: Request):
        kinds = [(kind, _title(kind), len(services.reference.list(kind))) for kind in services.reference.kinds()]
        return render(request, "reference_index.html", kinds=kinds)

    @router.get("/ui/reference/{kind}")
    def kind_page(request: Request, kind: str):
        resource = resource_for(kind)
        rows = [view(v) for v in services.reference.list(kind)]
        return render(
            request, "reference_kind.html", resource=resource, rows=rows,
            title=_title(kind), lookups=Lookups(services),
        )

    @router.post("/ui/reference/{kind}")
    def add(
        request: Request,
        kind: str,
        form: dict[str, str] = Depends(form_data),
        table: str | None = None,
    ):
        resource = resource_for(kind)
        table_id = table if table and re.fullmatch(r"[A-Za-z0-9_-]+", table) else "reference"
        data, problems = parse_form(form, resource.form())
        status = 422
        if not problems:
            try:
                value = services.reference.create(kind, data)
            except DomainError as exc:
                problems, status = inline_problem(exc)
            else:
                return row_page(request, "_row_added.html", resource, view(value), status_code=201, table_id=table_id)
        return render(
            request, "_add_errors.html", status_code=status,
            headers={"HX-Retarget": f"#add-errors-{table_id}", "HX-Reswap": "innerHTML"},
            messages=problems,
        )

    @router.get("/ui/reference/{kind}/{code}/row")
    def display_row(request: Request, kind: str, code: str):
        resource = resource_for(kind)
        return row_page(request, "_row.html", resource, view(fetch(kind, code)))

    @router.get("/ui/reference/{kind}/{code}/edit")
    def edit_row(request: Request, kind: str, code: str):
        resource = resource_for(kind)
        return row_page(request, "_edit_row.html", resource, view(fetch(kind, code)), messages=[])

    @router.put("/ui/reference/{kind}/{code}")
    def save(request: Request, kind: str, code: str, form: dict[str, str] = Depends(form_data)):
        resource = resource_for(kind)
        existing_value = fetch(kind, code)
        data, problems = parse_form(form, resource.form())
        status = 422
        if not problems:
            try:
                value = services.reference.update(kind, code, data)
            except DomainError as exc:
                problems, status = inline_problem(exc)
            else:
                return row_page(request, "_row.html", resource, view(value))
        values = {**view(existing_value), **form, "id": code}
        return row_page(request, "_edit_row.html", resource, values, status_code=status, messages=problems)

    @router.delete("/ui/reference/{kind}/{code}")
    def delete(kind: str, code: str):
        resource_for(kind)
        try:
            services.reference.delete(kind, code)
        except DomainError as exc:
            raise UiError(exc) from exc
        return HTMLResponse("")

    return router
