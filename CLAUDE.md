# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Archimaid is **spec-only**: the repo contains just `README.md` and `domain.puml`. There is no code, toolchain, build, lint or test setup yet, and it is not a git repository. Don't assume commands exist. When scaffolding, add the real ones to this file.

Archimaid is a data-collection tool for functional, application and technical architecture analysis. A "Team" implements an "Application". The architects use the tool to gather the team's requirements and the existing technology stack, to design the future stack.

## Planned implementation (from README)

- Light backend: Python + FastAPI + PostgreSQL.
- The frontend is optional and should stay light.
- Must follow DDD and hexagonal architecture (ports & adapters). Most of the work is CRUD on the domain aggregates.

## Domain model (`domain.puml` is the source of truth)

There are two aggregates, plus value-object enums.

- **Team aggregate**: `Team` owns `TeamMember`s.
- **Application aggregate**: `Application` (belongs to a `Team` via `TeamId`) owns `Function`, `DataType`, `DataFlow` and `Technology`. `Persona` is also drawn in this package and has a 1-to-many "exercises" link to `Function`. It has no `ApplicationId`, so check whether it is global or per-application.
- Every entity has a UUID id, `created_at` and `updated_at`, and a `validate(): Boolean` method.
- `DataFlow` links a source `Application`, a target `Application` and a `DataType`. Its two application ids are `SourceApplicationId` and `TargetApplicationId`, so it crosses aggregate boundaries by id.
- Value-object enums:
  - Security levels: `Confidentiality`, `Integrity`, `Availability` and `Traceability` levels, each `EXTREME/SERIOUS/MODERATE/LOW`.
  - `FunctionCategory`, `UsageMode`, `TechnologyType` and `TechStandardStatus`.
- Most `Application`, `Function`, `DataType`, `DataFlow` and `Technology` attributes are nullable. Keep them optional in the API and schema.

### Derived and extracted fields

- `<<extracted>>` marks fields in the UML (`#` visibility) that are not input by the user:
  - `Application.RPO` / `Application.RTO`
  - `Technology.StandardStatus` / `StandardStatusDetails` / `ActionPlan`
- RPO/RTO are **computed at read time** from `availability_level`, not stored, and not taken as constructor parameters (see the commented-out note in `domain.puml`). Use a `compute_rpo_rto(availability_level)` function, so `availability_level` is the single source of truth. The mapping in that note is:

  | Availability | RPO | RTO |
  |---|---|---|
  | LOW | 72h | 24h |
  | MODERATE | 24h | 24h |
  | SERIOUS | 4h | 0h |
  | EXTREME | 2h | 0h |

### Inconsistencies in the diagram to resolve before coding

- `DataType --> UsageMode` is drawn, but the model has no such attribute on `DataType`. `UsageMode` is on `DataFlow`.
- `Team "1" -- "*" Application` appears twice, as "owns" and "same team".
- `DataFlow "1" -- "*" Application : references` is drawn as one link, while the class has two application ids (source and target).
