# Function-level data flows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A data flow end can also name a function (`source_function_id`, `target_function_id`) while keeping its application ids, across the domain, database, services, JSON API, web UI and diagram builder.

**Architecture:** Each end keeps its required application id and gains an optional function id. The function must belong to the application on the same end; this is checked in `CrudService` through a new `ParentLink.owner_field`. The database FK is `ON DELETE SET NULL`. The diagram builder ignores third-party functions, records the current application's function as `function_index` on a `DiagramFlow`, and the layout does not use it yet.

**Tech Stack:** Python 3.13, SQLAlchemy Core, Alembic, FastAPI, Jinja2 + HTMX, pytest, testcontainers (Postgres 16), `uv`, `ruff`, `mypy`.

**Spec:** `docs/superpowers/specs/2026-10-05-archimaid-function-flows-design.md` (read it first; it wins over this plan where they differ).

## Global Constraints

- Hexagonal: `domain` imports no framework; `adapters` depend on `application`, which depends on `ports`/`domain` (CLAUDE.md).
- Value objects are catalog tables; this change adds none.
- `tables.py` must stay in sync with the Alembic migrations; a test compares them.
- Errors: `InvalidEntity` / `DanglingReference` → 422; `ReferenceInUse` / `AlreadyExists` → 409; `NotFound` → 404.
- `CrudService.update` replaces only the keys it receives; the check runs on the merged entity.
- Web forms only send the fields they show.
- No Node/npm; no new dependency.
- The diagram's look does not change in this cycle: `test_reproduces_the_approved_sample_files` must keep passing untouched.
- Unit tests use the in-memory fakes in `tests/fakes.py`; adapter and end-to-end tests use real Postgres via testcontainers (`-m postgres`, needs a container runtime, see `.env.example`).
- Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Moving a flow end to another application without clearing its function must give 422, not store an inconsistent flow (Task 2).
2. Deleting a function that a flow uses must keep the flow and null the end, never 409 and never delete the flow (Task 1).
3. A function of another application on the *target* end (not only the source end) must be rejected (Task 2).
4. Choosing "—" in an edit row's function select must clear the function (Task 4).
5. A flow to a function of a third-party application must be drawn to its parent application, and a function-to-function flow inside one application must be counted, not drawn (Task 5).
6. Existing flows must survive the migration with both function ends NULL (Task 1).

## File Structure

| File | Change |
|---|---|
| `src/archimaid/domain/entities.py` | `DataFlow` gets two optional fields |
| `src/archimaid/adapters/persistence/tables.py` | two nullable `SET NULL` columns |
| `src/archimaid/adapters/persistence/migrations/versions/0003_data_flow_functions.py` | new migration |
| `src/archimaid/application/crud.py` | `ParentLink.owner_field` and its check |
| `src/archimaid/application/services.py` | two `ParentLink`s on data flows |
| `src/archimaid/adapters/api/schemas.py` | two optional fields on `DataFlowIn` |
| `src/archimaid/adapters/web/resources.py` | two `select_entity` fields on `DATA_FLOW`, new `functions` source |
| `src/archimaid/adapters/web/render.py` | `Lookups._functions` |
| `src/archimaid/adapters/web/pages.py`, `templates/data_flows.html` | function columns on the overview |
| `src/archimaid/adapters/web/diagram/model.py`, `builder.py` | `function_index` |
| `domain.puml`, backend spec | document the two associations and rules |
| tests | one file or section per task, named in each task |

---

### Task 1: Entity, schema, migration

**Files:**
- Modify: `src/archimaid/domain/entities.py` (class `DataFlow`)
- Modify: `src/archimaid/adapters/persistence/tables.py` (`data_flow`)
- Create: `src/archimaid/adapters/persistence/migrations/versions/0003_data_flow_functions.py`
- Test: `tests/domain/test_entities.py`, `tests/adapters/persistence/test_repository.py`, `tests/adapters/persistence/test_migration_0003.py` (new)

**Interfaces:**
- Produces: `DataFlow.source_function_id: UUID | None = None`, `DataFlow.target_function_id: UUID | None = None`; table columns `data_flow.source_function_id`, `data_flow.target_function_id` (FK `function.id`, `ON DELETE SET NULL`, nullable).

- [ ] **Step 1: Write the failing tests**

Append to `tests/domain/test_entities.py` (reuse the file's existing imports; add `DataFlow`, `UUID`/`uuid4`, `datetime` imports if missing):

```python
def test_data_flow_function_ends_default_to_none():
    flow = DataFlow(
        id=uuid4(), created_at=NOW, updated_at=NOW,
        source_application_id=uuid4(), target_application_id=uuid4(), data_type_id=uuid4(),
    )
    assert flow.source_function_id is None and flow.target_function_id is None
```

(If the file has no `NOW` constant, define `NOW = datetime(2026, 1, 1, tzinfo=UTC)` at the top.)

Append to `tests/adapters/persistence/test_repository.py`:

```python
def add_function(repos, app, name="Create invoice"):
    function = Function(application_id=app.id, name=name, **meta())
    repos.functions.add(function)
    return function


def add_function_flow(repos):
    team = add_team(repos)
    source, target = add_app(repos, team, "Billing"), add_app(repos, team, "Ledger")
    data_type = DataType(application_id=source.id, name="Invoice", **meta())
    repos.data_types.add(data_type)
    sender, receiver = add_function(repos, source), add_function(repos, target, "Post entry")
    flow = DataFlow(
        source_application_id=source.id, source_function_id=sender.id,
        target_application_id=target.id, target_function_id=receiver.id,
        data_type_id=data_type.id, **meta(),
    )
    repos.data_flows.add(flow)
    return flow, source, target, sender, receiver


def test_data_flow_round_trips_function_ends(repos):
    flow, *_ = add_function_flow(repos)
    assert repos.data_flows.get(flow.id) == flow


def test_deleting_a_function_keeps_the_flow_and_nulls_that_end(repos):
    # Review Focus test (2)
    flow, _, _, sender, receiver = add_function_flow(repos)
    repos.functions.delete(sender.id)
    stored = repos.data_flows.get(flow.id)
    assert stored is not None
    assert stored.source_function_id is None
    assert stored.target_function_id == receiver.id


def test_deleting_an_application_used_by_a_function_flow_is_still_blocked(repos):
    _, _, target, _, _ = add_function_flow(repos)
    with pytest.raises(ReferenceInUse):
        repos.applications.delete(target.id)
```

Create `tests/adapters/persistence/test_migration_0003.py`:

```python
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

import archimaid.adapters.persistence.migrate as migrate_module

pytestmark = pytest.mark.postgres


def _config(url: str) -> Config:
    config = Config()
    config.set_main_option(
        "script_location", str(Path(migrate_module.__file__).parent / "migrations")
    )
    config.set_main_option("sqlalchemy.url", url)
    return config


def _columns(engine) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns("data_flow")}


def test_existing_flows_survive_the_upgrade_and_downgrade_removes_the_columns(postgres_url):
    # Review Focus test (6)
    engine = create_engine(postgres_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    config = _config(postgres_url)
    command.upgrade(config, "0002")
    assert "source_function_id" not in _columns(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO team (id, name, description, created_at, updated_at) "
                "VALUES ('00000000-0000-0000-0000-000000000001', 'T', '', now(), now())"
            )
        )
        conn.execute(
            text(
                "INSERT INTO application (id, team_id, name, created_at, updated_at) "
                "VALUES ('00000000-0000-0000-0000-000000000002', "
                "'00000000-0000-0000-0000-000000000001', 'A', now(), now())"
            )
        )
        conn.execute(
            text(
                "INSERT INTO data_type (id, application_id, name, created_at, updated_at) "
                "VALUES ('00000000-0000-0000-0000-000000000003', "
                "'00000000-0000-0000-0000-000000000002', 'D', now(), now())"
            )
        )
        conn.execute(
            text(
                "INSERT INTO data_flow (id, source_application_id, target_application_id, "
                "data_type_id, created_at, updated_at) VALUES "
                "('00000000-0000-0000-0000-000000000004', "
                "'00000000-0000-0000-0000-000000000002', "
                "'00000000-0000-0000-0000-000000000002', "
                "'00000000-0000-0000-0000-000000000003', now(), now())"
            )
        )
    command.upgrade(config, "head")
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT source_function_id, target_function_id FROM data_flow")
        ).one()
    assert tuple(row) == (None, None)
    command.downgrade(config, "0002")
    assert "source_function_id" not in _columns(engine)
    assert "target_function_id" not in _columns(engine)
    engine.dispose()
```

If an INSERT fails because a column it omits is `NOT NULL` in `0001_schema.py`, add that column and a value to that INSERT; do not change the schema.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/domain/test_entities.py tests/adapters/persistence -q`
Expected: FAIL (`unexpected keyword argument 'source_function_id'`, and the migration test cannot find `0003`/the columns).

- [ ] **Step 3: Implement**

In `entities.py`, `DataFlow` becomes:

```python
@dataclass(kw_only=True)
class DataFlow(Entity):
    required_text: ClassVar[tuple[str, ...]] = ()

    source_application_id: UUID
    target_application_id: UUID
    data_type_id: UUID
    source_function_id: UUID | None = None
    target_function_id: UUID | None = None
    usage_mode: str | None = None
    usage_explanation: str | None = None
```

In `tables.py`, `data_flow` becomes:

```python
data_flow = Table(
    "data_flow",
    metadata,
    _id(),
    _id_ref("source_application_id", "application", "RESTRICT"),
    _id_ref("target_application_id", "application", "RESTRICT"),
    _id_ref("data_type_id", "data_type", "RESTRICT"),
    _id_ref("source_function_id", "function", "SET NULL", nullable=True),
    _id_ref("target_function_id", "function", "SET NULL", nullable=True),
    _code_ref("usage_mode", "usage_mode"),
    _text("usage_explanation"),
    *_timestamps(),
)
```

Create `0003_data_flow_functions.py`:

```python
"""A data flow end can also name a function of the application on that end."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in ("source_function_id", "target_function_id"):
        op.add_column(
            "data_flow",
            sa.Column(
                column, sa.Uuid, sa.ForeignKey("function.id", ondelete="SET NULL"), nullable=True
            ),
        )


def downgrade() -> None:
    for column in ("target_function_id", "source_function_id"):
        op.drop_column("data_flow", column)
```

Confirm the `down_revision` of `0003` matches the revision id declared in `0002_seed_reference_values.py` (`grep '^revision' ...versions/0002*.py`) and fix it if it differs.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/domain tests/adapters/persistence -q`
Expected: PASS (including the existing `test_sqlalchemy_metadata_matches_the_migrated_schema`).

- [ ] **Step 5: Commit**

```bash
git add src/archimaid/domain/entities.py src/archimaid/adapters/persistence tests/domain tests/adapters/persistence
git commit -m "feat(persistence): data flows can name a function on each end

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Service rule: the function belongs to the application on its end

**Files:**
- Modify: `src/archimaid/application/crud.py` (`ParentLink`, `CrudService._check`)
- Modify: `src/archimaid/application/services.py` (`data_flows`)
- Test: `tests/application/test_services.py`

**Interfaces:**
- Consumes: `DataFlow.source_function_id` / `target_function_id` (Task 1), `Function.application_id`.
- Produces: `ParentLink(field: str, repository: Repository[Any], owner_field: str | None = None)`. When `owner_field` is set and the id is not None, the parent entity's `application_id` must equal `getattr(entity, owner_field)`, else `InvalidEntity("<field> <id> does not belong to <owner_field> <owner id>")`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/application/test_services.py`:

```python
def flow_world(services):
    team = services.teams.create({"name": "T"})
    billing = services.applications.create({"team_id": team.id, "name": "Billing"})
    ledger = services.applications.create({"team_id": team.id, "name": "Ledger"})
    invoice = services.data_types.create({"application_id": billing.id, "name": "Invoice"})
    send = services.functions.create({"application_id": billing.id, "name": "Send"})
    post = services.functions.create({"application_id": ledger.id, "name": "Post"})
    return billing, ledger, invoice, send, post


def flow_data(billing, ledger, invoice, **extra):
    return {
        "source_application_id": billing.id,
        "target_application_id": ledger.id,
        "data_type_id": invoice.id,
        **extra,
    }


def test_flow_accepts_functions_of_the_applications_on_each_end(services):
    billing, ledger, invoice, send, post = flow_world(services)
    flow = services.data_flows.create(
        flow_data(billing, ledger, invoice, source_function_id=send.id, target_function_id=post.id)
    )
    assert (flow.source_function_id, flow.target_function_id) == (send.id, post.id)


def test_flow_without_functions_still_works(services):
    billing, ledger, invoice, _, _ = flow_world(services)
    flow = services.data_flows.create(flow_data(billing, ledger, invoice))
    assert flow.source_function_id is None and flow.target_function_id is None


def test_flow_rejects_a_source_function_of_another_application(services):
    billing, ledger, invoice, send, post = flow_world(services)
    with pytest.raises(InvalidEntity, match="does not belong"):
        services.data_flows.create(flow_data(billing, ledger, invoice, source_function_id=post.id))
    assert services.data_flows.list() == []


def test_flow_rejects_a_target_function_of_another_application(services):
    # Review Focus test (3)
    billing, ledger, invoice, send, post = flow_world(services)
    with pytest.raises(InvalidEntity, match="does not belong"):
        services.data_flows.create(flow_data(billing, ledger, invoice, target_function_id=send.id))
    assert services.data_flows.list() == []


def test_flow_rejects_an_unknown_function(services):
    billing, ledger, invoice, _, _ = flow_world(services)
    with pytest.raises(DanglingReference):
        services.data_flows.create(flow_data(billing, ledger, invoice, source_function_id=uuid4()))


def test_flow_between_two_functions_of_the_same_application_is_allowed(services):
    billing, _, invoice, send, _ = flow_world(services)
    archive = services.functions.create({"application_id": billing.id, "name": "Archive"})
    flow = services.data_flows.create(
        flow_data(billing, billing, invoice, source_function_id=send.id, target_function_id=archive.id)
    )
    assert flow.source_application_id == flow.target_application_id


def test_moving_an_end_to_another_application_requires_clearing_its_function(services):
    # Review Focus test (1)
    billing, ledger, invoice, send, post = flow_world(services)
    flow = services.data_flows.create(
        flow_data(billing, ledger, invoice, source_function_id=send.id)
    )
    with pytest.raises(InvalidEntity, match="does not belong"):
        services.data_flows.update(flow.id, {"source_application_id": ledger.id})
    assert services.data_flows.get(flow.id).source_application_id == billing.id
    moved = services.data_flows.update(
        flow.id, {"source_application_id": ledger.id, "source_function_id": None}
    )
    assert moved.source_application_id == ledger.id and moved.source_function_id is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/application/test_services.py -q`
Expected: the new tests FAIL (the unknown/foreign-function tests do not raise).

- [ ] **Step 3: Implement**

In `crud.py`:

```python
@dataclass(frozen=True)
class ParentLink:
    """An id field of the entity that must exist in ``repository``.

    With ``owner_field``, the parent must also belong to the application whose id
    is held in that other field of the entity.
    """

    field: str
    repository: Repository[Any]
    owner_field: str | None = None
```

and in `_check`, replace the parents loop with:

```python
        for link in self._parents:
            parent_id = getattr(entity, link.field)
            if parent_id is None:
                continue
            parent = link.repository.get(parent_id)
            if parent is None:
                raise DanglingReference(f"{link.field} {parent_id} does not exist")
            if link.owner_field is not None:
                owner_id = getattr(entity, link.owner_field)
                if parent.application_id != owner_id:
                    raise InvalidEntity(
                        f"{link.field} {parent_id} does not belong to "
                        f"{link.owner_field} {owner_id}"
                    )
```

Add `InvalidEntity` to the `archimaid.domain.errors` import in `crud.py` if missing.

In `services.py`, the data flow `parents` list becomes:

```python
            parents=[
                ParentLink("source_application_id", repos.applications),
                ParentLink("target_application_id", repos.applications),
                ParentLink("data_type_id", repos.data_types),
                ParentLink("source_function_id", repos.functions, owner_field="source_application_id"),
                ParentLink("target_function_id", repos.functions, owner_field="target_application_id"),
            ],
```

(wrap lines to the project's line length if `ruff` complains.)

- [ ] **Step 4: Run to verify success**

Run: `uv run pytest tests/application -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/archimaid/application tests/application
git commit -m "feat(application): a flow's function must belong to the application on its end

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: JSON API

**Files:**
- Modify: `src/archimaid/adapters/api/schemas.py` (`DataFlowIn`)
- Test: `tests/adapters/api/test_api.py`

**Interfaces:**
- Consumes: Task 2 service behavior. `crud_router` and `errors.py` need no change.
- Produces: `DataFlowIn.source_function_id: UUID | None = None`, `DataFlowIn.target_function_id: UUID | None = None` (inherited by `DataFlowOut`).

- [ ] **Step 1: Write the failing test**

Append to `tests/adapters/api/test_api.py`:

```python
def test_data_flows_accept_and_validate_function_ends(client):
    source, target = make_app(client), make_app(client)
    dt = post(client, f"/applications/{source['id']}/data-types", {"name": "Invoice"})
    sender = post(client, f"/applications/{source['id']}/functions", {"name": "Send"})
    receiver = post(client, f"/applications/{target['id']}/functions", {"name": "Post"})
    body = {
        "source_application_id": source["id"],
        "target_application_id": target["id"],
        "data_type_id": dt["id"],
    }
    flow = post(
        client,
        "/data-flows",
        {**body, "source_function_id": sender["id"], "target_function_id": receiver["id"]},
    )
    assert flow["source_function_id"] == sender["id"]
    assert flow["target_function_id"] == receiver["id"]
    plain = post(client, "/data-flows", body)
    assert plain["source_function_id"] is None and plain["target_function_id"] is None
    swapped = client.post("/data-flows", json={**body, "source_function_id": receiver["id"]})
    assert swapped.status_code == 422
    ghost = client.post("/data-flows", json={**body, "target_function_id": str(uuid4())})
    assert ghost.status_code == 422
    cleared = client.put(
        f"/data-flows/{flow['id']}", json={**body, "source_function_id": sender["id"]}
    )
    assert cleared.status_code == 200
    assert cleared.json()["target_function_id"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/adapters/api/test_api.py::test_data_flows_accept_and_validate_function_ends -q`
Expected: FAIL (`KeyError: 'source_function_id'`).

- [ ] **Step 3: Implement**

```python
class DataFlowIn(BaseModel):
    source_application_id: UUID
    target_application_id: UUID
    data_type_id: UUID
    source_function_id: UUID | None = None
    target_function_id: UUID | None = None
    usage_mode: str | None = None
    usage_explanation: str | None = None
```

- [ ] **Step 4: Run to verify success**

Run: `uv run pytest tests/adapters/api -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/archimaid/adapters/api/schemas.py tests/adapters/api/test_api.py
git commit -m "feat(api): data flows carry optional source and target function ids

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Web forms, tab and overview

**Files:**
- Modify: `src/archimaid/adapters/web/resources.py` (`Field.source` comment, `DATA_FLOW`)
- Modify: `src/archimaid/adapters/web/render.py` (`Lookups._load`, new `_functions`)
- Modify: `src/archimaid/adapters/web/pages.py` (`data_flows_page`), `src/archimaid/adapters/web/templates/data_flows.html`
- Test: `tests/adapters/web/test_data_flows.py`, `tests/adapters/web/test_render.py`

**Interfaces:**
- Consumes: Task 2 service validation (inline 422 for mismatch via the existing `inline_problem`).
- Produces: `Field.source` accepts `"functions"`; options are `Option(str(function.id), "<Application> › <Function>", "<Application>")`, sorted by `(application name, function name)` case-insensitively.

- [ ] **Step 1: Write the failing tests**

Append to `tests/adapters/web/test_data_flows.py` (it already defines `setup_two_apps` and `make_flow`):

```python
def make_functions(services, source, target):
    send = services.functions.create({"application_id": source.id, "name": "Send"})
    post = services.functions.create({"application_id": target.id, "name": "Post"})
    return send, post


def test_flow_forms_offer_functions_grouped_by_application(client, services):
    source, target, _ = setup_two_apps(services)
    make_functions(services, source, target)
    html = client.get(f"/ui/applications/{source.id}/tabs/data-flows").text
    assert 'aria-label="Source function"' in html and 'aria-label="Target function"' in html
    assert ">Billing › Send</option>" in html and ">Ledger › Post</option>" in html
    assert '<optgroup label="Ledger">' in html


def test_add_a_flow_between_functions(client, services):
    source, target, data_type = setup_two_apps(services)
    send, post = make_functions(services, source, target)
    response = client.post(
        "/ui/data-flows?table=outgoing",
        data={
            "source_application_id": str(source.id),
            "source_function_id": str(send.id),
            "target_application_id": str(target.id),
            "target_function_id": str(post.id),
            "data_type_id": str(data_type.id),
        },
    )
    assert response.status_code == 201
    assert "Billing › Send" in response.text and "Ledger › Post" in response.text
    flow = services.data_flows.list()[0]
    assert (flow.source_function_id, flow.target_function_id) == (send.id, post.id)


def test_a_function_of_the_wrong_application_is_an_inline_422(client, services):
    source, target, data_type = setup_two_apps(services)
    _, post = make_functions(services, source, target)
    response = client.post(
        "/ui/data-flows?table=outgoing",
        data={
            "source_application_id": str(source.id),
            "source_function_id": str(post.id),
            "target_application_id": str(target.id),
            "data_type_id": str(data_type.id),
        },
    )
    assert response.status_code == 422 and "does not belong" in response.text
    assert services.data_flows.list() == []


def test_choosing_the_blank_option_when_saving_clears_the_function(client, services):
    # Review Focus test (4)
    source, target, data_type = setup_two_apps(services)
    send, _ = make_functions(services, source, target)
    flow = make_flow(services, source, target, data_type, source_function_id=send.id)
    saved = client.put(
        f"/ui/data-flows/{flow.id}",
        data={
            "source_application_id": str(source.id),
            "source_function_id": "",
            "target_application_id": str(target.id),
            "target_function_id": "",
            "data_type_id": str(data_type.id),
        },
    )
    assert saved.status_code == 200
    assert services.data_flows.get(flow.id).source_function_id is None


def test_overview_shows_the_function_ends(client, services):
    source, target, data_type = setup_two_apps(services)
    send, post = make_functions(services, source, target)
    make_flow(services, source, target, data_type, source_function_id=send.id)
    html = client.get("/ui/data-flows").text
    assert "<th>Source function</th>" in html and "<th>Target function</th>" in html
    assert "Billing › Send" in html
    assert "<td>—</td>" in html
```

Append to `tests/adapters/web/test_render.py` (reuse its `services` fixture if it has one; otherwise build with `build_services(fake_repositories(), default_catalog())` as the other tests in that file do):

```python
def test_function_choices_are_grouped_by_application_and_sorted(services):
    team = services.teams.create({"name": "T"})
    zed = services.applications.create({"team_id": team.id, "name": "Zed"})
    abc = services.applications.create({"team_id": team.id, "name": "Abc"})
    services.functions.create({"application_id": zed.id, "name": "b"})
    services.functions.create({"application_id": zed.id, "name": "A"})
    services.functions.create({"application_id": abc.id, "name": "x"})
    groups = Lookups(services).choices(r.DATA_FLOW.field("source_function_id"))
    assert [(group, [o.label for o in options]) for group, options in groups] == [
        ("Abc", ["Abc › x"]),
        ("Zed", ["Zed › A", "Zed › b"]),
    ]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/adapters/web -q`
Expected: new tests FAIL (`KeyError` for the field, missing select, missing columns).

- [ ] **Step 3: Implement**

`resources.py`: update the `Field.source` comment to `# select_entity: "personas" | "applications" | "data_types" | "functions"`, and replace the `fields=(...)` of `DATA_FLOW` with:

```python
    fields=(
        Field(
            "source_application_id",
            "Source application",
            "select_entity",
            required=True,
            source="applications",
        ),
        Field("source_function_id", "Source function", "select_entity", source="functions"),
        Field(
            "target_application_id",
            "Target application",
            "select_entity",
            required=True,
            source="applications",
        ),
        Field("target_function_id", "Target function", "select_entity", source="functions"),
        Field("data_type_id", "Data type", "select_entity", required=True, source="data_types"),
        Field("usage_mode", "Usage mode", "select_ref", kind="usage_mode"),
        Field("usage_explanation", "Usage explanation"),
    )
```

`render.py`: in `_load`, add before the final `raise`:

```python
        if field.source == "functions":
            return self._functions()
```

and add next to `_data_types`:

```python
    def _functions(self) -> list[Option]:
        apps = {a.id: a.name for a in self._services.applications.list()}
        options = []
        for f in self._services.functions.list():
            app_name = apps.get(f.application_id, "?")
            options.append(Option(str(f.id), f"{app_name} › {f.name}", app_name))
        return sorted(options, key=lambda o: ((o.group or "").lower(), o.label.lower()))
```

`pages.py`, in `data_flows_page`, add to each flow dict:

```python
                "source_function": lookups.display(DATA_FLOW.field("source_function_id"), vars(f)),
                "target_function": lookups.display(DATA_FLOW.field("target_function_id"), vars(f)),
```

`data_flows.html`: the header row becomes
`<tr><th>Source</th><th>Source function</th><th>Target</th><th>Target function</th><th>Data type</th><th>Usage mode</th><th>Explanation</th></tr>`
and the body row gets `<td>{{ f.source_function }}</td>` after the source cell and `<td>{{ f.target_function }}</td>` after the target cell.

The application's Data flows tab needs no template change: `DATA_FLOW` shows all its fields, so the two new columns and form selects appear automatically.

- [ ] **Step 4: Run to verify success**

Run: `uv run pytest tests/adapters/web -q`
Expected: PASS. If an existing web test asserted the exact set of flow columns or form fields, update that assertion to include the two new function fields (the behavior change is intended).

- [ ] **Step 5: Commit**

```bash
git add src/archimaid/adapters/web tests/adapters/web
git commit -m "feat(web): function selects on data flow forms, tabs and overview

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Diagram builder

**Files:**
- Modify: `src/archimaid/adapters/web/diagram/model.py` (`DiagramFlow`)
- Modify: `src/archimaid/adapters/web/diagram/builder.py`
- Test: `tests/adapters/web/diagram/test_builder.py`

**Interfaces:**
- Consumes: `DataFlow.source_function_id` / `target_function_id`.
- Produces: `DiagramFlow(data_type: str, usage_mode: str | None = None, explanation: str | None = None, function_index: int | None = None)`. `function_index` is the position, in `DiagramModel.functions` order (sorted by `(name.casefold(), str(id))`), of the current application's function on the current-application end of the flow. The layout and renderer ignore it.

- [ ] **Step 1: Write the failing tests**

In `tests/adapters/web/diagram/test_builder.py`, change `World.flow` so a flow can carry function ends: it already forwards `**extra` into the service, so no change is needed. Append:

```python
def test_function_index_points_at_the_current_applications_function(services, world):
    billing, ledger = world.app("Billing"), world.app("Ledger")
    dtype = world.dtype(billing, "x")
    world.function(billing, "send")
    create = world.function(billing, "Create")  # sorts before "send"
    world.flow(billing, ledger, dtype, source_function_id=create.id)
    plain = world.flow(ledger, billing, dtype)
    model = build_diagram(services, billing.id)
    assert plain.source_function_id is None
    assert model.targets[0].flows[0].function_index == 0
    assert model.sources[0].flows[0].function_index is None


def test_incoming_flow_uses_the_target_function(services, world):
    billing, ledger = world.app("Billing"), world.app("Ledger")
    world.function(billing, "a")
    receive = world.function(billing, "b")
    world.flow(ledger, billing, world.dtype(ledger, "x"), target_function_id=receive.id)
    model = build_diagram(services, billing.id)
    assert model.sources[0].flows[0].function_index == 1


def test_functions_of_third_party_applications_stay_hidden_and_the_flow_goes_to_the_parent(
    services, world
):
    # Review Focus test (5)
    billing, ledger = world.app("Billing"), world.app("Ledger")
    post = world.function(ledger, "Post entry")
    world.flow(billing, ledger, world.dtype(billing, "x"), target_function_id=post.id)
    model = build_diagram(services, billing.id)
    assert [n.name for n in model.targets] == ["Ledger"]
    assert model.targets[0].flows[0].function_index is None
    assert "Post entry" not in repr(model)
    other_side = build_diagram(services, ledger.id)
    assert [n.name for n in other_side.sources] == ["Billing"]
    assert other_side.sources[0].flows[0].function_index == 0


def test_function_to_function_flow_inside_one_application_is_counted_not_drawn(services, world):
    # Review Focus test (5)
    a = world.app("A")
    send, receive = world.function(a, "send"), world.function(a, "receive")
    world.flow(
        a, a, world.dtype(a, "x"), source_function_id=send.id, target_function_id=receive.id
    )
    model = build_diagram(services, a.id)
    assert model.self_flows == 1
    assert model.targets == () and model.sources == ()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/adapters/web/diagram/test_builder.py -q`
Expected: the new tests FAIL (`AttributeError: 'DiagramFlow' object has no attribute 'function_index'`). The last test may already pass; that is fine.

- [ ] **Step 3: Implement**

`model.py`:

```python
@dataclass(frozen=True)
class DiagramFlow:
    data_type: str
    usage_mode: str | None = None
    explanation: str | None = None
    function_index: int | None = None  # position in DiagramModel.functions on this application's end
```

`builder.py`: after `diagram_functions` is built add

```python
    function_index = {f.id: index for index, f in enumerate(functions)}
```

change `group` to take the attribute holding the current application's function:

```python
    def group(
        flows: list[Any], other_attr: str, own_function_attr: str
    ) -> tuple[DiagramNeighbour, ...]:
        by_app: dict[UUID, list[DiagramFlow]] = {}
        for flow in flows:
            mode = mode_labels.get(flow.usage_mode, flow.usage_mode) if flow.usage_mode else None
            by_app.setdefault(getattr(flow, other_attr), []).append(
                DiagramFlow(
                    type_name(flow.data_type_id),
                    mode,
                    flow.usage_explanation,
                    function_index.get(getattr(flow, own_function_attr)),
                )
            )
```

(the rest of `group` is unchanged), and update the two calls in the returned `DiagramModel`:

```python
        targets=group(
            [f for f in outgoing if f.target_application_id != application_id],
            "target_application_id",
            "source_function_id",
        ),
        sources=group(
            [f for f in incoming if f.source_application_id != application_id],
            "source_application_id",
            "target_function_id",
        ),
```

`function_index.get(None)` returns `None`, which is the intended value for a flow with no function.

- [ ] **Step 4: Run to verify success**

Run: `uv run pytest tests/adapters/web/diagram -q`
Expected: PASS, including `test_reproduces_the_approved_sample_files` and the layout and route tests untouched.

- [ ] **Step 5: Commit**

```bash
git add src/archimaid/adapters/web/diagram tests/adapters/web/diagram
git commit -m "feat(diagram): builder records the current application's function on each flow

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Documentation, end-to-end test, final checks

**Files:**
- Modify: `domain.puml`, `docs/superpowers/specs/2026-10-02-archimaid-design.md`, `CLAUDE.md`
- Test: `tests/test_end_to_end_postgres.py`

- [ ] **Step 1: Write the end-to-end test**

Append to `tests/test_end_to_end_postgres.py`:

```python
def test_function_flows_over_real_postgres(client):
    team = client.post("/teams", json={"name": "Payments"}).json()
    source = client.post(
        "/applications", json={"team_id": team["id"], "name": "Billing"}
    ).json()
    target = client.post("/applications", json={"team_id": team["id"], "name": "Ledger"}).json()
    dtype = client.post(
        f"/applications/{source['id']}/data-types", json={"name": "Invoice"}
    ).json()
    sender = client.post(
        f"/applications/{source['id']}/functions", json={"name": "Send"}
    ).json()
    receiver = client.post(
        f"/applications/{target['id']}/functions", json={"name": "Post"}
    ).json()
    body = {
        "source_application_id": source["id"],
        "source_function_id": sender["id"],
        "target_application_id": target["id"],
        "target_function_id": receiver["id"],
        "data_type_id": dtype["id"],
    }
    flow = client.post("/data-flows", json=body)
    assert flow.status_code == 201

    # a function of the other application is rejected, not stored
    wrong = client.post("/data-flows", json={**body, "source_function_id": receiver["id"]})
    assert wrong.status_code == 422

    # the web tab and the diagram render it
    tab = client.get(f"/ui/applications/{source['id']}/tabs/data-flows")
    assert tab.status_code == 200 and "Billing › Send" in tab.text
    assert client.get(f"/ui/applications/{source['id']}/diagram.svg").status_code == 200

    # deleting the function keeps the flow and nulls that end
    deleted = client.delete(f"/applications/{source['id']}/functions/{sender['id']}")
    assert deleted.status_code == 204
    kept = client.get(f"/data-flows/{flow.json()['id']}").json()
    assert kept["source_function_id"] is None
    assert kept["target_function_id"] == receiver["id"]
```

`create_app` mounts the web UI (`install_web`), so the `/ui` assertions work on this client.

- [ ] **Step 2: Update the documentation**

`domain.puml`: add to `class DataFlow` after `-TargetApplicationId: UUID`:

```
        -SourceFunctionId: UUID | null
        -TargetFunctionId: UUID | null
```

and after the `DataFlow "*" -- "1" Application : TargetApplicationId` line:

```
DataFlow "*" -- "0..1" Function : SourceFunctionId
DataFlow "*" -- "0..1" Function : TargetFunctionId
```

Backend spec (`docs/superpowers/specs/2026-10-02-archimaid-design.md`): change the `data_flow` line (about line 67) to
`- \`data_flow\` (\`source_application_id\`, \`target_application_id\`, \`data_type_id\` FKs; optional \`source_function_id\`, \`target_function_id\` FKs to \`function\`, \`ON DELETE SET NULL\`, each function must belong to the application on its end; see \`2026-10-05-archimaid-function-flows-design.md\`)`,
and add after the line "Deleting an application that is the source or target of a data flow is therefore blocked with 409." a bullet:
`  - A data flow's optional function ends are \`SET NULL\`: deleting a function keeps the flow as an application-level link.`

`CLAUDE.md` (project): in the `application/` bullet of Architecture, after "`build_services()` in `services.py` is where each entity's reference fields (field → catalog kind) and parent-id checks are declared." append " A `ParentLink` with `owner_field` also checks that the parent belongs to the application held in that field (data flow function ends)."

- [ ] **Step 3: Run the whole suite and linters**

Run: `uv run pytest -q && uv run ruff check src tests && uv run mypy src`
Expected: all green, including the Postgres tests (they need the container runtime). Fix any ruff line-length complaints in the files touched by this plan.

- [ ] **Step 4: Manual check on the dev server (optional but recommended)**

Run the dev database and server from CLAUDE.md, open `http://localhost:8000/ui/`, add two functions in two applications, add a flow with both function ends on an application's Data flows tab, check the overview, then delete the source function and confirm the flow remains with `—`. The Diagram tab should look unchanged.

- [ ] **Step 5: Commit**

```bash
git add domain.puml docs CLAUDE.md tests/test_end_to_end_postgres.py
git commit -m "docs: function flows in the domain diagram, backend spec and CLAUDE.md; end-to-end test

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
