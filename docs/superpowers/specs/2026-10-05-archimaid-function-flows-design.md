# Archimaid function-level data flows: design

Date: 2026-10-05

Builds on the backend spec (`2026-10-02-archimaid-design.md`), the web frontend spec (`2026-10-02-archimaid-web-frontend-design.md`) and the diagram spec (`2026-10-03-archimaid-diagram-design.md`), all implemented. Where they differ, this spec wins for data flows.

This is cycle 1 of two. Cycle 2 (the diagram redraw: white current-application frame, personas inside the frame, arrows landing on function cells) has its own spec, written after a prototype render is approved. See "Out of scope".

## Purpose

Today a `DataFlow` links two applications. In practice a flow is between functions. A flow end can now also name a function, so an architect can record "function F of application A sends data type D to application B", "application B sends D to function G of A", or "function F of A sends D to function H of B".

## Decisions

| # | Decision |
|---|---|
| 1 | Each end keeps its required `*_application_id` and gains an optional `*_function_id`: `source_function_id`, `target_function_id`. A function end therefore always implies its parent application's link, and existing application-to-application flows stay valid unchanged. |
| 2 | A function must belong to the application on the same end (`function.application_id == flow.<end>_application_id`). Otherwise the write is rejected with `InvalidEntity` (HTTP 422). The check lives in the application service, since it spans two tables. |
| 3 | Deleting a function that a flow references does not fail and does not delete the flow: the flow's function end becomes NULL (`ON DELETE SET NULL`) and the flow stays as an application-level link. Deleting an application is still blocked (409) while flows reference it, as today. |
| 4 | A flow whose two ends are functions of the same application is allowed and stored. It is listed in the Data flows tab and overview, and counted, not drawn, in the diagram (it joins the existing `self_flows` count). |
| 5 | In the diagram, functions of third-party applications stay hidden. A flow to or from one is drawn to or from its parent application, exactly as an application-level flow. Only the current application's functions are known to the diagram, as `function_index` on a flow. |
| 6 | In this cycle the diagram does not change visually: arrows still end on the application frame. `function_index` is carried in the model for cycle 2. |

## Domain and persistence

- `DataFlow` gains `source_function_id: UUID | None = None` and `target_function_id: UUID | None = None`.
- Alembic migration `0003_data_flow_functions`: adds the two nullable columns, each a FK to `function(id)` with `ON DELETE SET NULL`. Existing rows get NULL, so there is no data migration. `downgrade` drops the columns. `tables.py` is updated to match (the existing test comparing it with the migrations covers this).
- `domain.puml` gains two optional associations from `DataFlow` to `Function` (`SourceFunctionId`, `TargetFunctionId`).
- The backend spec's data model section is updated to list the new fields and the three rules above.

## Application service

- `ParentLink` gains an optional `owner_field: str | None = None`. When set, the repository entity found for the link must have `application_id` equal to the value of the named field of the checked entity.
- `build_services()` adds, for data flows:
  `ParentLink("source_function_id", repos.functions, owner_field="source_application_id")` and
  `ParentLink("target_function_id", repos.functions, owner_field="target_application_id")`.
  A None id skips the link, as for the optional `persona_id` today.
- Errors: a missing function raises `DanglingReference` (422), as for other parents. A function of another application raises `InvalidEntity` with a message such as `source_function_id <id> does not belong to source_application_id <id>`.
- `CrudService.update` replaces only the keys it receives, and the check runs on the merged entity. Changing `source_application_id` without clearing a function that belonged to the old application therefore fails with 422. This is deliberate.
- The persistence layer needs no new code: `SqlRepository` is generic over the table definition, and filters by field already work.

## JSON API

`DataFlowIn` gains `source_function_id: UUID | None = None` and `target_function_id: UUID | None = None`; `DataFlowOut` inherits them. `crud_router` and `errors.py` are unchanged.

## Web UI

- `resources.DATA_FLOW` gains two `select_entity` fields, "Source function" and "Target function" (not required), placed right after the matching application field. A new option source `functions` in `Lookups` lists every function as `Application › Function`, grouped by application, sorted like `data_types`.
- The application dropdowns stay required. A mismatch comes back as the inline 422 error of the existing form handling.
- The application's Data flows tab and the global `/ui/data-flows` overview show the two function columns (`—` when empty). The outgoing and incoming queries are unchanged, because a function flow always carries its application ids.
- Filtering the function dropdown by the chosen application (an HTMX request) is not part of this cycle.

## Diagram builder

- `DiagramFlow` gains `function_index: int | None = None`: the position, in the sorted function list, of the current application's function on the current-application end of the flow, or None.
- `build_diagram` groups flows by the other application exactly as before. The function id of the other end is ignored, so third-party functions never appear.
- A flow whose both ends belong to the current application, including function-to-function flows, goes into `self_flows` and is not drawn.
- `layout.py` and `svg.py` ignore `function_index` in this cycle, so the approved sample renders and `test_reproduces_the_approved_sample_files` stay unchanged.

## Testing

- Domain: the entity accepts and defaults the two fields.
- Service (in-memory fakes, `tests/fakes.py` extended where needed): a function of the right application is accepted on each end; a function of another application is rejected with `InvalidEntity`; a missing function with `DanglingReference`; function-to-function in the same application is accepted; an update that changes an application without clearing its function is rejected; omitted functions behave as before.
- Persistence on Postgres (testcontainers): round trip with and without functions; deleting a function sets the flow's end to NULL and keeps the flow; deleting an application with function flows is still a 409; the migration test and the `tables.py` comparison pass; upgrade and downgrade on a database that already has flows.
- API: create and read with function ids; 422 for a mismatch; flows without function fields still work.
- Web: the form shows the two selects with grouped options; a mismatch shows the inline error; tab and overview show the function columns.
- Diagram builder: third-party function ids are ignored and the flow is grouped under its parent application; `function_index` is set for the current application's function on each end; a same-application function-to-function flow lands in `self_flows`; flows without functions are unchanged.
- End-to-end on Postgres: one scenario with function flows, checking the API, the tab and the diagram.

## Out of scope

- Cycle 2, the diagram redraw: white frame for the current application, personas inside the frame under their functions, and arrows ending on function cells. It needs a prototype render approved by the user first, because the source arrows and the personas compete for the space under a function cell.
- Dependent filtering of the function dropdown; drawing internal flows; function-level flows in any export other than the existing API and UI.

## Open items

None.
