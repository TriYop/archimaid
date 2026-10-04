# Archimaid

Archimaid is a data-collection tool for functional, application and technical architecture analysis.
A "Team" implements an "Application". As architects, we gather the team's requirements and existing
technology stack to design the future stack.

It follows DDD and hexagonal architecture; most of the work is CRUD on the domain aggregates.

## Features

- **JSON API** (FastAPI + PostgreSQL), documented at `/docs`: teams, members, personas, applications,
  functions, data types, technologies and data flows.
- **Configurable reference data**: value objects (availability levels, etc.) are catalog tables keyed by a
  text code, not enums. They can be maintained through `/reference/{kind}`.
- **Derived RPO/RTO**: read from the application's availability level, never stored or accepted as input.
- **Web UI** at `/ui/` (HTMX + Jinja2, no Node/npm, assets vendored in `static/`): pages with inline editing
  for every entity, an application page with tabs, an overview, and reference data admin pages.
- **Interaction diagram**: each application has a "Diagram" tab showing it with its personas and data flows,
  rendered as SVG. It is also available at `GET /ui/applications/{id}/diagram.svg`
  (add `?download=1` to get a file).
- **Function-level data flows**: a data flow can name the function on each end (source and target). The
  function must belong to the application at that end. Functions are shown on the flow forms, tabs, overview
  and diagram.

## Quick start

```bash
uv sync --dev

# dev database (host port 55432, since 5432 is often taken)
podman run -d --name archimaid-db -e POSTGRES_USER=archimaid -e POSTGRES_PASSWORD=archimaid \
    -e POSTGRES_DB=archimaid -p 55432:5432 docker.io/library/postgres:16-alpine
export DATABASE_URL=postgresql+psycopg://archimaid:archimaid@localhost:55432/archimaid

uv run python -m archimaid.adapters.persistence.migrate        # apply migrations
uv run uvicorn archimaid.main:build_app --factory --reload     # http://localhost:8000
```

- Web UI: http://localhost:8000/ui/
- API docs: http://localhost:8000/docs

## Tests

```bash
uv run pytest                                   # Postgres tests need a container runtime
uv run pytest -m postgres                       # only the container/Postgres tests
uv run ruff check src tests && uv run mypy src
```

The Postgres tests start `postgres:16-alpine` through testcontainers. Copy `.env.example` to `.env` to point
`DOCKER_HOST` at your runtime (e.g. the rootless podman socket with `TESTCONTAINERS_RYUK_DISABLED=true`).

## Documentation

- Domain model: `domain.puml` (PlantUML)
- Design specs and implementation plans: `docs/superpowers/` (the spec wins where it differs from other docs)
- Contributor and architecture notes: `CLAUDE.md`

A podman deployment package is designed and planned (`docs/superpowers/`) but not yet implemented.
