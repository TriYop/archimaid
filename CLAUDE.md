# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Archimaid is a data-collection tool for functional, application and technical architecture analysis. A `Team` implements an `Application`. Architects use the tool to record the team's requirements and existing technology stack, to design the future stack. Spec: `docs/superpowers/specs/2026-10-02-archimaid-design.md`. Domain diagram: `domain.puml`. The spec wins where they differ.

## Commands

```bash
uv sync --dev
uv run pytest                                   # all tests (Postgres tests need a container runtime)
uv run pytest tests/application/test_crud_service.py::test_create_rejects_unknown_reference_code
uv run pytest -m postgres                       # only the container/Postgres tests
uv run ruff check src tests && uv run mypy src

# dev database (host port 55432, since 5432 is often taken)
podman run -d --name archimaid-db -e POSTGRES_USER=archimaid -e POSTGRES_PASSWORD=archimaid \
    -e POSTGRES_DB=archimaid -p 55432:5432 docker.io/library/postgres:16-alpine
# or, where a compose provider is available: docker compose up -d db
export DATABASE_URL=postgresql+psycopg://archimaid:archimaid@localhost:55432/archimaid
uv run python -m archimaid.adapters.persistence.migrate        # alembic upgrade head
uv run uvicorn archimaid.main:build_app --factory --reload     # http://localhost:8000/docs
```

## Test configuration

The Postgres tests start real `postgres:16-alpine` containers through testcontainers, so they need a container runtime reachable via `DOCKER_HOST`. Copy `.env.example` to `.env` (git-ignored, loaded by `tests/conftest.py`; real environment variables win), e.g. the rootless podman socket plus `TESTCONTAINERS_RYUK_DISABLED=true`.

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
