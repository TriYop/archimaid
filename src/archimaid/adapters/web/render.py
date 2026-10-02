from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates

from archimaid.adapters.web import resources
from archimaid.adapters.web.resources import Field
from archimaid.application.services import Services

TEMPLATES_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals.update(
    TABS=resources.TABS,
    TEAM=resources.TEAM,
    MEMBER=resources.MEMBER,
    APPLICATION=resources.APPLICATION,
    FUNCTION=resources.FUNCTION,
    DATA_TYPE=resources.DATA_TYPE,
    TECHNOLOGY=resources.TECHNOLOGY,
    DATA_FLOW=resources.DATA_FLOW,
    PERSONA=resources.PERSONA,
)


def render(
    request: Request,
    name: str,
    status_code: int = 200,
    headers: Mapping[str, str] | None = None,
    **context: Any,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, name, context, status_code=status_code, headers=dict(headers or {})
    )


def present_rows(service: Any, entities: Sequence[Any]) -> list[dict[str, Any]]:
    """Entities as plain dicts, with any derived values the service adds (RPO/RTO)."""
    rows: list[dict[str, Any]] = []
    for item in service.present_many(list(entities)):
        rows.append(dict(item) if isinstance(item, Mapping) else dict(vars(item)))
    return rows


@dataclass(frozen=True)
class Option:
    value: str
    label: str
    group: str | None = None


class Lookups:
    """Dropdown options and display labels, loaded lazily and cached for one request."""

    def __init__(self, services: Services) -> None:
        self._services = services
        self._cache: dict[tuple[str, str], list[Option]] = {}

    def choices(self, field: Field) -> list[tuple[str | None, list[Option]]]:
        groups: dict[str | None, list[Option]] = {}
        for option in self._options(field):
            groups.setdefault(option.group, []).append(option)
        return list(groups.items())

    def display(self, field: Field, values: Mapping[str, Any]) -> str:
        if field.name == "rpo_rto":
            rpo, rto = values.get("rpo"), values.get("rto")
            return "—" if rpo is None or rto is None else f"{rpo} h / {rto} h"
        value = values.get(field.name)
        if value is None or value == "":
            return "—"
        if field.widget in ("select_ref", "select_entity"):
            labels = {option.value: option.label for option in self._options(field)}
            return labels.get(str(value), str(value))
        return str(value)

    def _options(self, field: Field) -> list[Option]:
        key = (field.widget, field.kind or field.source or "")
        if key not in self._cache:
            self._cache[key] = self._load(field)
        return self._cache[key]

    def _load(self, field: Field) -> list[Option]:
        if field.widget == "select_ref":
            assert field.kind is not None
            return [Option(v.code, v.label) for v in self._services.reference.list(field.kind)]
        if field.source == "personas":
            return self._personas()
        if field.source == "applications":
            return self._applications()
        if field.source == "data_types":
            return self._data_types()
        raise ValueError(f"unknown option source {field.source!r}")

    def _personas(self) -> list[Option]:
        personas = sorted(self._services.personas.list(), key=lambda p: p.name.lower())
        return [Option(str(p.id), p.name) for p in personas]

    def _applications(self) -> list[Option]:
        teams = {t.id: t.name for t in self._services.teams.list()}
        options = [
            Option(str(a.id), a.name, teams.get(a.team_id, "?"))
            for a in self._services.applications.list()
        ]
        return sorted(options, key=lambda o: ((o.group or "").lower(), o.label.lower()))

    def _data_types(self) -> list[Option]:
        apps = {a.id: a.name for a in self._services.applications.list()}
        options = []
        for d in self._services.data_types.list():
            app_name = apps.get(d.application_id, "?")
            options.append(Option(str(d.id), f"{app_name} › {d.name}", app_name))
        return sorted(options, key=lambda o: ((o.group or "").lower(), o.label.lower()))
