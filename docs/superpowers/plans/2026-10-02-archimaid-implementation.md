# Archimaid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Archimaid backend: a FastAPI + PostgreSQL CRUD service over the Team and Application aggregates, where all value objects are configuration tables.

**Architecture:** Hexagonal. `domain/` has pure dataclasses, reference value objects and errors. `ports/` has repository and `ReferenceCatalog` protocols. `application/` has a generic `CrudService` plus `ApplicationService` (derived RPO/RTO) and `ReferenceAdminService`. `adapters/persistence/` has SQLAlchemy Core repositories, a Postgres catalog and Alembic migrations. `adapters/api/` has a generic CRUD router factory and a reference router. Unit tests run on in-memory fakes. Adapter and end-to-end tests run against real Postgres through testcontainers.

**Tech Stack:** Python 3.12+, uv, FastAPI, SQLAlchemy 2.x Core (sync), psycopg 3, Alembic, pytest, httpx, testcontainers, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-10-02-archimaid-design.md`. Read it first. Its "Implementation decisions" section records choices made while planning.

## Global Constraints

- Python `>=3.12`. Use PEP 695 generics (`class Repo[T: Entity]`), `X | None` unions, and `from datetime import UTC`.
- Value objects are **configuration tables**, never enums. One table per value object, with `code TEXT PRIMARY KEY`.
- Referencing columns are text FKs to `<table>.code` with `ON UPDATE CASCADE ON DELETE RESTRICT`. There is no `active` flag.
- The domain package imports no FastAPI, SQLAlchemy, Pydantic or Alembic.
- RPO and RTO are never stored and never accepted as input. They are read from the `availability_level` row, in hours, as `rpo` and `rto`.
- `UsageMode` lives on `DataFlow` only. `Persona` is global, with a nullable `function.persona_id`.
- Delete semantics:
  - `team_member`, `function`, `data_type` and `technology` cascade with their parent.
  - `application`→`team`, `data_flow`→`application` (source and target), `data_flow`→`data_type` and `function`→`persona` are `RESTRICT`.
- Domain errors map to HTTP status codes:

  | Error | HTTP |
  |---|---|
  | `NotFound` | 404 |
  | `InvalidEntity`, `InvalidReferenceCode`, `DanglingReference` | 422 |
  | `ReferenceInUse`, `AlreadyExists` | 409 |

- Reference values are read and written by `code`, for example `{"availability_level": "SERIOUS"}`.
- No authentication in v1.
- Every commit message ends with this trailer line, which the commit commands below add with a second `-m`: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`
- Postgres-backed tests need Docker. If Docker is missing they skip. Before declaring Task 9 done, confirm that `uv run pytest -rs` shows **no skips**.

## Review Focus

Inputs and conditions the spec implies but doesn't spell out, with the behavior a reasonable person would expect. Each one has a pinning test in the owning task, marked **Review Focus test**.

1. A name that is empty or only whitespace, on create or on PUT, gets 422 and nothing is stored (Task 2 domain, Task 4 service, Task 8 API).
2. Creating a catalog value with an existing code, or renaming one onto an existing code, gets 409 and not 500 (Task 7 persistence, Task 8 API).
3. Deleting a team that has applications, an application that is the source or target of a flow, a data type used by a flow, or a persona used by a function gets 409. Deleting an application removes its functions, data types and technologies (Task 7).
4. A body id that points nowhere (`team_id`, `persona_id`, `source_application_id`, `data_type_id`) gets 422 and not 500 (Task 4 service, Task 8 API).
5. Reaching a nested resource through the wrong parent, for example `/applications/{A}/functions/{id of a function of B}`, or under a parent that doesn't exist, gets 404 (Task 8).

---

## File Structure

```
pyproject.toml
.gitignore
docker-compose.yml
src/archimaid/
  main.py                              uvicorn factory wiring (Postgres)
  domain/errors.py                     DomainError hierarchy
  domain/reference.py                  ReferenceValue VOs + REFERENCE_KINDS registry
  domain/entities.py                   Entity base + 8 entity dataclasses
  ports/repository.py                  Repository protocol + Repositories bundle
  ports/reference_catalog.py           ReferenceCatalog protocol
  application/crud.py                  CrudService, ParentLink
  application/applications.py          ApplicationService (adds rpo/rto)
  application/reference_admin.py       ReferenceAdminService
  application/services.py              Services bundle + build_services()
  adapters/persistence/tables.py       SQLAlchemy Core metadata
  adapters/persistence/pg_errors.py    FK/unique violation detection
  adapters/persistence/repository.py   SqlRepository + build_repositories()
  adapters/persistence/catalog.py      PostgresReferenceCatalog
  adapters/persistence/migrate.py      run_migrations(url) + CLI
  adapters/persistence/migrations/     Alembic env + versions 0001 (schema), 0002 (seed)
  adapters/api/errors.py               DomainError -> HTTP
  adapters/api/schemas.py              Pydantic in/out models
  adapters/api/crud_router.py          generic router factory
  adapters/api/reference_router.py     /reference endpoints
  adapters/api/app.py                  create_app(services)
tests/
  conftest.py                          Postgres fixtures (lazy imports)
  fakes.py                             in-memory repository + catalog
  domain/ application/ adapters/persistence/ adapters/api/
  test_end_to_end_postgres.py
```

---

### Task 0: Project scaffold

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `src/archimaid/__init__.py` and the package `__init__.py` files below, `tests/__init__.py` and the test package `__init__.py` files below, `tests/test_smoke.py`

**Interfaces:**
- Produces: an installable `archimaid` package and a working `uv run pytest`.

- [ ] **Step 1: Initialise git and create the package skeleton**

```bash
cd /home/yvan/Projects/ArchiMaid
git init
mkdir -p src/archimaid/{domain,ports,application,adapters/persistence/migrations/versions,adapters/api} \
         tests/{domain,application,adapters/persistence,adapters/api}
touch src/archimaid/__init__.py src/archimaid/domain/__init__.py src/archimaid/ports/__init__.py \
      src/archimaid/application/__init__.py src/archimaid/adapters/__init__.py \
      src/archimaid/adapters/persistence/__init__.py src/archimaid/adapters/api/__init__.py \
      tests/__init__.py tests/domain/__init__.py tests/application/__init__.py \
      tests/adapters/__init__.py tests/adapters/persistence/__init__.py tests/adapters/api/__init__.py
```

- [ ] **Step 2: Write `.gitignore`**

```
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
.mypy_cache/
*.egg-info/
dist/
```

- [ ] **Step 3: Write `pyproject.toml`**

```toml
[project]
name = "archimaid"
version = "0.1.0"
description = "Data collection tool for functional, application and technical architecture analysis"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn>=0.30",
    "sqlalchemy>=2.0",
    "psycopg[binary]>=3.2",
    "alembic>=1.13",
]

[dependency-groups]
dev = [
    "pytest>=8",
    "httpx>=0.27",
    "testcontainers[postgres]>=4.8",
    "ruff>=0.6",
    "mypy>=1.11",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/archimaid"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["postgres: needs Docker (testcontainers)"]

[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.ruff.lint.flake8-bugbear]
extend-immutable-calls = ["fastapi.Depends"]

[tool.mypy]
python_version = "3.12"
check_untyped_defs = true
ignore_missing_imports = true
```

- [ ] **Step 4: Write the smoke test**

`tests/test_smoke.py`:
```python
def test_package_imports():
    import archimaid

    assert archimaid is not None
```

- [ ] **Step 5: Install and run**

Run: `uv sync --dev && uv run pytest -v`
Expected: `tests/test_smoke.py::test_package_imports PASSED`

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: scaffold project, README, domain diagram and design spec" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 1: Domain errors and reference value objects

**Files:**
- Create: `src/archimaid/domain/errors.py`, `src/archimaid/domain/reference.py`
- Test: `tests/domain/test_reference.py`

**Interfaces:**
- Produces:
  - Errors, all subclasses of `DomainError`: `NotFound`, `InvalidEntity`, `InvalidReferenceCode`, `DanglingReference`, `ReferenceInUse`, `AlreadyExists`.
  - Frozen keyword-only dataclasses:
    - `ReferenceValue(code, label, description=None)`
    - `RankedValue(ReferenceValue)` adds `rank: int`
    - `AvailabilityLevel(RankedValue)` adds `rpo_hours: int, rto_hours: int`
  - Named subclasses: `ConfidentialityLevel`, `IntegrityLevel`, `TraceabilityLevel` (all `RankedValue`), and `FunctionCategory`, `UsageMode`, `TechnologyType`, `TechStandardStatus` (all `ReferenceValue`).
  - `REFERENCE_KINDS: dict[str, type[ReferenceValue]]`, keyed by the table name.

- [ ] **Step 1: Write the failing test**

`tests/domain/test_reference.py`:
```python
import dataclasses

import pytest

from archimaid.domain.errors import InvalidEntity
from archimaid.domain.reference import (
    REFERENCE_KINDS,
    AvailabilityLevel,
    ConfidentialityLevel,
    FunctionCategory,
)


def test_registry_has_the_eight_catalogs():
    assert set(REFERENCE_KINDS) == {
        "confidentiality_level",
        "integrity_level",
        "availability_level",
        "traceability_level",
        "function_category",
        "usage_mode",
        "technology_type",
        "tech_standard_status",
    }


def test_value_objects_are_immutable():
    value = FunctionCategory(code="BUSINESS", label="Business")
    with pytest.raises(dataclasses.FrozenInstanceError):
        value.label = "other"  # type: ignore[misc]


@pytest.mark.parametrize("code", ["", "  "])
def test_blank_code_is_rejected(code):
    with pytest.raises(InvalidEntity):
        FunctionCategory(code=code, label="Business")


def test_blank_label_is_rejected():
    with pytest.raises(InvalidEntity):
        FunctionCategory(code="BUSINESS", label=" ")


def test_levels_carry_a_rank():
    assert ConfidentialityLevel(code="LOW", label="Low", rank=1).rank == 1


def test_availability_hours_cannot_be_negative():
    with pytest.raises(InvalidEntity):
        AvailabilityLevel(code="LOW", label="Low", rank=1, rpo_hours=-1, rto_hours=0)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/domain/test_reference.py -v`
Expected: FAIL with `ModuleNotFoundError: archimaid.domain.reference`

- [ ] **Step 3: Implement**

`src/archimaid/domain/errors.py`:
```python
class DomainError(Exception):
    """Base class for all domain errors."""


class NotFound(DomainError):
    """The requested entity, catalog kind or catalog value does not exist."""


class InvalidEntity(DomainError):
    """An entity or value object violates a domain rule (e.g. blank required text)."""


class InvalidReferenceCode(DomainError):
    """A field holds a code that is not in its configuration table."""


class DanglingReference(DomainError):
    """An id field points to a row that does not exist."""


class ReferenceInUse(DomainError):
    """The row cannot be deleted because other rows still reference it."""


class AlreadyExists(DomainError):
    """A configuration value with that code already exists."""
```

`src/archimaid/domain/reference.py`:
```python
from dataclasses import dataclass

from archimaid.domain.errors import InvalidEntity


@dataclass(frozen=True, kw_only=True)
class ReferenceValue:
    code: str
    label: str
    description: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise InvalidEntity("code must not be blank")
        if not self.label.strip():
            raise InvalidEntity("label must not be blank")


@dataclass(frozen=True, kw_only=True)
class RankedValue(ReferenceValue):
    rank: int


@dataclass(frozen=True, kw_only=True)
class AvailabilityLevel(RankedValue):
    rpo_hours: int
    rto_hours: int

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.rpo_hours < 0 or self.rto_hours < 0:
            raise InvalidEntity("rpo_hours and rto_hours must not be negative")


class ConfidentialityLevel(RankedValue):
    pass


class IntegrityLevel(RankedValue):
    pass


class TraceabilityLevel(RankedValue):
    pass


class FunctionCategory(ReferenceValue):
    pass


class UsageMode(ReferenceValue):
    pass


class TechnologyType(ReferenceValue):
    pass


class TechStandardStatus(ReferenceValue):
    pass


REFERENCE_KINDS: dict[str, type[ReferenceValue]] = {
    "confidentiality_level": ConfidentialityLevel,
    "integrity_level": IntegrityLevel,
    "availability_level": AvailabilityLevel,
    "traceability_level": TraceabilityLevel,
    "function_category": FunctionCategory,
    "usage_mode": UsageMode,
    "technology_type": TechnologyType,
    "tech_standard_status": TechStandardStatus,
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/domain/test_reference.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/archimaid/domain tests/domain
git commit -m "feat(domain): errors and reference value objects" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Domain entities

**Files:**
- Create: `src/archimaid/domain/entities.py`
- Test: `tests/domain/test_entities.py`

**Interfaces:**
- Consumes: `InvalidEntity` from Task 1.
- Produces: keyword-only dataclasses, each with `validate() -> bool` that returns `True` or raises `InvalidEntity`. All have `id: UUID`, `created_at: datetime` and `updated_at: datetime`.
  - `Team(name, description="")`
  - `TeamMember(team_id, user_id, name)`
  - `Application(team_id, name, golden_app_id=None, auid=None, description=None, asset_cmdb=None, shortname=None, owner_uid=None, confidentiality_level=None, integrity_level=None, availability_level=None, traceability_level=None)`
  - `Function(application_id, name, description=None, category=None, persona_id=None)`
  - `DataType(application_id, name, definition=None, specificity=None, confidentiality_level=None, golden_source=None, golden_replica=None)`
  - `DataFlow(source_application_id, target_application_id, data_type_id, usage_mode=None, usage_explanation=None)`
  - `Technology(application_id, name, version=None, family=None, type=None, standard_status=None, standard_status_details=None, tech_standards_link=None, action_plan=None)`
  - `Persona(name, description=None, category=None)`
- `DataFlow` has no required text field. The other entities require non-blank `name`, and `TeamMember` also requires non-blank `user_id`.

- [ ] **Step 1: Write the failing test**

`tests/domain/test_entities.py`:
```python
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from archimaid.domain.entities import (
    Application,
    DataFlow,
    Function,
    Persona,
    Team,
    TeamMember,
    Technology,
)
from archimaid.domain.errors import InvalidEntity

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def meta():
    return {"id": uuid4(), "created_at": NOW, "updated_at": NOW}


def test_valid_team_validates_to_true():
    assert Team(name="Payments", **meta()).validate() is True


@pytest.mark.parametrize("name", ["", "   "])
def test_blank_name_is_rejected(name):  # Review Focus test (1)
    with pytest.raises(InvalidEntity):
        Team(name=name, **meta()).validate()


@pytest.mark.parametrize(
    "build",
    [
        lambda name: Application(team_id=uuid4(), name=name, **meta()),
        lambda name: Function(application_id=uuid4(), name=name, **meta()),
        lambda name: Technology(application_id=uuid4(), name=name, **meta()),
        lambda name: Persona(name=name, **meta()),
    ],
)
def test_every_named_entity_rejects_blank_name(build):
    with pytest.raises(InvalidEntity):
        build(" ").validate()


def test_team_member_requires_user_id_and_name():
    with pytest.raises(InvalidEntity):
        TeamMember(team_id=uuid4(), user_id=" ", name="Ann", **meta()).validate()
    with pytest.raises(InvalidEntity):
        TeamMember(team_id=uuid4(), user_id="u1", name="", **meta()).validate()


def test_optional_fields_default_to_none():
    app = Application(team_id=uuid4(), name="Billing", **meta())
    assert app.golden_app_id is None
    assert app.availability_level is None


def test_rpo_and_rto_are_not_stored_on_application():
    app = Application(team_id=uuid4(), name="Billing", **meta())
    assert not hasattr(app, "rpo")
    assert not hasattr(app, "rto")


def test_data_flow_has_usage_mode_and_no_required_text():
    flow = DataFlow(
        source_application_id=uuid4(),
        target_application_id=uuid4(),
        data_type_id=uuid4(),
        usage_mode="SOURCE",
        **meta(),
    )
    assert flow.validate() is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/domain/test_entities.py -v`
Expected: FAIL with `ModuleNotFoundError: archimaid.domain.entities`

- [ ] **Step 3: Implement**

`src/archimaid/domain/entities.py`:
```python
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar
from uuid import UUID

from archimaid.domain.errors import InvalidEntity


@dataclass(kw_only=True)
class Entity:
    id: UUID
    created_at: datetime
    updated_at: datetime

    required_text: ClassVar[tuple[str, ...]] = ("name",)

    def validate(self) -> bool:
        """Return True, or raise InvalidEntity if a required text field is blank."""
        for attr in self.required_text:
            value = getattr(self, attr)
            if not value or not value.strip():
                raise InvalidEntity(f"{attr} must not be blank")
        return True


@dataclass(kw_only=True)
class Team(Entity):
    name: str
    description: str = ""


@dataclass(kw_only=True)
class TeamMember(Entity):
    required_text: ClassVar[tuple[str, ...]] = ("user_id", "name")

    team_id: UUID
    user_id: str
    name: str


@dataclass(kw_only=True)
class Application(Entity):
    team_id: UUID
    name: str
    golden_app_id: str | None = None
    auid: str | None = None
    description: str | None = None
    asset_cmdb: str | None = None
    shortname: str | None = None
    owner_uid: str | None = None
    confidentiality_level: str | None = None
    integrity_level: str | None = None
    availability_level: str | None = None
    traceability_level: str | None = None


@dataclass(kw_only=True)
class Function(Entity):
    application_id: UUID
    name: str
    description: str | None = None
    category: str | None = None
    persona_id: UUID | None = None


@dataclass(kw_only=True)
class DataType(Entity):
    application_id: UUID
    name: str
    definition: str | None = None
    specificity: str | None = None
    confidentiality_level: str | None = None
    golden_source: str | None = None
    golden_replica: str | None = None


@dataclass(kw_only=True)
class DataFlow(Entity):
    required_text: ClassVar[tuple[str, ...]] = ()

    source_application_id: UUID
    target_application_id: UUID
    data_type_id: UUID
    usage_mode: str | None = None
    usage_explanation: str | None = None


@dataclass(kw_only=True)
class Technology(Entity):
    application_id: UUID
    name: str
    version: str | None = None
    family: str | None = None
    type: str | None = None
    standard_status: str | None = None
    standard_status_details: str | None = None
    tech_standards_link: str | None = None
    action_plan: str | None = None


@dataclass(kw_only=True)
class Persona(Entity):
    name: str
    description: str | None = None
    category: str | None = None
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/domain -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/archimaid/domain/entities.py tests/domain/test_entities.py
git commit -m "feat(domain): entities with validate()" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Ports and in-memory fakes

**Files:**
- Create: `src/archimaid/ports/repository.py`, `src/archimaid/ports/reference_catalog.py`, `tests/fakes.py`
- Test: `tests/test_fakes.py`

**Interfaces:**
- Consumes: entities (Task 2) and reference VOs and errors (Task 1).
- Produces:
  - `Repository[T]` protocol:
    - `add(entity) -> None`
    - `get(entity_id: UUID) -> T | None`
    - `list(**filters) -> list[T]`, where each filter is column==value equality
    - `update(entity) -> None`
    - `delete(entity_id) -> None`, which raises `ReferenceInUse` when the row is still referenced
  - `Repositories` dataclass with fields `teams, members, applications, functions, data_types, data_flows, technologies, personas`, each a `Repository[...]`.
  - `ReferenceCatalog` protocol:
    - `exists(kind, code) -> bool`
    - `get(kind, code) -> ReferenceValue`, which raises `NotFound`
    - `list(kind) -> list[ReferenceValue]`, ordered by code
    - `create(kind, value) -> ReferenceValue`, which raises `AlreadyExists`
    - `update(kind, code, value) -> ReferenceValue`, which raises `NotFound` or `AlreadyExists`. A different `value.code` renames the value.
    - `delete(kind, code) -> None`, which raises `NotFound` or `ReferenceInUse`
    - An unknown `kind` raises `NotFound` everywhere.
  - Test fakes: `InMemoryRepository[T]` with `mark_in_use(entity_id)`, `InMemoryReferenceCatalog` with `mark_in_use(kind, code)`, `default_catalog()` and `fake_repositories()`.

- [ ] **Step 1: Write the failing test**

`tests/test_fakes.py`:
```python
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from archimaid.domain.entities import Team
from archimaid.domain.errors import AlreadyExists, NotFound, ReferenceInUse
from archimaid.domain.reference import FunctionCategory
from tests.fakes import InMemoryRepository, default_catalog

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def team(name="Payments"):
    return Team(id=uuid4(), name=name, created_at=NOW, updated_at=NOW)


def test_repository_add_get_update_delete():
    repo = InMemoryRepository[Team]()
    t = team()
    repo.add(t)
    assert repo.get(t.id) == t
    t.name = "Billing"
    repo.update(t)
    assert repo.get(t.id).name == "Billing"
    repo.delete(t.id)
    assert repo.get(t.id) is None


def test_repository_list_filters_by_attribute():
    repo = InMemoryRepository[Team]()
    a, b = team("A"), team("B")
    repo.add(a)
    repo.add(b)
    assert repo.list(name="B") == [b]
    assert len(repo.list()) == 2


def test_repository_delete_of_referenced_row_is_blocked():
    repo = InMemoryRepository[Team]()
    t = team()
    repo.add(t)
    repo.mark_in_use(t.id)
    with pytest.raises(ReferenceInUse):
        repo.delete(t.id)


def test_default_catalog_is_seeded():
    catalog = default_catalog()
    assert catalog.exists("availability_level", "SERIOUS")
    assert catalog.get("availability_level", "SERIOUS").rpo_hours == 4
    assert not catalog.exists("function_category", "NOPE")


def test_catalog_unknown_kind_is_not_found():
    with pytest.raises(NotFound):
        default_catalog().exists("nope", "X")


def test_catalog_create_duplicate_and_delete():
    catalog = default_catalog()
    value = FunctionCategory(code="EXTRA", label="Extra")
    catalog.create("function_category", value)
    with pytest.raises(AlreadyExists):
        catalog.create("function_category", value)
    catalog.delete("function_category", "EXTRA")
    with pytest.raises(NotFound):
        catalog.get("function_category", "EXTRA")


def test_catalog_rename_and_rename_conflict():
    catalog = default_catalog()
    catalog.update("function_category", "BUSINESS", FunctionCategory(code="BIZ", label="Biz"))
    assert catalog.exists("function_category", "BIZ")
    assert not catalog.exists("function_category", "BUSINESS")
    with pytest.raises(AlreadyExists):
        catalog.update("function_category", "BIZ", FunctionCategory(code="COMMON", label="x"))


def test_catalog_delete_of_value_in_use_is_blocked():
    catalog = default_catalog()
    catalog.mark_in_use("function_category", "BUSINESS")
    with pytest.raises(ReferenceInUse):
        catalog.delete("function_category", "BUSINESS")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_fakes.py -v`
Expected: FAIL with `ModuleNotFoundError: tests.fakes`

- [ ] **Step 3: Implement**

`src/archimaid/ports/repository.py`:
```python
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from archimaid.domain.entities import (
    Application,
    DataFlow,
    DataType,
    Entity,
    Function,
    Persona,
    Team,
    TeamMember,
    Technology,
)


class Repository[T: Entity](Protocol):
    def add(self, entity: T) -> None: ...

    def get(self, entity_id: UUID) -> T | None: ...

    def list(self, **filters: Any) -> list[T]:
        """Return entities whose attributes equal every given filter value."""
        ...

    def update(self, entity: T) -> None: ...

    def delete(self, entity_id: UUID) -> None:
        """Delete the entity. Raises ReferenceInUse if other rows still reference it."""
        ...


@dataclass
class Repositories:
    teams: Repository[Team]
    members: Repository[TeamMember]
    applications: Repository[Application]
    functions: Repository[Function]
    data_types: Repository[DataType]
    data_flows: Repository[DataFlow]
    technologies: Repository[Technology]
    personas: Repository[Persona]
```

`src/archimaid/ports/reference_catalog.py`:
```python
from typing import Protocol

from archimaid.domain.reference import ReferenceValue


class ReferenceCatalog(Protocol):
    """Access to the configuration tables. An unknown ``kind`` raises NotFound."""

    def exists(self, kind: str, code: str) -> bool: ...

    def get(self, kind: str, code: str) -> ReferenceValue: ...

    def list(self, kind: str) -> list[ReferenceValue]: ...

    def create(self, kind: str, value: ReferenceValue) -> ReferenceValue:
        """Raises AlreadyExists if the code is taken."""
        ...

    def update(self, kind: str, code: str, value: ReferenceValue) -> ReferenceValue:
        """Replace the value. A different ``value.code`` renames it (and cascades).

        Raises NotFound if ``code`` is unknown, AlreadyExists if the new code is taken.
        """
        ...

    def delete(self, kind: str, code: str) -> None:
        """Raises NotFound, or ReferenceInUse if entities still reference the value."""
        ...
```

`tests/fakes.py`:
```python
from typing import Any
from uuid import UUID

from archimaid.domain.entities import Entity
from archimaid.domain.errors import AlreadyExists, NotFound, ReferenceInUse
from archimaid.domain.reference import (
    REFERENCE_KINDS,
    AvailabilityLevel,
    ConfidentialityLevel,
    FunctionCategory,
    IntegrityLevel,
    ReferenceValue,
    TechnologyType,
    TechStandardStatus,
    TraceabilityLevel,
    UsageMode,
)
from archimaid.ports.repository import Repositories


class InMemoryRepository[T: Entity]:
    def __init__(self) -> None:
        self._items: dict[UUID, T] = {}
        self._in_use: set[UUID] = set()

    def mark_in_use(self, entity_id: UUID) -> None:
        self._in_use.add(entity_id)

    def add(self, entity: T) -> None:
        self._items[entity.id] = entity

    def get(self, entity_id: UUID) -> T | None:
        return self._items.get(entity_id)

    def list(self, **filters: Any) -> list[T]:
        return [
            item
            for item in self._items.values()
            if all(getattr(item, name) == value for name, value in filters.items())
        ]

    def update(self, entity: T) -> None:
        self._items[entity.id] = entity

    def delete(self, entity_id: UUID) -> None:
        if entity_id in self._in_use:
            raise ReferenceInUse(f"{entity_id} is still referenced")
        del self._items[entity_id]


class InMemoryReferenceCatalog:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, ReferenceValue]] = {kind: {} for kind in REFERENCE_KINDS}
        self._in_use: set[tuple[str, str]] = set()

    def mark_in_use(self, kind: str, code: str) -> None:
        self._in_use.add((kind, code))

    def _table(self, kind: str) -> dict[str, ReferenceValue]:
        try:
            return self._data[kind]
        except KeyError:
            raise NotFound(f"unknown reference kind {kind!r}") from None

    def exists(self, kind: str, code: str) -> bool:
        return code in self._table(kind)

    def get(self, kind: str, code: str) -> ReferenceValue:
        try:
            return self._table(kind)[code]
        except KeyError:
            raise NotFound(f"{kind} {code!r} not found") from None

    def list(self, kind: str) -> list[ReferenceValue]:
        table = self._table(kind)
        return [table[code] for code in sorted(table)]

    def create(self, kind: str, value: ReferenceValue) -> ReferenceValue:
        table = self._table(kind)
        if value.code in table:
            raise AlreadyExists(f"{kind} {value.code!r} already exists")
        table[value.code] = value
        return value

    def update(self, kind: str, code: str, value: ReferenceValue) -> ReferenceValue:
        table = self._table(kind)
        if code not in table:
            raise NotFound(f"{kind} {code!r} not found")
        if value.code != code and value.code in table:
            raise AlreadyExists(f"{kind} {value.code!r} already exists")
        del table[code]
        table[value.code] = value
        return value

    def delete(self, kind: str, code: str) -> None:
        table = self._table(kind)
        if code not in table:
            raise NotFound(f"{kind} {code!r} not found")
        if (kind, code) in self._in_use:
            raise ReferenceInUse(f"{kind} {code!r} is still referenced")
        del table[code]


def default_catalog() -> InMemoryReferenceCatalog:
    """A catalog seeded with the values the unit tests rely on."""
    catalog = InMemoryReferenceCatalog()
    levels = (("EXTREME", 4), ("SERIOUS", 3), ("MODERATE", 2), ("LOW", 1))
    for kind, cls in (
        ("confidentiality_level", ConfidentialityLevel),
        ("integrity_level", IntegrityLevel),
        ("traceability_level", TraceabilityLevel),
    ):
        for code, rank in levels:
            catalog.create(kind, cls(code=code, label=code.title(), rank=rank))
    rpo_rto = {"EXTREME": (2, 0), "SERIOUS": (4, 0), "MODERATE": (24, 24), "LOW": (72, 24)}
    for code, rank in levels:
        rpo, rto = rpo_rto[code]
        catalog.create(
            "availability_level",
            AvailabilityLevel(
                code=code, label=code.title(), rank=rank, rpo_hours=rpo, rto_hours=rto
            ),
        )
    for code in ("COMMON", "BUSINESS", "EXCHANGE", "DATA"):
        catalog.create("function_category", FunctionCategory(code=code, label=code.title()))
    for code in ("SOURCE", "CONSUMER", "PROXY"):
        catalog.create("usage_mode", UsageMode(code=code, label=code.title()))
    catalog.create("technology_type", TechnologyType(code="DATABASE", label="Database"))
    catalog.create("tech_standard_status", TechStandardStatus(code="REFERENCE", label="Reference"))
    return catalog


def fake_repositories() -> Repositories:
    return Repositories(
        teams=InMemoryRepository(),
        members=InMemoryRepository(),
        applications=InMemoryRepository(),
        functions=InMemoryRepository(),
        data_types=InMemoryRepository(),
        data_flows=InMemoryRepository(),
        technologies=InMemoryRepository(),
        personas=InMemoryRepository(),
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_fakes.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/archimaid/ports tests/fakes.py tests/test_fakes.py
git commit -m "feat(ports): repository and reference catalog ports with in-memory fakes" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Generic CRUD service

**Files:**
- Create: `src/archimaid/application/crud.py`
- Test: `tests/application/test_crud_service.py`

**Interfaces:**
- Consumes: `Repository`, `ReferenceCatalog`, `Entity` and the errors.
- Produces:
  - `ParentLink(field: str, repository: Repository)`, a frozen dataclass naming an id field and the repository its id must exist in.
  - `utc_now() -> datetime`.
  - `CrudService[T]` with constructor `CrudService(entity_cls, repository, catalog, *, reference_fields: Mapping[str, str] | None = None, parents: Sequence[ParentLink] = (), clock=utc_now)`, where `reference_fields` maps a field name to a catalog kind.
  - `CrudService` methods:
    - `create(data: Mapping[str, Any]) -> T`
    - `get(entity_id) -> T`, which raises `NotFound`
    - `list(**filters) -> list[T]`
    - `update(entity_id, data) -> T`, which replaces the given fields and sets `updated_at`
    - `delete(entity_id) -> None`
    - `present_many(entities) -> list[Any]`, which defaults to the entities themselves. `ApplicationService` overrides it.
  - Validation order on create and update: `entity.validate()`, then catalog codes (`InvalidReferenceCode`), then parent ids (`DanglingReference`). A `None` code or id is skipped.

- [ ] **Step 1: Write the failing test**

`tests/application/test_crud_service.py`:
```python
from datetime import UTC, datetime, timedelta
from itertools import count
from uuid import uuid4

import pytest

from archimaid.application.crud import CrudService, ParentLink
from archimaid.domain.entities import Application, Team
from archimaid.domain.errors import (
    DanglingReference,
    InvalidEntity,
    InvalidReferenceCode,
    NotFound,
    ReferenceInUse,
)
from tests.fakes import InMemoryRepository, default_catalog

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def ticking_clock():
    ticks = count()
    return lambda: NOW + timedelta(minutes=next(ticks))


@pytest.fixture
def team_repo():
    return InMemoryRepository[Team]()


@pytest.fixture
def app_repo():
    return InMemoryRepository[Application]()


@pytest.fixture
def apps(team_repo, app_repo):
    return CrudService(
        Application,
        app_repo,
        default_catalog(),
        reference_fields={"availability_level": "availability_level"},
        parents=[ParentLink("team_id", team_repo)],
        clock=ticking_clock(),
    )


@pytest.fixture
def team(team_repo):
    t = Team(id=uuid4(), name="Payments", created_at=NOW, updated_at=NOW)
    team_repo.add(t)
    return t


def test_create_assigns_id_and_timestamps_and_stores(apps, app_repo, team):
    app = apps.create({"team_id": team.id, "name": "Billing"})
    assert app_repo.get(app.id) == app
    assert app.created_at == app.updated_at


@pytest.mark.parametrize("name", ["", "   "])
def test_create_rejects_blank_name_and_stores_nothing(apps, app_repo, team, name):
    # Review Focus test (1)
    with pytest.raises(InvalidEntity):
        apps.create({"team_id": team.id, "name": name})
    assert app_repo.list() == []


def test_create_rejects_unknown_reference_code(apps, team):
    with pytest.raises(InvalidReferenceCode):
        apps.create({"team_id": team.id, "name": "Billing", "availability_level": "NOPE"})


def test_create_accepts_known_and_null_reference_codes(apps, team):
    assert apps.create(
        {"team_id": team.id, "name": "A", "availability_level": "SERIOUS"}
    ).availability_level == "SERIOUS"
    assert apps.create(
        {"team_id": team.id, "name": "B", "availability_level": None}
    ).availability_level is None


def test_create_rejects_unknown_parent_id(apps, app_repo):
    # Review Focus test (4)
    with pytest.raises(DanglingReference):
        apps.create({"team_id": uuid4(), "name": "Billing"})
    assert app_repo.list() == []


def test_get_missing_raises_not_found(apps):
    with pytest.raises(NotFound):
        apps.get(uuid4())


def test_list_filters(apps, team):
    apps.create({"team_id": team.id, "name": "A"})
    apps.create({"team_id": team.id, "name": "B"})
    assert [a.name for a in apps.list(name="B")] == ["B"]
    assert len(apps.list()) == 2


def test_update_replaces_fields_keeps_created_at_and_bumps_updated_at(apps, team):
    app = apps.create({"team_id": team.id, "name": "Billing"})
    updated = apps.update(app.id, {"team_id": team.id, "name": "Billing v2"})
    assert updated.name == "Billing v2"
    assert updated.created_at == app.created_at
    assert updated.updated_at > app.created_at


def test_update_that_fails_validation_leaves_stored_entity_untouched(apps, team):
    app = apps.create({"team_id": team.id, "name": "Billing"})
    with pytest.raises(InvalidEntity):  # Review Focus test (1), PUT path
        apps.update(app.id, {"team_id": team.id, "name": " "})
    with pytest.raises(DanglingReference):  # Review Focus test (4), PUT path
        apps.update(app.id, {"team_id": uuid4(), "name": "x"})
    assert apps.get(app.id).name == "Billing"


def test_update_missing_raises_not_found(apps, team):
    with pytest.raises(NotFound):
        apps.update(uuid4(), {"team_id": team.id, "name": "x"})


def test_delete_removes_and_missing_raises(apps, team):
    app = apps.create({"team_id": team.id, "name": "Billing"})
    apps.delete(app.id)
    with pytest.raises(NotFound):
        apps.get(app.id)
    with pytest.raises(NotFound):
        apps.delete(app.id)


def test_delete_propagates_reference_in_use(apps, app_repo, team):
    app = apps.create({"team_id": team.id, "name": "Billing"})
    app_repo.mark_in_use(app.id)
    with pytest.raises(ReferenceInUse):
        apps.delete(app.id)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/application/test_crud_service.py -v`
Expected: FAIL with `ModuleNotFoundError: archimaid.application.crud`

- [ ] **Step 3: Implement**

`src/archimaid/application/crud.py`:
```python
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from archimaid.domain.entities import Entity
from archimaid.domain.errors import DanglingReference, InvalidReferenceCode, NotFound
from archimaid.ports.reference_catalog import ReferenceCatalog
from archimaid.ports.repository import Repository


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ParentLink:
    """An id field of the entity that must exist in ``repository``."""

    field: str
    repository: Repository[Any]


class CrudService[T: Entity]:
    def __init__(
        self,
        entity_cls: type[T],
        repository: Repository[T],
        catalog: ReferenceCatalog,
        *,
        reference_fields: Mapping[str, str] | None = None,
        parents: Sequence[ParentLink] = (),
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._entity_cls = entity_cls
        self._repo = repository
        self._catalog = catalog
        self._reference_fields = dict(reference_fields or {})
        self._parents = tuple(parents)
        self._clock = clock

    def create(self, data: Mapping[str, Any]) -> T:
        now = self._clock()
        entity = self._entity_cls(id=uuid4(), created_at=now, updated_at=now, **data)
        self._check(entity)
        self._repo.add(entity)
        return entity

    def get(self, entity_id: UUID) -> T:
        entity = self._repo.get(entity_id)
        if entity is None:
            raise NotFound(f"{self._entity_cls.__name__} {entity_id} not found")
        return entity

    def list(self, **filters: Any) -> list[T]:
        return self._repo.list(**filters)

    def update(self, entity_id: UUID, data: Mapping[str, Any]) -> T:
        existing = self.get(entity_id)
        updated = replace(existing, **data, updated_at=self._clock())
        self._check(updated)
        self._repo.update(updated)
        return updated

    def delete(self, entity_id: UUID) -> None:
        self.get(entity_id)
        self._repo.delete(entity_id)

    def present_many(self, entities: Sequence[T]) -> list[Any]:
        """Objects handed to the API layer. Subclasses may add derived fields."""
        return list(entities)

    def _check(self, entity: T) -> None:
        entity.validate()
        for field, kind in self._reference_fields.items():
            code = getattr(entity, field)
            if code is not None and not self._catalog.exists(kind, code):
                raise InvalidReferenceCode(f"{code!r} is not a valid {kind}")
        for link in self._parents:
            parent_id = getattr(entity, link.field)
            if parent_id is not None and link.repository.get(parent_id) is None:
                raise DanglingReference(f"{link.field} {parent_id} does not exist")
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/application/test_crud_service.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add src/archimaid/application/crud.py tests/application/test_crud_service.py
git commit -m "feat(application): generic CRUD service with reference and parent validation" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: ApplicationService, ReferenceAdminService and service wiring

**Files:**
- Create: `src/archimaid/application/applications.py`, `src/archimaid/application/reference_admin.py`, `src/archimaid/application/services.py`
- Test: `tests/application/test_services.py`

**Interfaces:**
- Consumes: `CrudService`, `ParentLink`, `utc_now` (Task 4), `Repositories`, `ReferenceCatalog` and `REFERENCE_KINDS`.
- Produces:
  - `ApplicationService(CrudService[Application])` whose `present_many(apps)` returns one dict per application with every entity field plus `rpo` and `rto` (int hours or `None`).
  - `ReferenceAdminService(catalog)` with:
    - `kinds() -> list[str]`
    - `list(kind) -> list[ReferenceValue]`
    - `get(kind, code) -> ReferenceValue`
    - `create(kind, data: Mapping[str, Any]) -> ReferenceValue`
    - `update(kind, code, data: Mapping[str, Any]) -> ReferenceValue`
    - `delete(kind, code) -> None`
    - An unknown kind raises `NotFound`.
  - `Services` dataclass with fields `teams, members, applications, functions, data_types, data_flows, technologies, personas, reference`.
  - `build_services(repos: Repositories, catalog: ReferenceCatalog, clock=utc_now) -> Services`.

Wiring table (`reference_fields` is field→kind, `parents` is id field→repository):

| Service | reference_fields | parents |
|---|---|---|
| teams | none | none |
| members | none | `team_id`→teams |
| applications | the four levels, each → its own kind | `team_id`→teams |
| functions | `category`→`function_category` | `application_id`→applications, `persona_id`→personas |
| data_types | `confidentiality_level`→`confidentiality_level` | `application_id`→applications |
| data_flows | `usage_mode`→`usage_mode` | `source_application_id`, `target_application_id`→applications, `data_type_id`→data_types |
| technologies | `type`→`technology_type`, `standard_status`→`tech_standard_status` | `application_id`→applications |
| personas | none | none |

- [ ] **Step 1: Write the failing test**

`tests/application/test_services.py`:
```python
from uuid import uuid4

import pytest

from archimaid.application.services import build_services
from archimaid.domain.errors import (
    AlreadyExists,
    DanglingReference,
    InvalidEntity,
    InvalidReferenceCode,
    NotFound,
    ReferenceInUse,
)
from archimaid.domain.reference import AvailabilityLevel
from tests.fakes import default_catalog, fake_repositories


@pytest.fixture
def catalog():
    return default_catalog()


@pytest.fixture
def services(catalog):
    return build_services(fake_repositories(), catalog)


def make_app(services, **extra):
    team = services.teams.create({"name": "Payments"})
    return services.applications.create({"team_id": team.id, "name": "Billing", **extra})


def test_application_view_exposes_derived_rpo_and_rto(services):
    app = make_app(services, availability_level="SERIOUS")
    [row] = services.applications.present_many([app])
    assert (row["rpo"], row["rto"]) == (4, 0)
    assert row["name"] == "Billing"
    assert row["availability_level"] == "SERIOUS"


def test_application_without_availability_has_null_rpo_and_rto(services):
    [row] = services.applications.present_many([make_app(services)])
    assert row["rpo"] is None
    assert row["rto"] is None


def test_rpo_and_rto_follow_catalog_edits(services, catalog):
    app = make_app(services, availability_level="SERIOUS")
    catalog.update(
        "availability_level",
        "SERIOUS",
        AvailabilityLevel(code="SERIOUS", label="Serious", rank=3, rpo_hours=1, rto_hours=2),
    )
    [row] = services.applications.present_many([app])
    assert (row["rpo"], row["rto"]) == (1, 2)


def test_application_rejects_unknown_level_code(services):
    team = services.teams.create({"name": "Payments"})
    with pytest.raises(InvalidReferenceCode):
        services.applications.create(
            {"team_id": team.id, "name": "A", "integrity_level": "NOPE"}
        )


def test_team_member_requires_existing_team(services):
    with pytest.raises(DanglingReference):
        services.members.create({"team_id": uuid4(), "user_id": "u1", "name": "Ann"})


def test_function_requires_existing_persona(services):
    app = make_app(services)
    with pytest.raises(DanglingReference):
        services.functions.create(
            {"application_id": app.id, "name": "Invoice", "persona_id": uuid4()}
        )
    persona = services.personas.create({"name": "Accountant"})
    fn = services.functions.create(
        {"application_id": app.id, "name": "Invoice", "persona_id": persona.id, "category": "DATA"}
    )
    assert fn.persona_id == persona.id


def test_data_flow_requires_existing_apps_and_data_type(services):
    source, target = make_app(services), make_app(services)
    data_type = services.data_types.create({"application_id": source.id, "name": "Invoice"})
    flow = {
        "source_application_id": source.id,
        "target_application_id": target.id,
        "data_type_id": data_type.id,
        "usage_mode": "SOURCE",
    }
    assert services.data_flows.create(flow).usage_mode == "SOURCE"
    for field in ("source_application_id", "target_application_id", "data_type_id"):
        with pytest.raises(DanglingReference):
            services.data_flows.create({**flow, field: uuid4()})
    with pytest.raises(InvalidReferenceCode):
        services.data_flows.create({**flow, "usage_mode": "NOPE"})


def test_technology_validates_both_codes(services):
    app = make_app(services)
    with pytest.raises(InvalidReferenceCode):
        services.technologies.create({"application_id": app.id, "name": "PG", "type": "NOPE"})
    with pytest.raises(InvalidReferenceCode):
        services.technologies.create(
            {"application_id": app.id, "name": "PG", "standard_status": "NOPE"}
        )
    tech = services.technologies.create(
        {"application_id": app.id, "name": "PG", "type": "DATABASE", "standard_status": "REFERENCE"}
    )
    assert tech.type == "DATABASE"


def test_reference_admin_lists_kinds_and_values(services):
    assert "availability_level" in services.reference.kinds()
    assert [v.code for v in services.reference.list("usage_mode")] == [
        "CONSUMER",
        "PROXY",
        "SOURCE",
    ]


def test_reference_admin_create_get_update_delete(services):
    created = services.reference.create(
        "function_category", {"code": "EXTRA", "label": "Extra"}
    )
    assert services.reference.get("function_category", "EXTRA") == created
    updated = services.reference.update(
        "function_category", "EXTRA", {"code": "EXTRA", "label": "Extra 2"}
    )
    assert updated.label == "Extra 2"
    services.reference.delete("function_category", "EXTRA")
    with pytest.raises(NotFound):
        services.reference.get("function_category", "EXTRA")


def test_reference_admin_builds_the_kind_specific_value(services):
    value = services.reference.create(
        "availability_level",
        {"code": "TINY", "label": "Tiny", "rank": 0, "rpo_hours": 1, "rto_hours": 1},
    )
    assert isinstance(value, AvailabilityLevel)


def test_reference_admin_errors(services, catalog):
    with pytest.raises(NotFound):
        services.reference.list("nope")
    with pytest.raises(AlreadyExists):
        services.reference.create("usage_mode", {"code": "SOURCE", "label": "Source"})
    with pytest.raises(InvalidEntity):
        services.reference.create("usage_mode", {"code": " ", "label": "x"})
    catalog.mark_in_use("usage_mode", "PROXY")
    with pytest.raises(ReferenceInUse):
        services.reference.delete("usage_mode", "PROXY")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/application/test_services.py -v`
Expected: FAIL with `ModuleNotFoundError: archimaid.application.services`

- [ ] **Step 3: Implement**

`src/archimaid/application/applications.py`:
```python
from collections.abc import Sequence
from dataclasses import fields
from typing import Any

from archimaid.application.crud import CrudService
from archimaid.domain.entities import Application
from archimaid.domain.reference import AvailabilityLevel


class ApplicationService(CrudService[Application]):
    def present_many(self, entities: Sequence[Application]) -> list[Any]:
        """Entity fields plus ``rpo``/``rto`` read from the availability_level catalog."""
        levels = {
            value.code: value
            for value in self._catalog.list("availability_level")
            if isinstance(value, AvailabilityLevel)
        }
        rows: list[Any] = []
        for app in entities:
            row = {f.name: getattr(app, f.name) for f in fields(app)}
            level = levels.get(app.availability_level) if app.availability_level else None
            row["rpo"] = level.rpo_hours if level else None
            row["rto"] = level.rto_hours if level else None
            rows.append(row)
        return rows
```

`src/archimaid/application/reference_admin.py`:
```python
from collections.abc import Mapping
from typing import Any

from archimaid.domain.errors import NotFound
from archimaid.domain.reference import REFERENCE_KINDS, ReferenceValue
from archimaid.ports.reference_catalog import ReferenceCatalog


class ReferenceAdminService:
    def __init__(self, catalog: ReferenceCatalog) -> None:
        self._catalog = catalog

    def kinds(self) -> list[str]:
        return list(REFERENCE_KINDS)

    def list(self, kind: str) -> list[ReferenceValue]:
        self._require(kind)
        return self._catalog.list(kind)

    def get(self, kind: str, code: str) -> ReferenceValue:
        self._require(kind)
        return self._catalog.get(kind, code)

    def create(self, kind: str, data: Mapping[str, Any]) -> ReferenceValue:
        value = self._build(kind, data)
        return self._catalog.create(kind, value)

    def update(self, kind: str, code: str, data: Mapping[str, Any]) -> ReferenceValue:
        value = self._build(kind, data)
        return self._catalog.update(kind, code, value)

    def delete(self, kind: str, code: str) -> None:
        self._require(kind)
        self._catalog.delete(kind, code)

    def _require(self, kind: str) -> type[ReferenceValue]:
        try:
            return REFERENCE_KINDS[kind]
        except KeyError:
            raise NotFound(f"unknown reference kind {kind!r}") from None

    def _build(self, kind: str, data: Mapping[str, Any]) -> ReferenceValue:
        return self._require(kind)(**data)
```

`src/archimaid/application/services.py`:
```python
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from archimaid.application.applications import ApplicationService
from archimaid.application.crud import CrudService, ParentLink, utc_now
from archimaid.application.reference_admin import ReferenceAdminService
from archimaid.domain.entities import (
    Application,
    DataFlow,
    DataType,
    Function,
    Persona,
    Team,
    TeamMember,
    Technology,
)
from archimaid.ports.reference_catalog import ReferenceCatalog
from archimaid.ports.repository import Repositories


@dataclass
class Services:
    teams: CrudService[Team]
    members: CrudService[TeamMember]
    applications: ApplicationService
    functions: CrudService[Function]
    data_types: CrudService[DataType]
    data_flows: CrudService[DataFlow]
    technologies: CrudService[Technology]
    personas: CrudService[Persona]
    reference: ReferenceAdminService


def build_services(
    repos: Repositories,
    catalog: ReferenceCatalog,
    clock: Callable[[], datetime] = utc_now,
) -> Services:
    return Services(
        teams=CrudService(Team, repos.teams, catalog, clock=clock),
        members=CrudService(
            TeamMember,
            repos.members,
            catalog,
            parents=[ParentLink("team_id", repos.teams)],
            clock=clock,
        ),
        applications=ApplicationService(
            Application,
            repos.applications,
            catalog,
            reference_fields={
                "confidentiality_level": "confidentiality_level",
                "integrity_level": "integrity_level",
                "availability_level": "availability_level",
                "traceability_level": "traceability_level",
            },
            parents=[ParentLink("team_id", repos.teams)],
            clock=clock,
        ),
        functions=CrudService(
            Function,
            repos.functions,
            catalog,
            reference_fields={"category": "function_category"},
            parents=[
                ParentLink("application_id", repos.applications),
                ParentLink("persona_id", repos.personas),
            ],
            clock=clock,
        ),
        data_types=CrudService(
            DataType,
            repos.data_types,
            catalog,
            reference_fields={"confidentiality_level": "confidentiality_level"},
            parents=[ParentLink("application_id", repos.applications)],
            clock=clock,
        ),
        data_flows=CrudService(
            DataFlow,
            repos.data_flows,
            catalog,
            reference_fields={"usage_mode": "usage_mode"},
            parents=[
                ParentLink("source_application_id", repos.applications),
                ParentLink("target_application_id", repos.applications),
                ParentLink("data_type_id", repos.data_types),
            ],
            clock=clock,
        ),
        technologies=CrudService(
            Technology,
            repos.technologies,
            catalog,
            reference_fields={
                "type": "technology_type",
                "standard_status": "tech_standard_status",
            },
            parents=[ParentLink("application_id", repos.applications)],
            clock=clock,
        ),
        personas=CrudService(Persona, repos.personas, catalog, clock=clock),
        reference=ReferenceAdminService(catalog),
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/application -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/archimaid/application tests/application/test_services.py
git commit -m "feat(application): application service with derived RPO/RTO, reference admin, wiring" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Postgres schema, seed migrations and test fixtures

**Files:**
- Create: `src/archimaid/adapters/persistence/tables.py`, `src/archimaid/adapters/persistence/migrate.py`, `src/archimaid/adapters/persistence/migrations/env.py`, `src/archimaid/adapters/persistence/migrations/script.py.mako`, `src/archimaid/adapters/persistence/migrations/versions/0001_schema.py`, `src/archimaid/adapters/persistence/migrations/versions/0002_seed_reference_values.py`, `tests/conftest.py`
- Test: `tests/adapters/persistence/test_migrations.py`

**Interfaces:**
- Consumes: `REFERENCE_KINDS` and the entity classes.
- Produces:
  - `tables.metadata`, `tables.REFERENCE_TABLES: dict[str, Table]` (keyed by kind), `tables.ENTITY_TABLES: dict[type[Entity], Table]`.
  - `migrate.run_migrations(url: str) -> None`, which upgrades to head. `python -m archimaid.adapters.persistence.migrate` runs it with `DATABASE_URL`.
  - pytest fixtures `postgres_url` (session) and `engine` (function, fresh migrated schema per test). Both skip when Docker is unavailable.
- Table and column names equal the entity field names in Task 2. Catalog tables have `code`, `label` and `description`, plus `rank` (and `rpo_hours`, `rto_hours` for `availability_level`).

- [ ] **Step 1: Write the failing test and fixtures**

`tests/conftest.py`:
```python
import pytest


@pytest.fixture(scope="session")
def postgres_url():
    try:
        from testcontainers.postgres import PostgresContainer

        container = PostgresContainer("postgres:16-alpine", driver="psycopg")
        container.start()
    except Exception as exc:  # Docker missing or not running
        pytest.skip(f"Docker/Postgres unavailable: {exc}")
    yield container.get_connection_url()
    container.stop()


@pytest.fixture
def engine(postgres_url):
    from sqlalchemy import create_engine, text

    from archimaid.adapters.persistence.migrate import run_migrations

    engine = create_engine(postgres_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    run_migrations(postgres_url)
    yield engine
    engine.dispose()
```

`tests/adapters/persistence/test_migrations.py`:
```python
import pytest
from sqlalchemy import inspect, text

from archimaid.adapters.persistence.tables import metadata

pytestmark = pytest.mark.postgres

LEVELS = {"EXTREME", "SERIOUS", "MODERATE", "LOW"}
SEEDED = {
    "confidentiality_level": LEVELS,
    "integrity_level": LEVELS,
    "availability_level": LEVELS,
    "traceability_level": LEVELS,
    "function_category": {"COMMON", "BUSINESS", "EXCHANGE", "DATA"},
    "usage_mode": {"SOURCE", "CONSUMER", "PROXY"},
    "technology_type": {
        "OPERATING_SYSTEM",
        "FRAMEWORK_LIBRARY",
        "WEB_SERVER",
        "APPLICATION_SERVER",
        "DATABASE",
        "SOFTWARE",
        "SAAS_SERVICE",
        "RUNTIME_INTERPRETER",
        "CI_CD",
        "DEV_LANG",
        "ETL",
    },
    "tech_standard_status": {
        "EMERGING",
        "UPCOMING",
        "REFERENCE",
        "CONFINED",
        "TO_BE_PHASED_OUT",
        "DECOMMISSIONED",
        "REJECTED",
    },
}


def test_every_catalog_is_seeded_with_the_original_enum_values(engine):
    with engine.connect() as conn:
        for kind, codes in SEEDED.items():
            rows = conn.execute(text(f"SELECT code FROM {kind}")).all()
            assert {r[0] for r in rows} == codes, kind


def test_availability_levels_carry_the_rpo_rto_mapping(engine):
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT code, rpo_hours, rto_hours FROM availability_level")
        ).all()
    assert {r[0]: (r[1], r[2]) for r in rows} == {
        "LOW": (72, 24),
        "MODERATE": (24, 24),
        "SERIOUS": (4, 0),
        "EXTREME": (2, 0),
    }


def test_rank_orders_levels_from_extreme_to_low(engine):
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT code FROM integrity_level ORDER BY rank DESC")).all()
    assert [r[0] for r in rows] == ["EXTREME", "SERIOUS", "MODERATE", "LOW"]


def test_sqlalchemy_metadata_matches_the_migrated_schema(engine):
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) - {"alembic_version"} == set(metadata.tables)
    for table in metadata.tables.values():
        db_columns = {c["name"] for c in inspector.get_columns(table.name)}
        assert {c.name for c in table.columns} == db_columns, table.name
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/adapters/persistence/test_migrations.py -v`
Expected: collection error `ModuleNotFoundError: archimaid.adapters.persistence.tables`

- [ ] **Step 3: Implement the table metadata**

`src/archimaid/adapters/persistence/tables.py`:
```python
from dataclasses import fields

from sqlalchemy import Column, DateTime, ForeignKey, Integer, MetaData, Table, Text, Uuid

from archimaid.domain.entities import (
    Application,
    DataFlow,
    DataType,
    Entity,
    Function,
    Persona,
    Team,
    TeamMember,
    Technology,
)
from archimaid.domain.reference import REFERENCE_KINDS, ReferenceValue

metadata = MetaData()


def _catalog_table(kind: str, cls: type[ReferenceValue]) -> Table:
    base = {"code", "label", "description"}
    columns = [
        Column("code", Text, primary_key=True),
        Column("label", Text, nullable=False),
        Column("description", Text),
    ]
    columns += [Column(f.name, Integer, nullable=False) for f in fields(cls) if f.name not in base]
    return Table(kind, metadata, *columns)


REFERENCE_TABLES: dict[str, Table] = {
    kind: _catalog_table(kind, cls) for kind, cls in REFERENCE_KINDS.items()
}


def _id() -> Column:
    return Column("id", Uuid, primary_key=True)


def _timestamps() -> list[Column]:
    return [
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
    ]


def _text(name: str, nullable: bool = True) -> Column:
    return Column(name, Text, nullable=nullable)


def _code_ref(column: str, kind: str) -> Column:
    return Column(
        column,
        Text,
        ForeignKey(f"{kind}.code", onupdate="CASCADE", ondelete="RESTRICT"),
    )


def _id_ref(column: str, table: str, ondelete: str, nullable: bool = False) -> Column:
    return Column(column, Uuid, ForeignKey(f"{table}.id", ondelete=ondelete), nullable=nullable)


team = Table(
    "team",
    metadata,
    _id(),
    _text("name", nullable=False),
    Column("description", Text, nullable=False, server_default=""),
    *_timestamps(),
)

team_member = Table(
    "team_member",
    metadata,
    _id(),
    _id_ref("team_id", "team", "CASCADE"),
    _text("user_id", nullable=False),
    _text("name", nullable=False),
    *_timestamps(),
)

application = Table(
    "application",
    metadata,
    _id(),
    _id_ref("team_id", "team", "RESTRICT"),
    _text("name", nullable=False),
    _text("golden_app_id"),
    _text("auid"),
    _text("description"),
    _text("asset_cmdb"),
    _text("shortname"),
    _text("owner_uid"),
    _code_ref("confidentiality_level", "confidentiality_level"),
    _code_ref("integrity_level", "integrity_level"),
    _code_ref("availability_level", "availability_level"),
    _code_ref("traceability_level", "traceability_level"),
    *_timestamps(),
)

persona = Table(
    "persona",
    metadata,
    _id(),
    _text("name", nullable=False),
    _text("description"),
    _text("category"),
    *_timestamps(),
)

function = Table(
    "function",
    metadata,
    _id(),
    _id_ref("application_id", "application", "CASCADE"),
    _id_ref("persona_id", "persona", "RESTRICT", nullable=True),
    _text("name", nullable=False),
    _text("description"),
    _code_ref("category", "function_category"),
    *_timestamps(),
)

data_type = Table(
    "data_type",
    metadata,
    _id(),
    _id_ref("application_id", "application", "CASCADE"),
    _text("name", nullable=False),
    _text("definition"),
    _text("specificity"),
    _code_ref("confidentiality_level", "confidentiality_level"),
    _text("golden_source"),
    _text("golden_replica"),
    *_timestamps(),
)

data_flow = Table(
    "data_flow",
    metadata,
    _id(),
    _id_ref("source_application_id", "application", "RESTRICT"),
    _id_ref("target_application_id", "application", "RESTRICT"),
    _id_ref("data_type_id", "data_type", "RESTRICT"),
    _code_ref("usage_mode", "usage_mode"),
    _text("usage_explanation"),
    *_timestamps(),
)

technology = Table(
    "technology",
    metadata,
    _id(),
    _id_ref("application_id", "application", "CASCADE"),
    _text("name", nullable=False),
    _text("version"),
    _text("family"),
    _code_ref("type", "technology_type"),
    _code_ref("standard_status", "tech_standard_status"),
    _text("standard_status_details"),
    _text("tech_standards_link"),
    _text("action_plan"),
    *_timestamps(),
)

ENTITY_TABLES: dict[type[Entity], Table] = {
    Team: team,
    TeamMember: team_member,
    Application: application,
    Function: function,
    DataType: data_type,
    DataFlow: data_flow,
    Technology: technology,
    Persona: persona,
}
```

- [ ] **Step 4: Implement migration plumbing**

`src/archimaid/adapters/persistence/migrate.py`:
```python
import os
from pathlib import Path

from alembic import command
from alembic.config import Config


def run_migrations(url: str) -> None:
    """Upgrade the database at ``url`` to the latest revision."""
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")


if __name__ == "__main__":
    run_migrations(os.environ["DATABASE_URL"])
```

`src/archimaid/adapters/persistence/migrations/env.py`:
```python
from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
```

`src/archimaid/adapters/persistence/migrations/script.py.mako`:
```
"""${message}"""
import sqlalchemy as sa
from alembic import op

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 5: Implement migration 0001 (schema)**

`src/archimaid/adapters/persistence/migrations/versions/0001_schema.py`:
```python
"""Initial schema: configuration tables and entity tables."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

CATALOGS = {
    "confidentiality_level": ("rank",),
    "integrity_level": ("rank",),
    "availability_level": ("rank", "rpo_hours", "rto_hours"),
    "traceability_level": ("rank",),
    "function_category": (),
    "usage_mode": (),
    "technology_type": (),
    "tech_standard_status": (),
}

ENTITY_TABLES = (
    "data_flow",
    "technology",
    "data_type",
    "function",
    "persona",
    "application",
    "team_member",
    "team",
)


def _id():
    return sa.Column("id", sa.Uuid, primary_key=True)


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _text(name, nullable=True):
    return sa.Column(name, sa.Text, nullable=nullable)


def _code_ref(column, kind):
    return sa.Column(
        column,
        sa.Text,
        sa.ForeignKey(f"{kind}.code", onupdate="CASCADE", ondelete="RESTRICT"),
    )


def _id_ref(column, table, ondelete, nullable=False):
    return sa.Column(
        column, sa.Uuid, sa.ForeignKey(f"{table}.id", ondelete=ondelete), nullable=nullable
    )


def upgrade() -> None:
    for name, extra in CATALOGS.items():
        op.create_table(
            name,
            sa.Column("code", sa.Text, primary_key=True),
            sa.Column("label", sa.Text, nullable=False),
            sa.Column("description", sa.Text),
            *[sa.Column(column, sa.Integer, nullable=False) for column in extra],
        )

    op.create_table(
        "team",
        _id(),
        _text("name", nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        *_timestamps(),
    )
    op.create_table(
        "team_member",
        _id(),
        _id_ref("team_id", "team", "CASCADE"),
        _text("user_id", nullable=False),
        _text("name", nullable=False),
        *_timestamps(),
    )
    op.create_table(
        "application",
        _id(),
        _id_ref("team_id", "team", "RESTRICT"),
        _text("name", nullable=False),
        _text("golden_app_id"),
        _text("auid"),
        _text("description"),
        _text("asset_cmdb"),
        _text("shortname"),
        _text("owner_uid"),
        _code_ref("confidentiality_level", "confidentiality_level"),
        _code_ref("integrity_level", "integrity_level"),
        _code_ref("availability_level", "availability_level"),
        _code_ref("traceability_level", "traceability_level"),
        *_timestamps(),
    )
    op.create_table(
        "persona",
        _id(),
        _text("name", nullable=False),
        _text("description"),
        _text("category"),
        *_timestamps(),
    )
    op.create_table(
        "function",
        _id(),
        _id_ref("application_id", "application", "CASCADE"),
        _id_ref("persona_id", "persona", "RESTRICT", nullable=True),
        _text("name", nullable=False),
        _text("description"),
        _code_ref("category", "function_category"),
        *_timestamps(),
    )
    op.create_table(
        "data_type",
        _id(),
        _id_ref("application_id", "application", "CASCADE"),
        _text("name", nullable=False),
        _text("definition"),
        _text("specificity"),
        _code_ref("confidentiality_level", "confidentiality_level"),
        _text("golden_source"),
        _text("golden_replica"),
        *_timestamps(),
    )
    op.create_table(
        "data_flow",
        _id(),
        _id_ref("source_application_id", "application", "RESTRICT"),
        _id_ref("target_application_id", "application", "RESTRICT"),
        _id_ref("data_type_id", "data_type", "RESTRICT"),
        _code_ref("usage_mode", "usage_mode"),
        _text("usage_explanation"),
        *_timestamps(),
    )
    op.create_table(
        "technology",
        _id(),
        _id_ref("application_id", "application", "CASCADE"),
        _text("name", nullable=False),
        _text("version"),
        _text("family"),
        _code_ref("type", "technology_type"),
        _code_ref("standard_status", "tech_standard_status"),
        _text("standard_status_details"),
        _text("tech_standards_link"),
        _text("action_plan"),
        *_timestamps(),
    )


def downgrade() -> None:
    for name in ENTITY_TABLES:
        op.drop_table(name)
    for name in CATALOGS:
        op.drop_table(name)
```

- [ ] **Step 6: Implement migration 0002 (seed)**

`src/archimaid/adapters/persistence/migrations/versions/0002_seed_reference_values.py`:
```python
"""Seed the configuration tables with the original enum values."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

LEVELS = (("EXTREME", 4), ("SERIOUS", 3), ("MODERATE", 2), ("LOW", 1))
RPO_RTO_HOURS = {"EXTREME": (2, 0), "SERIOUS": (4, 0), "MODERATE": (24, 24), "LOW": (72, 24)}
PLAIN = {
    "function_category": ("COMMON", "BUSINESS", "EXCHANGE", "DATA"),
    "usage_mode": ("SOURCE", "CONSUMER", "PROXY"),
    "technology_type": (
        "OPERATING_SYSTEM",
        "FRAMEWORK_LIBRARY",
        "WEB_SERVER",
        "APPLICATION_SERVER",
        "DATABASE",
        "SOFTWARE",
        "SAAS_SERVICE",
        "RUNTIME_INTERPRETER",
        "CI_CD",
        "DEV_LANG",
        "ETL",
    ),
    "tech_standard_status": (
        "EMERGING",
        "UPCOMING",
        "REFERENCE",
        "CONFINED",
        "TO_BE_PHASED_OUT",
        "DECOMMISSIONED",
        "REJECTED",
    ),
}
RANKED = ("confidentiality_level", "integrity_level", "traceability_level")


def _label(code: str) -> str:
    return code.replace("_", " ").capitalize()


def upgrade() -> None:
    for name in RANKED:
        table = sa.table(name, sa.column("code"), sa.column("label"), sa.column("rank"))
        op.bulk_insert(
            table, [{"code": c, "label": _label(c), "rank": r} for c, r in LEVELS]
        )

    availability = sa.table(
        "availability_level",
        sa.column("code"),
        sa.column("label"),
        sa.column("rank"),
        sa.column("rpo_hours"),
        sa.column("rto_hours"),
    )
    op.bulk_insert(
        availability,
        [
            {
                "code": c,
                "label": _label(c),
                "rank": r,
                "rpo_hours": RPO_RTO_HOURS[c][0],
                "rto_hours": RPO_RTO_HOURS[c][1],
            }
            for c, r in LEVELS
        ],
    )

    for name, codes in PLAIN.items():
        table = sa.table(name, sa.column("code"), sa.column("label"))
        op.bulk_insert(table, [{"code": c, "label": _label(c)} for c in codes])


def downgrade() -> None:
    for name in (*RANKED, "availability_level", *PLAIN):
        op.execute(sa.text(f"DELETE FROM {name}"))
```

- [ ] **Step 7: Run to verify it passes**

Run: `uv run pytest tests/adapters/persistence/test_migrations.py -v -rs`
Expected: 4 passed. If they are skipped, Docker is unavailable: start it and re-run.

- [ ] **Step 8: Commit**

```bash
git add src/archimaid/adapters/persistence tests/conftest.py tests/adapters/persistence/test_migrations.py
git commit -m "feat(persistence): Postgres schema, seed migrations and test fixtures" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Postgres repository and catalog adapters

**Files:**
- Create: `src/archimaid/adapters/persistence/pg_errors.py`, `src/archimaid/adapters/persistence/repository.py`, `src/archimaid/adapters/persistence/catalog.py`
- Test: `tests/adapters/persistence/test_repository.py`, `tests/adapters/persistence/test_catalog.py`

**Interfaces:**
- Consumes: `tables` (Task 6) and the ports and errors.
- Produces:
  - `pg_errors.is_foreign_key_violation(exc: IntegrityError) -> bool` and `pg_errors.is_unique_violation(exc) -> bool`.
  - `SqlRepository[T](engine, table, entity_cls)` implementing `Repository[T]`:
    - A foreign-key violation on `add` or `update` raises `DanglingReference`.
    - A foreign-key violation on `delete` raises `ReferenceInUse`.
    - `list` orders by `created_at, id`.
  - `build_repositories(engine) -> Repositories`.
  - `PostgresReferenceCatalog(engine)` implementing `ReferenceCatalog`. A unique violation on `create` or `update` raises `AlreadyExists`, and an FK violation on `delete` raises `ReferenceInUse`.

- [ ] **Step 1: Write the failing repository test**

`tests/adapters/persistence/test_repository.py`:
```python
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from archimaid.adapters.persistence.repository import build_repositories
from archimaid.domain.entities import (
    Application,
    DataFlow,
    DataType,
    Function,
    Persona,
    Team,
    TeamMember,
    Technology,
)
from archimaid.domain.errors import DanglingReference, ReferenceInUse

pytestmark = pytest.mark.postgres

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def meta():
    return {"id": uuid4(), "created_at": NOW, "updated_at": NOW}


@pytest.fixture
def repos(engine):
    return build_repositories(engine)


def add_team(repos):
    team = Team(name="Payments", description="d", **meta())
    repos.teams.add(team)
    return team


def add_app(repos, team, name="Billing"):
    app = Application(team_id=team.id, name=name, **meta())
    repos.applications.add(app)
    return app


def test_application_round_trips_every_field(repos):
    team = add_team(repos)
    app = Application(
        team_id=team.id,
        name="Billing",
        golden_app_id="G1",
        auid="A1",
        description="d",
        asset_cmdb="C",
        shortname="bil",
        owner_uid="u1",
        confidentiality_level="LOW",
        integrity_level="MODERATE",
        availability_level="SERIOUS",
        traceability_level="EXTREME",
        **meta(),
    )
    repos.applications.add(app)
    assert repos.applications.get(app.id) == app


def test_all_other_entities_round_trip(repos):
    team = add_team(repos)
    app = add_app(repos, team)
    persona = Persona(name="Accountant", description="d", category="finance", **meta())
    repos.personas.add(persona)
    member = TeamMember(team_id=team.id, user_id="u1", name="Ann", **meta())
    repos.members.add(member)
    function = Function(
        application_id=app.id, name="Invoice", description="d", category="DATA",
        persona_id=persona.id, **meta(),
    )
    repos.functions.add(function)
    data_type = DataType(
        application_id=app.id, name="Invoice", definition="d", specificity="s",
        confidentiality_level="LOW", golden_source="gs", golden_replica="gr", **meta(),
    )
    repos.data_types.add(data_type)
    flow = DataFlow(
        source_application_id=app.id, target_application_id=app.id, data_type_id=data_type.id,
        usage_mode="SOURCE", usage_explanation="why", **meta(),
    )
    repos.data_flows.add(flow)
    tech = Technology(
        application_id=app.id, name="PG", version="16", family="sql", type="DATABASE",
        standard_status="REFERENCE", standard_status_details="d", tech_standards_link="http://x",
        action_plan="none", **meta(),
    )
    repos.technologies.add(tech)
    assert repos.teams.get(team.id) == team
    assert repos.personas.get(persona.id) == persona
    assert repos.members.get(member.id) == member
    assert repos.functions.get(function.id) == function
    assert repos.data_types.get(data_type.id) == data_type
    assert repos.data_flows.get(flow.id) == flow
    assert repos.technologies.get(tech.id) == tech


def test_get_missing_returns_none(repos):
    assert repos.teams.get(uuid4()) is None


def test_list_filters_by_column(repos):
    team = add_team(repos)
    other = add_team(repos)
    a = add_app(repos, team, "A")
    add_app(repos, other, "B")
    assert repos.applications.list(team_id=team.id) == [a]
    assert len(repos.applications.list()) == 2


def test_update_persists_changes(repos):
    team = add_team(repos)
    app = add_app(repos, team)
    app.name = "Billing v2"
    app.availability_level = "LOW"
    repos.applications.update(app)
    assert repos.applications.get(app.id) == app


def test_add_with_unknown_parent_or_code_is_a_dangling_reference(repos):
    # Review Focus test (4), database backstop
    with pytest.raises(DanglingReference):
        repos.applications.add(Application(team_id=uuid4(), name="X", **meta()))
    team = add_team(repos)
    with pytest.raises(DanglingReference):
        repos.applications.add(
            Application(team_id=team.id, name="X", availability_level="NOPE", **meta())
        )


def test_delete_team_with_applications_is_blocked(repos):  # Review Focus test (3)
    team = add_team(repos)
    add_app(repos, team)
    with pytest.raises(ReferenceInUse):
        repos.teams.delete(team.id)


def test_delete_team_cascades_to_members(repos):
    team = add_team(repos)
    member = TeamMember(team_id=team.id, user_id="u1", name="Ann", **meta())
    repos.members.add(member)
    repos.teams.delete(team.id)
    assert repos.members.get(member.id) is None


def test_delete_application_cascades_to_its_children(repos):  # Review Focus test (3)
    team = add_team(repos)
    app = add_app(repos, team)
    function = Function(application_id=app.id, name="Invoice", **meta())
    data_type = DataType(application_id=app.id, name="Invoice", **meta())
    tech = Technology(application_id=app.id, name="PG", **meta())
    repos.functions.add(function)
    repos.data_types.add(data_type)
    repos.technologies.add(tech)
    repos.applications.delete(app.id)
    assert repos.functions.get(function.id) is None
    assert repos.data_types.get(data_type.id) is None
    assert repos.technologies.get(tech.id) is None


def test_delete_application_used_as_flow_source_or_target_is_blocked(repos):
    # Review Focus test (3)
    team = add_team(repos)
    source, target = add_app(repos, team, "S"), add_app(repos, team, "T")
    data_type = DataType(application_id=source.id, name="Invoice", **meta())
    repos.data_types.add(data_type)
    repos.data_flows.add(
        DataFlow(
            source_application_id=source.id, target_application_id=target.id,
            data_type_id=data_type.id, **meta(),
        )
    )
    with pytest.raises(ReferenceInUse):
        repos.applications.delete(target.id)
    with pytest.raises(ReferenceInUse):
        repos.applications.delete(source.id)  # cascades to data_type, which the flow blocks
    assert repos.applications.get(source.id) is not None


def test_delete_data_type_used_by_flow_is_blocked(repos):  # Review Focus test (3)
    team = add_team(repos)
    app = add_app(repos, team)
    data_type = DataType(application_id=app.id, name="Invoice", **meta())
    repos.data_types.add(data_type)
    repos.data_flows.add(
        DataFlow(
            source_application_id=app.id, target_application_id=app.id,
            data_type_id=data_type.id, **meta(),
        )
    )
    with pytest.raises(ReferenceInUse):
        repos.data_types.delete(data_type.id)


def test_delete_persona_used_by_function_is_blocked(repos):  # Review Focus test (3)
    team = add_team(repos)
    app = add_app(repos, team)
    persona = Persona(name="Accountant", **meta())
    repos.personas.add(persona)
    repos.functions.add(Function(application_id=app.id, name="Invoice", persona_id=persona.id, **meta()))
    with pytest.raises(ReferenceInUse):
        repos.personas.delete(persona.id)
```

- [ ] **Step 2: Write the failing catalog test**

`tests/adapters/persistence/test_catalog.py`:
```python
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from archimaid.adapters.persistence.catalog import PostgresReferenceCatalog
from archimaid.adapters.persistence.repository import build_repositories
from archimaid.domain.entities import Application, Team
from archimaid.domain.errors import AlreadyExists, NotFound, ReferenceInUse
from archimaid.domain.reference import AvailabilityLevel, FunctionCategory

pytestmark = pytest.mark.postgres

NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def catalog(engine):
    return PostgresReferenceCatalog(engine)


def application_using(engine, availability_level):
    repos = build_repositories(engine)
    team = Team(id=uuid4(), name="T", created_at=NOW, updated_at=NOW)
    repos.teams.add(team)
    app = Application(
        id=uuid4(), team_id=team.id, name="A", availability_level=availability_level,
        created_at=NOW, updated_at=NOW,
    )
    repos.applications.add(app)
    return repos, app


def test_get_returns_the_kind_specific_value_object(catalog):
    value = catalog.get("availability_level", "SERIOUS")
    assert isinstance(value, AvailabilityLevel)
    assert (value.rpo_hours, value.rto_hours, value.rank) == (4, 0, 3)


def test_list_and_exists(catalog):
    assert [v.code for v in catalog.list("usage_mode")] == ["CONSUMER", "PROXY", "SOURCE"]
    assert catalog.exists("usage_mode", "SOURCE")
    assert not catalog.exists("usage_mode", "NOPE")


def test_unknown_kind_and_unknown_code_are_not_found(catalog):
    with pytest.raises(NotFound):
        catalog.list("nope")
    with pytest.raises(NotFound):
        catalog.get("usage_mode", "NOPE")


def test_create_then_delete_unreferenced_value(catalog):
    created = catalog.create("function_category", FunctionCategory(code="EXTRA", label="Extra"))
    assert catalog.get("function_category", "EXTRA") == created
    catalog.delete("function_category", "EXTRA")
    assert not catalog.exists("function_category", "EXTRA")


def test_create_with_existing_code_is_already_exists(catalog):  # Review Focus test (2)
    with pytest.raises(AlreadyExists):
        catalog.create("function_category", FunctionCategory(code="DATA", label="Dup"))


def test_update_changes_columns(catalog):
    catalog.update(
        "availability_level", "SERIOUS",
        AvailabilityLevel(code="SERIOUS", label="Serious", rank=3, rpo_hours=1, rto_hours=2),
    )
    value = catalog.get("availability_level", "SERIOUS")
    assert (value.rpo_hours, value.rto_hours) == (1, 2)


def test_update_unknown_code_is_not_found(catalog):
    with pytest.raises(NotFound):
        catalog.update("function_category", "NOPE", FunctionCategory(code="NOPE", label="x"))


def test_rename_cascades_to_referencing_rows(engine, catalog):
    repos, app = application_using(engine, "SERIOUS")
    catalog.update(
        "availability_level", "SERIOUS",
        AvailabilityLevel(code="HIGH", label="High", rank=3, rpo_hours=4, rto_hours=0),
    )
    assert repos.applications.get(app.id).availability_level == "HIGH"
    assert not catalog.exists("availability_level", "SERIOUS")


def test_rename_onto_an_existing_code_is_already_exists(catalog):  # Review Focus test (2)
    with pytest.raises(AlreadyExists):
        catalog.update(
            "function_category", "DATA", FunctionCategory(code="COMMON", label="x")
        )
    assert catalog.exists("function_category", "DATA")


def test_delete_value_in_use_is_blocked_and_value_stays(engine, catalog):
    application_using(engine, "LOW")
    with pytest.raises(ReferenceInUse):
        catalog.delete("availability_level", "LOW")
    assert catalog.exists("availability_level", "LOW")


def test_delete_unknown_code_is_not_found(catalog):
    with pytest.raises(NotFound):
        catalog.delete("function_category", "NOPE")
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/adapters/persistence -v`
Expected: collection errors `ModuleNotFoundError: archimaid.adapters.persistence.repository` / `.catalog`

- [ ] **Step 4: Implement**

`src/archimaid/adapters/persistence/pg_errors.py`:
```python
from psycopg import errors
from sqlalchemy.exc import IntegrityError


def is_foreign_key_violation(exc: IntegrityError) -> bool:
    return isinstance(exc.orig, errors.ForeignKeyViolation | errors.RestrictViolation)


def is_unique_violation(exc: IntegrityError) -> bool:
    return isinstance(exc.orig, errors.UniqueViolation)
```

`src/archimaid/adapters/persistence/repository.py`:
```python
from dataclasses import fields
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, Table, delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from archimaid.adapters.persistence.pg_errors import is_foreign_key_violation
from archimaid.adapters.persistence.tables import ENTITY_TABLES
from archimaid.domain.entities import (
    Application,
    DataFlow,
    DataType,
    Entity,
    Function,
    Persona,
    Team,
    TeamMember,
    Technology,
)
from archimaid.domain.errors import DanglingReference, DomainError, ReferenceInUse
from archimaid.ports.repository import Repositories


class SqlRepository[T: Entity]:
    def __init__(self, engine: Engine, table: Table, entity_cls: type[T]) -> None:
        self._engine = engine
        self._table = table
        self._entity_cls = entity_cls

    def add(self, entity: T) -> None:
        values = {f.name: getattr(entity, f.name) for f in fields(entity)}
        self._write(insert(self._table).values(**values), DanglingReference)

    def get(self, entity_id: UUID) -> T | None:
        with self._engine.connect() as conn:
            row = conn.execute(select(self._table).where(self._table.c.id == entity_id)).first()
        return self._entity_cls(**row._mapping) if row else None

    def list(self, **filters: Any) -> list[T]:
        statement = select(self._table).order_by(self._table.c.created_at, self._table.c.id)
        for name, value in filters.items():
            statement = statement.where(self._table.c[name] == value)
        with self._engine.connect() as conn:
            rows = conn.execute(statement).all()
        return [self._entity_cls(**row._mapping) for row in rows]

    def update(self, entity: T) -> None:
        values = {
            f.name: getattr(entity, f.name)
            for f in fields(entity)
            if f.name not in ("id", "created_at")
        }
        statement = update(self._table).where(self._table.c.id == entity.id).values(**values)
        self._write(statement, DanglingReference)

    def delete(self, entity_id: UUID) -> None:
        self._write(delete(self._table).where(self._table.c.id == entity_id), ReferenceInUse)

    def _write(self, statement: Any, on_fk_violation: type[DomainError]) -> None:
        try:
            with self._engine.begin() as conn:
                conn.execute(statement)
        except IntegrityError as exc:
            if is_foreign_key_violation(exc):
                raise on_fk_violation(str(exc.orig).splitlines()[0]) from exc
            raise


def build_repositories(engine: Engine) -> Repositories:
    def repo[E: Entity](entity_cls: type[E]) -> SqlRepository[E]:
        return SqlRepository(engine, ENTITY_TABLES[entity_cls], entity_cls)

    return Repositories(
        teams=repo(Team),
        members=repo(TeamMember),
        applications=repo(Application),
        functions=repo(Function),
        data_types=repo(DataType),
        data_flows=repo(DataFlow),
        technologies=repo(Technology),
        personas=repo(Persona),
    )
```

`src/archimaid/adapters/persistence/catalog.py`:
```python
from dataclasses import asdict

from sqlalchemy import Engine, Table, delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from archimaid.adapters.persistence.pg_errors import is_foreign_key_violation, is_unique_violation
from archimaid.adapters.persistence.tables import REFERENCE_TABLES
from archimaid.domain.errors import AlreadyExists, NotFound, ReferenceInUse
from archimaid.domain.reference import REFERENCE_KINDS, ReferenceValue


class PostgresReferenceCatalog:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def exists(self, kind: str, code: str) -> bool:
        table = self._table(kind)
        with self._engine.connect() as conn:
            return conn.execute(select(table.c.code).where(table.c.code == code)).first() is not None

    def get(self, kind: str, code: str) -> ReferenceValue:
        table = self._table(kind)
        with self._engine.connect() as conn:
            row = conn.execute(select(table).where(table.c.code == code)).first()
        if row is None:
            raise NotFound(f"{kind} {code!r} not found")
        return REFERENCE_KINDS[kind](**row._mapping)

    def list(self, kind: str) -> list[ReferenceValue]:
        table = self._table(kind)
        with self._engine.connect() as conn:
            rows = conn.execute(select(table).order_by(table.c.code)).all()
        return [REFERENCE_KINDS[kind](**row._mapping) for row in rows]

    def create(self, kind: str, value: ReferenceValue) -> ReferenceValue:
        table = self._table(kind)
        try:
            with self._engine.begin() as conn:
                conn.execute(insert(table).values(**asdict(value)))
        except IntegrityError as exc:
            if is_unique_violation(exc):
                raise AlreadyExists(f"{kind} {value.code!r} already exists") from exc
            raise
        return value

    def update(self, kind: str, code: str, value: ReferenceValue) -> ReferenceValue:
        table = self._table(kind)
        statement = update(table).where(table.c.code == code).values(**asdict(value))
        try:
            with self._engine.begin() as conn:
                matched = conn.execute(statement).rowcount
        except IntegrityError as exc:
            if is_unique_violation(exc):
                raise AlreadyExists(f"{kind} {value.code!r} already exists") from exc
            raise
        if matched == 0:
            raise NotFound(f"{kind} {code!r} not found")
        return value

    def delete(self, kind: str, code: str) -> None:
        table = self._table(kind)
        try:
            with self._engine.begin() as conn:
                matched = conn.execute(delete(table).where(table.c.code == code)).rowcount
        except IntegrityError as exc:
            if is_foreign_key_violation(exc):
                raise ReferenceInUse(f"{kind} {code!r} is still referenced") from exc
            raise
        if matched == 0:
            raise NotFound(f"{kind} {code!r} not found")

    def _table(self, kind: str) -> Table:
        try:
            return REFERENCE_TABLES[kind]
        except KeyError:
            raise NotFound(f"unknown reference kind {kind!r}") from None
```

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/adapters/persistence -v -rs`
Expected: all passed, none skipped

- [ ] **Step 6: Commit**

```bash
git add src/archimaid/adapters/persistence tests/adapters/persistence
git commit -m "feat(persistence): SQL repositories and Postgres reference catalog" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: HTTP API

**Files:**
- Create: `src/archimaid/adapters/api/errors.py`, `src/archimaid/adapters/api/schemas.py`, `src/archimaid/adapters/api/crud_router.py`, `src/archimaid/adapters/api/reference_router.py`, `src/archimaid/adapters/api/app.py`
- Test: `tests/adapters/api/test_api.py`

**Interfaces:**
- Consumes: `Services` (Task 5), `CrudService`, `REFERENCE_KINDS`, the errors, and the fakes from Task 3 in the tests.
- Produces:
  - `install_error_handlers(app: FastAPI) -> None` implementing the status mapping from the Global Constraints.
  - Pydantic models `<Entity>In` and `<Entity>Out` for the eight entities, in `schemas.py`.
  - `crud_router(*, service, in_model, out_model, parent_field=None, parent_dependency=None, filters=None) -> APIRouter` with `GET ""`, `POST ""`, `GET/PUT/DELETE "/{entity_id}"`.
  - `reference_router(service: ReferenceAdminService) -> APIRouter` under `/reference`.
  - `create_app(services: Services) -> FastAPI` with these routes:
    - `/teams` and `/teams/{team_id}/members`
    - `/applications`, filter `team_id`
    - `/applications/{application_id}/functions`, `/data-types` and `/technologies`
    - `/data-flows`, filters `source_application_id`, `target_application_id` and `data_type_id`
    - `/personas`
    - `/reference`

- [ ] **Step 1: Write the failing test**

`tests/adapters/api/test_api.py`:
```python
from uuid import UUID, uuid4

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
def client(repos, catalog):
    return TestClient(create_app(build_services(repos, catalog)))


def post(client, url, body, status=201):
    response = client.post(url, json=body)
    assert response.status_code == status, response.text
    return response.json()


def make_team(client, name="Payments"):
    return post(client, "/teams", {"name": name})


def make_app(client, team=None, **extra):
    team = team or make_team(client)
    return post(client, "/applications", {"team_id": team["id"], "name": "Billing", **extra})


# ---------------------------------------------------------------- teams / generic CRUD


def test_team_crud_round_trip(client):
    team = make_team(client)
    assert client.get(f"/teams/{team['id']}").json()["name"] == "Payments"
    assert [t["id"] for t in client.get("/teams").json()] == [team["id"]]
    put = client.put(f"/teams/{team['id']}", json={"name": "Billing", "description": "d"})
    assert put.status_code == 200
    assert put.json()["name"] == "Billing"
    assert client.delete(f"/teams/{team['id']}").status_code == 204
    assert client.get(f"/teams/{team['id']}").status_code == 404


@pytest.mark.parametrize("name", ["", "   "])
def test_blank_name_is_422_on_create_and_put(client, repos, name):  # Review Focus test (1)
    assert client.post("/teams", json={"name": name}).status_code == 422
    assert repos.teams.list() == []
    team = make_team(client)
    assert client.put(f"/teams/{team['id']}", json={"name": name}).status_code == 422
    assert client.get(f"/teams/{team['id']}").json()["name"] == "Payments"


def test_missing_required_field_is_422(client):
    assert client.post("/teams", json={}).status_code == 422


def test_malformed_uuid_in_path_is_422(client):
    assert client.get("/teams/not-a-uuid").status_code == 422


def test_delete_of_a_referenced_entity_is_409(client, repos):
    team = make_team(client)
    repos.teams.mark_in_use(UUID(team["id"]))
    assert client.delete(f"/teams/{team['id']}").status_code == 409


def test_team_members_are_nested_under_their_team(client):
    team = make_team(client)
    member = post(client, f"/teams/{team['id']}/members", {"user_id": "u1", "name": "Ann"})
    assert member["team_id"] == team["id"]
    assert len(client.get(f"/teams/{team['id']}/members").json()) == 1
    assert client.get(f"/teams/{make_team(client, 'B')['id']}/members").json() == []


# ---------------------------------------------------------------- applications


def test_application_exposes_derived_rpo_rto(client):
    app = make_app(client, availability_level="SERIOUS")
    assert (app["rpo"], app["rto"]) == (4, 0)
    fetched = client.get(f"/applications/{app['id']}").json()
    assert (fetched["rpo"], fetched["rto"]) == (4, 0)
    assert client.get("/applications").json()[0]["rpo"] == 4


def test_application_without_availability_has_null_rpo_rto(client):
    app = make_app(client)
    assert app["rpo"] is None and app["rto"] is None


def test_rpo_rto_in_the_request_body_are_ignored(client):
    app = make_app(client, rpo=999, rto=999)
    assert app["rpo"] is None


def test_application_with_unknown_level_code_is_422(client):
    team = make_team(client)
    response = client.post(
        "/applications",
        json={"team_id": team["id"], "name": "A", "availability_level": "NOPE"},
    )
    assert response.status_code == 422


def test_application_with_unknown_team_is_422_not_500(client):  # Review Focus test (4)
    response = client.post("/applications", json={"team_id": str(uuid4()), "name": "A"})
    assert response.status_code == 422
    team = make_team(client)
    app = make_app(client, team)
    response = client.put(
        f"/applications/{app['id']}", json={"team_id": str(uuid4()), "name": "A"}
    )
    assert response.status_code == 422


def test_applications_can_be_filtered_by_team(client):
    team_a, team_b = make_team(client, "A"), make_team(client, "B")
    app_a = make_app(client, team_a)
    make_app(client, team_b)
    ids = [a["id"] for a in client.get(f"/applications?team_id={team_a['id']}").json()]
    assert ids == [app_a["id"]]
    assert client.get("/applications?team_id=nope").status_code == 422


# ---------------------------------------------------------------- nested resources


def test_functions_are_scoped_to_their_application(client):
    app_a, app_b = make_app(client), make_app(client)
    fn = post(client, f"/applications/{app_a['id']}/functions",
              {"name": "Invoice", "category": "BUSINESS"})
    assert fn["application_id"] == app_a["id"]
    assert len(client.get(f"/applications/{app_a['id']}/functions").json()) == 1
    assert client.get(f"/applications/{app_b['id']}/functions").json() == []


def test_reaching_a_nested_resource_through_the_wrong_parent_is_404(client):
    # Review Focus test (5)
    app_a, app_b = make_app(client), make_app(client)
    fn = post(client, f"/applications/{app_a['id']}/functions", {"name": "Invoice"})
    wrong = f"/applications/{app_b['id']}/functions/{fn['id']}"
    assert client.get(wrong).status_code == 404
    assert client.put(wrong, json={"name": "x"}).status_code == 404
    assert client.delete(wrong).status_code == 404
    assert client.get(f"/applications/{app_a['id']}/functions/{fn['id']}").status_code == 200


def test_nested_routes_under_a_missing_parent_are_404(client):
    ghost = uuid4()
    assert client.get(f"/applications/{ghost}/functions").status_code == 404
    assert client.post(f"/applications/{ghost}/technologies", json={"name": "PG"}).status_code == 404
    assert client.get(f"/teams/{ghost}/members").status_code == 404


def test_function_with_unknown_persona_is_422(client):  # Review Focus test (4)
    app = make_app(client)
    response = client.post(
        f"/applications/{app['id']}/functions",
        json={"name": "Invoice", "persona_id": str(uuid4())},
    )
    assert response.status_code == 422
    persona = post(client, "/personas", {"name": "Accountant"})
    ok = post(client, f"/applications/{app['id']}/functions",
              {"name": "Invoice", "persona_id": persona["id"]})
    assert ok["persona_id"] == persona["id"]


def test_data_types_and_technologies_crud(client):
    app = make_app(client)
    dt = post(client, f"/applications/{app['id']}/data-types",
              {"name": "Invoice", "confidentiality_level": "LOW", "golden_source": "ERP"})
    assert dt["golden_source"] == "ERP"
    tech = post(client, f"/applications/{app['id']}/technologies",
                {"name": "PG", "type": "DATABASE", "standard_status": "REFERENCE"})
    assert tech["type"] == "DATABASE"
    bad = client.post(f"/applications/{app['id']}/technologies",
                      json={"name": "PG", "type": "NOPE"})
    assert bad.status_code == 422


def test_data_flows_validate_references_and_filter(client):
    source, target = make_app(client), make_app(client)
    dt = post(client, f"/applications/{source['id']}/data-types", {"name": "Invoice"})
    body = {
        "source_application_id": source["id"],
        "target_application_id": target["id"],
        "data_type_id": dt["id"],
        "usage_mode": "SOURCE",
        "usage_explanation": "billing export",
    }
    flow = post(client, "/data-flows", body)
    assert flow["usage_mode"] == "SOURCE"
    assert client.post("/data-flows", json={**body, "data_type_id": str(uuid4())}).status_code == 422
    assert client.post("/data-flows", json={**body, "usage_mode": "NOPE"}).status_code == 422
    found = client.get(f"/data-flows?source_application_id={source['id']}").json()
    assert [f["id"] for f in found] == [flow["id"]]
    assert client.get(f"/data-flows?source_application_id={target['id']}").json() == []


# ---------------------------------------------------------------- reference admin API


def test_reference_kinds_and_values_are_listed(client):
    assert "availability_level" in client.get("/reference").json()
    codes = [v["code"] for v in client.get("/reference/usage_mode").json()]
    assert codes == ["CONSUMER", "PROXY", "SOURCE"]
    serious = client.get("/reference/availability_level/SERIOUS").json()
    assert (serious["rpo_hours"], serious["rto_hours"], serious["rank"]) == (4, 0, 3)


def test_unknown_reference_kind_is_404_even_with_a_bad_body(client):  # Review Focus test (5)
    assert client.get("/reference/nope").status_code == 404
    assert client.get("/reference/nope/X").status_code == 404
    assert client.post("/reference/nope", json={"junk": 1}).status_code == 404
    assert client.delete("/reference/nope/X").status_code == 404


def test_reference_create_update_delete(client):
    created = post(client, "/reference/function_category", {"code": "EXTRA", "label": "Extra"})
    assert created["code"] == "EXTRA"
    put = client.put("/reference/function_category/EXTRA",
                     json={"code": "EXTRA", "label": "Extra 2", "description": "d"})
    assert put.status_code == 200 and put.json()["label"] == "Extra 2"
    assert client.delete("/reference/function_category/EXTRA").status_code == 204
    assert client.get("/reference/function_category/EXTRA").status_code == 404


def test_reference_body_must_match_the_kind(client):
    # availability needs rank + rpo/rto; plain kinds reject extra fields
    assert client.post("/reference/availability_level",
                       json={"code": "T", "label": "T", "rank": 1}).status_code == 422
    assert client.post("/reference/function_category",
                       json={"code": "T", "label": "T", "rank": 1}).status_code == 422
    assert client.post("/reference/integrity_level",
                       json={"code": "T", "label": "T"}).status_code == 422
    ok = post(client, "/reference/availability_level",
              {"code": "TINY", "label": "Tiny", "rank": 0, "rpo_hours": 1, "rto_hours": 1})
    assert ok["rpo_hours"] == 1


def test_reference_blank_code_is_422(client):
    assert client.post("/reference/usage_mode", json={"code": " ", "label": "x"}).status_code == 422


def test_reference_duplicate_code_is_409(client):  # Review Focus test (2)
    assert client.post("/reference/usage_mode", json={"code": "SOURCE", "label": "x"}).status_code == 409
    response = client.put("/reference/usage_mode/PROXY", json={"code": "SOURCE", "label": "x"})
    assert response.status_code == 409


def test_reference_delete_in_use_is_409(client, catalog):
    catalog.mark_in_use("usage_mode", "PROXY")
    assert client.delete("/reference/usage_mode/PROXY").status_code == 409


def test_reference_update_of_unknown_code_is_404(client):
    response = client.put("/reference/usage_mode/NOPE", json={"code": "NOPE", "label": "x"})
    assert response.status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/adapters/api/test_api.py -v`
Expected: collection error `ModuleNotFoundError: archimaid.adapters.api.app`

- [ ] **Step 3: Implement errors and schemas**

`src/archimaid/adapters/api/errors.py`:
```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from archimaid.domain.errors import (
    AlreadyExists,
    DanglingReference,
    DomainError,
    InvalidEntity,
    InvalidReferenceCode,
    NotFound,
    ReferenceInUse,
)

STATUS_BY_ERROR: dict[type[DomainError], int] = {
    NotFound: 404,
    InvalidEntity: 422,
    InvalidReferenceCode: 422,
    DanglingReference: 422,
    ReferenceInUse: 409,
    AlreadyExists: 409,
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        status = STATUS_BY_ERROR.get(type(exc), 500)
        return JSONResponse(status_code=status, content={"detail": str(exc)})
```

`src/archimaid/adapters/api/schemas.py`:
```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class TeamIn(BaseModel):
    name: str
    description: str = ""


class TeamOut(_Out, TeamIn):
    pass


class TeamMemberIn(BaseModel):
    user_id: str
    name: str


class TeamMemberOut(_Out, TeamMemberIn):
    team_id: UUID


class ApplicationIn(BaseModel):
    team_id: UUID
    name: str
    golden_app_id: str | None = None
    auid: str | None = None
    description: str | None = None
    asset_cmdb: str | None = None
    shortname: str | None = None
    owner_uid: str | None = None
    confidentiality_level: str | None = None
    integrity_level: str | None = None
    availability_level: str | None = None
    traceability_level: str | None = None


class ApplicationOut(_Out, ApplicationIn):
    rpo: int | None = None  # hours, derived from availability_level
    rto: int | None = None  # hours, derived from availability_level


class FunctionIn(BaseModel):
    name: str
    description: str | None = None
    category: str | None = None
    persona_id: UUID | None = None


class FunctionOut(_Out, FunctionIn):
    application_id: UUID


class DataTypeIn(BaseModel):
    name: str
    definition: str | None = None
    specificity: str | None = None
    confidentiality_level: str | None = None
    golden_source: str | None = None
    golden_replica: str | None = None


class DataTypeOut(_Out, DataTypeIn):
    application_id: UUID


class DataFlowIn(BaseModel):
    source_application_id: UUID
    target_application_id: UUID
    data_type_id: UUID
    usage_mode: str | None = None
    usage_explanation: str | None = None


class DataFlowOut(_Out, DataFlowIn):
    pass


class TechnologyIn(BaseModel):
    name: str
    version: str | None = None
    family: str | None = None
    type: str | None = None
    standard_status: str | None = None
    standard_status_details: str | None = None
    tech_standards_link: str | None = None
    action_plan: str | None = None


class TechnologyOut(_Out, TechnologyIn):
    application_id: UUID


class PersonaIn(BaseModel):
    name: str
    description: str | None = None
    category: str | None = None


class PersonaOut(_Out, PersonaIn):
    pass
```

- [ ] **Step 4: Implement the generic CRUD router**

`src/archimaid/adapters/api/crud_router.py`:
```python
from collections.abc import Callable, Mapping
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from archimaid.application.crud import CrudService
from archimaid.domain.entities import Entity
from archimaid.domain.errors import InvalidEntity, NotFound


def _no_parent() -> None:
    return None


def crud_router[T: Entity](
    *,
    service: CrudService[T],
    in_model: type[BaseModel],
    out_model: type[BaseModel],
    parent_field: str | None = None,
    parent_dependency: Callable[..., UUID] | None = None,
    filters: Mapping[str, type] | None = None,
) -> APIRouter:
    """CRUD routes for one entity.

    For a nested resource pass ``parent_field`` (the entity's id field for the parent) and a
    ``parent_dependency`` that declares the path parameter, checks the parent exists (404) and
    returns its id. ``filters`` maps query-parameter names to a converter (e.g. ``UUID``).
    """
    router = APIRouter()
    parent_dep = parent_dependency or _no_parent
    query_filters = filters or {}

    def present(entities: list[T]) -> list[BaseModel]:
        return [out_model.model_validate(item) for item in service.present_many(entities)]

    def scoped(entity_id: UUID, parent: UUID | None) -> T:
        entity = service.get(entity_id)
        if parent_field is not None and getattr(entity, parent_field) != parent:
            raise NotFound(f"{type(entity).__name__} {entity_id} not found")
        return entity

    @router.get("", response_model=list[out_model])
    def list_items(request: Request, parent: UUID | None = Depends(parent_dep)):
        selected: dict[str, Any] = {}
        for name, convert in query_filters.items():
            if name in request.query_params:
                try:
                    selected[name] = convert(request.query_params[name])
                except ValueError as exc:
                    raise InvalidEntity(f"invalid value for {name}") from exc
        if parent_field is not None:
            selected[parent_field] = parent
        return present(service.list(**selected))

    @router.post("", status_code=201, response_model=out_model)
    def create_item(body: in_model, parent: UUID | None = Depends(parent_dep)):  # type: ignore[valid-type]
        data = body.model_dump()  # type: ignore[attr-defined]
        if parent_field is not None:
            data[parent_field] = parent
        return present([service.create(data)])[0]

    @router.get("/{entity_id}", response_model=out_model)
    def get_item(entity_id: UUID, parent: UUID | None = Depends(parent_dep)):
        return present([scoped(entity_id, parent)])[0]

    @router.put("/{entity_id}", response_model=out_model)
    def replace_item(
        entity_id: UUID,
        body: in_model,  # type: ignore[valid-type]
        parent: UUID | None = Depends(parent_dep),
    ):
        scoped(entity_id, parent)
        return present([service.update(entity_id, body.model_dump())])[0]  # type: ignore[attr-defined]

    @router.delete("/{entity_id}", status_code=204)
    def delete_item(entity_id: UUID, parent: UUID | None = Depends(parent_dep)):
        scoped(entity_id, parent)
        service.delete(entity_id)
        return Response(status_code=204)

    return router
```

- [ ] **Step 5: Implement the reference router and app factory**

`src/archimaid/adapters/api/reference_router.py`:
```python
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, ValidationError

from archimaid.application.reference_admin import ReferenceAdminService
from archimaid.domain.errors import NotFound
from archimaid.domain.reference import REFERENCE_KINDS, AvailabilityLevel, RankedValue


class ReferenceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    label: str
    description: str | None = None


class RankedReferenceIn(ReferenceIn):
    rank: int


class AvailabilityReferenceIn(RankedReferenceIn):
    rpo_hours: int
    rto_hours: int


def _model_for(kind: str) -> type[BaseModel]:
    cls = REFERENCE_KINDS.get(kind)
    if cls is None:
        raise NotFound(f"unknown reference kind {kind!r}")
    if issubclass(cls, AvailabilityLevel):
        return AvailabilityReferenceIn
    if issubclass(cls, RankedValue):
        return RankedReferenceIn
    return ReferenceIn


def _validated(kind: str, body: dict[str, Any]) -> dict[str, Any]:
    model = _model_for(kind)  # unknown kind -> 404 before body validation
    try:
        return model.model_validate(body).model_dump()
    except ValidationError as exc:
        raise RequestValidationError(
            exc.errors(include_url=False, include_context=False)
        ) from exc


def reference_router(service: ReferenceAdminService) -> APIRouter:
    router = APIRouter(prefix="/reference", tags=["reference"])

    @router.get("")
    def list_kinds():
        return service.kinds()

    @router.get("/{kind}")
    def list_values(kind: str):
        return [asdict(value) for value in service.list(kind)]

    @router.post("/{kind}", status_code=201)
    def create_value(kind: str, body: dict[str, Any]):
        return asdict(service.create(kind, _validated(kind, body)))

    @router.get("/{kind}/{code}")
    def get_value(kind: str, code: str):
        return asdict(service.get(kind, code))

    @router.put("/{kind}/{code}")
    def replace_value(kind: str, code: str, body: dict[str, Any]):
        return asdict(service.update(kind, code, _validated(kind, body)))

    @router.delete("/{kind}/{code}", status_code=204)
    def delete_value(kind: str, code: str):
        service.delete(kind, code)
        return Response(status_code=204)

    return router
```

`src/archimaid/adapters/api/app.py`:
```python
from uuid import UUID

from fastapi import FastAPI

from archimaid.adapters.api import schemas
from archimaid.adapters.api.crud_router import crud_router
from archimaid.adapters.api.errors import install_error_handlers
from archimaid.adapters.api.reference_router import reference_router
from archimaid.application.services import Services


def create_app(services: Services) -> FastAPI:
    app = FastAPI(title="Archimaid")
    install_error_handlers(app)

    def team_parent(team_id: UUID) -> UUID:
        services.teams.get(team_id)  # 404 if the team does not exist
        return team_id

    def application_parent(application_id: UUID) -> UUID:
        services.applications.get(application_id)  # 404 if the application does not exist
        return application_id

    app.include_router(
        crud_router(service=services.teams, in_model=schemas.TeamIn, out_model=schemas.TeamOut),
        prefix="/teams",
        tags=["teams"],
    )
    app.include_router(
        crud_router(
            service=services.members,
            in_model=schemas.TeamMemberIn,
            out_model=schemas.TeamMemberOut,
            parent_field="team_id",
            parent_dependency=team_parent,
        ),
        prefix="/teams/{team_id}/members",
        tags=["teams"],
    )
    app.include_router(
        crud_router(
            service=services.applications,
            in_model=schemas.ApplicationIn,
            out_model=schemas.ApplicationOut,
            filters={"team_id": UUID},
        ),
        prefix="/applications",
        tags=["applications"],
    )
    for segment, service, in_model, out_model in (
        ("functions", services.functions, schemas.FunctionIn, schemas.FunctionOut),
        ("data-types", services.data_types, schemas.DataTypeIn, schemas.DataTypeOut),
        ("technologies", services.technologies, schemas.TechnologyIn, schemas.TechnologyOut),
    ):
        app.include_router(
            crud_router(
                service=service,
                in_model=in_model,
                out_model=out_model,
                parent_field="application_id",
                parent_dependency=application_parent,
            ),
            prefix=f"/applications/{{application_id}}/{segment}",
            tags=["applications"],
        )
    app.include_router(
        crud_router(
            service=services.data_flows,
            in_model=schemas.DataFlowIn,
            out_model=schemas.DataFlowOut,
            filters={
                "source_application_id": UUID,
                "target_application_id": UUID,
                "data_type_id": UUID,
            },
        ),
        prefix="/data-flows",
        tags=["data-flows"],
    )
    app.include_router(
        crud_router(
            service=services.personas,
            in_model=schemas.PersonaIn,
            out_model=schemas.PersonaOut,
        ),
        prefix="/personas",
        tags=["personas"],
    )
    app.include_router(reference_router(services.reference))
    return app
```

- [ ] **Step 6: Run to verify it passes**

Run: `uv run pytest tests/adapters/api -v`
Expected: all passed. If a test fails because FastAPI returns 500, run with `-x` and read the traceback. The `TestClient` re-raises server errors.

- [ ] **Step 7: Run the whole suite so far**

Run: `uv run pytest -q -rs`
Expected: everything passes. The only skips allowed are Postgres tests when Docker is unavailable.

- [ ] **Step 8: Commit**

```bash
git add src/archimaid/adapters/api tests/adapters/api
git commit -m "feat(api): generic CRUD routers, reference admin API and error mapping" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Wiring, end-to-end test, dev tooling and docs

**Files:**
- Create: `src/archimaid/main.py`, `docker-compose.yml`, `tests/test_end_to_end_postgres.py`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: everything above.
- Produces: `main.build_app() -> FastAPI`, run with `uvicorn archimaid.main:build_app --factory`, and an updated `CLAUDE.md`.

- [ ] **Step 1: Write the failing end-to-end test**

`tests/test_end_to_end_postgres.py`:
```python
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


def test_scenario_over_real_postgres(client):
    team = client.post("/teams", json={"name": "Payments"}).json()
    app = client.post(
        "/applications",
        json={"team_id": team["id"], "name": "Billing", "availability_level": "SERIOUS"},
    ).json()
    assert (app["rpo"], app["rto"]) == (4, 0)

    function = client.post(
        f"/applications/{app['id']}/functions", json={"name": "Invoice", "category": "BUSINESS"}
    )
    assert function.status_code == 201

    # referenced rows cannot be deleted
    assert client.delete(f"/teams/{team['id']}").status_code == 409
    assert client.delete("/reference/availability_level/SERIOUS").status_code == 409

    # unknown codes and ids are 422, not 500
    assert client.post(
        "/applications",
        json={"team_id": team["id"], "name": "X", "availability_level": "NOPE"},
    ).status_code == 422
    assert client.post(
        "/applications",
        json={"team_id": "00000000-0000-0000-0000-000000000000", "name": "X"},
    ).status_code == 422

    # editing the catalog changes the derived values immediately
    edited = client.put(
        "/reference/availability_level/SERIOUS",
        json={"code": "SERIOUS", "label": "Serious", "rank": 3, "rpo_hours": 1, "rto_hours": 1},
    )
    assert edited.status_code == 200
    assert client.get(f"/applications/{app['id']}").json()["rpo"] == 1

    # renaming a code cascades to the applications that use it
    renamed = client.put(
        "/reference/availability_level/SERIOUS",
        json={"code": "HIGH", "label": "High", "rank": 3, "rpo_hours": 1, "rto_hours": 1},
    )
    assert renamed.status_code == 200
    assert client.get(f"/applications/{app['id']}").json()["availability_level"] == "HIGH"

    # deleting the application removes its functions; then the team can go
    assert client.delete(f"/applications/{app['id']}").status_code == 204
    assert client.get(f"/applications/{app['id']}/functions").status_code == 404
    assert client.delete(f"/teams/{team['id']}").status_code == 204
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_end_to_end_postgres.py -v -rs`
Expected: PASS or FAIL depending on earlier tasks. If it passes already, the wiring from Tasks 5 to 8 is correct. The failure to fix would be a real defect in an earlier task, so fix it there. Skipped means Docker is missing.

- [ ] **Step 3: Write `main.py` and `docker-compose.yml`**

`src/archimaid/main.py`:
```python
import os

from fastapi import FastAPI
from sqlalchemy import create_engine

from archimaid.adapters.api.app import create_app
from archimaid.adapters.persistence.catalog import PostgresReferenceCatalog
from archimaid.adapters.persistence.repository import build_repositories
from archimaid.application.services import build_services


def build_app() -> FastAPI:
    """ASGI factory. Needs DATABASE_URL, e.g. postgresql+psycopg://user:pw@host/db."""
    engine = create_engine(os.environ["DATABASE_URL"])
    services = build_services(build_repositories(engine), PostgresReferenceCatalog(engine))
    return create_app(services)
```

`docker-compose.yml`:
```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: archimaid
      POSTGRES_PASSWORD: archimaid
      POSTGRES_DB: archimaid
    ports:
      - "5432:5432"
```

- [ ] **Step 4: Start the real app against a dev database**

Run:
```bash
docker compose up -d db
export DATABASE_URL=postgresql+psycopg://archimaid:archimaid@localhost:5432/archimaid
uv run python -m archimaid.adapters.persistence.migrate
uv run uvicorn archimaid.main:build_app --factory --port 8000 &
sleep 2
curl -s localhost:8000/reference/availability_level
curl -s -X POST localhost:8000/teams -H 'content-type: application/json' -d '{"name":"Payments"}'
kill %1
```
Expected: the first `curl` prints four availability levels with RPO/RTO. The second prints the new team JSON with a UUID `id`.

- [ ] **Step 5: Lint and type-check**

Run: `uv run ruff check --fix src tests && uv run ruff format src tests && uv run mypy src`
Expected: ruff clean. Fix any mypy errors in the code, not by loosening config. For example, add `# type: ignore[...]` only on the dynamic Pydantic model annotations in `crud_router.py`.

- [ ] **Step 6: Replace `CLAUDE.md`**

```markdown
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Archimaid is a data-collection tool for functional, application and technical architecture analysis. A `Team` implements an `Application`. Architects use the tool to record the team's requirements and existing technology stack, to design the future stack. Spec: `docs/superpowers/specs/2026-10-02-archimaid-design.md`. Domain diagram: `domain.puml`. The spec wins where they differ.

## Commands

```bash
uv sync --dev
uv run pytest                                   # all tests (Postgres tests need Docker)
uv run pytest tests/application/test_crud_service.py::test_create_rejects_unknown_reference_code
uv run pytest -m postgres                       # only the Docker/Postgres tests
uv run ruff check src tests && uv run mypy src

docker compose up -d db                         # dev database
export DATABASE_URL=postgresql+psycopg://archimaid:archimaid@localhost:5432/archimaid
uv run python -m archimaid.adapters.persistence.migrate        # alembic upgrade head
uv run uvicorn archimaid.main:build_app --factory --reload     # http://localhost:8000/docs
```

## Architecture

Hexagonal. Dependencies point inward: `adapters` → `application` → `ports`/`domain`. `src/archimaid/domain` imports no framework.

- `domain/`: entity dataclasses (`validate()` returns True or raises `InvalidEntity`), `ReferenceValue` value objects, and the `DomainError` hierarchy.
- `ports/`: `Repository[T]`, the `Repositories` bundle and `ReferenceCatalog`.
- `application/`: `CrudService` is generic. `build_services()` in `services.py` is where each entity's reference fields (field → catalog kind) and parent-id checks are declared. `ApplicationService` adds the derived `rpo`/`rto`. `ReferenceAdminService` maintains the catalogs.
- `adapters/persistence/`: SQLAlchemy Core (sync) repositories, `PostgresReferenceCatalog`, and Alembic migrations in `migrations/versions/` (0001 schema, 0002 seed). `tables.py` must stay in sync with the migrations, and a test compares them.
- `adapters/api/`: `crud_router()` builds the CRUD routes for any entity. Nested resources pass `parent_field` and `parent_dependency`. `reference_router` serves `/reference/{kind}`. `errors.py` maps domain errors to HTTP codes.

Key design rules:

- **Value objects are configuration tables, not enums.** There are eight catalog tables, keyed by their text `code`. Entities store the code, and FKs are `ON UPDATE CASCADE ON DELETE RESTRICT`. Adding a new catalog means adding a VO in `domain/reference.py` and its `REFERENCE_KINDS` entry, a migration, and a field entry in `build_services()`.
- **RPO/RTO are derived.** They are read from the `availability_level` row when an application is presented. They are never stored or accepted as input.
- **Delete semantics.** Children cascade with their parent (members, functions, data types, technologies). Cross-aggregate references are `RESTRICT` and return 409.
- **Errors.** `NotFound` → 404, `InvalidEntity` / `InvalidReferenceCode` / `DanglingReference` → 422, `ReferenceInUse` / `AlreadyExists` → 409.
- Unit tests use the in-memory fakes in `tests/fakes.py`. Adapter and end-to-end tests use a real Postgres through testcontainers (`tests/conftest.py`).
```

- [ ] **Step 7: Final verification: full suite with no skips**

Run: `uv run pytest -q -rs`
Expected: all tests pass, and the `-rs` summary lists **no skipped** tests. If Postgres tests are skipped, start Docker and re-run. Do not call the work finished while any are skipped.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: app wiring, end-to-end test, dev database and docs" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-review against the spec

- **Config tables and schema (Persistence):** the eight tables, with `rank` and the availability RPO/RTO columns, are in Task 6. Seeded values and the mapping are checked by `test_migrations.py`.
- **FK rules (`ON UPDATE CASCADE`, `ON DELETE RESTRICT`):** in the Task 6 schema, with behavior tested in Task 7 (rename cascade, blocked delete).
- **Entity tables and nullability, `Persona` global:** Tasks 2 and 6. `usage_mode` is on `data_flow` only.
- **Derived RPO/RTO:** Task 5 (service), Task 8 (API), Task 9 (end to end).
- **Hexagonal layout and ports:** Tasks 3 to 5 (domain, ports, application), Tasks 6 to 8 (adapters).
- **API routes and error mapping:** Task 8, including the 404 versus 422 ordering on reference kinds.
- **Admin catalog API (CRUD, rename, per-kind validation):** Tasks 5, 7 and 8.
- **Testing strategy (fakes, real Postgres, `TestClient` over fakes):** Tasks 3 to 9.
- **Changes to `domain.puml`:** not in a task. The diagram is documentation, and the spec lists its corrections. After Task 9, update the diagram by hand.
