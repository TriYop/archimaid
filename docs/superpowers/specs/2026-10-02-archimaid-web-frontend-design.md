# Archimaid web frontend: design

Date: 2026-10-02

Builds on `docs/superpowers/specs/2026-10-02-archimaid-design.md` (backend) and the merged backend implementation. Where this spec and the backend spec disagree about the backend, the backend spec wins. This spec adds a UI only; it changes no domain, persistence or JSON API behavior.

## Purpose

A basic HTML frontend for architects to enter and browse the data Archimaid collects (teams, applications and their functions, data types, technologies, data flows, personas) and to maintain the configuration tables (the eight value-object catalogs).

Constraints:

- Node.js and npm must not be required to build or run it. No build step.
- Assets ship in the repo. Nothing is loaded from a CDN.
- English only. No authentication in v1 (as for the API).

## Decisions

| # | Decision |
|---|---|
| 1 | HTMX + Jinja2: a server-rendered web adapter, `src/archimaid/adapters/web/`. |
| 2 | The web adapter calls the application services directly, never the JSON API and never persistence. The JSON API is unchanged. |
| 3 | Navigation is a drill-down: Team → Application → tabs, plus top-level Personas, Data flows overview and Reference data pages. |
| 4 | Editing is inline: a row swaps into a form in place, and an add form sits above each table. |
| 5 | The UI is English only. Strings live in the templates, with no i18n layer. |
| 6 | Styling is vendored Pico.css, with a small `app.css` for local tweaks. |
| 7 | Entities are described as data (`Resource` and `Field` definitions), and shared templates and one generic router render and serve any of them. |

## Structure

```
src/archimaid/adapters/web/
  __init__.py
  app.py            web_router(services) -> APIRouter, mounted at /ui
  resources.py      Field, Resource and the resource definitions
  forms.py          form fields -> service data dicts
  render.py         Jinja2 environment and template helpers
  resource_router.py  generic row/edit/add/delete routes for a Resource
  reference.py      /ui/reference routes (keyed by code)
  pages.py          team, application, personas, data flows, home pages
  templates/        base.html, page templates, shared table/row/form fragments
  static/           htmx.min.js, pico.min.css, app.css, VENDORED.md
```

- `create_app(services)` includes `web_router(services)` next to the JSON routers. `main.py` is unchanged.
- The web adapter imports only `archimaid.application`, `archimaid.domain` and its own modules. It imports nothing from `adapters/persistence`.
- The templates and static files are located relative to the package (`Path(__file__).parent`) and ship in the wheel.
- Dependencies added: `jinja2` and `python-multipart` (pure Python). The vendored `htmx.min.js` (a 2.x release) and `pico.min.css` (a 2.x release) are committed under `static/`. `VENDORED.md` records each file's version, source URL, SHA-256 and license (both MIT).

## URLs

The web UI lives under `/ui`. `/` redirects to `/ui/`, which redirects to `/ui/teams`. Static files are served at `/ui/static`.

| Page / action | Route |
|---|---|
| Teams list page | `GET /ui/teams` |
| Team page | `GET /ui/teams/{team_id}` |
| Application page | `GET /ui/applications/{application_id}?tab=details\|functions\|data-types\|technologies\|data-flows` |
| Application tab fragment | `GET /ui/applications/{application_id}/tabs/{tab}` |
| Personas page | `GET /ui/personas` |
| Data flows overview (read-only) | `GET /ui/data-flows` |
| Reference data index | `GET /ui/reference` |
| Reference data kind page | `GET /ui/reference/{kind}` |

Every editable resource has the same action routes, where `<base>` is its list path:

| Action | Route | Returns |
|---|---|---|
| Add | `POST <base>` | the new display row, or the add form with the error |
| Display row (cancel) | `GET <base>/{id}/row` | the display row |
| Edit form | `GET <base>/{id}/edit` | the edit row |
| Save | `PUT <base>/{id}` | the display row, or the edit row with the error |
| Delete | `DELETE <base>/{id}` | empty body, or the display row with the error |

Bases: `/ui/teams`, `/ui/teams/{team_id}/members`, `/ui/applications`, `/ui/applications/{application_id}/functions`, `/ui/applications/{application_id}/data-types`, `/ui/applications/{application_id}/technologies`, `/ui/data-flows`, `/ui/personas`. Reference data uses `/ui/reference/{kind}` with the code in place of `{id}`.

`POST /ui/applications` takes the team from a hidden `team_id` field in the add form on the team page. `POST /ui/data-flows` takes its application ids from the form (the tab's add form pre-fills this application as source or target). The `GET /ui/data-flows` overview page renders its rows without edit or delete actions; the editable rows live in the application tabs and use the action routes above.

Nested bases return 404 for a missing parent and for an id that belongs to another parent, as the JSON API does. A missing record is a 404 page or fragment.

## Pages

- **Teams:** a table (name, description) with an add form above it. The name links to the team page.
- **Team page:** inline edit of name and description. A **Members** table (user id, name). An **Applications** table (name, short name, the four levels, derived RPO/RTO) with an add form (name, short name, level dropdowns). The application name links to its page.
- **Application page:** breadcrumbs (Teams › Team › App) and tabs, loaded as fragments and addressable with `?tab=`.
  - **Details:** every application field (name, short name, golden app id, auid, asset CMDB, owner uid, description, four level dropdowns) with inline edit. RPO/RTO are shown read-only as "4 h / 0 h", or "—" when there is no availability level.
  - **Functions:** name, description, category (dropdown from `function_category`), persona (dropdown of personas).
  - **Data types:** name, definition, specificity, confidentiality level (dropdown), golden source, golden replica.
  - **Technologies:** name, version, family, type (`technology_type`), standard status (`tech_standard_status`), standard status details, standards link, action plan.
  - **Data flows:** two tables, **Outgoing** (this application is the source) and **Incoming** (it is the target). Both use the same columns: source application, target application, data type, usage mode, usage explanation. The add form in each table pre-fills this application as source or target, and asks for the other application (grouped by team), a data type, a usage mode and an explanation. The data type dropdown lists all data types, labelled "Application › Data type" and grouped by application, because the domain does not tie a flow's data type to its source or target.
- **Personas:** name, description, category.
- **Data flows overview:** a read-only table of every flow with links to both applications. Editing happens in the application tabs.
- **Reference data:** the index lists the eight catalogs. A kind page is an inline table whose columns follow the kind: `code`, `label`, `description`, plus `rank` for the ranked kinds and `rpo_hours` and `rto_hours` for availability. Ranked kinds are listed by rank, highest first. A note says that changing a code renames it everywhere. A blocked delete shows why.
- **Dropdowns** are filled from the configuration tables at render time, so a new catalog value appears in every form at once. An empty option means "none" where the field is nullable.

## Interaction

- Actions target the closest row (`hx-target="closest tr"`, `hx-swap="outerHTML"`). The add form prepends the new row on success and clears itself.
- Full-page requests get a complete page. Requests with the `HX-Request` header get only the fragment. Rows, edit rows, add forms and error banners are shared templates, so a page and its fragments never drift apart.
- Deletes use `hx-confirm`. Deleting an application warns that it also removes its functions, data types and technologies.
- The 4xx statuses are swapped in. The base template sets HTMX's `responseHandling` in a `<meta name="htmx-config">` tag so 404, 409 and 422 responses are swapped, with no custom JavaScript.
- Pages and tabs read without JavaScript. Editing needs JavaScript, because HTMX sends the `PUT` and `DELETE` requests.
- Web forms send only the fields they show. `CrudService.update` replaces only the keys it is given, so fields a form does not show are kept.

## Resources and fields

A `Resource` has a slug, a title, the service that handles it, an optional parent link and an ordered list of `Field`s. A `Field` has a name, a label, a widget and a `required` flag. The widgets are:

| Widget | Use |
|---|---|
| `text`, `textarea`, `number` | plain values |
| `select_ref(kind)` | a code from a configuration table |
| `select_entity(...)` | an id of another entity, with a label function and optional grouping |
| `readonly` | a derived or display-only value (e.g. RPO/RTO) |

The field lists are those in "Pages". Required fields are the entities' required text fields from the backend spec (`name`, and `user_id` for members). Table cells show codes as their labels.

## Forms and errors

- `forms.py` turns the submitted fields into the dict the service expects: surrounding whitespace is stripped, a blank optional field becomes `None`, an empty select becomes `None`, numbers become ints and entity ids become UUIDs. A required text field stays `""`, so the domain's own "must not be blank" error appears.
- A value that cannot be parsed (for example a non-numeric `rank`) is reported next to its field with a 422.
- Domain errors from the services are shown as a banner (`role="alert"`) at the top of the form or row with the same text the JSON API uses. They map to statuses as in the backend spec: `InvalidEntity`, `InvalidReferenceCode` and `DanglingReference` give 422, `ReferenceInUse` and `AlreadyExists` give 409, and `NotFound` gives 404. Domain errors do not reliably name the field, so they are not attached to one.
- The form keeps what the user typed when it is re-rendered with an error.
- Jinja2 autoescaping is on for all templates, including text inside confirm dialogs.
- There is no CSRF handling, because there are no sessions or cookies and no authentication in v1.

## Testing

All tests use `TestClient` over the in-memory fakes (`tests/fakes.py`), with no browser.

- **Per resource:** the list page, add, display row, edit row, save, delete, a blank name returning 422 with the form and message kept, a blocked delete returning 409 with a reason, and a wrong or missing parent returning 404.
- **Dropdowns:** options come from the catalogs, ranked kinds in rank order, and the empty option is present for nullable fields.
- **Content:** derived RPO/RTO is shown, the data type dropdown is grouped by application, and text such as `<script>` is escaped everywhere it is rendered.
- **Fragments:** an `HX-Request` returns a fragment and a normal request a full page.
- **Reference data:** add, rename with the cascade note, edit of rank and hours, and a blocked delete.
- **Forms:** blank and empty-select handling, number and UUID parsing, a bad number reported against its field.
- **Packaging:** the templates and static files resolve at runtime from an installed package.
- **End to end:** one scenario through `/ui` against real Postgres (team → application → function → data flow, a blocked delete, a catalog rename visible in an application row).

What cannot be tested automatically is how the pages look and feel in a browser. After the build the app is run and its pages fetched, and the visual check is manual.

## Out of scope

Authentication, search, pagination, sorting, export, bulk import, a data flow diagram, i18n, and a no-JavaScript editing fallback.

## Open items

- The exact HTMX and Pico.css versions are pinned at implementation time and recorded in `VENDORED.md`. Downloading them needs network access once.
- Visual and usability review in a real browser is the user's.
