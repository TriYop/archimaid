# Archimaid Web Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a server-rendered HTMX + Jinja2 web UI, under `/ui`, that lets architects enter and browse all Archimaid data and maintain the configuration tables, with no Node.js or npm.

**Architecture:** A new driving adapter, `src/archimaid/adapters/web/`, calls the existing application services (never the JSON API, never persistence). Entities are described as data (`Resource` and `Field`), and shared Jinja2 macros plus one generic router render and serve all of them. HTMX swaps table rows in place. Page routes return full pages; row, form and tab routes return fragments.

**Tech Stack:** FastAPI, Jinja2 (via `starlette.templating`), python-multipart, vendored `htmx.min.js` 2.0.4 and `pico.min.css` 2.0.6, pytest with `TestClient` over the in-memory fakes, one end-to-end test on Postgres.

**Spec:** `docs/superpowers/specs/2026-10-02-archimaid-web-frontend-design.md` (read it first). The backend spec is `docs/superpowers/specs/2026-10-02-archimaid-design.md`.

## Global Constraints

- Node.js and npm are never required. No build step. Nothing is loaded from a CDN at runtime: HTMX and Pico.css are committed under `src/archimaid/adapters/web/static/`. (A CDN is used once, in Task 0, only to download them.)
- English only. Strings live in the templates. No authentication, no CSRF handling (no sessions).
- The web adapter imports only `archimaid.application`, `archimaid.domain` and its own modules. It never imports `archimaid.adapters.persistence` or `archimaid.adapters.api`.
- The JSON API and its paths do not change. The web UI lives under `/ui`; `/` redirects to `/ui/`, which redirects to `/ui/teams`. Static files are served at `/ui/static`.
- Page routes return complete pages. Tab, row, edit-row, add and error routes return fragments. This is decided by the route, not by the `HX-Request` header.
- Every editable resource has these action routes under its base: `POST <base>` (add), `GET <base>/{id}/row` (display row), `GET <base>/{id}/edit` (edit row), `PUT <base>/{id}` (save), `DELETE <base>/{id}`.
- Statuses: `InvalidEntity`, `InvalidReferenceCode`, `DanglingReference` and parse problems give 422; `ReferenceInUse` and `AlreadyExists` give 409; `NotFound` gives 404.
- Add failures: status above, body is an error banner, headers `HX-Retarget: #add-errors-<table_id>` and `HX-Reswap: innerHTML`. Save failures that a form can show (`InvalidEntity`, `InvalidReferenceCode`, `DanglingReference`, `AlreadyExists`) re-render the edit row with a banner. `NotFound` and `ReferenceInUse` anywhere become a flash message: headers `HX-Retarget: #flash` and `HX-Reswap: innerHTML`; on a normal (non-HTMX) navigation they render a full error page with the same status.
- Web forms send only the fields they show. `CrudService.update` replaces only the keys it receives, so fields a form does not show are kept.
- Jinja2 autoescaping is on everywhere (Starlette's default). Never use `|safe` on user data.
- Python `>=3.12`. Do not add `from __future__ import annotations` to `resource_router.py` or `pages.py` unless needed (FastAPI resolves their annotations from live objects).
- Pytest output in this environment may be condensed by a tool that hides warnings and skip reasons. Use `rtk proxy uv run pytest -rs ...` for raw output. Test output must be pristine (no warnings).
- Every commit message ends with this trailer line, added with a second `-m`: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`

## Review Focus

Conditions the spec implies but no obvious test would exercise, each with a pinning test in the owning task, marked **Review Focus test**.

1. User text containing HTML or quotes (`<script>`, `"`) is escaped in table cells, input values and the delete-confirm attribute (Task 2, Task 6).
2. A failed action never leaves the page showing JSON or a blank swap: a missing record, a blocked delete and a wrong or missing parent give a flash message with the right status (Task 2, Task 3, Task 5).
3. Editing a row that shows only some fields does not wipe the fields it hides (an application edited from the team page keeps its description) (Task 3).
4. Blank, invalid or hostile input never gives a 500: blank name, non-numeric rank, bad UUID, empty select, NUL character (Task 1, Task 6, Task 7).
5. Renaming a catalog code from the UI shows the new code in applications that use it, and a code that would break the URL is rejected (Task 6, Task 7).
6. Deleting a record from its own page redirects instead of leaving an empty page (Task 3, Task 4).

---

## File Structure

```
pyproject.toml                          + jinja2, python-multipart
src/archimaid/adapters/api/app.py       + install_web(app, services)
src/archimaid/adapters/web/
  __init__.py
  app.py              install_web(): static mount, redirects, routers, error handler
  resources.py        Field, Resource, the 8 resource definitions, TABS, reference_resource()
  forms.py            parse_form(), form_data dependency
  render.py           templates, render(), Option, Lookups, present_rows()
  errors.py           UiError, status_for(), inline_problem(), ui_error_handler()
  resource_router.py  generic add/row/edit/save/delete routes for a Resource
  reference.py        /ui/reference pages and actions (keyed by code)
  pages.py            teams, team, application (+ tabs, details), personas, data flows pages
  templates/          base, error, fragments, page and tab templates
  static/             htmx.min.js, pico.min.css, app.css, VENDORED.md
tests/adapters/web/
  conftest.py  test_static.py  test_forms.py  test_resources.py  test_render.py
  test_resource_router.py  test_team_pages.py  test_application_pages.py
  test_data_flows.py  test_reference_ui.py
tests/test_web_end_to_end_postgres.py
```

---

### Task 0: Dependencies, vendored assets and the `/ui` skeleton

**Files:**
- Modify: `pyproject.toml` (via `uv add`), `src/archimaid/adapters/api/app.py`
- Create: `src/archimaid/adapters/web/__init__.py`, `src/archimaid/adapters/web/app.py`, `src/archimaid/adapters/web/static/htmx.min.js`, `static/pico.min.css`, `static/app.css`, `static/VENDORED.md`, `tests/adapters/web/__init__.py`, `tests/adapters/web/conftest.py`
- Test: `tests/adapters/web/test_static.py`

**Interfaces:**
- Produces: `install_web(app: FastAPI, services: Services) -> None` in `archimaid.adapters.web.app`, called by `create_app`. It mounts `/ui/static`, adds `GET /` → `/ui/` and `GET /ui/` → `/ui/teams` (HTTP 307). Later tasks extend `install_web`.
- Produces: test fixtures `catalog`, `repos`, `services`, `client` (TestClient over the fakes) and `hx` (`{"HX-Request": "true"}`).

- [ ] **Step 1: Add the dependencies**

Run: `uv add jinja2 python-multipart`
Expected: `pyproject.toml` lists both under `dependencies` and `uv.lock` is updated.

- [ ] **Step 2: Download and record the vendored assets** (one-time network use; the files are then committed)

```bash
cd /home/yvan/Projects/ArchiMaid
S=src/archimaid/adapters/web/static
mkdir -p $S tests/adapters/web
HTMX_URL=https://cdn.jsdelivr.net/npm/htmx.org@2.0.4/dist/htmx.min.js
PICO_URL=https://cdn.jsdelivr.net/npm/@picocss/pico@2.0.6/css/pico.min.css
curl -fsSL -o $S/htmx.min.js "$HTMX_URL"
curl -fsSL -o $S/pico.min.css "$PICO_URL"
HTMX_LICENSE=$(curl -fsSL https://cdn.jsdelivr.net/npm/htmx.org@2.0.4/package.json | python3 -c 'import json,sys; print(json.load(sys.stdin)["license"])')
PICO_LICENSE=$(curl -fsSL https://cdn.jsdelivr.net/npm/@picocss/pico@2.0.6/package.json | python3 -c 'import json,sys; print(json.load(sys.stdin)["license"])')
cat > $S/VENDORED.md <<EOF
# Vendored front-end assets

Downloaded once and committed. Nothing is loaded from a CDN at runtime, and Node.js/npm are not used.

| File | Version | Source | SHA-256 | License |
|---|---|---|---|---|
| htmx.min.js | 2.0.4 | $HTMX_URL | $(sha256sum $S/htmx.min.js | cut -d' ' -f1) | $HTMX_LICENSE |
| pico.min.css | 2.0.6 | $PICO_URL | $(sha256sum $S/pico.min.css | cut -d' ' -f1) | $PICO_LICENSE |
EOF
cat $S/VENDORED.md
```
Expected: two files of more than 10 KB, and `VENDORED.md` with two rows, each with a 64-character hash and a license (htmx `0BSD`, Pico `MIT`). If the downloads fail (no network), stop and report BLOCKED. If a newer 2.x version is needed because these URLs are gone, use it and update the versions in `VENDORED.md` and this task's commit message.

- [ ] **Step 3: Write `app.css`**

`src/archimaid/adapters/web/static/app.css`:
```css
td.actions { white-space: nowrap; }
td.actions button { margin: 0 0.25rem 0 0; padding: 0.25rem 0.6rem; width: auto; }
article.error, .error { color: var(--pico-del-color); }
article.error ul { margin: 0; padding-left: 1.2rem; }
details.add { margin-bottom: 1rem; }
details.add form { padding: 1rem 0; }
tr.editing td { vertical-align: top; }
tr.editing input, tr.editing select, tr.editing textarea { margin-bottom: 0; }
nav.tabs ul { flex-wrap: wrap; }
nav.tabs a[aria-current="page"] { font-weight: bold; }
```

- [ ] **Step 4: Write the fixtures and the failing tests**

`tests/adapters/web/__init__.py`: empty file.

`tests/adapters/web/conftest.py`:
```python
import pytest
from fastapi.testclient import TestClient

from archimaid.adapters.api.app import create_app
from archimaid.application.services import build_services
from tests.fakes import default_catalog, fake_repositories


@pytest.fixture
def catalog():
    return default_catalog()


@pytest.fixture
def repos():
    return fake_repositories()


@pytest.fixture
def services(repos, catalog):
    return build_services(repos, catalog)


@pytest.fixture
def client(services):
    return TestClient(create_app(services))


@pytest.fixture
def hx():
    """Headers an HTMX request sends."""
    return {"HX-Request": "true"}
```

`tests/adapters/web/test_static.py`:
```python
import hashlib
from pathlib import Path

import archimaid.adapters.web as web

STATIC = Path(web.__file__).parent / "static"


def test_vendored_assets_are_served(client):
    htmx = client.get("/ui/static/htmx.min.js")
    assert htmx.status_code == 200
    assert "javascript" in htmx.headers["content-type"]
    assert len(htmx.content) > 10_000
    pico = client.get("/ui/static/pico.min.css")
    assert pico.status_code == 200
    assert "--pico-" in pico.text
    assert client.get("/ui/static/app.css").status_code == 200


def test_vendored_md_records_the_hash_of_every_vendored_file():
    text = (STATIC / "VENDORED.md").read_text()
    for name in ("htmx.min.js", "pico.min.css"):
        digest = hashlib.sha256((STATIC / name).read_bytes()).hexdigest()
        assert name in text
        assert digest in text


def test_root_redirects_to_ui(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/ui/"


def test_ui_index_redirects_to_teams(client):
    response = client.get("/ui/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/ui/teams"


def test_json_api_is_unchanged(client):
    assert client.get("/teams").status_code == 200
    assert client.get("/reference").status_code == 200
```

- [ ] **Step 5: Run to verify it fails**

Run: `uv run pytest tests/adapters/web/test_static.py -v`
Expected: FAIL (`/ui/static/...` returns 404, `ModuleNotFoundError: archimaid.adapters.web`).

- [ ] **Step 6: Implement the skeleton**

`src/archimaid/adapters/web/__init__.py`: empty file.

`src/archimaid/adapters/web/app.py`:
```python
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
```

In `src/archimaid/adapters/api/app.py`, add the import `from archimaid.adapters.web.app import install_web` next to the other adapter imports, and call it just before `return app`:
```python
    app.include_router(reference_router(services.reference))
    install_web(app, services)
    return app
```

- [ ] **Step 7: Run to verify it passes**

Run: `rtk proxy uv run pytest -rs`
Expected: all tests pass (the earlier 144 plus the new ones), 0 skipped, 0 warnings.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock src/archimaid/adapters/web src/archimaid/adapters/api/app.py tests/adapters/web
git commit -m "feat(web): /ui skeleton with vendored htmx 2.0.4 and pico 2.0.6" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 1: Resource definitions and form parsing

**Files:**
- Create: `src/archimaid/adapters/web/resources.py`, `src/archimaid/adapters/web/forms.py`
- Test: `tests/adapters/web/test_resources.py`, `tests/adapters/web/test_forms.py`

**Interfaces:**
- Produces in `resources.py`:
  - `Field(name, label, widget="text", required=False, nullable=True, kind=None, source=None)`, a frozen dataclass. Widgets: `text`, `textarea`, `number`, `select_ref` (needs `kind`), `select_entity` (needs `source`: `"personas"`, `"applications"` or `"data_types"`), `readonly`.
  - `Resource(slug, title, base, service_name, fields, table_fields=None, form_fields=None, parent_field=None, hidden_uuid=(), page=None, after_delete=None, delete_warning=None)`, a frozen dataclass, with methods `columns() -> tuple[Field, ...]`, `form() -> tuple[Field, ...]`, `editable() -> tuple[Field, ...]` (all non-readonly fields), `field(name) -> Field`, `url(ctx) -> str` (`base.format(**ctx)`), `confirm_delete() -> str`.
  - Constants `TEAM`, `MEMBER`, `APPLICATION`, `FUNCTION`, `DATA_TYPE`, `TECHNOLOGY`, `DATA_FLOW`, `PERSONA`, `ALL_RESOURCES`, `TABS`, and `reference_resource(kind) -> Resource`.
- Produces in `forms.py`: `parse_form(form, fields, *, uuid_fields=()) -> tuple[dict[str, Any], list[str]]` (the data for the service, and a list of problem messages) and `async def form_data(request) -> dict[str, str]` (a FastAPI dependency).
- Parsing rules, all after `.strip()`: text and textarea give the string, except that a blank optional nullable field gives `None` (a blank required or non-nullable field stays `""`, so the domain reports "must not be blank"); number gives an int or `None` when blank (required blank is a problem, a non-integer is a problem); `select_ref` gives the code or `None` when blank; `select_entity` gives a `UUID` or `None` when blank (required blank is a problem, a bad UUID is a problem); `readonly` is skipped. Problem messages read `"<Label>: <reason>"`.

- [ ] **Step 1: Write the failing tests**

`tests/adapters/web/test_forms.py`:
```python
from uuid import UUID, uuid4

import pytest

from archimaid.adapters.web.forms import parse_form
from archimaid.adapters.web.resources import Field


def f(name="x", widget="text", **kw):
    return Field(name, name.title(), widget, **kw)


def test_text_is_stripped_and_blank_optional_becomes_none():
    data, problems = parse_form({"x": "  hello "}, [f()])
    assert (data, problems) == ({"x": "hello"}, [])
    assert parse_form({"x": "   "}, [f()]) == ({"x": None}, [])
    assert parse_form({}, [f()]) == ({"x": None}, [])


def test_blank_required_text_stays_empty_so_the_domain_reports_it():
    assert parse_form({"x": " "}, [f(required=True)]) == ({"x": ""}, [])


def test_blank_non_nullable_text_stays_empty_string():
    assert parse_form({"x": ""}, [f(widget="textarea", nullable=False)]) == ({"x": ""}, [])


def test_number_parses_ints_and_reports_bad_values():
    assert parse_form({"x": " 42 "}, [f(widget="number")]) == ({"x": 42}, [])
    assert parse_form({"x": ""}, [f(widget="number")]) == ({"x": None}, [])
    data, problems = parse_form({"x": "12.5"}, [f(widget="number")])
    assert problems == ["X: must be a whole number"]
    _, required = parse_form({"x": ""}, [f(widget="number", required=True)])
    assert required == ["X: is required"]


def test_select_ref_blank_is_none_otherwise_the_code():
    field = f("level", "select_ref", kind="integrity_level")
    assert parse_form({"level": ""}, [field]) == ({"level": None}, [])
    assert parse_form({"level": "LOW"}, [field]) == ({"level": "LOW"}, [])


def test_select_entity_parses_uuids():
    field = f("persona_id", "select_entity", source="personas")
    some = uuid4()
    assert parse_form({"persona_id": str(some)}, [field]) == ({"persona_id": some}, [])
    assert parse_form({"persona_id": ""}, [field]) == ({"persona_id": None}, [])
    _, problems = parse_form({"persona_id": "nope"}, [field])
    assert problems == ["Persona_Id: is not a valid choice"]
    _, required = parse_form({"persona_id": ""}, [f("persona_id", "select_entity", source="personas", required=True)])
    assert required == ["Persona_Id: is required"]


def test_readonly_fields_are_skipped():
    assert parse_form({"x": "1"}, [f(widget="readonly")]) == ({}, [])


def test_uuid_fields_are_required_hidden_inputs():
    team = uuid4()
    data, problems = parse_form({"team_id": str(team)}, [], uuid_fields=("team_id",))
    assert data == {"team_id": UUID(str(team))} and problems == []
    _, missing = parse_form({}, [], uuid_fields=("team_id",))
    assert missing == ["team_id is missing or not a valid id"]


@pytest.mark.parametrize("raw", ["x\u0000y", "<b>bold</b>", "\"quoted\""])
def test_hostile_text_is_passed_through_unchanged(raw):
    # escaping is the template's job and rejecting NUL is the domain/persistence's job
    assert parse_form({"x": raw}, [f()]) == ({"x": raw}, [])
```

`tests/adapters/web/test_resources.py`:
```python
from dataclasses import fields as dc_fields

import pytest

from archimaid.adapters.web import resources as r
from archimaid.application.services import Services
from archimaid.domain import entities as e
from archimaid.domain.reference import REFERENCE_KINDS

ENTITY_OF = {
    r.TEAM: e.Team,
    r.MEMBER: e.TeamMember,
    r.APPLICATION: e.Application,
    r.FUNCTION: e.Function,
    r.DATA_TYPE: e.DataType,
    r.TECHNOLOGY: e.Technology,
    r.DATA_FLOW: e.DataFlow,
    r.PERSONA: e.Persona,
}


def test_all_resources_lists_the_eight_entities():
    assert set(r.ALL_RESOURCES) == set(ENTITY_OF)


@pytest.mark.parametrize("resource", r.ALL_RESOURCES, ids=lambda x: x.slug)
def test_resource_matches_services_and_entity(resource):
    assert resource.service_name in {f.name for f in dc_fields(Services)}
    entity_fields = {f.name for f in dc_fields(ENTITY_OF[resource])}
    for field in resource.fields:
        if field.widget != "readonly":
            assert field.name in entity_fields, field.name
    assert set(resource.hidden_uuid) <= entity_fields
    if resource.parent_field:
        assert resource.parent_field in entity_fields


@pytest.mark.parametrize("resource", r.ALL_RESOURCES, ids=lambda x: x.slug)
def test_widgets_have_what_they_need(resource):
    for field in resource.fields:
        if field.widget == "select_ref":
            assert field.kind in REFERENCE_KINDS
        if field.widget == "select_entity":
            assert field.source in {"personas", "applications", "data_types"}


@pytest.mark.parametrize("resource", r.ALL_RESOURCES, ids=lambda x: x.slug)
def test_form_fields_are_a_subset_of_columns(resource):
    columns = {f.name for f in resource.columns()}
    assert {f.name for f in resource.form()} <= columns
    assert all(f.widget != "readonly" for f in resource.form())


def test_application_table_is_narrower_than_its_details_form():
    names = [f.name for f in r.APPLICATION.columns()]
    assert names == [
        "name", "shortname", "confidentiality_level", "integrity_level",
        "availability_level", "traceability_level", "rpo_rto",
    ]
    editable = [f.name for f in r.APPLICATION.editable()]
    assert "golden_app_id" in editable and "description" in editable
    assert "rpo_rto" not in editable
    assert r.APPLICATION.field("rpo_rto").widget == "readonly"


def test_urls_and_confirm_text():
    assert r.MEMBER.url({"team_id": "t1"}) == "/ui/teams/t1/members"
    assert r.APPLICATION.url({}) == "/ui/applications"
    assert "functions, data types and technologies" in r.APPLICATION.confirm_delete()
    assert r.PERSONA.confirm_delete() == "Delete this persona?"


def test_team_description_is_not_nullable():
    assert r.TEAM.field("description").nullable is False


def test_reference_resource_columns_follow_the_kind():
    plain = [f.name for f in r.reference_resource("usage_mode").fields]
    assert plain == ["code", "label", "description"]
    ranked = [f.name for f in r.reference_resource("integrity_level").fields]
    assert ranked == ["code", "label", "description", "rank"]
    avail = r.reference_resource("availability_level")
    assert [f.name for f in avail.fields][-3:] == ["rank", "rpo_hours", "rto_hours"]
    assert avail.base == "/ui/reference/availability_level"
    assert avail.slug == "ref-availability_level"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/adapters/web/test_forms.py tests/adapters/web/test_resources.py -v`
Expected: collection errors, `ModuleNotFoundError: archimaid.adapters.web.resources` / `.forms`.

- [ ] **Step 3: Implement `resources.py`**

`src/archimaid/adapters/web/resources.py`:
```python
from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from archimaid.domain.reference import REFERENCE_KINDS

Widget = Literal["text", "textarea", "number", "select_ref", "select_entity", "readonly"]


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    widget: Widget = "text"
    required: bool = False
    nullable: bool = True
    kind: str | None = None  # select_ref: the catalog kind
    source: str | None = None  # select_entity: "personas" | "applications" | "data_types"


@dataclass(frozen=True)
class Resource:
    slug: str  # id prefix in the HTML, e.g. "team"
    title: str  # singular noun used in buttons and messages
    base: str  # URL template, e.g. "/ui/applications/{application_id}/functions"
    service_name: str  # attribute of Services that handles it
    fields: tuple[Field, ...]
    table_fields: tuple[str, ...] | None = None  # columns shown (default: all)
    form_fields: tuple[str, ...] | None = None  # fields in add/edit forms (default: editable)
    parent_field: str | None = None  # nested: entity field set from the path
    hidden_uuid: tuple[str, ...] = ()  # extra UUID inputs accepted on add (sent hidden)
    page: str | None = None  # "/ui/teams/{id}": the record's own page
    after_delete: str | None = None  # where to go after deleting it from its own page
    delete_warning: str | None = None

    def field(self, name: str) -> Field:
        return next(f for f in self.fields if f.name == name)

    def columns(self) -> tuple[Field, ...]:
        if self.table_fields is None:
            return self.fields
        return tuple(self.field(name) for name in self.table_fields)

    def editable(self) -> tuple[Field, ...]:
        return tuple(f for f in self.fields if f.widget != "readonly")

    def form(self) -> tuple[Field, ...]:
        if self.form_fields is None:
            return self.editable()
        return tuple(self.field(name) for name in self.form_fields)

    def url(self, ctx: Mapping[str, Any]) -> str:
        return self.base.format(**ctx)

    def confirm_delete(self) -> str:
        return self.delete_warning or f"Delete this {self.title.lower()}?"


def _level(name: str, label: str) -> Field:
    return Field(name, label, "select_ref", kind=name)


TEAM = Resource(
    slug="team",
    title="Team",
    base="/ui/teams",
    service_name="teams",
    fields=(
        Field("name", "Name", required=True),
        Field("description", "Description", "textarea", nullable=False),
    ),
    page="/ui/teams/{id}",
    after_delete="/ui/teams",
    delete_warning="Delete this team?",
)

MEMBER = Resource(
    slug="member",
    title="Member",
    base="/ui/teams/{team_id}/members",
    service_name="members",
    fields=(
        Field("user_id", "User id", required=True),
        Field("name", "Name", required=True),
    ),
    parent_field="team_id",
)

APPLICATION = Resource(
    slug="application",
    title="Application",
    base="/ui/applications",
    service_name="applications",
    fields=(
        Field("name", "Name", required=True),
        Field("shortname", "Short name"),
        Field("golden_app_id", "Golden app id"),
        Field("auid", "AUID"),
        Field("asset_cmdb", "Asset CMDB"),
        Field("owner_uid", "Owner uid"),
        Field("description", "Description", "textarea"),
        _level("confidentiality_level", "Confidentiality"),
        _level("integrity_level", "Integrity"),
        _level("availability_level", "Availability"),
        _level("traceability_level", "Traceability"),
        Field("rpo_rto", "RPO / RTO", "readonly"),
    ),
    table_fields=(
        "name",
        "shortname",
        "confidentiality_level",
        "integrity_level",
        "availability_level",
        "traceability_level",
        "rpo_rto",
    ),
    form_fields=(
        "name",
        "shortname",
        "confidentiality_level",
        "integrity_level",
        "availability_level",
        "traceability_level",
    ),
    hidden_uuid=("team_id",),
    page="/ui/applications/{id}",
    after_delete="/ui/teams/{team_id}",
    delete_warning="Delete this application and its functions, data types and technologies?",
)

FUNCTION = Resource(
    slug="function",
    title="Function",
    base="/ui/applications/{application_id}/functions",
    service_name="functions",
    fields=(
        Field("name", "Name", required=True),
        Field("description", "Description", "textarea"),
        Field("category", "Category", "select_ref", kind="function_category"),
        Field("persona_id", "Persona", "select_entity", source="personas"),
    ),
    parent_field="application_id",
)

DATA_TYPE = Resource(
    slug="data-type",
    title="Data type",
    base="/ui/applications/{application_id}/data-types",
    service_name="data_types",
    fields=(
        Field("name", "Name", required=True),
        Field("definition", "Definition", "textarea"),
        Field("specificity", "Specificity"),
        _level("confidentiality_level", "Confidentiality"),
        Field("golden_source", "Golden source"),
        Field("golden_replica", "Golden replica"),
    ),
    parent_field="application_id",
)

TECHNOLOGY = Resource(
    slug="technology",
    title="Technology",
    base="/ui/applications/{application_id}/technologies",
    service_name="technologies",
    fields=(
        Field("name", "Name", required=True),
        Field("version", "Version"),
        Field("family", "Family"),
        Field("type", "Type", "select_ref", kind="technology_type"),
        Field("standard_status", "Standard status", "select_ref", kind="tech_standard_status"),
        Field("standard_status_details", "Status details", "textarea"),
        Field("tech_standards_link", "Standards link"),
        Field("action_plan", "Action plan", "textarea"),
    ),
    parent_field="application_id",
)

DATA_FLOW = Resource(
    slug="data-flow",
    title="Data flow",
    base="/ui/data-flows",
    service_name="data_flows",
    fields=(
        Field("source_application_id", "Source application", "select_entity", required=True, source="applications"),
        Field("target_application_id", "Target application", "select_entity", required=True, source="applications"),
        Field("data_type_id", "Data type", "select_entity", required=True, source="data_types"),
        Field("usage_mode", "Usage mode", "select_ref", kind="usage_mode"),
        Field("usage_explanation", "Usage explanation"),
    ),
)

PERSONA = Resource(
    slug="persona",
    title="Persona",
    base="/ui/personas",
    service_name="personas",
    fields=(
        Field("name", "Name", required=True),
        Field("description", "Description", "textarea"),
        Field("category", "Category"),
    ),
)

ALL_RESOURCES = (TEAM, MEMBER, APPLICATION, FUNCTION, DATA_TYPE, TECHNOLOGY, DATA_FLOW, PERSONA)

TABS = (
    ("details", "Details"),
    ("functions", "Functions"),
    ("data-types", "Data types"),
    ("technologies", "Technologies"),
    ("data-flows", "Data flows"),
)


def reference_resource(kind: str) -> Resource:
    """The editable table for one configuration catalog; its columns follow the value object."""
    names = {f.name for f in dataclasses.fields(REFERENCE_KINDS[kind])}
    fields = [
        Field("code", "Code", required=True),
        Field("label", "Label", required=True),
        Field("description", "Description", "textarea"),
    ]
    if "rank" in names:
        fields.append(Field("rank", "Rank", "number", required=True))
    if "rpo_hours" in names:
        fields.append(Field("rpo_hours", "RPO (hours)", "number", required=True))
        fields.append(Field("rto_hours", "RTO (hours)", "number", required=True))
    return Resource(
        slug=f"ref-{kind}",
        title="Value",
        base=f"/ui/reference/{kind}",
        service_name="reference",
        fields=tuple(fields),
    )
```

- [ ] **Step 4: Implement `forms.py`**

`src/archimaid/adapters/web/forms.py`:
```python
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from fastapi import Request

from archimaid.adapters.web.resources import Field


async def form_data(request: Request) -> dict[str, str]:
    """FastAPI dependency: the submitted form as plain strings."""
    form = await request.form()
    return {key: value for key, value in form.items() if isinstance(value, str)}


def parse_form(
    form: Mapping[str, str],
    fields: Sequence[Field],
    *,
    uuid_fields: Sequence[str] = (),
) -> tuple[dict[str, Any], list[str]]:
    """Turn submitted strings into the dict a service expects, plus problem messages."""
    data: dict[str, Any] = {}
    problems: list[str] = []
    for field in fields:
        if field.widget == "readonly":
            continue
        raw = form.get(field.name, "").strip()
        try:
            data[field.name] = _convert(field, raw)
        except ValueError as exc:
            problems.append(f"{field.label}: {exc}")
    for name in uuid_fields:
        try:
            data[name] = UUID(form.get(name, "").strip())
        except ValueError:
            problems.append(f"{name} is missing or not a valid id")
    return data, problems


def _convert(field: Field, raw: str) -> Any:
    if field.widget in ("text", "textarea"):
        if raw or field.required or not field.nullable:
            return raw
        return None
    if field.widget == "number":
        if not raw:
            if field.required:
                raise ValueError("is required")
            return None
        try:
            return int(raw)
        except ValueError:
            raise ValueError("must be a whole number") from None
    if field.widget == "select_entity":
        if not raw:
            if field.required:
                raise ValueError("is required")
            return None
        try:
            return UUID(raw)
        except ValueError:
            raise ValueError("is not a valid choice") from None
    if not raw:  # select_ref
        if field.required:
            raise ValueError("is required")
        return None
    return raw
```
Note: the problem label for the test `"Persona_Id: ..."` comes from the test's `Field` label (`name.title()`), not from the code.

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/adapters/web/test_forms.py tests/adapters/web/test_resources.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/archimaid/adapters/web/resources.py src/archimaid/adapters/web/forms.py tests/adapters/web/test_forms.py tests/adapters/web/test_resources.py
git commit -m "feat(web): resource definitions and form parsing" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Rendering, shared templates, the generic resource router, Teams and Personas pages

**Files:**
- Create: `src/archimaid/adapters/web/render.py`, `errors.py`, `resource_router.py`, `pages.py`, and the templates `base.html`, `error.html`, `_flash.html`, `_resource.html`, `_row.html`, `_edit_row.html`, `_row_added.html`, `_add_errors.html`, `teams.html`, `personas.html` (all under `src/archimaid/adapters/web/templates/`)
- Modify: `src/archimaid/adapters/web/app.py`
- Test: `tests/adapters/web/test_render.py`, `tests/adapters/web/test_resource_router.py`

**Interfaces:**
- Consumes: `Resource`, `Field`, constants, `TABS` (Task 1); `parse_form`, `form_data` (Task 1); `Services`.
- Produces in `render.py`: `templates` (Starlette `Jinja2Templates` with the resource constants and `TABS` as Jinja globals), `render(request, name, status_code=200, headers=None, **context) -> HTMLResponse`, `Option(value, label, group=None)`, `Lookups(services)` with `.choices(field) -> list[tuple[str | None, list[Option]]]` (grouped, in order) and `.display(field, values) -> str`, and `present_rows(service, entities) -> list[dict[str, Any]]`.
- Produces in `errors.py`: `UiError(error: DomainError)`, `status_for(exc) -> int`, `inline_problem(exc) -> tuple[list[str], int]` (raises `UiError` for `NotFound` and `ReferenceInUse`), `async ui_error_handler(request, exc)`.
- Produces in `resource_router.py`: `resource_router(resource, services, *, parent_dependency=None) -> APIRouter` with the five action routes (path parameter `entity_id`; query parameter `table` names the target table, default the resource slug).
- Produces in `pages.py`: `pages_router(services) -> APIRouter` with `GET /ui/teams` and `GET /ui/personas`. Later tasks add routes to it.
- `install_web` gains a `ROUTED_RESOURCES` list of `(resource, parent_dependency_or_None)`; this task registers `TEAM` and `PERSONA`.

- [ ] **Step 1: Write the failing tests for `Lookups`**

`tests/adapters/web/test_render.py`:
```python
from archimaid.adapters.web import resources as r
from archimaid.adapters.web.render import Lookups, present_rows


def test_ref_choices_follow_catalog_order(services):
    groups = Lookups(services).choices(r.APPLICATION.field("integrity_level"))
    assert len(groups) == 1 and groups[0][0] is None
    assert [o.value for o in groups[0][1]] == ["EXTREME", "SERIOUS", "MODERATE", "LOW"]


def test_application_choices_are_grouped_by_team_and_sorted(services):
    team_b = services.teams.create({"name": "B team"})
    team_a = services.teams.create({"name": "A team"})
    services.applications.create({"team_id": team_b.id, "name": "Zeta"})
    services.applications.create({"team_id": team_a.id, "name": "Beta"})
    services.applications.create({"team_id": team_a.id, "name": "Alpha"})
    groups = Lookups(services).choices(r.DATA_FLOW.field("source_application_id"))
    assert [(g, [o.label for o in opts]) for g, opts in groups] == [
        ("A team", ["Alpha", "Beta"]),
        ("B team", ["Zeta"]),
    ]


def test_data_type_choices_are_labelled_with_their_application(services):
    team = services.teams.create({"name": "T"})
    app = services.applications.create({"team_id": team.id, "name": "Billing"})
    services.data_types.create({"application_id": app.id, "name": "Invoice"})
    groups = Lookups(services).choices(r.DATA_FLOW.field("data_type_id"))
    assert groups[0][0] == "Billing"
    assert groups[0][1][0].label == "Billing › Invoice"


def test_persona_choices_are_sorted_by_name(services):
    services.personas.create({"name": "zed"})
    services.personas.create({"name": "Alice"})
    groups = Lookups(services).choices(r.FUNCTION.field("persona_id"))
    assert [o.label for o in groups[0][1]] == ["Alice", "zed"]


def test_display_formats(services):
    lookups = Lookups(services)
    level = r.APPLICATION.field("availability_level")
    assert lookups.display(level, {"availability_level": "SERIOUS"}) == "Serious"
    assert lookups.display(level, {"availability_level": None}) == "—"
    assert lookups.display(r.TEAM.field("name"), {"name": ""}) == "—"
    rpo = r.APPLICATION.field("rpo_rto")
    assert lookups.display(rpo, {"rpo": 4, "rto": 0}) == "4 h / 0 h"
    assert lookups.display(rpo, {"rpo": None, "rto": None}) == "—"


def test_present_rows_adds_derived_values_for_applications(services):
    team = services.teams.create({"name": "T"})
    app = services.applications.create(
        {"team_id": team.id, "name": "A", "availability_level": "SERIOUS"}
    )
    [row] = present_rows(services.applications, [app])
    assert (row["rpo"], row["rto"]) == (4, 0) and row["id"] == app.id
    [team_row] = present_rows(services.teams, [team])
    assert team_row["name"] == "T"
```

- [ ] **Step 2: Write the failing tests for the router, teams and personas**

`tests/adapters/web/test_resource_router.py`:
```python
from uuid import uuid4


def make_team(services, name="Payments", description=""):
    return services.teams.create({"name": name, "description": description})


# ------------------------------------------------------------------ pages


def test_teams_page_is_a_full_page_with_table_and_add_form(client, services):
    team = make_team(services)
    response = client.get("/ui/teams")
    assert response.status_code == 200
    html = response.text
    assert "<html" in html
    assert "/ui/static/htmx.min.js" in html and "/ui/static/pico.min.css" in html
    assert "htmx-config" in html and "responseHandling" in html
    assert 'id="flash"' in html
    assert 'id="rows-teams"' in html
    assert f'<tr id="team-{team.id}"' in html
    assert f'href="/ui/teams/{team.id}"' in html
    assert 'hx-post="/ui/teams?table=teams"' in html
    assert 'id="add-errors-teams"' in html


def test_personas_page_lists_personas(client, services):
    services.personas.create({"name": "Accountant", "category": "finance"})
    html = client.get("/ui/personas").text
    assert "Accountant" in html and "finance" in html
    assert 'hx-post="/ui/personas?table=personas"' in html


# ------------------------------------------------------------------ add


def test_add_returns_the_new_row_and_clears_the_error_area(client, services):
    response = client.post("/ui/teams?table=teams", data={"name": " Payments ", "description": "d"})
    assert response.status_code == 201
    team = services.teams.list()[0]
    assert team.name == "Payments"
    html = response.text
    assert f'<tr id="team-{team.id}"' in html
    assert "<html" not in html
    assert 'id="add-errors-teams"' in html and "hx-swap-oob" in html


def test_add_with_a_blank_name_is_422_and_stores_nothing(client, services):
    response = client.post("/ui/teams?table=teams", data={"name": "  "})
    assert response.status_code == 422
    assert response.headers["HX-Retarget"] == "#add-errors-teams"
    assert response.headers["HX-Reswap"] == "innerHTML"
    assert "name must not be blank" in response.text
    assert services.teams.list() == []


def test_add_retargets_to_the_table_named_in_the_query(client):
    response = client.post("/ui/personas?table=people", data={"name": ""})
    assert response.headers["HX-Retarget"] == "#add-errors-people"


def test_html_in_values_is_escaped_in_rows_inputs_and_confirm(client, services):
    # Review Focus test (1)
    nasty = '<script>alert(1)</script> "q"'
    team = make_team(services, name=nasty)
    row = client.get(f"/ui/teams/{team.id}/row").text
    assert "<script>alert(1)" not in row
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in row
    edit = client.get(f"/ui/teams/{team.id}/edit").text
    assert "<script>alert(1)" not in edit
    assert "&lt;script&gt;" in edit and "&#34;q&#34;" in edit
    page = client.post("/ui/teams?table=teams", data={"name": nasty}).text
    assert "<script>alert(1)" not in page


# ------------------------------------------------------------------ rows


def test_display_row_and_edit_row_are_fragments(client, services):
    team = make_team(services)
    row = client.get(f"/ui/teams/{team.id}/row")
    assert row.status_code == 200 and "<html" not in row.text
    assert f'hx-get="/ui/teams/{team.id}/edit"' in row.text
    assert f'hx-delete="/ui/teams/{team.id}"' in row.text
    edit = client.get(f"/ui/teams/{team.id}/edit")
    assert edit.status_code == 200 and "<html" not in edit.text
    assert 'name="name"' in edit.text and 'value="Payments"' in edit.text
    assert f'hx-put="/ui/teams/{team.id}"' in edit.text
    assert f'hx-get="/ui/teams/{team.id}/row"' in edit.text


def test_save_updates_and_returns_the_display_row(client, services):
    team = make_team(services)
    response = client.put(f"/ui/teams/{team.id}", data={"name": "Billing", "description": "x"})
    assert response.status_code == 200
    assert "Billing" in response.text and "hx-put" not in response.text
    assert services.teams.get(team.id).name == "Billing"


def test_save_with_a_blank_name_rerenders_the_edit_row_with_the_typed_values(client, services):
    team = make_team(services)
    response = client.put(f"/ui/teams/{team.id}", data={"name": " ", "description": "typed"})
    assert response.status_code == 422
    assert "name must not be blank" in response.text
    assert 'role="alert"' in response.text
    assert ">typed</textarea>" in response.text
    assert f'hx-put="/ui/teams/{team.id}"' in response.text
    assert services.teams.get(team.id).name == "Payments"


# ------------------------------------------------------------------ delete and failures


def test_delete_returns_an_empty_body_and_removes_the_record(client, services):
    team = make_team(services)
    response = client.delete(f"/ui/teams/{team.id}")
    assert response.status_code == 200 and response.text == ""
    assert services.teams.list() == []


def test_blocked_delete_is_a_409_flash_message(client, services, repos, hx):
    # Review Focus test (2)
    team = make_team(services)
    repos.teams.mark_in_use(team.id)
    response = client.delete(f"/ui/teams/{team.id}", headers=hx)
    assert response.status_code == 409
    assert response.headers["HX-Retarget"] == "#flash"
    assert response.headers["HX-Reswap"] == "innerHTML"
    assert "still referenced" in response.text
    assert "<html" not in response.text
    assert services.teams.get(team.id).name == "Payments"


def test_missing_record_is_a_404_flash_for_every_row_action(client, hx):
    # Review Focus test (2)
    ghost = uuid4()
    for method, url in (
        ("get", f"/ui/teams/{ghost}/row"),
        ("get", f"/ui/teams/{ghost}/edit"),
        ("put", f"/ui/teams/{ghost}"),
        ("delete", f"/ui/teams/{ghost}"),
    ):
        response = getattr(client, method)(url, headers=hx)
        assert response.status_code == 404, (method, url)
        assert response.headers["HX-Retarget"] == "#flash"


def test_the_same_error_without_htmx_is_a_full_error_page(client):
    response = client.get(f"/ui/teams/{uuid4()}/row")
    assert response.status_code == 404
    assert "<html" in response.text and "not found" in response.text


def test_persona_add_edit_save_delete(client, services):
    added = client.post("/ui/personas?table=personas", data={"name": "Accountant", "category": "finance"})
    assert added.status_code == 201
    persona = services.personas.list()[0]
    assert persona.category == "finance"
    saved = client.put(f"/ui/personas/{persona.id}", data={"name": "Auditor", "description": "", "category": ""})
    assert saved.status_code == 200
    assert services.personas.get(persona.id).category is None
    assert client.delete(f"/ui/personas/{persona.id}").status_code == 200
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/adapters/web/test_render.py tests/adapters/web/test_resource_router.py -v`
Expected: collection error `ModuleNotFoundError: archimaid.adapters.web.render`.

- [ ] **Step 4: Implement `render.py`**

`src/archimaid/adapters/web/render.py`:
```python
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
```

- [ ] **Step 5: Implement `errors.py`**

`src/archimaid/adapters/web/errors.py`:
```python
from fastapi import Request
from fastapi.responses import HTMLResponse

from archimaid.adapters.web.render import render
from archimaid.domain.errors import (
    AlreadyExists,
    DanglingReference,
    DomainError,
    InvalidEntity,
    InvalidReferenceCode,
    NotFound,
    ReferenceInUse,
)


class UiError(Exception):
    """A domain error a form cannot show in place; rendered as a flash message or error page."""

    def __init__(self, error: DomainError) -> None:
        super().__init__(str(error))
        self.error = error


_STATUS: tuple[tuple[type[DomainError], int], ...] = (
    (NotFound, 404),
    (ReferenceInUse, 409),
    (AlreadyExists, 409),
    (InvalidEntity, 422),
    (InvalidReferenceCode, 422),
    (DanglingReference, 422),
)


def status_for(exc: DomainError) -> int:
    for cls, status in _STATUS:
        if isinstance(exc, cls):
            return status
    return 500


def inline_problem(exc: DomainError) -> tuple[list[str], int]:
    """Messages and status for errors a form shows in place; the rest become a UiError."""
    if isinstance(exc, NotFound | ReferenceInUse):
        raise UiError(exc) from exc
    return [str(exc)], status_for(exc)


async def ui_error_handler(request: Request, exc: UiError) -> HTMLResponse:
    status = status_for(exc.error)
    message = str(exc.error)
    if request.headers.get("HX-Request"):
        return render(
            request,
            "_flash.html",
            status_code=status,
            headers={"HX-Retarget": "#flash", "HX-Reswap": "innerHTML"},
            message=message,
        )
    return render(request, "error.html", status_code=status, message=message, code=status)
```

- [ ] **Step 6: Implement the generic router**

`src/archimaid/adapters/web/resource_router.py`:
```python
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
```

- [ ] **Step 7: Implement the pages router and wire everything**

`src/archimaid/adapters/web/pages.py`:
```python
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
```

Replace the contents of `src/archimaid/adapters/web/app.py` with:
```python
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
```

- [ ] **Step 8: Write the templates**

`src/archimaid/adapters/web/templates/base.html`:
```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="htmx-config" content='{"responseHandling":[{"code":"204","swap":false},{"code":"[23]..","swap":true},{"code":"[45]..","swap":true,"error":false}]}'>
  <title>{% block title %}Archimaid{% endblock %} · Archimaid</title>
  <link rel="stylesheet" href="/ui/static/pico.min.css">
  <link rel="stylesheet" href="/ui/static/app.css">
  <script src="/ui/static/htmx.min.js" defer></script>
</head>
<body>
  <header class="container">
    <nav>
      <ul><li><strong>Archimaid</strong></li></ul>
      <ul>
        <li><a href="/ui/teams">Teams</a></li>
        <li><a href="/ui/personas">Personas</a></li>
        <li><a href="/ui/data-flows">Data flows</a></li>
        <li><a href="/ui/reference">Reference data</a></li>
      </ul>
    </nav>
  </header>
  <main class="container">
    <div id="flash" aria-live="polite"></div>
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

`src/archimaid/adapters/web/templates/error.html`:
```html
{% extends "base.html" %}
{% block title %}Error {{ code }}{% endblock %}
{% block content %}
<h1>{{ code }}</h1>
<article class="error" role="alert">{{ message }}</article>
<p><a href="/ui/teams">Back to teams</a></p>
{% endblock %}
```

`src/archimaid/adapters/web/templates/_flash.html`:
```html
<article class="error" role="alert">{{ message }}</article>
```

`src/archimaid/adapters/web/templates/_add_errors.html`:
```html
{% from "_resource.html" import errors %}{{ errors(messages) }}
```

`src/archimaid/adapters/web/templates/_resource.html`:
```html
{% macro errors(messages) -%}
{%- if messages %}<article class="error" role="alert"><ul>{% for m in messages %}<li>{{ m }}</li>{% endfor %}</ul></article>{% endif -%}
{%- endmacro %}

{% macro widget(field, value, lookups) -%}
{%- set shown = '' if value is none else value -%}
{%- if field.widget == 'textarea' -%}
<textarea name="{{ field.name }}" aria-label="{{ field.label }}" rows="2"{% if field.required %} required{% endif %}>{{ shown }}</textarea>
{%- elif field.widget == 'number' -%}
<input type="number" step="1" name="{{ field.name }}" aria-label="{{ field.label }}" value="{{ shown }}"{% if field.required %} required{% endif %}>
{%- elif field.widget in ('select_ref', 'select_entity') -%}
<select name="{{ field.name }}" aria-label="{{ field.label }}"{% if field.required %} required{% endif %}>
  {%- if not field.required %}<option value="">—</option>{% endif %}
  {%- for group, options in lookups.choices(field) %}
    {%- if group %}<optgroup label="{{ group }}">{% endif %}
    {%- for opt in options %}<option value="{{ opt.value }}"{% if opt.value == shown|string %} selected{% endif %}>{{ opt.label }}</option>{% endfor %}
    {%- if group %}</optgroup>{% endif %}
  {%- endfor %}
</select>
{%- else -%}
<input type="text" name="{{ field.name }}" aria-label="{{ field.label }}" value="{{ shown }}"{% if field.required %} required{% endif %}>
{%- endif -%}
{%- endmacro %}

{% macro row(resource, values, lookups, ctx) -%}
{%- set item_id = values['id'] -%}
{%- set url = resource.url(ctx) -%}
<tr id="{{ resource.slug }}-{{ item_id }}">
  {%- for f in resource.columns() %}
  <td>{% if loop.first and resource.page %}<a href="{{ resource.page.format(id=item_id) }}">{{ lookups.display(f, values) }}</a>{% else %}{{ lookups.display(f, values) }}{% endif %}</td>
  {%- endfor %}
  <td class="actions">
    <button type="button" class="outline secondary" hx-get="{{ url }}/{{ item_id }}/edit" hx-target="closest tr" hx-swap="outerHTML">Edit</button>
    <button type="button" class="outline contrast" hx-delete="{{ url }}/{{ item_id }}" hx-confirm="{{ resource.confirm_delete() }}" hx-target="closest tr" hx-swap="outerHTML">Delete</button>
  </td>
</tr>
{%- endmacro %}

{% macro edit_row(resource, values, lookups, ctx, messages) -%}
{%- set item_id = values['id'] -%}
{%- set url = resource.url(ctx) -%}
{%- set editable = resource.form() | map(attribute='name') | list -%}
<tr id="{{ resource.slug }}-{{ item_id }}" class="editing">
  {%- for f in resource.columns() %}
  <td>
    {%- if loop.first %}{{ errors(messages) }}{% endif -%}
    {%- if f.name in editable %}{{ widget(f, values.get(f.name), lookups) }}{% else %}{{ lookups.display(f, values) }}{% endif -%}
  </td>
  {%- endfor %}
  <td class="actions">
    <button type="button" hx-put="{{ url }}/{{ item_id }}" hx-include="closest tr" hx-target="closest tr" hx-swap="outerHTML">Save</button>
    <button type="button" class="outline secondary" hx-get="{{ url }}/{{ item_id }}/row" hx-target="closest tr" hx-swap="outerHTML">Cancel</button>
  </td>
</tr>
{%- endmacro %}

{% macro add_form(resource, lookups, ctx, table_id, fixed) -%}
<details class="add">
  <summary role="button" class="outline">Add {{ resource.title | lower }}</summary>
  <form hx-post="{{ resource.url(ctx) }}?table={{ table_id }}" hx-target="#rows-{{ table_id }}" hx-swap="afterbegin" hx-on::after-request="if (event.detail.successful) this.reset()">
    <div id="add-errors-{{ table_id }}"></div>
    {%- for f in resource.form() if f.name not in fixed %}
    <label>{{ f.label }}{% if f.required %} *{% endif %}
      {{ widget(f, none, lookups) }}
    </label>
    {%- endfor %}
    {%- for name, value in fixed.items() %}
    <input type="hidden" name="{{ name }}" value="{{ value }}">
    {%- endfor %}
    <button type="submit">Add</button>
  </form>
</details>
{%- endmacro %}

{% macro table(resource, rows, lookups, ctx, table_id, fixed={}, add=True) -%}
{% if add %}{{ add_form(resource, lookups, ctx, table_id, fixed) }}{% endif %}
<figure>
  <table>
    <thead><tr>{% for f in resource.columns() %}<th scope="col">{{ f.label }}</th>{% endfor %}<th scope="col"></th></tr></thead>
    <tbody id="rows-{{ table_id }}">
      {%- for values in rows %}
      {{ row(resource, values, lookups, ctx) }}
      {%- endfor %}
    </tbody>
  </table>
</figure>
{%- endmacro %}
```

`src/archimaid/adapters/web/templates/_row.html`:
```html
{% from "_resource.html" import row %}{{ row(resource, values, lookups, ctx) }}
```

`src/archimaid/adapters/web/templates/_edit_row.html`:
```html
{% from "_resource.html" import edit_row %}{{ edit_row(resource, values, lookups, ctx, messages) }}
```

`src/archimaid/adapters/web/templates/_row_added.html`:
```html
{% from "_resource.html" import row %}{{ row(resource, values, lookups, ctx) }}
<div id="add-errors-{{ table_id }}" hx-swap-oob="true"></div>
```

`src/archimaid/adapters/web/templates/teams.html`:
```html
{% extends "base.html" %}
{% from "_resource.html" import table %}
{% block title %}Teams{% endblock %}
{% block content %}
<h1>Teams</h1>
{{ table(TEAM, rows, lookups, {}, "teams") }}
{% endblock %}
```

`src/archimaid/adapters/web/templates/personas.html`:
```html
{% extends "base.html" %}
{% from "_resource.html" import table %}
{% block title %}Personas{% endblock %}
{% block content %}
<h1>Personas</h1>
{{ table(PERSONA, rows, lookups, {}, "personas") }}
{% endblock %}
```

- [ ] **Step 9: Run to verify it passes**

Run: `rtk proxy uv run pytest tests/adapters/web -v -rs`
Expected: all pass, 0 skipped, no warnings. If a test fails because of whitespace in the rendered HTML, adjust the template, not the test's intent.

- [ ] **Step 10: Run the whole suite**

Run: `rtk proxy uv run pytest -rs`
Expected: everything passes, 0 skipped, 0 warnings.

- [ ] **Step 11: Commit**

```bash
git add src/archimaid/adapters/web tests/adapters/web
git commit -m "feat(web): rendering, shared templates, generic resource router, teams and personas pages" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Team page, members and applications

**Files:**
- Modify: `src/archimaid/adapters/web/pages.py`, `src/archimaid/adapters/web/app.py`
- Create: `src/archimaid/adapters/web/templates/team.html`
- Test: `tests/adapters/web/test_team_pages.py`

**Interfaces:**
- Consumes: everything from Tasks 1 and 2.
- Produces: `GET /ui/teams/{team_id}` (full page); routed resources `MEMBER` (nested under `/ui/teams/{team_id}/members`, parent dependency `team_parent`) and `APPLICATION` (flat `/ui/applications`, `team_id` sent as a hidden input).
- `pages.py` gains a private helper `_fetch(service, entity_id)` that returns the entity or raises `UiError(NotFound)`; later tasks reuse it.

- [ ] **Step 1: Write the failing tests**

`tests/adapters/web/test_team_pages.py`:
```python
from uuid import uuid4


def make_team(services, name="Payments"):
    return services.teams.create({"name": name})


def make_app(services, team, **extra):
    return services.applications.create({"team_id": team.id, "name": "Billing", **extra})


# ------------------------------------------------------------------ team page


def test_team_page_shows_header_members_and_applications(client, services):
    team = make_team(services)
    member = services.members.create({"team_id": team.id, "user_id": "u1", "name": "Ann"})
    app = make_app(services, team, availability_level="SERIOUS", shortname="bil")
    html = client.get(f"/ui/teams/{team.id}").text
    assert "<html" in html
    assert 'href="/ui/teams"' in html
    assert f'<tr id="team-{team.id}"' in html
    assert f'<tr id="member-{member.id}"' in html and "Ann" in html
    assert f'<tr id="application-{app.id}"' in html
    assert f'href="/ui/applications/{app.id}"' in html
    assert "bil" in html and "4 h / 0 h" in html
    assert f'hx-post="/ui/teams/{team.id}/members?table=members"' in html
    assert 'hx-post="/ui/applications?table=applications"' in html
    assert f'name="team_id" value="{team.id}"' in html


def test_the_team_header_has_no_add_form(client, services):
    team = make_team(services)
    html = client.get(f"/ui/teams/{team.id}").text
    assert 'hx-post="/ui/teams?table=team"' not in html


def test_application_add_form_offers_levels_in_rank_order(client, services):
    team = make_team(services)
    html = client.get(f"/ui/teams/{team.id}").text
    assert html.index('<option value="EXTREME"') < html.index('<option value="LOW"')
    assert '<option value="SERIOUS"' in html


def test_missing_team_page_is_a_404_page(client):
    response = client.get(f"/ui/teams/{uuid4()}")
    assert response.status_code == 404 and "<html" in response.text


# ------------------------------------------------------------------ members


def test_add_member_under_a_team(client, services):
    team = make_team(services)
    response = client.post(
        f"/ui/teams/{team.id}/members?table=members", data={"user_id": "u1", "name": "Ann"}
    )
    assert response.status_code == 201
    member = services.members.list()[0]
    assert member.team_id == team.id
    assert f'<tr id="member-{member.id}"' in response.text
    assert f'hx-get="/ui/teams/{team.id}/members/{member.id}/edit"' in response.text


def test_member_blank_user_id_is_422(client, services):
    team = make_team(services)
    response = client.post(
        f"/ui/teams/{team.id}/members?table=members", data={"user_id": " ", "name": "Ann"}
    )
    assert response.status_code == 422
    assert "user_id must not be blank" in response.text
    assert services.members.list() == []


def test_member_save_and_delete(client, services):
    team = make_team(services)
    member = services.members.create({"team_id": team.id, "user_id": "u1", "name": "Ann"})
    base = f"/ui/teams/{team.id}/members/{member.id}"
    saved = client.put(base, data={"user_id": "u2", "name": "Ann B"})
    assert saved.status_code == 200
    updated = services.members.get(member.id)
    assert (updated.user_id, updated.name, updated.team_id) == ("u2", "Ann B", team.id)
    assert client.delete(base).status_code == 200
    assert services.members.list() == []


def test_member_through_the_wrong_team_is_a_404_flash(client, services, hx):
    # Review Focus test (2)
    team_a, team_b = make_team(services, "A"), make_team(services, "B")
    member = services.members.create({"team_id": team_a.id, "user_id": "u1", "name": "Ann"})
    wrong = f"/ui/teams/{team_b.id}/members/{member.id}"
    for method, url in (("get", wrong + "/row"), ("get", wrong + "/edit"), ("delete", wrong)):
        response = getattr(client, method)(url, headers=hx)
        assert response.status_code == 404, url
        assert response.headers["HX-Retarget"] == "#flash"
    assert client.put(wrong, data={"user_id": "x", "name": "x"}, headers=hx).status_code == 404
    assert services.members.get(member.id).user_id == "u1"


def test_member_under_a_missing_team_is_a_404_flash(client, hx):
    response = client.post(
        f"/ui/teams/{uuid4()}/members?table=members", data={"user_id": "u", "name": "n"}, headers=hx
    )
    assert response.status_code == 404 and response.headers["HX-Retarget"] == "#flash"


# ------------------------------------------------------------------ applications


def test_add_application_from_the_team_page(client, services):
    team = make_team(services)
    response = client.post(
        "/ui/applications?table=applications",
        data={
            "team_id": str(team.id),
            "name": "Billing",
            "shortname": "bil",
            "availability_level": "SERIOUS",
        },
    )
    assert response.status_code == 201
    app = services.applications.list()[0]
    assert app.team_id == team.id and app.availability_level == "SERIOUS"
    assert f'href="/ui/applications/{app.id}"' in response.text
    assert "4 h / 0 h" in response.text


def test_add_application_without_or_with_an_unknown_team_is_422(client, services):
    # Review Focus test (4)
    missing = client.post("/ui/applications?table=applications", data={"name": "A"})
    assert missing.status_code == 422 and "team_id" in missing.text
    ghost = client.post(
        "/ui/applications?table=applications", data={"team_id": str(uuid4()), "name": "A"}
    )
    assert ghost.status_code == 422 and "does not exist" in ghost.text
    bad = client.post(
        "/ui/applications?table=applications", data={"team_id": "nope", "name": "A"}
    )
    assert bad.status_code == 422
    assert services.applications.list() == []


def test_add_application_with_an_unknown_level_is_422(client, services):
    team = make_team(services)
    response = client.post(
        "/ui/applications?table=applications",
        data={"team_id": str(team.id), "name": "A", "availability_level": "NOPE"},
    )
    assert response.status_code == 422
    assert "is not a valid availability_level" in response.text


def test_editing_a_row_does_not_wipe_the_fields_it_hides(client, services):
    # Review Focus test (3)
    team = make_team(services)
    app = make_app(services, team, description="keep me", golden_app_id="G1", auid="A1")
    response = client.put(
        f"/ui/applications/{app.id}",
        data={
            "name": "Renamed",
            "shortname": "",
            "confidentiality_level": "",
            "integrity_level": "LOW",
            "availability_level": "SERIOUS",
            "traceability_level": "",
        },
    )
    assert response.status_code == 200
    saved = services.applications.get(app.id)
    assert (saved.name, saved.shortname, saved.integrity_level) == ("Renamed", None, "LOW")
    assert saved.description == "keep me"
    assert (saved.golden_app_id, saved.auid, saved.team_id) == ("G1", "A1", team.id)
    assert "4 h / 0 h" in response.text


def test_application_edit_row_preselects_the_current_levels(client, services):
    team = make_team(services)
    app = make_app(services, team, integrity_level="MODERATE")
    html = client.get(f"/ui/applications/{app.id}/edit").text
    assert '<option value="MODERATE" selected>' in html
    assert "4 h" not in html and "—" in html  # the RPO/RTO cell is shown read-only


def test_application_save_with_a_blank_name_is_422(client, services):
    team = make_team(services)
    app = make_app(services, team)
    response = client.put(f"/ui/applications/{app.id}", data={"name": " "})
    assert response.status_code == 422 and "name must not be blank" in response.text
    assert services.applications.get(app.id).name == "Billing"


# ------------------------------------------------------------------ delete from own page


def test_deleting_an_application_from_its_own_page_redirects_to_its_team(client, services):
    # Review Focus test (6)
    team = make_team(services)
    app = make_app(services, team)
    own_page = f"http://testserver/ui/applications/{app.id}?tab=details"
    response = client.delete(f"/ui/applications/{app.id}", headers={"HX-Current-URL": own_page})
    assert response.status_code == 200
    assert response.headers["HX-Redirect"] == f"/ui/teams/{team.id}"
    assert services.applications.list() == []


def test_deleting_an_application_from_the_team_page_just_removes_the_row(client, services):
    team = make_team(services)
    app = make_app(services, team)
    team_page = f"http://testserver/ui/teams/{team.id}"
    response = client.delete(f"/ui/applications/{app.id}", headers={"HX-Current-URL": team_page})
    assert response.status_code == 200 and response.text == ""
    assert "HX-Redirect" not in response.headers


def test_deleting_a_team_from_its_own_page_redirects_to_the_teams_list(client, services):
    # Review Focus test (6)
    team = make_team(services)
    own_page = f"http://testserver/ui/teams/{team.id}"
    response = client.delete(f"/ui/teams/{team.id}", headers={"HX-Current-URL": own_page})
    assert response.headers["HX-Redirect"] == "/ui/teams"

```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/adapters/web/test_team_pages.py -v`
Expected: the team page tests fail with 404, the member and application tests fail with 404/405 (the routes do not exist yet).

- [ ] **Step 3: Add the team page route**

In `src/archimaid/adapters/web/pages.py`, add these imports at the top:
```python
from typing import Any
from uuid import UUID

from archimaid.adapters.web.errors import UiError
from archimaid.domain.errors import NotFound
```
Add this module-level helper above `pages_router`:
```python
def _fetch(service: Any, entity_id: UUID) -> Any:
    try:
        return service.get(entity_id)
    except NotFound as exc:
        raise UiError(exc) from exc
```
Add this route inside `pages_router`, before `return router`:
```python
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
```

- [ ] **Step 4: Add the template**

`src/archimaid/adapters/web/templates/team.html`:
```html
{% extends "base.html" %}
{% from "_resource.html" import table %}
{% block title %}{{ team.name }}{% endblock %}
{% block content %}
<nav aria-label="breadcrumb">
  <ul><li><a href="/ui/teams">Teams</a></li><li>{{ team.name }}</li></ul>
</nav>
<h1>{{ team.name }}</h1>
{{ table(TEAM, team_rows, lookups, {}, "team", add=False) }}
<h2>Members</h2>
{{ table(MEMBER, member_rows, lookups, {"team_id": team.id}, "members") }}
<h2>Applications</h2>
{{ table(APPLICATION, app_rows, lookups, {}, "applications", {"team_id": team.id}) }}
{% endblock %}
```

- [ ] **Step 5: Route the member and application resources**

In `src/archimaid/adapters/web/app.py`: change the resources import to
`from archimaid.adapters.web.resources import APPLICATION, MEMBER, PERSONA, TEAM, Resource`,
add `from archimaid.domain.errors import NotFound`, and inside `install_web`, before the `routed` list, add:
```python
    def team_parent(team_id: UUID) -> UUID:
        try:
            services.teams.get(team_id)
        except NotFound as exc:
            raise UiError(exc) from exc
        return team_id
```
Then extend the `routed` list:
```python
    routed: list[tuple[Resource, Callable[..., UUID] | None]] = [
        (TEAM, None),
        (MEMBER, team_parent),
        (APPLICATION, None),
        (PERSONA, None),
    ]
```

- [ ] **Step 6: Run to verify it passes**

Run: `rtk proxy uv run pytest tests/adapters/web -v -rs`
Expected: all pass, 0 skipped, no warnings.

- [ ] **Step 7: Run the whole suite**

Run: `rtk proxy uv run pytest -rs`
Expected: everything passes.

- [ ] **Step 8: Commit**

```bash
git add src/archimaid/adapters/web tests/adapters/web
git commit -m "feat(web): team page with members and applications" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Application page, tabs, details form, functions, data types and technologies

**Files:**
- Modify: `src/archimaid/adapters/web/pages.py`, `src/archimaid/adapters/web/app.py`
- Create: templates `application.html`, `_tab_panel.html`, `tabs/details.html`, `tabs/functions.html`, `tabs/data-types.html`, `tabs/technologies.html`, `tabs/data-flows.html` (the data-flows tab is a stub filled in Task 5)
- Test: `tests/adapters/web/test_application_pages.py`

**Interfaces:**
- Consumes: Tasks 1-3; `_fetch` from `pages.py`.
- Produces:
  - `GET /ui/applications/{application_id}?tab=<tab>` (full page; default tab `details`; unknown tab gives a 404 page).
  - `GET /ui/applications/{application_id}/tabs/{tab}` (fragment: tab bar plus content, to swap into `#tab-panel`).
  - `PUT /ui/applications/{application_id}/details` (saves the Details form, returns the refreshed panel).
  - Routed resources `FUNCTION`, `DATA_TYPE`, `TECHNOLOGY` nested under `/ui/applications/{application_id}/...` with parent dependency `application_parent`.
- The tab key list is `TABS` from `resources.py`; the data-flows tab renders `tabs/data-flows.html`, which in this task contains a one-line placeholder that Task 5 replaces.

- [ ] **Step 1: Write the failing tests**

`tests/adapters/web/test_application_pages.py`:
```python
from uuid import uuid4


def make_app(services, **extra):
    team = services.teams.create({"name": "Payments"})
    app = services.applications.create({"team_id": team.id, "name": "Billing", **extra})
    return team, app


# ------------------------------------------------------------------ page and tabs


def test_application_page_has_breadcrumbs_tabs_and_the_details_tab(client, services):
    team, app = make_app(services, availability_level="SERIOUS", golden_app_id="G1")
    html = client.get(f"/ui/applications/{app.id}").text
    assert "<html" in html
    assert f'href="/ui/teams/{team.id}"' in html and "Payments" in html
    assert 'id="tab-panel"' in html
    for key in ("details", "functions", "data-types", "technologies", "data-flows"):
        assert f'hx-get="/ui/applications/{app.id}/tabs/{key}"' in html
        assert f'hx-push-url="/ui/applications/{app.id}?tab={key}"' in html
    assert 'aria-current="page"' in html
    assert 'value="G1"' in html and "4 h / 0 h" in html


def test_tab_query_selects_the_tab_and_marks_it_current(client, services):
    _, app = make_app(services)
    html = client.get(f"/ui/applications/{app.id}?tab=functions").text
    assert f'hx-post="/ui/applications/{app.id}/functions?table=functions"' in html
    current = html.index('aria-current="page"')
    assert "tabs/functions" in html[html.rfind("<a", 0, current):current]


def test_unknown_tab_is_a_404_page(client, services):
    _, app = make_app(services)
    assert client.get(f"/ui/applications/{app.id}?tab=nope").status_code == 404
    assert client.get(f"/ui/applications/{app.id}/tabs/nope").status_code == 404


def test_missing_application_page_is_a_404_page(client):
    response = client.get(f"/ui/applications/{uuid4()}")
    assert response.status_code == 404 and "<html" in response.text


def test_tab_fragment_is_not_a_full_page(client, services):
    _, app = make_app(services)
    response = client.get(f"/ui/applications/{app.id}/tabs/technologies")
    assert response.status_code == 200
    assert "<html" not in response.text
    assert f'hx-post="/ui/applications/{app.id}/technologies?table=technologies"' in response.text
    assert 'aria-current="page"' in response.text


# ------------------------------------------------------------------ details form


def test_details_save_updates_the_application_and_reports_saved(client, services):
    _, app = make_app(services)
    response = client.put(
        f"/ui/applications/{app.id}/details",
        data={
            "name": "Billing v2",
            "shortname": "bil",
            "golden_app_id": "G9",
            "auid": "A9",
            "asset_cmdb": "C9",
            "owner_uid": "u9",
            "description": "now described",
            "confidentiality_level": "LOW",
            "integrity_level": "MODERATE",
            "availability_level": "EXTREME",
            "traceability_level": "",
        },
    )
    assert response.status_code == 200
    assert "Saved." in response.text and "2 h / 0 h" in response.text
    saved = services.applications.get(app.id)
    assert (saved.name, saved.golden_app_id, saved.owner_uid) == ("Billing v2", "G9", "u9")
    assert saved.description == "now described" and saved.traceability_level is None
    assert saved.availability_level == "EXTREME"


def test_details_save_with_a_blank_name_is_422_and_keeps_what_was_typed(client, services):
    _, app = make_app(services)
    response = client.put(
        f"/ui/applications/{app.id}/details", data={"name": " ", "description": "typed text"}
    )
    assert response.status_code == 422
    assert "name must not be blank" in response.text
    assert "typed text" in response.text and "Saved." not in response.text
    assert services.applications.get(app.id).name == "Billing"


def test_details_save_with_an_unknown_level_is_422(client, services):
    _, app = make_app(services)
    response = client.put(
        f"/ui/applications/{app.id}/details", data={"name": "A", "integrity_level": "NOPE"}
    )
    assert response.status_code == 422 and "is not a valid integrity_level" in response.text


def test_details_tab_has_a_delete_button_that_confirms(client, services):
    _, app = make_app(services)
    html = client.get(f"/ui/applications/{app.id}/tabs/details").text
    assert f'hx-delete="/ui/applications/{app.id}"' in html
    assert "functions, data types and technologies" in html


def test_details_values_are_escaped(client, services):
    # Review Focus test (1)
    _, app = make_app(services, description='</textarea><script>alert(1)</script>')
    html = client.get(f"/ui/applications/{app.id}/tabs/details").text
    assert "<script>alert(1)" not in html and "&lt;/textarea&gt;" in html


# ------------------------------------------------------------------ functions


def test_functions_tab_lists_only_this_applications_functions(client, services):
    _, app_a = make_app(services)
    _, app_b = make_app(services)
    services.functions.create({"application_id": app_a.id, "name": "Invoice"})
    services.functions.create({"application_id": app_b.id, "name": "Refund"})
    html = client.get(f"/ui/applications/{app_a.id}/tabs/functions").text
    assert "Invoice" in html and "Refund" not in html


def test_add_function_with_category_and_persona(client, services):
    _, app = make_app(services)
    persona = services.personas.create({"name": "Accountant"})
    page = client.get(f"/ui/applications/{app.id}/tabs/functions").text
    assert f'<option value="{persona.id}"' in page and '<option value="BUSINESS"' in page
    response = client.post(
        f"/ui/applications/{app.id}/functions?table=functions",
        data={
            "name": "Invoice",
            "description": "",
            "category": "BUSINESS",
            "persona_id": str(persona.id),
        },
    )
    assert response.status_code == 201
    fn = services.functions.list()[0]
    assert (fn.application_id, fn.persona_id, fn.category) == (app.id, persona.id, "BUSINESS")
    assert "Accountant" in response.text and "Business" in response.text


def test_function_with_an_unknown_persona_or_category_is_422(client, services):
    # Review Focus test (4)
    _, app = make_app(services)
    base = f"/ui/applications/{app.id}/functions?table=functions"
    ghost = client.post(base, data={"name": "F", "persona_id": str(uuid4())})
    assert ghost.status_code == 422 and "does not exist" in ghost.text
    garbage = client.post(base, data={"name": "F", "persona_id": "nope"})
    assert garbage.status_code == 422
    category = client.post(base, data={"name": "F", "category": "NOPE"})
    assert category.status_code == 422 and "is not a valid function_category" in category.text
    assert services.functions.list() == []


def test_function_save_keeps_its_application(client, services):
    _, app = make_app(services)
    fn = services.functions.create({"application_id": app.id, "name": "Invoice"})
    other = services.applications.create({"team_id": app.team_id, "name": "Other"})
    base = f"/ui/applications/{app.id}/functions/{fn.id}"
    response = client.put(
        base, data={"name": "Invoice v2", "application_id": str(other.id), "category": "DATA"}
    )
    assert response.status_code == 200
    saved = services.functions.get(fn.id)
    assert (saved.name, saved.category, saved.application_id) == ("Invoice v2", "DATA", app.id)


def test_function_through_the_wrong_application_is_404(client, services, hx):
    # Review Focus test (2)
    _, app_a = make_app(services)
    _, app_b = make_app(services)
    fn = services.functions.create({"application_id": app_a.id, "name": "Invoice"})
    wrong = f"/ui/applications/{app_b.id}/functions/{fn.id}"
    assert client.get(wrong + "/row", headers=hx).status_code == 404
    assert client.delete(wrong, headers=hx).status_code == 404
    assert services.functions.get(fn.id).name == "Invoice"


def test_functions_under_a_missing_application_are_404(client, hx):
    response = client.post(
        f"/ui/applications/{uuid4()}/functions?table=functions", data={"name": "F"}, headers=hx
    )
    assert response.status_code == 404 and response.headers["HX-Retarget"] == "#flash"


# ------------------------------------------------------------------ data types, technologies


def test_add_data_type_and_technology(client, services):
    _, app = make_app(services)
    dt = client.post(
        f"/ui/applications/{app.id}/data-types?table=data-types",
        data={
            "name": "Invoice",
            "confidentiality_level": "LOW",
            "golden_source": "ERP",
            "golden_replica": "DWH",
        },
    )
    assert dt.status_code == 201
    stored = services.data_types.list()[0]
    assert (stored.golden_source, stored.golden_replica) == ("ERP", "DWH")
    tech = client.post(
        f"/ui/applications/{app.id}/technologies?table=technologies",
        data={
            "name": "PostgreSQL",
            "version": "16",
            "type": "DATABASE",
            "standard_status": "REFERENCE",
            "tech_standards_link": "http://standards/pg",
        },
    )
    assert tech.status_code == 201
    assert services.technologies.list()[0].type == "DATABASE"


def test_technology_with_unknown_codes_is_422(client, services):
    _, app = make_app(services)
    base = f"/ui/applications/{app.id}/technologies?table=technologies"
    assert client.post(base, data={"name": "T", "type": "NOPE"}).status_code == 422
    assert client.post(base, data={"name": "T", "standard_status": "NOPE"}).status_code == 422
    assert services.technologies.list() == []


def test_data_type_and_technology_tabs_list_rows(client, services):
    _, app = make_app(services)
    services.data_types.create({"application_id": app.id, "name": "Invoice"})
    services.technologies.create({"application_id": app.id, "name": "PostgreSQL"})
    assert "Invoice" in client.get(f"/ui/applications/{app.id}/tabs/data-types").text
    assert "PostgreSQL" in client.get(f"/ui/applications/{app.id}/tabs/technologies").text


def test_deleting_an_application_deletes_through_the_details_button(client, services):
    team, app = make_app(services)
    response = client.delete(
        f"/ui/applications/{app.id}",
        headers={"HX-Current-URL": f"http://testserver/ui/applications/{app.id}?tab=functions"},
    )
    assert response.headers["HX-Redirect"] == f"/ui/teams/{team.id}"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/adapters/web/test_application_pages.py -v`
Expected: failures (404 on the application page and the nested routes).

- [ ] **Step 3: Add the application routes to `pages.py`**

In `src/archimaid/adapters/web/pages.py`, add these imports at the top:
```python
from fastapi import Depends

from archimaid.adapters.web.errors import inline_problem
from archimaid.adapters.web.forms import form_data, parse_form
from archimaid.adapters.web.resources import APPLICATION, TABS
from archimaid.domain.errors import DomainError
```
(Keep the existing imports; merge `Depends` into the existing `from fastapi import APIRouter, Request` line.)

Add these routes and the helper inside `pages_router`, before `return router`:
```python
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
```

- [ ] **Step 4: Write the templates**

`src/archimaid/adapters/web/templates/application.html`:
```html
{% extends "base.html" %}
{% block title %}{{ app.name }}{% endblock %}
{% block content %}
<nav aria-label="breadcrumb">
  <ul>
    <li><a href="/ui/teams">Teams</a></li>
    <li><a href="/ui/teams/{{ team.id }}">{{ team.name }}</a></li>
    <li>{{ app.name }}</li>
  </ul>
</nav>
<h1>{{ app.name }}</h1>
<div id="tab-panel">{% include "_tab_panel.html" %}</div>
{% endblock %}
```

`src/archimaid/adapters/web/templates/_tab_panel.html`:
```html
<nav class="tabs">
  <ul>
    {%- for key, label in TABS %}
    <li><a href="/ui/applications/{{ app.id }}?tab={{ key }}"
           hx-get="/ui/applications/{{ app.id }}/tabs/{{ key }}"
           hx-target="#tab-panel" hx-swap="innerHTML"
           hx-push-url="/ui/applications/{{ app.id }}?tab={{ key }}"
           {%- if key == tab %} aria-current="page"{% endif %}>{{ label }}</a></li>
    {%- endfor %}
  </ul>
</nav>
{% include "tabs/" ~ tab ~ ".html" %}
```

`src/archimaid/adapters/web/templates/tabs/details.html`:
```html
{% from "_resource.html" import widget, errors %}
<form hx-put="/ui/applications/{{ app.id }}/details" hx-target="#tab-panel" hx-swap="innerHTML">
  {{ errors(messages) }}
  {% if saved %}<p><ins>Saved.</ins></p>{% endif %}
  {%- for f in APPLICATION.editable() %}
  <label>{{ f.label }}{% if f.required %} *{% endif %}
    {{ widget(f, values.get(f.name), lookups) }}
  </label>
  {%- endfor %}
  <p><strong>RPO / RTO:</strong> {{ lookups.display(APPLICATION.field("rpo_rto"), app_values) }}</p>
  <button type="submit">Save</button>
</form>
<hr>
<button type="button" class="outline contrast"
        hx-delete="/ui/applications/{{ app.id }}"
        hx-confirm="{{ APPLICATION.confirm_delete() }}"
        hx-swap="none">Delete application</button>
```

`src/archimaid/adapters/web/templates/tabs/functions.html`:
```html
{% from "_resource.html" import table %}
{{ table(FUNCTION, rows, lookups, {"application_id": app.id}, "functions") }}
```

`src/archimaid/adapters/web/templates/tabs/data-types.html`:
```html
{% from "_resource.html" import table %}
{{ table(DATA_TYPE, rows, lookups, {"application_id": app.id}, "data-types") }}
```

`src/archimaid/adapters/web/templates/tabs/technologies.html`:
```html
{% from "_resource.html" import table %}
{{ table(TECHNOLOGY, rows, lookups, {"application_id": app.id}, "technologies") }}
```

`src/archimaid/adapters/web/templates/tabs/data-flows.html` (placeholder, replaced in Task 5):
```html
<p>Data flows are added in the next step.</p>
```

- [ ] **Step 5: Route the nested resources**

In `src/archimaid/adapters/web/app.py`: extend the resources import to
`from archimaid.adapters.web.resources import APPLICATION, DATA_TYPE, FUNCTION, MEMBER, PERSONA, TEAM, TECHNOLOGY, Resource`,
add this helper next to `team_parent`:
```python
    def application_parent(application_id: UUID) -> UUID:
        try:
            services.applications.get(application_id)
        except NotFound as exc:
            raise UiError(exc) from exc
        return application_id
```
and extend the `routed` list:
```python
    routed: list[tuple[Resource, Callable[..., UUID] | None]] = [
        (TEAM, None),
        (MEMBER, team_parent),
        (APPLICATION, None),
        (FUNCTION, application_parent),
        (DATA_TYPE, application_parent),
        (TECHNOLOGY, application_parent),
        (PERSONA, None),
    ]
```

- [ ] **Step 6: Run to verify it passes**

Run: `rtk proxy uv run pytest tests/adapters/web -v -rs`
Expected: all pass, 0 skipped, no warnings.

- [ ] **Step 7: Run the whole suite**

Run: `rtk proxy uv run pytest -rs`
Expected: everything passes.

- [ ] **Step 8: Commit**

```bash
git add src/archimaid/adapters/web tests/adapters/web
git commit -m "feat(web): application page with tabs, details form, functions, data types and technologies" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Data flows (application tab and overview page)

**Files:**
- Modify: `src/archimaid/adapters/web/pages.py`, `src/archimaid/adapters/web/app.py`, `src/archimaid/adapters/web/templates/tabs/data-flows.html`
- Create: `src/archimaid/adapters/web/templates/data_flows.html`
- Test: `tests/adapters/web/test_data_flows.py`

**Interfaces:**
- Consumes: Tasks 1-4. `tab_context` already supplies `outgoing_rows` and `incoming_rows` for the data-flows tab.
- Produces: the real `tabs/data-flows.html` (two tables); `GET /ui/data-flows` (read-only overview, no edit or delete buttons); `DATA_FLOW` routed at `/ui/data-flows` (flat; the application ids come from the form).

- [ ] **Step 1: Write the failing tests**

`tests/adapters/web/test_data_flows.py`:
```python
from uuid import uuid4


def setup_two_apps(services):
    team_a = services.teams.create({"name": "Team A"})
    team_b = services.teams.create({"name": "Team B"})
    source = services.applications.create({"team_id": team_a.id, "name": "Billing"})
    target = services.applications.create({"team_id": team_b.id, "name": "Ledger"})
    data_type = services.data_types.create({"application_id": source.id, "name": "Invoice"})
    return source, target, data_type


def make_flow(services, source, target, data_type, **extra):
    return services.data_flows.create(
        {
            "source_application_id": source.id,
            "target_application_id": target.id,
            "data_type_id": data_type.id,
            **extra,
        }
    )


def test_data_flows_tab_splits_outgoing_and_incoming(client, services):
    source, target, data_type = setup_two_apps(services)
    flow = make_flow(services, source, target, data_type, usage_mode="SOURCE")
    out = client.get(f"/ui/applications/{source.id}/tabs/data-flows").text
    assert 'id="rows-outgoing"' in out and 'id="rows-incoming"' in out
    outgoing = out[out.index('id="rows-outgoing"') : out.index('id="rows-incoming"')]
    incoming = out[out.index('id="rows-incoming"') :]
    assert f'<tr id="data-flow-{flow.id}"' in outgoing
    assert "<tr id=" not in incoming
    assert "Ledger" in outgoing and "Billing › Invoice" in outgoing and "Source" in outgoing
    inbound = client.get(f"/ui/applications/{target.id}/tabs/data-flows").text
    inbound_in = inbound[inbound.index('id="rows-incoming"') :]
    assert f'<tr id="data-flow-{flow.id}"' in inbound_in


def test_add_forms_prefill_this_application_as_source_or_target(client, services):
    source, target, _ = setup_two_apps(services)
    html = client.get(f"/ui/applications/{source.id}/tabs/data-flows").text
    assert 'hx-post="/ui/data-flows?table=outgoing"' in html
    assert 'hx-post="/ui/data-flows?table=incoming"' in html
    assert f'name="source_application_id" value="{source.id}"' in html
    assert f'name="target_application_id" value="{source.id}"' in html


def test_other_application_options_are_grouped_by_team_and_data_types_by_application(client, services):
    source, target, _ = setup_two_apps(services)
    html = client.get(f"/ui/applications/{source.id}/tabs/data-flows").text
    assert '<optgroup label="Team A">' in html and '<optgroup label="Team B">' in html
    assert '<optgroup label="Billing">' in html
    assert ">Billing › Invoice</option>" in html


def test_add_an_outgoing_flow(client, services):
    source, target, data_type = setup_two_apps(services)
    response = client.post(
        "/ui/data-flows?table=outgoing",
        data={
            "source_application_id": str(source.id),
            "target_application_id": str(target.id),
            "data_type_id": str(data_type.id),
            "usage_mode": "PROXY",
            "usage_explanation": "nightly export",
        },
    )
    assert response.status_code == 201
    flow = services.data_flows.list()[0]
    assert (flow.usage_mode, flow.usage_explanation) == ("PROXY", "nightly export")
    assert "nightly export" in response.text and "Ledger" in response.text


def test_flow_form_problems_are_422(client, services):
    # Review Focus test (4)
    source, target, data_type = setup_two_apps(services)
    full = {
        "source_application_id": str(source.id),
        "target_application_id": str(target.id),
        "data_type_id": str(data_type.id),
    }
    url = "/ui/data-flows?table=outgoing"
    missing = client.post(url, data={**full, "target_application_id": ""})
    assert missing.status_code == 422 and "Target application: is required" in missing.text
    ghost_type = client.post(url, data={**full, "data_type_id": str(uuid4())})
    assert ghost_type.status_code == 422 and "does not exist" in ghost_type.text
    ghost_app = client.post(url, data={**full, "source_application_id": str(uuid4())})
    assert ghost_app.status_code == 422
    bad_mode = client.post(url, data={**full, "usage_mode": "NOPE"})
    assert bad_mode.status_code == 422 and "is not a valid usage_mode" in bad_mode.text
    assert services.data_flows.list() == []


def test_flow_edit_row_has_source_target_and_data_type_selects(client, services):
    source, target, data_type = setup_two_apps(services)
    flow = make_flow(services, source, target, data_type)
    html = client.get(f"/ui/data-flows/{flow.id}/edit").text
    for name in ("source_application_id", "target_application_id", "data_type_id", "usage_mode"):
        assert f'name="{name}"' in html
    assert f'<option value="{target.id}" selected>' in html


def test_flow_save_and_delete(client, services):
    source, target, data_type = setup_two_apps(services)
    flow = make_flow(services, source, target, data_type)
    saved = client.put(
        f"/ui/data-flows/{flow.id}",
        data={
            "source_application_id": str(source.id),
            "target_application_id": str(source.id),
            "data_type_id": str(data_type.id),
            "usage_mode": "CONSUMER",
            "usage_explanation": "internal",
        },
    )
    assert saved.status_code == 200
    stored = services.data_flows.get(flow.id)
    assert (stored.target_application_id, stored.usage_mode) == (source.id, "CONSUMER")
    assert client.delete(f"/ui/data-flows/{flow.id}").status_code == 200
    assert services.data_flows.list() == []


def test_overview_lists_every_flow_with_links_and_no_actions(client, services):
    source, target, data_type = setup_two_apps(services)
    make_flow(services, source, target, data_type, usage_mode="SOURCE", usage_explanation="export")
    response = client.get("/ui/data-flows")
    html = response.text
    assert response.status_code == 200 and "<html" in html
    assert f'href="/ui/applications/{source.id}"' in html and "Billing" in html
    assert f'href="/ui/applications/{target.id}"' in html and "Ledger" in html
    assert "Invoice" in html and "Source" in html and "export" in html
    assert "hx-delete" not in html and "hx-get" not in html and "hx-post" not in html


def test_overview_escapes_explanations(client, services):
    # Review Focus test (1)
    source, target, data_type = setup_two_apps(services)
    make_flow(services, source, target, data_type, usage_explanation="<img src=x onerror=alert(1)>")
    html = client.get("/ui/data-flows").text
    assert "<img src=x" not in html and "&lt;img src=x" in html


def test_an_application_used_by_a_flow_cannot_be_deleted_in_the_ui(client, services, repos, hx):
    # Review Focus test (2): the fake repository does not model foreign keys, so mark it in use
    source, target, data_type = setup_two_apps(services)
    make_flow(services, source, target, data_type)
    repos.applications.mark_in_use(target.id)
    response = client.delete(f"/ui/applications/{target.id}", headers=hx)
    assert response.status_code == 409
    assert response.headers["HX-Retarget"] == "#flash" and "still referenced" in response.text
    assert services.applications.get(target.id).name == "Ledger"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/adapters/web/test_data_flows.py -v`
Expected: failures (the tab shows the placeholder; `POST /ui/data-flows` and `GET /ui/data-flows` do not exist).

- [ ] **Step 3: Replace the data-flows tab**

`src/archimaid/adapters/web/templates/tabs/data-flows.html`:
```html
{% from "_resource.html" import table %}
<h3>Outgoing</h3>
<p><small>This application is the source.</small></p>
{{ table(DATA_FLOW, outgoing_rows, lookups, {}, "outgoing", {"source_application_id": app.id}) }}
<h3>Incoming</h3>
<p><small>This application is the target.</small></p>
{{ table(DATA_FLOW, incoming_rows, lookups, {}, "incoming", {"target_application_id": app.id}) }}
```

- [ ] **Step 4: Add the overview page**

In `src/archimaid/adapters/web/pages.py`, add inside `pages_router` before `return router`:
```python
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
```
and add `DATA_FLOW` to the resources import: `from archimaid.adapters.web.resources import APPLICATION, DATA_FLOW, TABS`.

`src/archimaid/adapters/web/templates/data_flows.html`:
```html
{% extends "base.html" %}
{% block title %}Data flows{% endblock %}
{% block content %}
<h1>Data flows</h1>
<p><small>Read-only overview. Flows are added and edited on each application's "Data flows" tab.</small></p>
<figure>
  <table>
    <thead><tr><th>Source</th><th>Target</th><th>Data type</th><th>Usage mode</th><th>Explanation</th></tr></thead>
    <tbody>
      {%- for f in flows %}
      <tr>
        <td><a href="/ui/applications/{{ f.source_id }}">{{ f.source_name }}</a></td>
        <td><a href="/ui/applications/{{ f.target_id }}">{{ f.target_name }}</a></td>
        <td>{{ f.data_type }}</td>
        <td>{{ f.usage_mode }}</td>
        <td>{{ f.explanation }}</td>
      </tr>
      {%- endfor %}
    </tbody>
  </table>
</figure>
{% endblock %}
```

- [ ] **Step 5: Route the flow resource**

In `src/archimaid/adapters/web/app.py`, add `DATA_FLOW` to the resources import and to the `routed` list (after `TECHNOLOGY`): `(DATA_FLOW, None),`.

- [ ] **Step 6: Run to verify it passes**

Run: `rtk proxy uv run pytest tests/adapters/web -v -rs`
Expected: all pass, 0 skipped, no warnings.

- [ ] **Step 7: Run the whole suite**

Run: `rtk proxy uv run pytest -rs`
Expected: everything passes.

- [ ] **Step 8: Commit**

```bash
git add src/archimaid/adapters/web tests/adapters/web
git commit -m "feat(web): data flows tab and overview page" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Reference data admin UI

**Files:**
- Create: `src/archimaid/adapters/web/reference.py`, templates `reference_index.html`, `reference_kind.html`
- Modify: `src/archimaid/adapters/web/app.py`
- Test: `tests/adapters/web/test_reference_ui.py`

**Interfaces:**
- Consumes: `reference_resource(kind)` (Task 1), `parse_form`, `form_data`, `Lookups`, `render`, `UiError`, `inline_problem`, `Services.reference` (`kinds()`, `list`, `get`, `create`, `update`, `delete`).
- Produces: `reference_router(services) -> APIRouter` with `GET /ui/reference` (index), `GET /ui/reference/{kind}` (page), and the action routes under `/ui/reference/{kind}`: `POST`, `GET /{code}/row`, `GET /{code}/edit`, `PUT /{code}`, `DELETE /{code}`. An unknown kind is a 404 (page or flash). A row's id is the code; its HTML id is `ref-<kind>-<code>`. The add form's table id is `reference`.

- [ ] **Step 1: Write the failing tests**

`tests/adapters/web/test_reference_ui.py`:
```python
def test_index_lists_the_eight_catalogs(client):
    html = client.get("/ui/reference").text
    assert "<html" in html
    for kind in (
        "confidentiality_level", "integrity_level", "availability_level", "traceability_level",
        "function_category", "usage_mode", "technology_type", "tech_standard_status",
    ):
        assert f'href="/ui/reference/{kind}"' in html


def test_ranked_kind_page_lists_values_by_rank_with_a_rank_column(client):
    html = client.get("/ui/reference/integrity_level").text
    assert "<html" in html and "<th scope=\"col\">Rank</th>" in html
    positions = [
        html.index(f'id="ref-integrity_level-{code}"')
        for code in ("EXTREME", "SERIOUS", "MODERATE", "LOW")
    ]
    assert positions == sorted(positions)
    assert 'hx-post="/ui/reference/integrity_level?table=reference"' in html
    assert "renames it everywhere" in html


def test_plain_kind_has_no_rank_and_availability_has_hours(client):
    plain = client.get("/ui/reference/usage_mode").text
    assert "Rank" not in plain
    avail = client.get("/ui/reference/availability_level").text
    assert "RPO (hours)" in avail and "RTO (hours)" in avail


def test_unknown_kind_is_a_404_page_and_a_404_flash(client, hx):
    assert client.get("/ui/reference/nope").status_code == 404
    response = client.post("/ui/reference/nope?table=reference", data={"code": "X"}, headers=hx)
    assert response.status_code == 404 and response.headers["HX-Retarget"] == "#flash"


def test_add_a_plain_value(client, catalog):
    response = client.post(
        "/ui/reference/function_category?table=reference",
        data={"code": "EXTRA", "label": "Extra", "description": ""},
    )
    assert response.status_code == 201
    assert catalog.exists("function_category", "EXTRA")
    assert '<tr id="ref-function_category-EXTRA"' in response.text
    assert 'hx-get="/ui/reference/function_category/EXTRA/edit"' in response.text


def test_add_a_ranked_and_an_availability_value(client, catalog):
    ranked = client.post(
        "/ui/reference/integrity_level?table=reference",
        data={"code": "TINY", "label": "Tiny", "rank": "0"},
    )
    assert ranked.status_code == 201 and catalog.get("integrity_level", "TINY").rank == 0
    avail = client.post(
        "/ui/reference/availability_level?table=reference",
        data={"code": "MINI", "label": "Mini", "rank": "0", "rpo_hours": "1", "rto_hours": "2"},
    )
    assert avail.status_code == 201
    assert catalog.get("availability_level", "MINI").rto_hours == 2


def test_add_problems_are_422_or_409(client, catalog):
    # Review Focus test (4) and (5)
    url = "/ui/reference/integrity_level?table=reference"
    for code in ("a/b", "lower", "A B", "É"):
        response = client.post(url, data={"code": code, "label": "x", "rank": "1"})
        assert response.status_code == 422, code
        assert "code must contain only" in response.text
    # surrounding whitespace is stripped by the form, so " PAD " is accepted as "PAD"
    padded = client.post(url, data={"code": " PAD ", "label": "Pad", "rank": "1"})
    assert padded.status_code == 201 and catalog.exists("integrity_level", "PAD")
    not_a_number = client.post(url, data={"code": "NUM", "label": "x", "rank": "1.5"})
    assert not_a_number.status_code == 422 and "Rank: must be a whole number" in not_a_number.text
    no_rank = client.post(url, data={"code": "NUM", "label": "x", "rank": ""})
    assert no_rank.status_code == 422 and "Rank: is required" in no_rank.text
    blank_label = client.post(url, data={"code": "NUM", "label": " ", "rank": "1"})
    assert blank_label.status_code == 422 and "label must not be blank" in blank_label.text
    duplicate = client.post(url, data={"code": "LOW", "label": "again", "rank": "1"})
    assert duplicate.status_code == 409 and "already exists" in duplicate.text
    assert duplicate.headers["HX-Retarget"] == "#add-errors-reference"
    assert not catalog.exists("integrity_level", "NUM")


def test_hostile_text_in_a_label_is_escaped(client, catalog):
    # Review Focus test (1)
    client.post(
        "/ui/reference/usage_mode?table=reference",
        data={"code": "XSS", "label": '<script>alert(1)</script>"'},
    )
    html = client.get("/ui/reference/usage_mode").text
    assert "<script>alert(1)" not in html and "&lt;script&gt;" in html


def test_edit_row_and_save(client, catalog):
    edit = client.get("/ui/reference/availability_level/SERIOUS/edit")
    assert edit.status_code == 200 and "<html" not in edit.text
    assert 'name="code"' in edit.text and 'value="SERIOUS"' in edit.text
    assert 'name="rpo_hours"' in edit.text and 'value="4"' in edit.text
    assert 'hx-put="/ui/reference/availability_level/SERIOUS"' in edit.text
    saved = client.put(
        "/ui/reference/availability_level/SERIOUS",
        data={"code": "SERIOUS", "label": "Serious", "description": "", "rank": "3",
              "rpo_hours": "1", "rto_hours": "1"},
    )
    assert saved.status_code == 200
    assert catalog.get("availability_level", "SERIOUS").rpo_hours == 1


def test_rename_changes_the_row_id_and_the_stored_code(client, catalog):
    # Review Focus test (5)
    client.post("/ui/reference/function_category?table=reference", data={"code": "EXTRA", "label": "Extra"})
    response = client.put(
        "/ui/reference/function_category/EXTRA",
        data={"code": "EXTRA2", "label": "Extra", "description": ""},
    )
    assert response.status_code == 200
    assert '<tr id="ref-function_category-EXTRA2"' in response.text
    assert catalog.exists("function_category", "EXTRA2") and not catalog.exists("function_category", "EXTRA")


def test_rename_onto_an_existing_code_is_409_and_keeps_the_edit_row(client, catalog):
    response = client.put(
        "/ui/reference/function_category/DATA",
        data={"code": "COMMON", "label": "x", "description": ""},
    )
    assert response.status_code == 409 and "already exists" in response.text
    assert 'hx-put="/ui/reference/function_category/DATA"' in response.text
    assert catalog.exists("function_category", "DATA")


def test_save_with_a_bad_code_or_number_is_422(client, catalog):
    bad_code = client.put(
        "/ui/reference/function_category/DATA", data={"code": "a/b", "label": "x"}
    )
    assert bad_code.status_code == 422
    bad_number = client.put(
        "/ui/reference/integrity_level/LOW", data={"code": "LOW", "label": "Low", "rank": "x"}
    )
    assert bad_number.status_code == 422 and "Rank: must be a whole number" in bad_number.text
    assert catalog.exists("function_category", "DATA")


def test_delete_a_value_and_a_blocked_delete(client, catalog, hx):
    client.post("/ui/reference/function_category?table=reference", data={"code": "EXTRA", "label": "Extra"})
    ok = client.delete("/ui/reference/function_category/EXTRA")
    assert ok.status_code == 200 and ok.text == ""
    assert not catalog.exists("function_category", "EXTRA")
    catalog.mark_in_use("usage_mode", "PROXY")
    blocked = client.delete("/ui/reference/usage_mode/PROXY", headers=hx)
    assert blocked.status_code == 409 and blocked.headers["HX-Retarget"] == "#flash"
    assert "still referenced" in blocked.text and catalog.exists("usage_mode", "PROXY")


def test_missing_value_is_a_404_flash(client, hx):
    for method, url in (
        ("get", "/ui/reference/usage_mode/NOPE/row"),
        ("get", "/ui/reference/usage_mode/NOPE/edit"),
        ("delete", "/ui/reference/usage_mode/NOPE"),
    ):
        response = getattr(client, method)(url, headers=hx)
        assert response.status_code == 404 and response.headers["HX-Retarget"] == "#flash", url


def test_a_renamed_level_shows_up_in_application_forms(client, services, catalog):
    # Review Focus test (5): the dropdowns read the catalog on every render
    client.put(
        "/ui/reference/integrity_level/LOW",
        data={"code": "TRIVIAL", "label": "Trivial", "description": "", "rank": "1"},
    )
    team = services.teams.create({"name": "T"})
    html = client.get(f"/ui/teams/{team.id}").text
    integrity = html[html.index('name="integrity_level"') :]
    integrity = integrity[: integrity.index("</select>")]
    assert '<option value="TRIVIAL"' in integrity and '<option value="LOW"' not in integrity
```

Note: the fake catalog does not cascade renames to entities (only the Postgres tests cover that); the test above only checks the dropdown.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/adapters/web/test_reference_ui.py -v`
Expected: failures (404 on every `/ui/reference...` route).

- [ ] **Step 3: Implement the reference router**

`src/archimaid/adapters/web/reference.py`:
```python
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
        table_id = table or "reference"
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
        fetch(kind, code)
        data, problems = parse_form(form, resource.form())
        status = 422
        if not problems:
            try:
                value = services.reference.update(kind, code, data)
            except DomainError as exc:
                problems, status = inline_problem(exc)
            else:
                return row_page(request, "_row.html", resource, view(value))
        values = {**form, "id": code}
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
```

- [ ] **Step 4: Write the templates**

`src/archimaid/adapters/web/templates/reference_index.html`:
```html
{% extends "base.html" %}
{% block title %}Reference data{% endblock %}
{% block content %}
<h1>Reference data</h1>
<p><small>Configuration tables behind the dropdowns. Changes apply everywhere immediately.</small></p>
<ul>
  {%- for kind, title, count in kinds %}
  <li><a href="/ui/reference/{{ kind }}">{{ title }}</a> ({{ count }})</li>
  {%- endfor %}
</ul>
{% endblock %}
```

`src/archimaid/adapters/web/templates/reference_kind.html`:
```html
{% extends "base.html" %}
{% from "_resource.html" import table %}
{% block title %}{{ title }}{% endblock %}
{% block content %}
<nav aria-label="breadcrumb">
  <ul><li><a href="/ui/reference">Reference data</a></li><li>{{ title }}</li></ul>
</nav>
<h1>{{ title }}</h1>
<p><small>Changing a code renames it everywhere it is used. A value that is still referenced cannot be deleted. Codes use A-Z, 0-9 and underscore.</small></p>
{{ table(resource, rows, lookups, {}, "reference") }}
{% endblock %}
```

- [ ] **Step 5: Mount the router**

In `src/archimaid/adapters/web/app.py`, add `from archimaid.adapters.web.reference import reference_router` and, right after `app.include_router(pages_router(services), include_in_schema=False)`, add:
```python
    app.include_router(reference_router(services), include_in_schema=False)
```

- [ ] **Step 6: Run to verify it passes**

Run: `rtk proxy uv run pytest tests/adapters/web -v -rs`
Expected: all pass, 0 skipped, no warnings.

- [ ] **Step 7: Run the whole suite**

Run: `rtk proxy uv run pytest -rs`
Expected: everything passes.

- [ ] **Step 8: Commit**

```bash
git add src/archimaid/adapters/web tests/adapters/web
git commit -m "feat(web): reference data admin pages with inline editing" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: End-to-end test on Postgres, packaging check, docs, lint and types

**Files:**
- Create: `tests/test_web_end_to_end_postgres.py`
- Modify: `CLAUDE.md`; fix any ruff/mypy findings in the new code

**Interfaces:**
- Consumes: everything above plus `build_repositories`, `PostgresReferenceCatalog`, `build_services`, `create_app`, and the `engine` fixture.

- [ ] **Step 1: Write the end-to-end test**

`tests/test_web_end_to_end_postgres.py`:
```python
import re

import pytest
from fastapi.testclient import TestClient

from archimaid.adapters.api.app import create_app
from archimaid.adapters.persistence.catalog import PostgresReferenceCatalog
from archimaid.adapters.persistence.repository import build_repositories
from archimaid.application.services import build_services

pytestmark = pytest.mark.postgres


@pytest.fixture
def client(engine):
    services = build_services(build_repositories(engine), PostgresReferenceCatalog(engine))
    return TestClient(create_app(services))


def row_id(html, prefix):
    return re.search(rf'<tr id="{prefix}-([0-9a-f-]+)"', html).group(1)


def test_web_ui_scenario_over_real_postgres(client):
    hx = {"HX-Request": "true"}

    team = row_id(client.post("/ui/teams?table=teams", data={"name": "Payments"}).text, "team")
    app_a = row_id(
        client.post(
            "/ui/applications?table=applications",
            data={"team_id": team, "name": "Billing", "availability_level": "SERIOUS"},
        ).text,
        "application",
    )
    app_b = row_id(
        client.post("/ui/applications?table=applications", data={"team_id": team, "name": "Ledger"}).text,
        "application",
    )
    assert "4 h / 0 h" in client.get(f"/ui/teams/{team}").text

    function = client.post(
        f"/ui/applications/{app_a}/functions?table=functions",
        data={"name": "Invoice", "category": "BUSINESS"},
    )
    assert function.status_code == 201
    data_type = row_id(
        client.post(
            f"/ui/applications/{app_a}/data-types?table=data-types",
            data={"name": "Invoice", "confidentiality_level": "LOW"},
        ).text,
        "data-type",
    )
    flow = client.post(
        "/ui/data-flows?table=outgoing",
        data={
            "source_application_id": app_a,
            "target_application_id": app_b,
            "data_type_id": data_type,
            "usage_mode": "SOURCE",
        },
    )
    assert flow.status_code == 201
    overview = client.get("/ui/data-flows").text
    assert "Billing" in overview and "Ledger" in overview

    # blocked deletes are flash messages with no Postgres text
    blocked_team = client.delete(f"/ui/teams/{team}", headers=hx)
    assert blocked_team.status_code == 409 and blocked_team.headers["HX-Retarget"] == "#flash"
    blocked_app = client.delete(f"/ui/applications/{app_b}", headers=hx)
    assert blocked_app.status_code == 409
    for body in (blocked_team.text, blocked_app.text):
        assert "violates" not in body and "_fkey" not in body

    # hostile input is a 422, never a 500
    assert client.post("/ui/teams?table=teams", data={"name": "x\u0000"}).status_code == 422
    assert client.post(
        "/ui/reference/integrity_level?table=reference",
        data={"code": "BIG", "label": "Big", "rank": str(2**40)},
    ).status_code == 422
    assert client.post(
        "/ui/reference/usage_mode?table=reference", data={"code": "A/B", "label": "x"}
    ).status_code == 422

    # renaming a catalog code shows the new label in the application rows
    renamed = client.put(
        "/ui/reference/availability_level/SERIOUS",
        data={"code": "HIGH", "label": "High", "description": "", "rank": "3",
              "rpo_hours": "4", "rto_hours": "0"},
    )
    assert renamed.status_code == 200
    team_page = client.get(f"/ui/teams/{team}").text
    assert "High" in team_page and "4 h / 0 h" in team_page
    assert client.delete("/ui/reference/availability_level/HIGH", headers=hx).status_code == 409

    # deleting from the application's own page redirects to the team
    flow_id = row_id(client.get(f"/ui/applications/{app_a}/tabs/data-flows").text, "data-flow")
    assert client.delete(f"/ui/data-flows/{flow_id}").status_code == 200
    own_page = {"HX-Current-URL": f"http://testserver/ui/applications/{app_a}?tab=details"}
    deleted = client.delete(f"/ui/applications/{app_a}", headers=own_page)
    assert deleted.headers["HX-Redirect"] == f"/ui/teams/{team}"
    assert client.get(f"/ui/applications/{app_a}").status_code == 404
```

- [ ] **Step 2: Run it**

Run: `rtk proxy uv run pytest tests/test_web_end_to_end_postgres.py -v -rs`
Expected: PASS (not skipped). If it fails, the cause is a defect in an earlier task's code or templates: diagnose it, fix the minimal code, and record the defect, file and line in your report. Do not weaken the test.

- [ ] **Step 3: Check packaging**

Run:
```bash
uv build --wheel -o /tmp/archimaid-wheel
unzip -l /tmp/archimaid-wheel/*.whl | grep -E "web/(templates|static)/" | awk '{print $4}' | sort
rm -rf /tmp/archimaid-wheel
```
Expected: the list includes `htmx.min.js`, `pico.min.css`, `app.css`, `VENDORED.md`, `base.html`, `_resource.html`, `tabs/details.html`, `tabs/data-flows.html`, `reference_kind.html` and every other template. If anything is missing, fix `pyproject.toml` (hatch `[tool.hatch.build.targets.wheel]`) so non-Python files under `src/archimaid` ship.

- [ ] **Step 4: Lint and type-check**

Run: `uv run ruff check src tests && uv run mypy src`
Expected: clean. Fix findings in the code without loosening the config. Long single-line template-test strings may trip E501: wrap them. A narrowly targeted `# type: ignore[code]` with a reason is acceptable only for FastAPI's `add_exception_handler` typing. Do not run `ruff format` on files outside the web adapter and its tests.

- [ ] **Step 5: Update `CLAUDE.md`**

In `CLAUDE.md`: in the Architecture list, add this bullet after the `adapters/api/` bullet:
```
- `adapters/web/`: the HTMX + Jinja2 UI under `/ui` (pages and inline editing; no Node/npm; assets vendored in `static/`, see `static/VENDORED.md`). It calls the application services directly. Entities are described as `Resource`/`Field` data in `resources.py`; `resource_router.py` and the macros in `templates/_resource.html` render and serve any of them. Page routes return full pages, row/tab/error routes return fragments; errors that a form cannot show in place go to the `#flash` area through `HX-Retarget` (see `errors.py`).
```
In the Commands block, add after the uvicorn line:
```
# web UI: http://localhost:8000/ui/  (the JSON API's docs are at /docs)
```
Add one line to "Key design rules": `- **Web forms only send the fields they show.** \`CrudService.update\` replaces only the keys it receives, so a table row that hides fields never wipes them.`

- [ ] **Step 6: Final verification**

Run: `rtk proxy uv run pytest -rs`
Expected: all tests pass, 0 skipped, 0 warnings. Run `podman ps -a` and confirm nothing is left running. Start the app and fetch a page, as a smoke test:
```bash
podman run -d --name archimaid-smoke-db -e POSTGRES_USER=archimaid -e POSTGRES_PASSWORD=archimaid -e POSTGRES_DB=archimaid -p 55432:5432 docker.io/library/postgres:16-alpine
sleep 5
export DATABASE_URL=postgresql+psycopg://archimaid:archimaid@localhost:55432/archimaid
uv run python -m archimaid.adapters.persistence.migrate
uv run uvicorn archimaid.main:build_app --factory --port 8123 &
UVICORN_PID=$!
sleep 3
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" http://localhost:8123/
curl -s http://localhost:8123/ui/teams | grep -c "htmx.min.js"
curl -s http://localhost:8123/ui/reference/availability_level | grep -c "ref-availability_level-SERIOUS"
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8123/ui/static/pico.min.css
kill $UVICORN_PID; podman rm -f archimaid-smoke-db
podman ps -a; pgrep -a uvicorn | wc -l
```
Expected: `307 http://localhost:8123/ui/`, then `1`, `1`, `200`, and no containers or uvicorn processes left. Paste the output into the report.

- [ ] **Step 7: Commit**

```bash
git add tests/test_web_end_to_end_postgres.py CLAUDE.md src tests pyproject.toml uv.lock
git commit -m "feat(web): end-to-end test on Postgres, packaging check and docs" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-review against the spec

- **Decisions 1-7** (HTMX + Jinja2 adapter; services not the JSON API; drill-down; inline editing; English; Pico.css; resource/field-driven templates): Tasks 0-6.
- **Structure and dependencies** (package layout, jinja2, python-multipart, vendored assets with `VENDORED.md`): Tasks 0-2, 7 (wheel check).
- **URLs table**: Task 0 (redirects, static), Task 2 (teams, personas, action routes), Task 3 (team page, members, applications), Task 4 (application page, tabs, details), Task 5 (data flows page and flow actions), Task 6 (reference pages and actions). `POST /ui/applications` takes `team_id` from the hidden input, as the spec says.
- **Pages**: the details, functions, data types, technologies and data flows tabs (Tasks 4-5), RPO/RTO as "4 h / 0 h" or "—" (Tasks 2-4), data type dropdown "Application › Data type" grouped by application (Task 2 `Lookups`, Task 5 tests).
- **Interaction**: row targets, add form prepend, oob error clearing, `hx-confirm` with the application warning, `responseHandling` meta, fragment-by-route, flash area, `HX-Redirect` after deleting from the record's own page, partial-form updates: Tasks 2-4.
- **Forms and errors**: parsing rules and banner messages (Task 1, Task 2), statuses (Task 2), escaping (Review Focus 1).
- **Testing section**: per-resource tests, dropdown order, derived RPO/RTO, escaping, fragments versus pages, reference admin, form parsing, packaging (Task 7 wheel check; Task 0 asserts the assets are served and hashed), end-to-end (Task 7).
- **Gaps recorded:** the spec's "packaging: templates and static files resolve at runtime from an installed package" is checked by listing the built wheel (Task 7 step 3) and by `StaticFiles`/`Jinja2Templates` loading from `Path(__file__)` in the other tests; it is not a test that installs the wheel.
