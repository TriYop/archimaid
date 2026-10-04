# Archimaid: design

Date: 2026-10-02

## Purpose

Archimaid is a data-collection tool for functional, application and technical architecture analysis. A `Team` implements an `Application`. Architects use the tool to record the team's requirements and the existing technology stack, so they can design the future stack.

Constraints (from `README.md`):

- Python, FastAPI and PostgreSQL for a light backend. Any frontend is optional and light.
- DDD and hexagonal architecture. Most of the work is CRUD on the domain aggregates.
- `domain.puml` describes the domain. This spec records the decisions made on top of it, and where they differ, this spec wins. `domain.puml` should be updated to match (see "Changes to `domain.puml`").

Out of scope for v1: authentication and authorization. `Application.Owner_uid` and `TeamMember.UserId` are plain strings.

## Decisions

| # | Decision |
|---|---|
| 1 | Value objects are **configuration tables**, not enums. |
| 2 | One table per value object, with real foreign keys and per-type columns. |
| 3 | A retired value cannot be deleted while referenced: the FK is `ON DELETE RESTRICT`, and there is no `active` flag. |
| 4 | The stable `code` (text) is the primary key. Referencing columns use `ON UPDATE CASCADE`. |
| 5 | Initial values are seeded by Alembic migrations. Runtime changes go through an admin CRUD API. |
| 6 | The domain holds typed `ReferenceValue` VOs and a `ReferenceCatalog` port. Application services validate codes through it. |
| 7 | `UsageMode` belongs to `DataFlow` only. `DataType` has no usage mode. |
| 8 | `Persona` is global and shared across applications. `Function.persona_id` is a nullable FK. |
| 9 | The duplicate Team–Application link in the diagram was a mistake. There is a single `Team 1 — * Application` link. |

## Persistence

### Configuration tables

Each table has `code TEXT PRIMARY KEY`, `label TEXT NOT NULL` and `description TEXT NULL`.

| Table | Extra columns | Initial values |
|---|---|---|
| `confidentiality_level` | `rank INT NOT NULL` | EXTREME, SERIOUS, MODERATE, LOW |
| `integrity_level` | `rank INT NOT NULL` | EXTREME, SERIOUS, MODERATE, LOW |
| `availability_level` | `rank INT NOT NULL`, `rpo_hours INT NOT NULL`, `rto_hours INT NOT NULL` | EXTREME, SERIOUS, MODERATE, LOW |
| `traceability_level` | `rank INT NOT NULL` | EXTREME, SERIOUS, MODERATE, LOW |
| `function_category` | none | COMMON, BUSINESS, EXCHANGE, DATA |
| `usage_mode` | none | SOURCE, CONSUMER, PROXY |
| `technology_type` | none | OPERATING_SYSTEM, FRAMEWORK_LIBRARY, WEB_SERVER, APPLICATION_SERVER, DATABASE, SOFTWARE, SAAS_SERVICE, RUNTIME_INTERPRETER, CI_CD, DEV_LANG, ETL |
| `tech_standard_status` | none | EMERGING, UPCOMING, REFERENCE, CONFINED, TO_BE_PHASED_OUT, DECOMMISSIONED, REJECTED |

`rank` orders the levels so they can be sorted and compared. EXTREME has the highest rank.

Seeded RPO/RTO for `availability_level` (from the note in `domain.puml`):

| Level | `rpo_hours` | `rto_hours` |
|---|---|---|
| LOW | 72 | 24 |
| MODERATE | 24 | 24 |
| SERIOUS | 4 | 0 |
| EXTREME | 2 | 0 |

### Entity tables

Tables follow `domain.puml`. Every table has a UUID primary key, `created_at` and `updated_at`.

- `team`, `team_member` (`team_id` FK)
- `application` (`team_id` FK, required)
- `function` (`application_id` FK, `persona_id` nullable FK to `persona`)
- `data_type` (`application_id` FK)
- `data_flow` (`source_application_id`, `target_application_id`, `data_type_id` FKs; optional `source_function_id` and `target_function_id` FKs to `function`, `ON DELETE SET NULL`, each function must belong to the application on its end; see `2026-10-05-archimaid-function-flows-design.md`)
- `technology` (`application_id` FK)
- `persona` (global, no owner). `Persona.Category` stays free text.

Columns that hold a configuration value are text FKs to the matching table's `code`, declared `ON UPDATE CASCADE ON DELETE RESTRICT`. They stay nullable wherever the diagram says nullable:

| Column | Config table |
|---|---|
| `application.confidentiality_level`, `integrity_level`, `availability_level`, `traceability_level` | the four level tables |
| `data_type.confidentiality_level` | `confidentiality_level` |
| `function.category` | `function_category` |
| `data_flow.usage_mode` | `usage_mode` |
| `technology.type` | `technology_type` |
| `technology.standard_status` | `tech_standard_status` |

Deleting a `Persona` that functions still reference is blocked, the same as for configuration values.

### Derived and extracted fields

- `Application.RPO` and `Application.RTO` are **not stored**. They are read from the `availability_level` row the application references, and are never accepted as input. They are null when `availability_level` is null.
- `Technology.StandardStatus`, `StandardStatusDetails` and `ActionPlan` are marked `<<extracted>>` in the diagram. They are stored as ordinary nullable columns. This spec doesn't define how they are produced.

## Hexagonal layout

Dependencies point inward.

- `domain/`: entities and aggregates (`Team`, `TeamMember`, `Application`, `Function`, `DataType`, `DataFlow`, `Technology`, `Persona`) and one immutable `ReferenceValue` VO per catalog, for example `AvailabilityLevel(code, label, rank, rpo_hours, rto_hours)`. It also holds the domain errors `InvalidReferenceCode`, `ReferenceInUse` and `NotFound`. It imports no FastAPI, SQLAlchemy or Pydantic.
- `ports/`: one repository port per aggregate, plus `ReferenceCatalog` with `exists`, `get`, `list`, `create`, `update` and `delete`, all keyed by (`kind`, `code`).
- `application/`: use-case services such as `CreateApplication` and `UpdateTechnology`. They validate every reference code through `ReferenceCatalog` before saving, and raise `InvalidReferenceCode` on a miss. `ReferenceAdminService` handles catalog maintenance.
- `adapters/api/`: FastAPI routers and Pydantic schemas.
- `adapters/persistence/`: SQLAlchemy repositories, the Postgres `ReferenceCatalog`, and Alembic migrations (schema and seed data).

The foreign keys are a backstop. Domain-level validation through the port is the primary check, so it can be tested without a database.

## API

- Aggregate resources are plain CRUD:
  - `/teams`, with `/teams/{id}/members`
  - `/applications`, with `functions`, `data-types` and `technologies` as sub-resources
  - `/data-flows`
  - `/personas`
- Reference values are written and read by code, for example `{"availability_level": "SERIOUS"}`.
- Reading an `Application` returns the derived `rpo` and `rto`.
- Admin catalog API: `GET`/`POST /reference/{kind}` and `GET`/`PUT`/`DELETE /reference/{kind}/{code}`. `kind` is one of the eight catalog names. The body schema is validated per kind (`rank` on the levels, `rpo_hours` and `rto_hours` on availability).
- Error mapping:

| Domain error | HTTP status |
|---|---|
| `InvalidReferenceCode` | 422 |
| `NotFound` | 404 |
| `ReferenceInUse` | 409 |

  The persistence adapter turns an FK `RESTRICT` violation into `ReferenceInUse`, so the client gets a 409 rather than a 500.

## Testing

- Domain and application tests use in-memory fakes of the ports. No database is needed.
- Adapter tests run against a real PostgreSQL (testcontainers or a docker-compose service). They run the migrations and check the seed data, the 409-on-delete case, and the derived RPO/RTO.
- API tests use FastAPI's `TestClient` over the fakes.

## Implementation decisions (added while planning)

- **Delete semantics for entity foreign keys.**
  - Children inside an aggregate cascade: `team_member` with its `team`, and `function`, `data_type` and `technology` with their `application`.
  - References across aggregates are `RESTRICT`: `application` to `team`, `data_flow` to its source and target `application`, `data_flow` to `data_type`, and `function` to `persona`.
  - Deleting an application that is the source or target of a data flow is therefore blocked with 409.
  - A data flow's optional function ends are `SET NULL`: deleting a function keeps the flow as an application-level link.
- **Extra domain errors:**

  | Error | Meaning | HTTP |
  |---|---|---|
  | `InvalidEntity` | a required text field is blank | 422 |
  | `DanglingReference` | an id field points to a row that doesn't exist | 422 |
  | `AlreadyExists` | a catalog code is already taken (create or rename) | 409 |

- `validate()` returns `True` or raises `InvalidEntity`.
- A catalog `PUT` replaces the whole value. Sending a different `code` renames it, and the change cascades to referencing rows.
- Applications are read with `rpo` and `rto`, in hours, and both are `null` when `availability_level` is `null`.
- Stack: Python 3.12+, SQLAlchemy Core (sync), psycopg 3, Alembic, FastAPI and pytest with testcontainers.
- A nested resource requested through the wrong parent (for example `/applications/{A}/functions/{id of a function of B}`) returns 404.

## Changes to `domain.puml`

- Remove the duplicate `Team "1" -- "*" Application : same team` link.
- Remove the `DataType --> UsageMode` arrow and add `DataFlow --> UsageMode : UsageMode`.
- Replace the `DataFlow "1" -- "*" Application : references` link with two links, for `SourceApplicationId` and `TargetApplicationId`.
- Add `Persona "1" -- "*" Function` as a nullable FK (`Function.PersonaId`) and move `Persona` out of the Application aggregate, since it is global.
- Draw the value-object enums as configuration tables, or note that they are catalogs.

## Open items

- Authentication is out of scope for v1. Revisit it if the tool is shared between teams.
- `tech_standard_status` may later need an ordering or a "blocking" flag. Left out for now.
