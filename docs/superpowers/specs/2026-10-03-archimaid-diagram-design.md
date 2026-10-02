# Archimaid application interaction diagram: design

Date: 2026-10-03

Builds on the backend spec (`2026-10-02-archimaid-design.md`) and the web frontend spec (`2026-10-02-archimaid-web-frontend-design.md`), both implemented and merged. It adds a read-only diagram; it changes no domain, persistence or JSON API behavior.

## Purpose

For one application, draw an SVG diagram of its interactions with other applications (its data flows) and with users (personas using its functions), centered on that application.

**Approved visual reference** (a throwaway prototype was built and approved by the user; the renders are kept as the target look):

- `assets/diagram/full.svg` and `full.png`: a rich example (5 functions, 3 personas with one shared, 3 targets, 4 sources, parallel flows, a truncated name, a self-flow footnote).
- `assets/diagram/small.svg`: two functions and one outgoing flow.
- `assets/diagram/empty.svg`: an application with nothing around it.

The implementation must reproduce this look and layout. Where this text and the sample files differ in a minor visual detail, the sample files are the reference. The one exception is the footnote text: the samples predate the "No data flows or personas yet." note, which this spec defines.

## Decisions

| # | Decision |
|---|---|
| 1 | A pure-Python SVG renderer with no new dependency (not a template, not a diagram library). |
| 2 | It lives in the web adapter, `src/archimaid/adapters/web/diagram/`, in three parts: `model.py` (plain dataclasses), `builder.py` (the only part that calls services), and `layout.py` + `svg.py` (coordinates and markup, with no knowledge of services or HTTP). |
| 3 | Outgoing flows (the application is the source) put the other application in the **top** row. Incoming flows (the application is the target) put it in the **bottom** row. Arrows always point up. |
| 4 | Personas are drawn as **stick figures** with the name underneath, in their own row between the current application and the source applications. Source arrows are routed around the figures. |
| 5 | Each flow gets its own arrow labelled with the data type's name. Hover shows details. Parallel flows between the same pair are offset lines with labels on alternating sides. |
| 6 | Available as a **Diagram tab** on the application page and as a **downloadable `.svg`**. No JSON API endpoint for now. |
| 7 | The picture is embedded with `<object>`, with its width and height set from the diagram's own size. |

## Data model and builder

`model.py` (frozen dataclasses, no behavior): `DiagramFunction(name, persona: str | None)`, `DiagramFlow(data_type, usage_mode, explanation)`, `DiagramNeighbour(name, flows: list[DiagramFlow])`, and `DiagramModel(application: str, functions: list[DiagramFunction], targets: list[DiagramNeighbour], sources: list[DiagramNeighbour], self_flows: int)`. Personas are identified by name in the model; two different personas that share a name would be drawn as one (acceptable: they would be indistinguishable in the picture).

`builder.py`, `build_diagram(services, application_id) -> DiagramModel`:

- functions: `services.functions.list(application_id=id)`, each with its persona's name through `services.personas.get` (cached);
- targets: flows from `services.data_flows.list(source_application_id=id)`, grouped by the target application's name;
- sources: flows from `services.data_flows.list(target_application_id=id)`, grouped by the source application's name;
- flow details: the data type's name (`services.data_types.get`), the usage mode's label (from `services.reference.get("usage_mode", code)`, or none), and the explanation;
- a flow whose source and target are both this application is not drawn; it is counted in `self_flows`;
- ordering is stable: neighbours sorted by name (case-insensitive, then id), flows by data type name, functions by name;
- an application can appear in both the top and the bottom row;
- an unknown application id raises `NotFound`.

## Layout and rendering

All sizes are pixels. Text widths are estimated as `len(text) * font_size * 0.56`; names are truncated with "…" (the full text is in the tooltip).

**Constants:** margin 40, gap between boxes in a row 40, other-application box height 44, current-application header band 36, function cell height 56, frame padding 6, persona figure block 78 high. Fonts: sans-serif, 13 px (15 px bold for the current application's name, 11 px for flow labels).

**Boxes:**

- Other applications: blue `#2b6cb0`, rounded 4, white text, centered, name truncated to 28 characters, width `clamp(text + 32, 120, 240)`.
- Current application: one blue frame. A header band shows the name (bold, truncated to 40 characters) centered. Below it, one cell per function (fill `#3f83c9`, white text, truncated to 24 characters) separated by 2 px gaps where the frame shows through. Cell widths start at `clamp(text + 24, 100, 200)` and are scaled to fill the frame. Frame width is at least 260, at least the header text plus 40, and wide enough for its arrows: `24 + 36 px` per attachment point on its busier edge (the top edge counts the flows to targets; the bottom edge counts the flows from sources plus the persona arrows), so the 16 px spacing between attachment points always holds. For ordinary diagrams this term is not the largest, so it changes nothing. Without functions: one italic "(no functions)" cell.
- Personas: a stick figure drawn in black (1.5 px strokes, round caps): a white-filled head circle of radius 8, a body line, an arms line 26 px wide, two leg lines, and the name centered below (13 px, truncated to 24 characters). The persona's box width is `max(48, text + 12)`.

**Rows, top to bottom:** targets, the frame, personas, sources. A row with nothing in it is omitted and the gaps close. Vertical gaps: 120 between the targets and the frame, 80 between the frame and personas, 140 between personas and sources (120 when there are no personas). Every row is centered on the canvas's vertical axis. Canvas width is the widest row plus both margins. Personas are placed under the average x of the functions they serve and pushed apart by the 40 px gap (then re-centered on the average desired offset).

**Arrows** (black, 1.5 px, straight lines with a black triangle marker at the head; heads at: the target box for outgoing flows, the frame's bottom edge for incoming flows and personas):

- Several flows between the same pair are spaced 16 px apart on both ends. Attachment points on the frame edge are spread so none are closer than 16 px (sort, push right, pull back if past the edge).
- Persona arrows go from the top of the figure's head (a persona with several functions fans out by 6 px steps) to the frame's bottom edge at the function cell's center.
- Incoming-flow attachment points on the frame's bottom edge are chosen on a 4 px grid, nearest to the source box's x, not within 16 px of an occupied point (function centers that have a persona arrow, and earlier choices) and such that the line does not cross any persona's box (width plus 10 px margin on each side) between the persona row's top and bottom. If no such point exists the nearest free point is used, then the wanted point.
- Drawing order: arrows, then boxes, then labels. Labels have a white backing rectangle (92% opaque).
- Labels: the data type name (11 px, truncated to 24 characters) beside the line, kept inside the canvas (a label that would cross the canvas edge is moved inward). Outgoing flows at the middle of the line; incoming flows 18% along from the source box (so they sit below the persona row). For parallel flows, even-indexed labels go on the left of the line and odd-indexed on the right; the third and later are staggered by 16 px.
- Tooltips (`<title>`): on each flow arrow "data type — usage mode — explanation"; on each persona arrow "Persona uses Function"; on boxes, the full name.

**Footnote:** at bottom left, 11 px grey: "N self-referencing data flow(s) not drawn." when `self_flows > 0`. If the application has no flows and no personas, the same spot reads "No data flows or personas yet."

**Document:** `<?xml ...?>` declaration, `<svg xmlns viewBox width height role="img">` with a `<title>` ("Interactions of <name>"), a white background rectangle, and a `<marker id="arrow">` definition. No external references, scripts or fonts. All user text goes through one escape function that strips characters XML 1.0 forbids and escapes `& < > " '`. Output for the same data is byte-for-byte identical.

## Web integration

- `GET /ui/applications/{application_id}/diagram.svg`: `image/svg+xml; charset=utf-8`; headers `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'`, `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`. With `?download=1` it also sends `Content-Disposition: attachment; filename="<slug>-interactions.svg"`, where the slug is the application's name lower-cased and reduced to ASCII letters, digits and hyphens (fallback `application`). An unknown id gives the existing error page with status 404.
- A **Diagram** tab (key `diagram`, label "Diagram") is added after "Data flows" in `TABS`. Its template shows the `<object type="image/svg+xml" data="…/diagram.svg" width height>` with a text fallback link, a "Download SVG" link, and a one-line hint that hovering shows details. The tab computes the diagram once to obtain its width and height. A wide diagram scrolls horizontally inside the tab.
- The tab is addressable as `?tab=diagram` like the others.

## Testing

- Layout and renderer (no services): boxes in a row never overlap and stay inside the canvas; arrow endpoints touch box edges; no incoming-flow arrow crosses a persona figure when a free path exists; output is identical on repeated runs; the output parses as XML for hostile text, NUL and control characters; counts of arrows, markers and persona figures match the model.
- Builder (in-memory fakes): flow direction to rows, both-direction flows in both rows, grouping and parallel flows, a persona shared by two functions, ordering, the self-flow count, an unknown application.
- Routes: content type and security headers, the download header and a safe filename for a hostile name, 404s, the tab content, the tab list.
- End-to-end on real Postgres: the diagram of a real scenario parses and has the expected arrows.
- Manual check: sample SVGs rendered to PNG with `rsvg-convert` and compared by eye with the approved references.

## Out of scope

A JSON API endpoint (a small addition later), PNG or PDF export, zoom or pan, filtering, the neighbours' own flows (more than one level), flows tied to individual functions, editing from the diagram, and exact text measurement (widths are estimates).

## Open items

- Very long names or very many neighbours produce a wide picture; the tab scrolls, with no wrapping or paging.
- Fonts are the viewer's sans-serif fallback; text may be slightly wider or narrower than estimated.
