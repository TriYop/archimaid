# Application Interaction Diagram Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate an SVG diagram of an application's interactions (data flows and persona/function usage), show it in a new "Diagram" tab of the web UI, and offer it as a downloadable `.svg`.

**Architecture:** A pure renderer inside the web adapter, `src/archimaid/adapters/web/diagram/`. `model.py` holds plain dataclasses, `builder.py` is the only part that calls the application services, `layout.py` computes all coordinates, `svg.py` writes the markup. The web layer adds one route that returns the SVG and a tab that embeds it with `<object>`. The geometry is a port of a prototype the user approved; a regression test holds the renderer to the approved sample files.

**Tech Stack:** Python standard library only (no new dependency), FastAPI/Jinja2 (already present), pytest with `TestClient` over the in-memory fakes, one end-to-end test on Postgres, `rsvg-convert` for the final visual check.

**Spec:** `docs/superpowers/specs/2026-10-03-archimaid-diagram-design.md` (read it first). The approved reference renders are in `docs/superpowers/specs/assets/diagram/` (`full.svg`, `full.png`, `small.svg`, `empty.svg`).

## Global Constraints

- No new runtime or dev dependency. The renderer uses only the standard library.
- The diagram package imports only `archimaid.application` (the `Services` type), `archimaid.domain` and its own modules. It never imports `archimaid.adapters.persistence` or `archimaid.adapters.api`.
- `layout.py` and `svg.py` are pure: no service calls, no HTTP, no I/O. Only `builder.py` calls services.
- All user text reaches the SVG only through `text.escape()` / `text.truncate()`, which strip characters XML 1.0 forbids (including NUL, other C0 controls except tab/newline/CR, lone surrogates, U+FFFE/U+FFFF) and escape `& < > " '`. Never build SVG markup from unescaped user text.
- Output is deterministic: the same model always gives the same bytes.
- Sizes and colors are exactly those in the spec (margin 40, gap 40, application box height 44, header band 36, function cell 56, frame padding 6, persona block 78; blue `#2b6cb0`, cells `#3f83c9`). The renderer's geometry for the spec's sample data must equal the approved sample files (a test pins this).
- `GET /ui/applications/{id}/diagram.svg` returns `image/svg+xml; charset=utf-8` with `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'`, `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`; with `?download=1` also `Content-Disposition: attachment; filename="<slug>-interactions.svg"`, slug = lower-cased ASCII letters/digits/hyphens (fallback `application`).
- Failures use the existing web error handling: an unknown application is a 404 error page, a malformed id is the existing 422 HTML handling.
- The dev server (port 8000) and dev Postgres container (`archimaid-dev-db`, port 55433) belong to the user: do not stop, restart or modify them, and use other ports for anything you start.
- Pytest output in this environment may be condensed by a tool that hides warnings and skip reasons. Use `rtk proxy uv run pytest -rs ...` for raw output. The suite must end with 0 skipped and 0 warnings. `ruff check src tests` and `mypy src` must stay clean (no config loosening, no `# noqa`).
- Every commit message ends with this trailer line, added with a second `-m`: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`

## Review Focus

Conditions the spec implies but no obvious test would exercise; each has a pinning test in the owning task, marked **Review Focus test**.

1. Hostile or control text in any name (NUL, other control characters, lone surrogates, `<script>`, `&`, quotes) never produces malformed XML or injected markup, and the response always encodes as UTF-8 (Tasks 0, 2, 4).
2. Degenerate models render without crashing: no functions, no flows, only self-flows, a neighbour that is both source and target, a persona shared by several functions, and 30 neighbours with several flows each (Tasks 1, 3).
3. Incoming-flow arrows do not run through a persona figure when a free path exists, and attachment points on the frame's bottom edge stay at least 16 px apart (Task 1).
4. The download filename cannot inject headers or path segments, whatever the application's name (Task 4).
5. An unknown or malformed application id, and an unknown tab, give 404/422 pages, never a 500 (Task 4).
6. The tab's `<object>` has the diagram's real width and height, so it is not clipped or collapsed (Task 4).

---

## File Structure

```
src/archimaid/adapters/web/diagram/
  __init__.py      re-exports build_diagram, draw, Diagram
  model.py         DiagramFunction, DiagramFlow, DiagramNeighbour, DiagramModel
  text.py          clean, truncate, text_width, escape
  files.py         filename_slug
  layout.py        Rect, Figure, Label, Arrow, Layout, compute_layout
  svg.py           render_svg, Diagram, draw
  builder.py       build_diagram(services, application_id)
src/archimaid/adapters/web/resources.py     + ("diagram", "Diagram") in TABS
src/archimaid/adapters/web/pages.py         + diagram.svg route, diagram tab context
src/archimaid/adapters/web/templates/tabs/diagram.html
src/archimaid/adapters/web/static/app.css   + .diagram
tests/adapters/web/diagram/
  __init__.py  samples.py  test_text.py  test_layout.py  test_svg.py
  test_builder.py  test_diagram_routes.py
tests/test_diagram_end_to_end_postgres.py
```

---

### Task 0: Model, text helpers and filename slug

**Files:**
- Create: `src/archimaid/adapters/web/diagram/__init__.py` (empty for now), `model.py`, `text.py`, `files.py`, `tests/adapters/web/diagram/__init__.py`, `tests/adapters/web/diagram/samples.py`
- Test: `tests/adapters/web/diagram/test_text.py`

**Interfaces:**
- Produces in `model.py` (all frozen dataclasses):
  - `DiagramFunction(name: str, persona: str | None = None)`
  - `DiagramFlow(data_type: str, usage_mode: str | None = None, explanation: str | None = None)`
  - `DiagramNeighbour(name: str, flows: tuple[DiagramFlow, ...])`
  - `DiagramModel(application: str, functions: tuple[DiagramFunction, ...] = (), targets: tuple[DiagramNeighbour, ...] = (), sources: tuple[DiagramNeighbour, ...] = (), self_flows: int = 0)`
- Produces in `text.py`: `clean(text) -> str`, `truncate(text, limit) -> str` (cleans, then cuts to `limit` characters with a final "…"), `text_width(text, size=13) -> float` (`len * size * 0.56`), `escape(text) -> str` (cleans, then `html.escape(..., quote=True)`).
- Produces in `files.py`: `filename_slug(name, fallback="application") -> str`.
- Produces in `samples.py` (test support): `FULL`, `SMALL`, `EMPTY`, `HOSTILE` as `DiagramModel` values (data below).

- [ ] **Step 1: Write the failing test and the samples**

`tests/adapters/web/diagram/__init__.py`: empty file.

`tests/adapters/web/diagram/samples.py`:
```python
from archimaid.adapters.web.diagram.model import (
    DiagramFlow,
    DiagramFunction,
    DiagramModel,
    DiagramNeighbour,
)


def flow(data_type, usage_mode=None, explanation=None):
    return DiagramFlow(data_type, usage_mode, explanation)


def neighbour(name, *flows):
    return DiagramNeighbour(name, tuple(flows))


# The data of the approved prototype renders (docs/superpowers/specs/assets/diagram/).
FULL = DiagramModel(
    application="Billing",
    functions=(
        DiagramFunction("Create invoice", "Accountant"),
        DiagramFunction("Send payment reminder", "Accountant"),
        DiagramFunction("Approve refund", "Finance manager"),
        DiagramFunction("Export ledger", "Auditor"),
        DiagramFunction("Archive documents", None),
    ),
    targets=(
        neighbour(
            "General Ledger",
            flow("Invoice", "Source", "posted nightly"),
            flow("Payment", "Source"),
        ),
        neighbour("Data Warehouse", flow("Invoice", "Source")),
        neighbour("Tax Authority Reporting Gateway Service", flow("VAT return", "Proxy")),
    ),
    sources=(
        neighbour("CRM", flow("Customer", "Source")),
        neighbour("Payment Gateway", flow("Transaction", "Source"), flow("Chargeback", "Source")),
        neighbour("ERP", flow("Price list", "Source"), flow("Product catalogue", "Source")),
        neighbour("General Ledger", flow("Exchange rates", "Source")),
    ),
    self_flows=1,
)

SMALL = DiagramModel(
    application="Notifier",
    functions=(DiagramFunction("Send email"), DiagramFunction("Send SMS")),
    targets=(neighbour("Mail server", flow("Message")),),
)

EMPTY = DiagramModel(application="Lonely app")

HOSTILE = DiagramModel(
    application='Evil <script>alert(1)</script> & "co"\x00',
    functions=(DiagramFunction("fn <b>bold</b>\x01", "P\"1'"),),
    targets=(neighbour("T&T <x>", flow("a<b>&c", "m", "e")),),
)
```

`tests/adapters/web/diagram/test_text.py`:
```python
import pytest

from archimaid.adapters.web.diagram.files import filename_slug
from archimaid.adapters.web.diagram.text import clean, escape, text_width, truncate


def test_clean_removes_characters_xml_forbids_and_keeps_the_allowed_ones():
    # Review Focus test (1)
    assert clean("a\x00b\x0bc\x0cd\x1fe\ud800f￾g￿h") == "abcdefgh"
    assert clean("tab\there\nnew\rline") == "tab\there\nnew\rline"
    assert clean("café — 日本語") == "café — 日本語"


def test_escape_escapes_markup_and_cleans():
    assert escape('<a href="x">&\'</a>\x00') == "&lt;a href=&quot;x&quot;&gt;&amp;&#x27;&lt;/a&gt;"


def test_escaped_text_always_encodes_to_utf8():
    # Review Focus test (1): a lone surrogate would make .encode("utf-8") raise
    escape("bad \ud800 text").encode("utf-8")


def test_truncate_cuts_with_an_ellipsis_and_cleans():
    assert truncate("short", 10) == "short"
    assert truncate("exactly10!", 10) == "exactly10!"
    assert truncate("0123456789ABC", 10) == "012345678…"
    assert truncate("a\x00bc", 10) == "abc"


def test_text_width_is_proportional_to_length_and_size():
    assert text_width("") == 0
    assert text_width("abcd", 10) == pytest.approx(22.4)
    assert text_width("abcd") == pytest.approx(4 * 13 * 0.56)


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Billing", "billing"),
        ('Billing / "Core" <v2>', "billing-core-v2"),
        ("  Léa's  App  ", "lea-s-app"),
        ("../../etc/passwd", "etc-passwd"),
        ("日本語", "application"),
        ("", "application"),
        ("a\r\nContent-Type: text/html", "a-content-type-text-html"),
        ("x" * 200, "x" * 60),
    ],
)
def test_filename_slug_is_safe_ascii(name, slug):
    # Review Focus test (4)
    assert filename_slug(name) == slug
    assert all(c.isascii() and (c.isalnum() or c == "-") for c in filename_slug(name))
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/adapters/web/diagram/test_text.py -v`
Expected: collection error `ModuleNotFoundError: archimaid.adapters.web.diagram`.

- [ ] **Step 3: Implement**

`src/archimaid/adapters/web/diagram/__init__.py`: empty file (filled in Task 2/3).

`src/archimaid/adapters/web/diagram/model.py`:
```python
from dataclasses import dataclass


@dataclass(frozen=True)
class DiagramFunction:
    name: str
    persona: str | None = None


@dataclass(frozen=True)
class DiagramFlow:
    data_type: str
    usage_mode: str | None = None
    explanation: str | None = None


@dataclass(frozen=True)
class DiagramNeighbour:
    name: str
    flows: tuple[DiagramFlow, ...]


@dataclass(frozen=True)
class DiagramModel:
    application: str
    functions: tuple[DiagramFunction, ...] = ()
    targets: tuple[DiagramNeighbour, ...] = ()  # other applications that receive data (top row)
    sources: tuple[DiagramNeighbour, ...] = ()  # other applications that send data (bottom row)
    self_flows: int = 0  # flows from the application to itself: counted, not drawn
```

`src/archimaid/adapters/web/diagram/text.py`:
```python
import html
import re

# Characters XML 1.0 cannot carry (C0 controls except tab/newline/CR, lone surrogates, U+FFFE/F).
_FORBIDDEN = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")


def clean(text: str) -> str:
    return _FORBIDDEN.sub("", text)


def truncate(text: str, limit: int) -> str:
    text = clean(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def text_width(text: str, size: float = 13) -> float:
    """Estimated rendered width: no font metrics are available, so 0.56 em per character."""
    return len(text) * size * 0.56


def escape(text: str) -> str:
    return html.escape(clean(text), quote=True)
```

`src/archimaid/adapters/web/diagram/files.py`:
```python
import re
import unicodedata


def filename_slug(name: str, fallback: str = "application") -> str:
    """Lower-case ASCII letters, digits and hyphens only; safe in a Content-Disposition header."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:60].strip("-")
    return slug or fallback
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/adapters/web/diagram/test_text.py -v`
Expected: all pass. If a slug expectation differs (e.g. `Léa's`), fix `filename_slug`, not the test, unless the expectation is clearly wrong; record any such change in your report.

- [ ] **Step 5: Commit**

```bash
git add src/archimaid/adapters/web/diagram tests/adapters/web/diagram
git commit -m "feat(diagram): model, text helpers and filename slug" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 1: Layout

**Files:**
- Create: `src/archimaid/adapters/web/diagram/layout.py`
- Test: `tests/adapters/web/diagram/test_layout.py`

**Interfaces:**
- Consumes: `DiagramModel` (Task 0), `truncate`, `text_width` (Task 0).
- Produces in `layout.py` (frozen dataclasses):
  - `Rect(text, x, y, w, h)` with properties `cx`, `right`, `bottom`. `text` is the full, untruncated name.
  - `Figure(name, x, y, w)` (a persona; `x`, `w` are its box, `y` the top of its `PERSONA_H` high block) with property `cx`.
  - `Label(text, x, y, w)` (`x` is the left of the white backing rectangle, `y` its vertical centre; `text` is already truncated).
  - `Arrow(kind, x1, y1, x2, y2, title, label)` where `kind` is `"target"`, `"source"` or `"persona"`, the arrowhead is at `(x2, y2)`, and `label` is a `Label | None`.
  - `Layout(width, height, application, frame, cells, targets, sources, personas, arrows, footnote, footnote_y)`.
  - `compute_layout(model) -> Layout`, plus the constants `MARGIN, GAP, APP_H, HEADER_H, CELL_H, PAD, PERSONA_H`.
- Arrows are listed targets first, then sources, then personas. Boxes: `targets` and `sources` are in model order.

- [ ] **Step 1: Write the failing test**

`tests/adapters/web/diagram/test_layout.py`:
```python
import pytest

from archimaid.adapters.web.diagram.layout import (
    GAP,
    PERSONA_H,
    compute_layout,
)
from archimaid.adapters.web.diagram.model import DiagramFunction, DiagramModel
from tests.adapters.web.diagram.samples import EMPTY, FULL, HOSTILE, SMALL, flow, neighbour

EPS = 0.01


def row_gaps_ok(rects):
    ordered = sorted(rects, key=lambda r: r.x)
    return all(b.x - a.right >= GAP - EPS for a, b in zip(ordered, ordered[1:], strict=False))


def inside_canvas(layout, rect):
    return (
        rect.x >= -EPS
        and rect.right <= layout.width + EPS
        and rect.y >= -EPS
        and rect.bottom <= layout.height + EPS
    )


def of_kind(layout, kind):
    return [a for a in layout.arrows if a.kind == kind]


def test_rows_are_stacked_targets_frame_personas_sources():
    layout = compute_layout(FULL)
    top = max(r.bottom for r in layout.targets)
    persona_top = min(p.y for p in layout.personas)
    persona_bottom = max(p.y + PERSONA_H for p in layout.personas)
    source_top = min(r.y for r in layout.sources)
    assert top < layout.frame.y
    assert layout.frame.bottom < persona_top
    assert persona_bottom < source_top


def test_boxes_do_not_overlap_in_a_row_and_stay_inside_the_canvas():
    layout = compute_layout(FULL)
    assert row_gaps_ok(layout.targets) and row_gaps_ok(layout.sources)
    ordered = sorted(layout.personas, key=lambda p: p.x)
    assert all(b.x - a.x - a.w >= GAP - EPS for a, b in zip(ordered, ordered[1:], strict=False))
    for rect in (*layout.targets, *layout.sources, layout.frame, *layout.cells):
        assert inside_canvas(layout, rect)
    for p in layout.personas:
        assert p.x >= -EPS and p.x + p.w <= layout.width + EPS
        assert p.y + PERSONA_H <= layout.height + EPS


def test_function_cells_fill_the_frame_inside_its_padding():
    layout = compute_layout(FULL)
    cells = sorted(layout.cells, key=lambda c: c.x)
    assert len(cells) == 5
    assert cells[0].x == pytest.approx(layout.frame.x + 6)
    assert cells[-1].right == pytest.approx(layout.frame.right - 6)
    assert all(b.x - a.right == pytest.approx(2) for a, b in zip(cells, cells[1:], strict=False))


def test_arrow_counts_for_the_full_sample():
    layout = compute_layout(FULL)
    assert len(of_kind(layout, "target")) == 4  # General Ledger x2, Data Warehouse, Tax Authority
    assert len(of_kind(layout, "source")) == 6  # CRM, Gateway x2, ERP x2, General Ledger
    assert len(of_kind(layout, "persona")) == 4  # Accountant x2, Finance manager, Auditor
    assert len(layout.personas) == 3  # the shared persona is drawn once


def test_every_arrow_points_up():
    layout = compute_layout(FULL)
    assert all(a.y2 < a.y1 for a in layout.arrows)


def test_arrow_endpoints_touch_the_boxes_they_connect():
    layout = compute_layout(FULL)
    frame = layout.frame
    for a in of_kind(layout, "target"):
        assert a.y1 == pytest.approx(frame.y)
        assert frame.x < a.x1 < frame.right
        assert any(abs(a.y2 - t.bottom) < EPS and t.x <= a.x2 <= t.right for t in layout.targets)
    for a in of_kind(layout, "source"):
        assert a.y2 == pytest.approx(frame.bottom)
        assert frame.x < a.x2 < frame.right
        assert any(abs(a.y1 - s.y) < EPS and s.x <= a.x1 <= s.right for s in layout.sources)
    centers = [c.cx for c in layout.cells]
    for a in of_kind(layout, "persona"):
        assert a.y2 == pytest.approx(frame.bottom)
        assert any(abs(a.x2 - c) < EPS for c in centers)
        assert any(
            abs(a.y1 - (p.y + 2)) < EPS and p.x <= a.x1 <= p.x + p.w for p in layout.personas
        )


def test_parallel_flows_are_offset_and_labelled_on_alternating_sides():
    layout = compute_layout(FULL)
    ledger = [
        a for a in of_kind(layout, "target") if a.title.startswith("Invoice — Source — posted")
    ]
    payment = [a for a in of_kind(layout, "target") if a.title.startswith("Payment")]
    assert len(ledger) == 1 and len(payment) == 1
    assert abs(ledger[0].x2 - payment[0].x2) == pytest.approx(16)
    assert ledger[0].label.x < ledger[0].x1 < payment[0].label.x  # left label vs right label


def test_attachment_points_on_the_bottom_edge_keep_their_distance():
    # Review Focus test (3)
    layout = compute_layout(FULL)
    ends = sorted(a.x2 for a in layout.arrows if a.kind in ("source", "persona"))
    assert all(b - a >= 15.99 for a, b in zip(ends, ends[1:], strict=False))


def test_source_arrows_avoid_persona_figures():
    # Review Focus test (3)
    layout = compute_layout(FULL)
    y_top = min(p.y for p in layout.personas)
    y_bottom = y_top + PERSONA_H
    for a in of_kind(layout, "source"):
        def x_at(y, a=a):
            return a.x1 + (a.x2 - a.x1) * (a.y1 - y) / (a.y1 - a.y2)

        lo, hi = sorted((x_at(y_top), x_at(y_bottom)))
        for p in layout.personas:
            assert hi < p.x or lo > p.x + p.w, (a.title, p.name)


def test_labels_are_the_data_type_names_and_persona_arrows_have_none():
    layout = compute_layout(FULL)
    assert {a.label.text for a in of_kind(layout, "target")} == {"Invoice", "Payment", "VAT return"}
    assert all(a.label is None for a in of_kind(layout, "persona"))
    titles = {a.title for a in layout.arrows}
    assert "Invoice — Source — posted nightly" in titles
    assert "Payment — Source" in titles
    assert "Accountant uses Create invoice" in titles


def test_small_sample_omits_empty_rows_and_has_no_footnote():
    layout = compute_layout(SMALL)
    assert layout.personas == () and layout.sources == ()
    assert len(layout.targets) == 1 and len(layout.cells) == 2
    assert layout.footnote is None and layout.footnote_y is None
    assert layout.height < compute_layout(FULL).height


def test_empty_application_is_a_frame_with_a_note():
    # Review Focus test (2)
    layout = compute_layout(EMPTY)
    assert layout.cells == () and layout.arrows == ()
    assert layout.footnote == "No data flows or personas yet."
    assert layout.frame.w >= 260


def test_footnote_counts_self_flows():
    assert compute_layout(FULL).footnote == "1 self-referencing data flow(s) not drawn."
    only_self = DiagramModel(application="Loop", self_flows=2)
    assert compute_layout(only_self).footnote == "2 self-referencing data flow(s) not drawn."


def test_layout_is_deterministic():
    assert compute_layout(FULL) == compute_layout(FULL)
    assert compute_layout(HOSTILE) == compute_layout(HOSTILE)


def test_a_neighbour_that_is_both_target_and_source_appears_in_both_rows():
    model = DiagramModel(
        application="A",
        targets=(neighbour("B", flow("x")),),
        sources=(neighbour("B", flow("y")),),
    )
    layout = compute_layout(model)
    assert [r.text for r in layout.targets] == ["B"] and [r.text for r in layout.sources] == ["B"]


def test_many_neighbours_and_flows_stay_valid():
    # Review Focus test (2)
    many = tuple(
        neighbour(f"App {i:02d} with a rather long name", *(flow(f"Type {j}") for j in range(3)))
        for i in range(30)
    )
    functions = tuple(DiagramFunction(f"Function {i}", f"Persona {i % 4}") for i in range(12))
    layout = compute_layout(DiagramModel("Hub", functions, targets=many, sources=many))
    assert row_gaps_ok(layout.targets) and row_gaps_ok(layout.sources)
    assert len(layout.arrows) == 30 * 3 * 2 + 12
    assert all(a.y2 < a.y1 for a in layout.arrows)
    for rect in (*layout.targets, *layout.sources, layout.frame):
        assert inside_canvas(layout, rect)


def test_a_persona_shared_by_functions_is_drawn_once_with_one_arrow_each():
    model = DiagramModel(
        application="A",
        functions=(
            DiagramFunction("f1", "Pat"),
            DiagramFunction("f2", "Pat"),
            DiagramFunction("f3", "Pat"),
        ),
    )
    layout = compute_layout(model)
    assert [p.name for p in layout.personas] == ["Pat"]
    assert len(of_kind(layout, "persona")) == 3


def test_full_names_are_kept_in_rects_and_truncation_happens_at_render_time():
    layout = compute_layout(FULL)
    assert "Tax Authority Reporting Gateway Service" in [r.text for r in layout.targets]


def test_widths_are_clamped_to_their_ranges():
    layout = compute_layout(FULL)
    assert all(120 - EPS <= r.w <= 240 + EPS for r in (*layout.targets, *layout.sources))
    tiny = compute_layout(DiagramModel("A", targets=(neighbour("x", flow("y")),)))
    assert tiny.targets[0].w == pytest.approx(120)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/adapters/web/diagram/test_layout.py -v`
Expected: collection error `ModuleNotFoundError: archimaid.adapters.web.diagram.layout`.

- [ ] **Step 3: Implement `layout.py`**

`src/archimaid/adapters/web/diagram/layout.py`:
```python
"""Geometry of the application interaction diagram. Pure functions: no I/O, no services."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from archimaid.adapters.web.diagram.model import DiagramFlow, DiagramModel
from archimaid.adapters.web.diagram.text import text_width, truncate

MARGIN, GAP, APP_H, HEADER_H, CELL_H, PAD, PERSONA_H = 40, 40, 44, 36, 56, 6, 78
CELL_GAP = 2
ARROW_SPACING = 16
GAP_TARGETS, GAP_PERSONAS, GAP_SOURCES, GAP_SOURCES_NO_PERSONAS = 120, 80, 140, 120
PERSONA_MARGIN = 10  # clearance kept between a source arrow and a persona box


@dataclass(frozen=True)
class Rect:
    text: str  # the full, untruncated name
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h


@dataclass(frozen=True)
class Figure:
    name: str
    x: float
    y: float
    w: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2


@dataclass(frozen=True)
class Label:
    text: str  # already truncated
    x: float  # left edge of the white backing rectangle
    y: float  # vertical centre
    w: float


@dataclass(frozen=True)
class Arrow:
    kind: str  # "target" | "source" | "persona"
    x1: float
    y1: float
    x2: float  # the arrowhead is at (x2, y2)
    y2: float
    title: str
    label: Label | None = None


@dataclass(frozen=True)
class Layout:
    width: float
    height: float
    application: str
    frame: Rect
    cells: tuple[Rect, ...]
    targets: tuple[Rect, ...]
    sources: tuple[Rect, ...]
    personas: tuple[Figure, ...]
    arrows: tuple[Arrow, ...]
    footnote: str | None
    footnote_y: float | None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _spread(positions: Sequence[float], low: float, high: float, gap: float) -> list[float]:
    """Keep the order of `positions`, clamp them to [low, high] and keep `gap` between them."""
    order = sorted(range(len(positions)), key=lambda i: positions[i])
    pos = [_clamp(positions[i], low, high) for i in order]
    for i in range(1, len(pos)):
        pos[i] = max(pos[i], pos[i - 1] + gap)
    if pos and pos[-1] > high:
        pos[-1] = high
        for i in range(len(pos) - 2, -1, -1):
            pos[i] = min(pos[i], pos[i + 1] - gap)
    out = [0.0] * len(positions)
    for rank, i in enumerate(order):
        out[i] = pos[rank]
    return out


def _flow_title(flow: DiagramFlow) -> str:
    return " — ".join(p for p in (flow.data_type, flow.usage_mode, flow.explanation) if p)


def _label(
    text: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    k: int,
    n: int,
    at: float,
) -> Label:
    """A label beside the line at fraction `at` from (x1, y1); parallel lines alternate sides."""
    shown = truncate(text, 24)
    width = text_width(shown, 11) + 8
    mx, my = x1 + (x2 - x1) * at, y1 + (y2 - y1) * at
    my += (k // 2) * 16  # the third and later parallel labels are staggered
    left_of_line = n > 1 and k % 2 == 0
    x = mx - 5 - width if left_of_line else mx + 5
    return Label(shown, x, my, width)


def _row_positions(widths: Sequence[float], cx: float) -> list[float]:
    total = sum(widths) + GAP * (len(widths) - 1) if widths else 0
    x = cx - total / 2
    out = []
    for w in widths:
        out.append(x)
        x += w + GAP
    return out


def compute_layout(model: DiagramModel) -> Layout:
    functions = model.functions

    # --- sizes
    cell_w = [_clamp(text_width(truncate(f.name, 24)) + 24, 100, 200) for f in functions] or [140.0]
    cell_gaps = CELL_GAP * (len(cell_w) - 1)
    frame_w = max(
        260.0,
        text_width(truncate(model.application, 40), 15) + 40,
        sum(cell_w) + cell_gaps + 2 * PAD,
    )
    scale = (frame_w - 2 * PAD - cell_gaps) / sum(cell_w)
    cell_w = [w * scale for w in cell_w]

    def neighbour_w(name: str) -> float:
        return _clamp(text_width(truncate(name, 28)) + 32, 120, 240)

    tgt_w = [neighbour_w(n.name) for n in model.targets]
    src_w = [neighbour_w(n.name) for n in model.sources]
    personas: list[str] = []
    for f in functions:
        if f.persona and f.persona not in personas:
            personas.append(f.persona)
    per_w = {p: max(48.0, text_width(truncate(p, 24)) + 12) for p in personas}

    def row_w(ws: Sequence[float]) -> float:
        return sum(ws) + GAP * (len(ws) - 1) if ws else 0

    persona_row = sum(per_w.values()) + GAP * (len(personas) - 1) if personas else 0
    canvas_w = max(frame_w, row_w(tgt_w), row_w(src_w), persona_row) + 2 * MARGIN
    cx = canvas_w / 2

    # --- vertical positions
    y_tgt = MARGIN if model.targets else None
    y_frame = (y_tgt + APP_H + GAP_TARGETS) if y_tgt is not None else MARGIN
    frame_h = HEADER_H + CELL_H + PAD
    frame_x = cx - frame_w / 2
    y_cells = y_frame + HEADER_H
    y_persona = (y_frame + frame_h + GAP_PERSONAS) if personas else None
    base = (y_persona + PERSONA_H) if y_persona is not None else (y_frame + frame_h)
    y_src = (
        base + (GAP_SOURCES if personas else GAP_SOURCES_NO_PERSONAS) if model.sources else None
    )
    bottom = (y_src + APP_H) if y_src is not None else base
    frame_bottom = y_frame + frame_h

    # --- horizontal positions
    cell_x: list[float] = []
    x = frame_x + PAD
    for w in cell_w:
        cell_x.append(x)
        x += w + CELL_GAP
    cell_cx = [x0 + w / 2 for x0, w in zip(cell_x, cell_w, strict=True)]
    tgt_x, src_x = _row_positions(tgt_w, cx), _row_positions(src_w, cx)

    # personas sit under the functions they serve, pushed apart if they would overlap
    served = {p: [i for i, f in enumerate(functions) if f.persona == p] for p in personas}
    desired = {p: sum(cell_cx[i] for i in served[p]) / len(served[p]) for p in personas}
    per_x: dict[str, float] = {}
    prev_right = -1e9
    for p in sorted(personas, key=lambda name: desired[name]):
        left = max(prev_right + GAP, desired[p] - per_w[p] / 2)
        per_x[p] = left
        prev_right = left + per_w[p]
    if personas:
        shift = sum(desired[p] - (per_x[p] + per_w[p] / 2) for p in personas) / len(personas)
        for p in personas:
            per_x[p] += shift

    arrows: list[Arrow] = []

    # --- targets (top row): from the frame's top edge up to the target box
    top_wanted: list[float] = []
    top_meta: list[tuple[DiagramFlow, float, float, float, int, int]] = []
    for neighbour, bx, bw in zip(model.targets, tgt_x, tgt_w, strict=True):
        for k, flow in enumerate(neighbour.flows):
            off = (k - (len(neighbour.flows) - 1) / 2) * ARROW_SPACING
            top_wanted.append(bx + bw / 2 + off)
            top_meta.append((flow, bx, bw, off, k, len(neighbour.flows)))
    top_end = _spread(top_wanted, frame_x + 12, frame_x + frame_w - 12, ARROW_SPACING)
    for (flow, bx, bw, off, k, n), x_frame in zip(top_meta, top_end, strict=True):
        assert y_tgt is not None
        x_box = _clamp(bx + bw / 2 + off, bx + 8, bx + bw - 8)
        y_box = y_tgt + APP_H
        arrows.append(
            Arrow(
                "target",
                x_frame,
                y_frame,
                x_box,
                y_box,
                _flow_title(flow),
                _label(flow.data_type, x_frame, y_frame, x_box, y_box, k, n, 0.5),
            )
        )

    # --- sources (bottom row): from the source box up to the frame's bottom edge
    if y_src is not None:
        src_top: float = y_src  # a plain float for the nested helpers below
        occupied = [cell_cx[i] for i, f in enumerate(functions) if f.persona]

        def free(c: float) -> bool:
            return all(abs(c - o) >= ARROW_SPACING for o in occupied)

        def clear_of_personas(x_box: float, x_end: float) -> bool:
            if y_persona is None:
                return True

            def x_at(y: float) -> float:
                return x_box + (x_end - x_box) * (src_top - y) / (src_top - frame_bottom)

            lo = min(x_at(y_persona), x_at(y_persona + PERSONA_H))
            hi = max(x_at(y_persona), x_at(y_persona + PERSONA_H))
            return all(
                hi < per_x[p] - PERSONA_MARGIN or lo > per_x[p] + per_w[p] + PERSONA_MARGIN
                for p in personas
            )

        candidates = [frame_x + 12 + 4 * j for j in range(int((frame_w - 24) / 4) + 1)]
        for neighbour, bx, bw in zip(model.sources, src_x, src_w, strict=True):
            for k, flow in enumerate(neighbour.flows):
                n = len(neighbour.flows)
                off = (k - (n - 1) / 2) * ARROW_SPACING
                want = _clamp(bx + bw / 2 + off, frame_x + 12, frame_x + frame_w - 12)
                x_box = _clamp(bx + bw / 2 + off, bx + 8, bx + bw - 8)
                nearest = sorted(candidates, key=lambda c: abs(c - want))
                x_frame = next(
                    (c for c in nearest if free(c) and clear_of_personas(x_box, c)),
                    next((c for c in nearest if free(c)), want),
                )
                occupied.append(x_frame)
                arrows.append(
                    Arrow(
                        "source",
                        x_box,
                        y_src,
                        x_frame,
                        frame_bottom,
                        _flow_title(flow),
                        _label(flow.data_type, x_box, y_src, x_frame, frame_bottom, k, n, 0.18),
                    )
                )

    # --- persona -> function arrows
    for p in personas:
        assert y_persona is not None
        indexes = served[p]
        for n, i in enumerate(indexes):
            off = (n - (len(indexes) - 1) / 2) * 6
            x_start = per_x[p] + per_w[p] / 2 + off
            arrows.append(
                Arrow(
                    "persona",
                    x_start,
                    y_persona + 2,
                    cell_cx[i],
                    frame_bottom,
                    f"{p} uses {functions[i].name}",
                )
            )

    # --- footnote
    footnote: str | None = None
    if model.self_flows:
        footnote = f"{model.self_flows} self-referencing data flow(s) not drawn."
    elif not (model.targets or model.sources or personas):
        footnote = "No data flows or personas yet."
    footnote_y: float | None = None
    if footnote:
        footnote_y = bottom + 28
        bottom += 20

    return Layout(
        width=canvas_w,
        height=bottom + MARGIN,
        application=model.application,
        frame=Rect(model.application, frame_x, y_frame, frame_w, frame_h),
        # with no functions `cell_w` holds one placeholder width, so the lengths differ on purpose
        cells=tuple(
            Rect(f.name, x0, y_cells, w, CELL_H)
            for f, x0, w in zip(functions, cell_x, cell_w, strict=False)
        ),
        targets=tuple(
            Rect(n.name, bx, y_tgt, bw, APP_H)
            for n, bx, bw in zip(model.targets, tgt_x, tgt_w, strict=True)
            if y_tgt is not None
        ),
        sources=tuple(
            Rect(n.name, bx, y_src, bw, APP_H)
            for n, bx, bw in zip(model.sources, src_x, src_w, strict=True)
            if y_src is not None
        ),
        personas=tuple(
            Figure(p, per_x[p], y_persona, per_w[p]) for p in personas if y_persona is not None
        ),
        arrows=tuple(arrows),
        footnote=footnote,
        footnote_y=footnote_y,
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/adapters/web/diagram/test_layout.py -v`
Expected: all pass. If a geometry test fails, check the port against the arithmetic in the spec ("Layout and rendering") before touching the test; the approved sample files in `docs/superpowers/specs/assets/diagram/` are the reference. Record any deviation in your report.

- [ ] **Step 5: Run the whole suite and lint**

Run: `rtk proxy uv run pytest -rs` then `uv run ruff check src tests` and `uv run mypy src`
Expected: all pass, 0 skipped, 0 warnings, ruff and mypy clean. Wrap long lines if ruff reports E501.

- [ ] **Step 6: Commit**

```bash
git add src/archimaid/adapters/web/diagram/layout.py tests/adapters/web/diagram/test_layout.py
git commit -m "feat(diagram): layout computation" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: SVG renderer and the approved-sample regression

**Files:**
- Create: `src/archimaid/adapters/web/diagram/svg.py`
- Modify: `src/archimaid/adapters/web/diagram/__init__.py`
- Test: `tests/adapters/web/diagram/test_svg.py`

**Interfaces:**
- Consumes: `Layout` and friends (Task 1), `escape`, `truncate` (Task 0), `compute_layout`, `DiagramModel`.
- Produces in `svg.py`: `render_svg(layout: Layout) -> str`, `Diagram(svg: str, width: int, height: int)` (frozen dataclass) and `draw(model: DiagramModel) -> Diagram` (`width`/`height` are the rounded values used in the SVG's `width`/`height` attributes).
- `diagram/__init__.py` exports `Diagram` and `draw` (and, from Task 3, `build_diagram`).
- Drawing order: arrow lines, then boxes (targets, sources, frame, cells or the "(no functions)" placeholder, persona figures), then labels, then the footnote.

- [ ] **Step 1: Write the failing test**

`tests/adapters/web/diagram/test_svg.py`:
```python
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from archimaid.adapters.web.diagram import Diagram, draw
from archimaid.adapters.web.diagram.layout import compute_layout
from archimaid.adapters.web.diagram.model import DiagramFunction, DiagramModel
from tests.adapters.web.diagram.samples import EMPTY, FULL, HOSTILE, SMALL

NS = "{http://www.w3.org/2000/svg}"
ASSETS = Path(__file__).resolve().parents[4] / "docs/superpowers/specs/assets/diagram"


def parse(svg: str) -> ET.Element:
    return ET.fromstring(svg.encode("utf-8"))


def drawable(root):
    keep = {"svg", "rect", "line", "circle", "path", "text", "polygon", "marker"}
    return [
        (el.tag, tuple(sorted(el.attrib.items())), (el.text or "").strip())
        for el in root.iter()
        if el.tag.removeprefix(NS) in keep
    ]


def test_draw_returns_well_formed_xml_with_matching_size():
    diagram = draw(FULL)
    assert isinstance(diagram, Diagram)
    root = parse(diagram.svg)
    assert root.tag == f"{NS}svg"
    assert root.get("width") == str(diagram.width) and root.get("height") == str(diagram.height)
    assert root.get("viewBox") == f"0 0 {diagram.width} {diagram.height}"
    assert root.get("role") == "img"
    assert diagram.svg.startswith('<?xml version="1.0" encoding="UTF-8"?>\n')


def test_counts_of_drawn_elements_match_the_layout():
    layout = compute_layout(FULL)
    root = parse(draw(FULL).svg)
    assert len(root.findall(f".//{NS}line")) == len(layout.arrows) == 14
    assert len(root.findall(f".//{NS}circle")) == len(layout.personas) == 3
    assert len(root.findall(f".//{NS}marker")) == 1
    assert root.findall(f".//{NS}line")[0].get("marker-end") == "url(#arrow)"
    assert root.find(f"{NS}title").text == "Interactions of Billing"


def test_every_flow_arrow_has_a_tooltip_and_persona_arrows_say_who_uses_what():
    root = parse(draw(FULL).svg)
    titles = [t.text for t in root.iter(f"{NS}title")]
    assert "Invoice — Source — posted nightly" in titles
    assert "Accountant uses Create invoice" in titles
    assert "Tax Authority Reporting Gateway Service" in titles  # full name on the box tooltip


def test_long_names_are_truncated_on_screen_but_kept_in_tooltips():
    root = parse(draw(FULL).svg)
    texts = [t.text for t in root.iter(f"{NS}text")]
    assert "Tax Authority Reporting Gat…" in texts
    assert "Tax Authority Reporting Gateway Service" not in texts


def test_hostile_text_is_escaped_and_the_document_stays_well_formed():
    # Review Focus test (1)
    diagram = draw(HOSTILE)
    root = parse(diagram.svg)  # raises if malformed
    assert "<script" not in diagram.svg and "<b>" not in diagram.svg
    assert "\x00" not in diagram.svg and "\x01" not in diagram.svg
    title = root.find(f"{NS}title").text
    assert title == 'Interactions of Evil <script>alert(1)</script> & "co"'
    assert not list(root.iter(f"{NS}script"))
    diagram.svg.encode("utf-8")


def test_lone_surrogates_and_controls_in_every_name_do_not_break_the_document():
    # Review Focus test (1)
    nasty = "x\ud800y\x00z\x1f"
    model = DiagramModel(
        application=nasty,
        functions=(DiagramFunction(nasty, nasty),),
    )
    diagram = draw(model)
    parse(diagram.svg)
    diagram.svg.encode("utf-8")


def test_empty_application_has_a_placeholder_cell_and_the_note():
    root = parse(draw(EMPTY).svg)
    texts = [t.text for t in root.iter(f"{NS}text")]
    assert "(no functions)" in texts
    assert "No data flows or personas yet." in texts
    assert not root.findall(f".//{NS}line")


def test_output_is_deterministic():
    assert draw(FULL).svg == draw(FULL).svg


@pytest.mark.parametrize("sample, name", [(FULL, "full"), (SMALL, "small")])
def test_reproduces_the_approved_sample_files(sample, name):
    """The geometry must equal the renders the user approved (docs/.../assets/diagram/)."""
    approved = parse((ASSETS / f"{name}.svg").read_text(encoding="utf-8"))
    ours = parse(draw(sample).svg)
    assert drawable(ours) == drawable(approved)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/adapters/web/diagram/test_svg.py -v`
Expected: collection error (`cannot import name 'draw'`).

- [ ] **Step 3: Implement `svg.py`**

`src/archimaid/adapters/web/diagram/svg.py`:
```python
"""Write the SVG for a Layout. Pure: every piece of user text goes through text.escape()."""

from __future__ import annotations

from dataclasses import dataclass

from archimaid.adapters.web.diagram.layout import (
    CELL_H,
    HEADER_H,
    MARGIN,
    Arrow,
    Figure,
    Layout,
    Rect,
    compute_layout,
)
from archimaid.adapters.web.diagram.model import DiagramModel
from archimaid.adapters.web.diagram.text import escape, truncate

BLUE = "#2b6cb0"
LIGHT_BLUE = "#3f83c9"


@dataclass(frozen=True)
class Diagram:
    svg: str
    width: int
    height: int


def _arrow(a: Arrow) -> str:
    return (
        f"<g><title>{escape(a.title)}</title>"
        f'<line x1="{a.x1:.1f}" y1="{a.y1:.1f}" x2="{a.x2:.1f}" y2="{a.y2:.1f}" '
        f'stroke="#000" stroke-width="1.5" marker-end="url(#arrow)"/></g>'
    )


def _app_box(r: Rect) -> str:
    return (
        f"<g><title>{escape(r.text)}</title>"
        f'<rect x="{r.x:.1f}" y="{r.y:.1f}" width="{r.w:.1f}" height="{r.h}" rx="4" fill="{BLUE}"/>'
        f'<text x="{r.x + r.w / 2:.1f}" y="{r.y + 27:.1f}" text-anchor="middle" fill="#fff" '
        f'font-size="13">{escape(truncate(r.text, 28))}</text></g>'
    )


def _frame(frame: Rect) -> str:
    return (
        f"<g><title>{escape(frame.text)}</title>"
        f'<rect x="{frame.x:.1f}" y="{frame.y:.1f}" width="{frame.w:.1f}" height="{frame.h}" '
        f'rx="4" fill="{BLUE}"/>'
        f'<text x="{frame.cx:.1f}" y="{frame.y + 24:.1f}" text-anchor="middle" fill="#fff" '
        f'font-size="15" font-weight="bold">{escape(truncate(frame.text, 40))}</text></g>'
    )


def _cell(c: Rect) -> str:
    return (
        f"<g><title>{escape(c.text)}</title>"
        f'<rect x="{c.x:.1f}" y="{c.y:.1f}" width="{c.w:.1f}" height="{CELL_H}" '
        f'fill="{LIGHT_BLUE}"/>'
        f'<text x="{c.x + c.w / 2:.1f}" y="{c.y + CELL_H / 2 + 4:.1f}" text-anchor="middle" '
        f'fill="#fff" font-size="13">{escape(truncate(c.text, 24))}</text></g>'
    )


def _figure(p: Figure) -> str:
    fx, top = p.cx, p.y
    return (
        f"<g><title>{escape(p.name)}</title>"
        f'<circle cx="{fx:.1f}" cy="{top + 10:.1f}" r="8" fill="#fff" stroke="#000" '
        f'stroke-width="1.5"/>'
        f'<path d="M{fx:.1f} {top + 18:.1f} V{top + 42:.1f} '
        f"M{fx - 13:.1f} {top + 28:.1f} H{fx + 13:.1f} "
        f"M{fx:.1f} {top + 42:.1f} L{fx - 10:.1f} {top + 58:.1f} "
        f'M{fx:.1f} {top + 42:.1f} L{fx + 10:.1f} {top + 58:.1f}" '
        f'fill="none" stroke="#000" stroke-width="1.5" stroke-linecap="round" '
        f'stroke-linejoin="round"/>'
        f'<text x="{fx:.1f}" y="{top + 74:.1f}" text-anchor="middle" fill="#000" font-size="13">'
        f"{escape(truncate(p.name, 24))}</text></g>"
    )


def render_svg(layout: Layout) -> str:
    lines = [_arrow(a) for a in layout.arrows]

    boxes = [_app_box(r) for r in layout.targets]
    boxes += [_app_box(r) for r in layout.sources]
    boxes.append(_frame(layout.frame))
    if layout.cells:
        boxes += [_cell(c) for c in layout.cells]
    else:
        boxes.append(
            f'<text x="{layout.frame.cx:.1f}" y="{layout.frame.y + HEADER_H + CELL_H / 2 + 4:.1f}" '
            f'text-anchor="middle" fill="#fff" font-size="13" font-style="italic">'
            f"(no functions)</text>"
        )
    boxes += [_figure(p) for p in layout.personas]

    labels = []
    for a in layout.arrows:
        if a.label is not None:
            lb = a.label
            labels.append(
                f'<rect x="{lb.x:.1f}" y="{lb.y - 8:.1f}" width="{lb.w:.1f}" height="16" '
                f'fill="#fff" fill-opacity="0.92"/>'
                f'<text x="{lb.x + 4:.1f}" y="{lb.y + 4:.1f}" font-size="11" fill="#000">'
                f"{escape(lb.text)}</text>"
            )

    footnote = ""
    if layout.footnote is not None and layout.footnote_y is not None:
        footnote = (
            f'<text x="{MARGIN}" y="{layout.footnote_y:.1f}" font-size="11" fill="#444">'
            f"{escape(layout.footnote)}</text>"
        )

    width, height = f"{layout.width:.0f}", f"{layout.height:.0f}"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" font-family="Helvetica, Arial, sans-serif">'
        f"<title>Interactions of {escape(layout.application)}</title>"
        '<defs><marker id="arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" '
        'orient="auto" markerUnits="userSpaceOnUse"><polygon points="0,0 10,4 0,8" fill="#000"/>'
        "</marker></defs>"
        '<rect width="100%" height="100%" fill="#fff"/>'
        + "".join(lines)
        + "".join(boxes)
        + "".join(labels)
        + footnote
        + "</svg>\n"
    )


def draw(model: DiagramModel) -> Diagram:
    layout = compute_layout(model)
    return Diagram(render_svg(layout), round(layout.width), round(layout.height))
```

`src/archimaid/adapters/web/diagram/__init__.py`:
```python
from archimaid.adapters.web.diagram.svg import Diagram, draw

__all__ = ["Diagram", "draw"]
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/adapters/web/diagram/test_svg.py -v`
Expected: all pass. `test_reproduces_the_approved_sample_files` is the key one: if it fails, the port of the geometry differs from the approved prototype. Compare the first differing element (tag, attributes, text) and fix the code in `layout.py`/`svg.py`; never edit the approved sample files or weaken the test. Note the approved files were produced with tooltip texts that are not compared (`title` elements are ignored).

- [ ] **Step 5: Visual check against the approved render**

Run (needs `rsvg-convert` and ImageMagick `compare`; skip this step and say so if they are missing):
```bash
mkdir -p /tmp/diagram_check && uv run python - <<'EOF'
from archimaid.adapters.web.diagram import draw
from tests.adapters.web.diagram.samples import FULL
open("/tmp/diagram_check/full.svg", "w", encoding="utf-8").write(draw(FULL).svg)
EOF
rsvg-convert -z 1 -o /tmp/diagram_check/full.png /tmp/diagram_check/full.svg
compare -metric AE /tmp/diagram_check/full.png docs/superpowers/specs/assets/diagram/full.png null: ; echo " differing pixels"
```
Expected: `0 differing pixels`. Report the number you see.

- [ ] **Step 6: Run the whole suite and lint**

Run: `rtk proxy uv run pytest -rs`, `uv run ruff check src tests`, `uv run mypy src`
Expected: all pass, 0 skipped, 0 warnings, clean. If ruff reports E501 (lines over 100 characters, likely in the long f-strings of `svg.py`), wrap them by splitting the string literals; the produced SVG text must not change, which `test_reproduces_the_approved_sample_files` verifies.

- [ ] **Step 7: Commit**

```bash
git add src/archimaid/adapters/web/diagram tests/adapters/web/diagram/test_svg.py
git commit -m "feat(diagram): SVG renderer, pinned to the approved sample renders" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Builder (services to model)

**Files:**
- Create: `src/archimaid/adapters/web/diagram/builder.py`
- Modify: `src/archimaid/adapters/web/diagram/__init__.py`
- Test: `tests/adapters/web/diagram/test_builder.py`

**Interfaces:**
- Consumes: `Services` (fields `applications`, `functions`, `personas`, `data_flows`, `data_types`, `reference`), the model classes (Task 0), `NotFound`.
- Produces: `build_diagram(services: Services, application_id: UUID) -> DiagramModel`, exported from `diagram/__init__.py`.
- Rules (from the spec): functions sorted by (name case-insensitive, id) with the persona's name; targets from `data_flows.list(source_application_id=id)` grouped by the target application, sources from `data_flows.list(target_application_id=id)` grouped by the source application; neighbours sorted by (name case-insensitive, id), flows sorted by (data type case-insensitive, usage mode, explanation); a flow whose source and target are both this application is counted in `self_flows` and not drawn; the usage mode shows as its catalog label (the code if unknown); an unknown application raises `NotFound`.

- [ ] **Step 1: Write the failing test**

`tests/adapters/web/diagram/test_builder.py`:
```python
from uuid import uuid4

import pytest

from archimaid.adapters.web.diagram import build_diagram
from archimaid.application.services import build_services
from archimaid.domain.errors import NotFound
from tests.fakes import default_catalog, fake_repositories


@pytest.fixture
def services():
    return build_services(fake_repositories(), default_catalog())


class World:
    """Small helper to build a scenario through the real services."""

    def __init__(self, services):
        self.s = services
        self.team = services.teams.create({"name": "Team"})

    def app(self, name):
        return self.s.applications.create({"team_id": self.team.id, "name": name})

    def dtype(self, app, name):
        return self.s.data_types.create({"application_id": app.id, "name": name})

    def flow(self, source, target, dtype, **extra):
        return self.s.data_flows.create(
            {
                "source_application_id": source.id,
                "target_application_id": target.id,
                "data_type_id": dtype.id,
                **extra,
            }
        )

    def function(self, app, name, persona=None):
        data = {"application_id": app.id, "name": name}
        if persona is not None:
            data["persona_id"] = persona.id
        return self.s.functions.create(data)


@pytest.fixture
def world(services):
    return World(services)


def test_unknown_application_is_not_found(services):
    with pytest.raises(NotFound):
        build_diagram(services, uuid4())


def test_an_application_with_nothing_gives_an_empty_model(services, world):
    app = world.app("Lonely")
    model = build_diagram(services, app.id)
    assert model.application == "Lonely"
    assert model.functions == () and model.targets == () and model.sources == ()
    assert model.self_flows == 0


def test_functions_are_sorted_and_carry_their_persona_name(services, world):
    app = world.app("Billing")
    accountant = services.personas.create({"name": "Accountant"})
    world.function(app, "send reminder", accountant)
    world.function(app, "Create invoice", accountant)
    world.function(app, "Archive")
    model = build_diagram(services, app.id)
    assert [(f.name, f.persona) for f in model.functions] == [
        ("Archive", None),
        ("Create invoice", "Accountant"),
        ("send reminder", "Accountant"),
    ]


def test_outgoing_flows_are_targets_and_incoming_flows_are_sources(services, world):
    billing, ledger, crm = world.app("Billing"), world.app("Ledger"), world.app("CRM")
    invoice = world.dtype(billing, "Invoice")
    customer = world.dtype(crm, "Customer")
    world.flow(billing, ledger, invoice, usage_mode="SOURCE", usage_explanation="nightly")
    world.flow(crm, billing, customer)
    model = build_diagram(services, billing.id)
    assert [n.name for n in model.targets] == ["Ledger"]
    assert [n.name for n in model.sources] == ["CRM"]
    flow = model.targets[0].flows[0]
    assert (flow.data_type, flow.usage_mode, flow.explanation) == ("Invoice", "Source", "nightly")
    incoming = model.sources[0].flows[0]
    assert (incoming.data_type, incoming.usage_mode, incoming.explanation) == (
        "Customer",
        None,
        None,
    )


def test_flows_to_the_same_application_are_grouped_and_sorted(services, world):
    billing, ledger = world.app("Billing"), world.app("Ledger")
    for name in ("payment", "Invoice"):
        world.flow(billing, ledger, world.dtype(billing, name))
    model = build_diagram(services, billing.id)
    assert len(model.targets) == 1
    assert [f.data_type for f in model.targets[0].flows] == ["Invoice", "payment"]


def test_neighbours_are_sorted_case_insensitively_and_equal_names_stay_separate(services, world):
    billing = world.app("Billing")
    dtype = world.dtype(billing, "T")
    for name in ("zeta", "Alpha", "Alpha"):
        world.flow(billing, world.app(name), dtype)
    model = build_diagram(services, billing.id)
    assert [n.name for n in model.targets] == ["Alpha", "Alpha", "zeta"]


def test_a_neighbour_in_both_directions_appears_in_both_lists(services, world):
    # Review Focus test (2)
    a, b = world.app("A"), world.app("B")
    world.flow(a, b, world.dtype(a, "x"))
    world.flow(b, a, world.dtype(b, "y"))
    model = build_diagram(services, a.id)
    assert [n.name for n in model.targets] == ["B"] and [n.name for n in model.sources] == ["B"]


def test_self_flows_are_counted_and_not_drawn(services, world):
    # Review Focus test (2)
    a, b = world.app("A"), world.app("B")
    dtype = world.dtype(a, "x")
    world.flow(a, a, dtype)
    world.flow(a, a, dtype)
    world.flow(a, b, dtype)
    model = build_diagram(services, a.id)
    assert model.self_flows == 2
    assert [n.name for n in model.targets] == ["B"] and model.sources == ()


def test_only_self_flows_leave_empty_rows_and_a_count(services, world):
    a = world.app("A")
    world.flow(a, a, world.dtype(a, "x"))
    model = build_diagram(services, a.id)
    assert model.targets == () and model.sources == () and model.self_flows == 1


def test_the_usage_mode_shows_its_catalog_label_not_its_code(services, world):
    billing, ledger = world.app("Billing"), world.app("Ledger")
    flow = world.flow(billing, ledger, world.dtype(billing, "T"), usage_mode="PROXY")
    model = build_diagram(services, billing.id)
    assert flow.usage_mode == "PROXY"
    assert model.targets[0].flows[0].usage_mode == "Proxy"


def test_flows_of_other_applications_are_not_included(services, world):
    a, b, c = world.app("A"), world.app("B"), world.app("C")
    world.flow(b, c, world.dtype(b, "x"))
    model = build_diagram(services, a.id)
    assert model.targets == () and model.sources == ()


def test_a_persona_shared_by_two_functions_is_named_on_both(services, world):
    app = world.app("A")
    pat = services.personas.create({"name": "Pat"})
    world.function(app, "f1", pat)
    world.function(app, "f2", pat)
    model = build_diagram(services, app.id)
    assert [f.persona for f in model.functions] == ["Pat", "Pat"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/adapters/web/diagram/test_builder.py -v`
Expected: collection error (`cannot import name 'build_diagram'`).

- [ ] **Step 3: Implement**

`src/archimaid/adapters/web/diagram/builder.py`:
```python
from __future__ import annotations

from typing import Any
from uuid import UUID

from archimaid.adapters.web.diagram.model import (
    DiagramFlow,
    DiagramFunction,
    DiagramModel,
    DiagramNeighbour,
)
from archimaid.application.services import Services


def build_diagram(services: Services, application_id: UUID) -> DiagramModel:
    """Collect everything the diagram shows through the application services.

    Raises NotFound if the application does not exist.
    """
    application = services.applications.get(application_id)

    app_names: dict[UUID, str] = {}
    type_names: dict[UUID, str] = {}
    persona_names: dict[UUID, str] = {}

    def app_name(app_id: UUID) -> str:
        if app_id not in app_names:
            app_names[app_id] = services.applications.get(app_id).name
        return app_names[app_id]

    def type_name(type_id: UUID) -> str:
        if type_id not in type_names:
            type_names[type_id] = services.data_types.get(type_id).name
        return type_names[type_id]

    def persona_name(persona_id: UUID) -> str:
        if persona_id not in persona_names:
            persona_names[persona_id] = services.personas.get(persona_id).name
        return persona_names[persona_id]

    mode_labels = {v.code: v.label for v in services.reference.list("usage_mode")}

    functions = sorted(
        services.functions.list(application_id=application_id),
        key=lambda f: (f.name.casefold(), str(f.id)),
    )
    diagram_functions = tuple(
        DiagramFunction(f.name, persona_name(f.persona_id) if f.persona_id else None)
        for f in functions
    )

    def group(flows: list[Any], other_attr: str) -> tuple[DiagramNeighbour, ...]:
        by_app: dict[UUID, list[DiagramFlow]] = {}
        for flow in flows:
            mode = mode_labels.get(flow.usage_mode, flow.usage_mode) if flow.usage_mode else None
            by_app.setdefault(getattr(flow, other_attr), []).append(
                DiagramFlow(type_name(flow.data_type_id), mode, flow.usage_explanation)
            )
        ordered = sorted(
            by_app.items(), key=lambda item: (app_name(item[0]).casefold(), str(item[0]))
        )
        return tuple(
            DiagramNeighbour(
                app_name(app_id),
                tuple(
                    sorted(
                        grouped,
                        key=lambda f: (
                            f.data_type.casefold(),
                            f.usage_mode or "",
                            f.explanation or "",
                        ),
                    )
                ),
            )
            for app_id, grouped in ordered
        )

    outgoing = services.data_flows.list(source_application_id=application_id)
    incoming = services.data_flows.list(target_application_id=application_id)
    self_flows = sum(1 for f in outgoing if f.target_application_id == application_id)

    return DiagramModel(
        application=application.name,
        functions=diagram_functions,
        targets=group(
            [f for f in outgoing if f.target_application_id != application_id],
            "target_application_id",
        ),
        sources=group(
            [f for f in incoming if f.source_application_id != application_id],
            "source_application_id",
        ),
        self_flows=self_flows,
    )
```

`src/archimaid/adapters/web/diagram/__init__.py`:
```python
from archimaid.adapters.web.diagram.builder import build_diagram
from archimaid.adapters.web.diagram.svg import Diagram, draw

__all__ = ["Diagram", "build_diagram", "draw"]
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/adapters/web/diagram -v`
Expected: all pass.

- [ ] **Step 5: Run the whole suite and lint**

Run: `rtk proxy uv run pytest -rs`, `uv run ruff check src tests`, `uv run mypy src`
Expected: all pass, 0 skipped, 0 warnings, clean.

- [ ] **Step 6: Commit**

```bash
git add src/archimaid/adapters/web/diagram tests/adapters/web/diagram/test_builder.py
git commit -m "feat(diagram): builder from services to diagram model" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Web integration (route, tab, template)

**Files:**
- Modify: `src/archimaid/adapters/web/resources.py` (`TABS`), `src/archimaid/adapters/web/pages.py`, `src/archimaid/adapters/web/static/app.css`
- Create: `src/archimaid/adapters/web/templates/tabs/diagram.html`
- Test: `tests/adapters/web/diagram/test_diagram_routes.py`

**Interfaces:**
- Consumes: `build_diagram`, `draw`, `Diagram`, `filename_slug`, the existing `_fetch`, `tab_context`, `render`, `UiError`.
- Produces: `("diagram", "Diagram")` as the last entry of `TABS`; `GET /ui/applications/{application_id}/diagram.svg[?download=1]`; the `diagram` key (a `Diagram`) in the diagram tab's template context; `tabs/diagram.html`.

- [ ] **Step 1: Write the failing test**

`tests/adapters/web/diagram/test_diagram_routes.py`:
```python
import re
import xml.etree.ElementTree as ET
from uuid import uuid4

from archimaid.adapters.web import resources as r

NS = "{http://www.w3.org/2000/svg}"


def make_app(services, name="Billing", **extra):
    team = services.teams.create({"name": "Team"})
    return services.applications.create({"team_id": team.id, "name": name, **extra})


def scenario(services):
    team = services.teams.create({"name": "T"})
    billing = services.applications.create({"team_id": team.id, "name": "Billing"})
    ledger = services.applications.create({"team_id": team.id, "name": "Ledger"})
    crm = services.applications.create({"team_id": team.id, "name": "CRM"})
    invoice = services.data_types.create({"application_id": billing.id, "name": "Invoice"})
    customer = services.data_types.create({"application_id": crm.id, "name": "Customer"})
    persona = services.personas.create({"name": "Accountant"})
    services.functions.create(
        {"application_id": billing.id, "name": "Create invoice", "persona_id": persona.id}
    )
    for source, target, dtype in ((billing, ledger, invoice), (crm, billing, customer)):
        services.data_flows.create(
            {
                "source_application_id": source.id,
                "target_application_id": target.id,
                "data_type_id": dtype.id,
                "usage_mode": "SOURCE",
            }
        )
    return billing


def test_svg_route_returns_a_standalone_svg_with_security_headers(client, services):
    app = scenario(services)
    response = client.get(f"/ui/applications/{app.id}/diagram.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert "utf-8" in response.headers["content-type"].lower()
    assert response.headers["content-security-policy"] == (
        "default-src 'none'; style-src 'unsafe-inline'"
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
    assert "content-disposition" not in response.headers
    root = ET.fromstring(response.content)
    assert root.tag == f"{NS}svg"
    assert len(root.findall(f".//{NS}line")) == 3  # 2 flows + 1 persona arrow
    assert "Interactions of Billing" in response.text


def test_download_sets_an_attachment_with_a_safe_filename(client, services):
    # Review Focus test (4)
    app = make_app(services, name='Billing / "Core" <v2>')
    response = client.get(f"/ui/applications/{app.id}/diagram.svg?download=1")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        'attachment; filename="billing-core-v2-interactions.svg"'
    )


def test_hostile_names_cannot_inject_headers_or_paths(client, services):
    # Review Focus test (4)
    for name, expected in (
        ("../../etc/passwd", "etc-passwd"),
        ("日本語", "application"),
        ("a\r\nX-Evil: 1", "a-x-evil-1"),
        ('x"; filename="evil.svg', "x-filename-evil-svg"),
    ):
        app = make_app(services, name=name)
        response = client.get(f"/ui/applications/{app.id}/diagram.svg?download=1")
        assert response.status_code == 200
        disposition = response.headers["content-disposition"]
        assert disposition == f'attachment; filename="{expected}-interactions.svg"'
        assert "x-evil" not in {h.lower() for h in response.headers}


def test_hostile_application_name_gives_a_well_formed_svg(client, services):
    # Review Focus test (1)
    app = make_app(services, name='Evil <script>alert(1)</script> & "co"')
    response = client.get(f"/ui/applications/{app.id}/diagram.svg")
    assert response.status_code == 200
    assert "<script" not in response.text
    ET.fromstring(response.content)


def test_unknown_and_malformed_ids_are_error_pages_not_500s(client):
    # Review Focus test (5)
    missing = client.get(f"/ui/applications/{uuid4()}/diagram.svg")
    assert missing.status_code == 404 and "<html" in missing.text
    malformed = client.get("/ui/applications/not-a-uuid/diagram.svg")
    assert malformed.status_code == 422 and "<html" in malformed.text
    bad_flag = client.get(f"/ui/applications/{uuid4()}/diagram.svg?download=maybe")
    assert bad_flag.status_code in (404, 422)


def test_diagram_is_the_last_tab():
    assert r.TABS[-1] == ("diagram", "Diagram")
    assert [key for key, _ in r.TABS] == [
        "details", "functions", "data-types", "technologies", "data-flows", "diagram",
    ]


def test_diagram_tab_embeds_the_svg_with_its_real_size(client, services):
    # Review Focus test (6)
    app = scenario(services)
    fragment = client.get(f"/ui/applications/{app.id}/tabs/diagram")
    assert fragment.status_code == 200 and "<html" not in fragment.text
    html = fragment.text
    assert '<object type="image/svg+xml"' in html
    match = re.search(
        rf'data="/ui/applications/{app.id}/diagram.svg" width="(\d+)" height="(\d+)"', html
    )
    assert match, html
    svg_root = ET.fromstring(client.get(f"/ui/applications/{app.id}/diagram.svg").content)
    assert (svg_root.get("width"), svg_root.get("height")) == match.groups()
    assert f'href="/ui/applications/{app.id}/diagram.svg?download=1"' in html
    assert "Download SVG" in html
    assert 'aria-current="page"' in html


def test_diagram_tab_is_reachable_as_a_page_and_listed_in_the_tab_bar(client, services):
    app = make_app(services)
    page = client.get(f"/ui/applications/{app.id}?tab=diagram")
    assert page.status_code == 200 and "<html" in page.text
    assert f'hx-get="/ui/applications/{app.id}/tabs/diagram"' in page.text
    assert f'hx-push-url="/ui/applications/{app.id}?tab=diagram"' in page.text
    current = page.text.index('aria-current="page"')
    assert "tabs/diagram" in page.text[page.text.rfind("<a", 0, current) : current]


def test_diagram_tab_title_text_is_escaped(client, services):
    # Review Focus test (1)
    app = make_app(services, name='<img src=x onerror=alert(1)> "q"')
    html = client.get(f"/ui/applications/{app.id}/tabs/diagram").text
    assert "<img src=x" not in html and "&lt;img src=x" in html


def test_an_application_with_no_data_still_renders_a_diagram(client, services):
    # Review Focus test (2)
    app = make_app(services, name="Lonely")
    response = client.get(f"/ui/applications/{app.id}/diagram.svg")
    assert response.status_code == 200
    assert "No data flows or personas yet." in response.text
    assert client.get(f"/ui/applications/{app.id}/tabs/diagram").status_code == 200
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/adapters/web/diagram/test_diagram_routes.py -v`
Expected: failures (404 on `/diagram.svg`, unknown tab, `TABS` has no diagram entry).

- [ ] **Step 3: Add the tab key and the CSS**

In `src/archimaid/adapters/web/resources.py`, extend `TABS`:
```python
TABS = (
    ("details", "Details"),
    ("functions", "Functions"),
    ("data-types", "Data types"),
    ("technologies", "Technologies"),
    ("data-flows", "Data flows"),
    ("diagram", "Diagram"),
)
```
Append to `src/archimaid/adapters/web/static/app.css`:
```css
.diagram { overflow-x: auto; margin-top: 1rem; }
.diagram object { display: block; max-width: none; }
```

- [ ] **Step 4: Add the route and the tab context in `pages.py`**

Add these imports at the top of `src/archimaid/adapters/web/pages.py` (merge `Response` into the existing `from fastapi import ...` line):
```python
from fastapi import Response

from archimaid.adapters.web.diagram import build_diagram, draw
from archimaid.adapters.web.diagram.files import filename_slug
```
In `tab_context`, add this branch after the `data-flows` branch (before `return context`):
```python
        elif tab == "diagram":
            context["diagram"] = draw(build_diagram(services, app.id))
```
Add this route inside `pages_router`, before `return router`:
```python
    @router.get("/ui/applications/{application_id}/diagram.svg")
    def application_diagram(application_id: UUID, download: int = 0):
        app = _fetch(services.applications, application_id)
        diagram = draw(build_diagram(services, application_id))
        headers = {
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        }
        if download:
            headers["Content-Disposition"] = (
                f'attachment; filename="{filename_slug(app.name)}-interactions.svg"'
            )
        return Response(
            content=diagram.svg,
            media_type="image/svg+xml; charset=utf-8",
            headers=headers,
        )
```

- [ ] **Step 5: Add the tab template**

`src/archimaid/adapters/web/templates/tabs/diagram.html`:
```html
<p>
  <small>Hover a box or an arrow for details.</small>
  <a href="/ui/applications/{{ app.id }}/diagram.svg?download=1" download>Download SVG</a>
</p>
<div class="diagram">
  <object type="image/svg+xml" data="/ui/applications/{{ app.id }}/diagram.svg" width="{{ diagram.width }}" height="{{ diagram.height }}" aria-label="Interaction diagram of {{ app.name }}">
    <a href="/ui/applications/{{ app.id }}/diagram.svg">Open the diagram</a>
  </object>
</div>
```

- [ ] **Step 6: Run to verify it passes**

Run: `rtk proxy uv run pytest tests/adapters/web -v -rs`
Expected: all pass, 0 skipped, no warnings (including every existing web test).

- [ ] **Step 7: Run the whole suite and lint**

Run: `rtk proxy uv run pytest -rs`, `uv run ruff check src tests`, `uv run mypy src`
Expected: all pass, 0 skipped, 0 warnings, clean.

- [ ] **Step 8: Commit**

```bash
git add src/archimaid/adapters/web tests/adapters/web/diagram/test_diagram_routes.py
git commit -m "feat(web): diagram tab and downloadable SVG for an application" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: End-to-end test, packaging, docs, lint and visual check

**Files:**
- Create: `tests/test_diagram_end_to_end_postgres.py`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: everything above plus `build_repositories`, `PostgresReferenceCatalog`, `build_services`, `create_app`, and the `engine` fixture.

- [ ] **Step 1: Write the end-to-end test**

`tests/test_diagram_end_to_end_postgres.py`:
```python
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from archimaid.adapters.api.app import create_app
from archimaid.adapters.persistence.catalog import PostgresReferenceCatalog
from archimaid.adapters.persistence.repository import build_repositories
from archimaid.application.services import build_services

pytestmark = pytest.mark.postgres
NS = "{http://www.w3.org/2000/svg}"


@pytest.fixture
def services(engine):
    return build_services(build_repositories(engine), PostgresReferenceCatalog(engine))


@pytest.fixture
def client(services):
    return TestClient(create_app(services))


def test_diagram_over_real_postgres(client, services):
    team = services.teams.create({"name": "Payments"})

    def app(name):
        return services.applications.create({"team_id": team.id, "name": name})

    billing, ledger, crm = app("Billing"), app("Ledger"), app("CRM")
    invoice = services.data_types.create({"application_id": billing.id, "name": "Invoice"})
    customer = services.data_types.create({"application_id": crm.id, "name": "Customer"})
    accountant = services.personas.create({"name": "Accountant"})
    for name in ("Create invoice", "Send reminder"):
        services.functions.create(
            {"application_id": billing.id, "name": name, "persona_id": accountant.id}
        )
    for source, target, dtype, mode in (
        (billing, ledger, invoice, "SOURCE"),
        (crm, billing, customer, "PROXY"),
        (billing, billing, invoice, None),  # a self-flow: counted, not drawn
    ):
        services.data_flows.create(
            {
                "source_application_id": source.id,
                "target_application_id": target.id,
                "data_type_id": dtype.id,
                "usage_mode": mode,
            }
        )

    response = client.get(f"/ui/applications/{billing.id}/diagram.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    root = ET.fromstring(response.content)
    lines = root.findall(f".//{NS}line")
    assert len(lines) == 2 + 2  # two flows (self-flow omitted) + two persona arrows
    titles = [t.text for t in root.iter(f"{NS}title")]
    assert "Invoice — Source" in titles and "Customer — Proxy" in titles
    texts = [t.text for t in root.iter(f"{NS}text")]
    assert "1 self-referencing data flow(s) not drawn." in texts
    assert {"Billing", "Ledger", "CRM", "Accountant"} <= set(texts)
    assert len(root.findall(f".//{NS}circle")) == 1  # one persona drawn once

    tab = client.get(f"/ui/applications/{billing.id}/tabs/diagram")
    assert tab.status_code == 200 and "<object" in tab.text
    download = client.get(f"/ui/applications/{billing.id}/diagram.svg?download=1")
    assert download.headers["content-disposition"] == (
        'attachment; filename="billing-interactions.svg"'
    )

    # an application whose name is full of markup characters still renders a valid SVG
    odd = services.applications.create({"team_id": team.id, "name": 'Odd <name> & "quotes"'})
    ET.fromstring(client.get(f"/ui/applications/{odd.id}/diagram.svg").content)
```

- [ ] **Step 2: Run it**

Run: `rtk proxy uv run pytest tests/test_diagram_end_to_end_postgres.py -v -rs`
Expected: PASS (not skipped). If it fails, the cause is a defect in an earlier task's code: diagnose it, fix the minimal code, and record it prominently in your report (file, line, reason). Do not weaken the test.

- [ ] **Step 3: Check packaging**

Run:
```bash
uv build --wheel -o /tmp/archimaid-diagram-wheel
unzip -l /tmp/archimaid-diagram-wheel/*.whl | grep -E "web/(diagram/|templates/tabs/diagram)" | awk '{print $4}' | sort
rm -rf /tmp/archimaid-diagram-wheel
```
Expected: the list includes every file under `adapters/web/diagram/` (`__init__.py`, `builder.py`, `files.py`, `layout.py`, `model.py`, `svg.py`, `text.py`) and `templates/tabs/diagram.html`.

- [ ] **Step 4: Lint and type-check**

Run: `uv run ruff check src tests && uv run mypy src`
Expected: clean. Fix findings in the code without loosening the config.

- [ ] **Step 5: Update `CLAUDE.md`**

In the Architecture list, add this bullet after the `adapters/web/` bullet:
```
- `adapters/web/diagram/`: the SVG interaction diagram of an application (the "Diagram" tab and `GET /ui/applications/{id}/diagram.svg`, `?download=1` for a file). `builder.py` is the only part that calls services; `layout.py` computes coordinates and `svg.py` writes the markup, both pure. All user text goes through `text.escape()`; geometry is pinned to the approved samples in `docs/superpowers/specs/assets/diagram/` by `tests/adapters/web/diagram/test_svg.py`.
```

- [ ] **Step 6: Final verification and visual check**

Run: `rtk proxy uv run pytest -rs`
Expected: all tests pass, 0 skipped, 0 warnings. Run `podman ps -a --format '{{.Names}}'` and confirm only `archimaid-dev-db` is listed.

Then render the real code's output for a realistic scenario and look at it (needs `rsvg-convert`; say so if missing):
```bash
mkdir -p /tmp/diagram_check && uv run python - <<'EOF'
from archimaid.adapters.web.diagram import draw
from tests.adapters.web.diagram.samples import EMPTY, FULL, HOSTILE, SMALL
for name, model in (("full", FULL), ("small", SMALL), ("empty", EMPTY), ("hostile", HOSTILE)):
    open(f"/tmp/diagram_check/{name}.svg", "w", encoding="utf-8").write(draw(model).svg)
EOF
for n in full small empty hostile; do rsvg-convert -z 1 -o /tmp/diagram_check/$n.png /tmp/diagram_check/$n.svg; done
compare -metric AE /tmp/diagram_check/full.png docs/superpowers/specs/assets/diagram/full.png null: ; echo " differing pixels (full vs approved)"
```
Expected: `0 differing pixels (full vs approved)`; the four PNGs exist. Report the numbers. Do not leave anything running.

- [ ] **Step 7: Commit**

```bash
git add tests/test_diagram_end_to_end_postgres.py CLAUDE.md
git commit -m "feat(diagram): end-to-end test on Postgres, packaging check and docs" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-review against the spec

- **Decisions 1-7** (pure-Python renderer; three-part package in the web adapter; flow direction to rows; stick-figure personas in their own row with source arrows routed around them; labelled arrows with hover details and parallel offsets; Diagram tab plus download; `<object>` embedding with explicit size): Tasks 0-4.
- **Data model and builder rules** (sorting, grouping, self-flow count, both-direction neighbours, usage-mode labels, `NotFound`): Tasks 0 and 3.
- **Layout and rendering** (constants, box sizes and colors, rows and gaps, persona placement, arrow attachment, label placement and staggering, drawing order, footnotes, document structure, escaping, determinism): Tasks 1 and 2, with the geometry tied to the approved samples by `test_reproduces_the_approved_sample_files` and the pixel comparison in Task 2 step 5 and Task 5 step 6.
- **Web integration** (route headers, download filename slug, tab, `<object>` with the real size, 404/422 behavior): Task 4, with Review Focus 4, 5 and 6 pinned.
- **Testing section** (layout, builder, routes, end-to-end, manual visual check): Tasks 1-5.
- **Gaps recorded:** "No data flows or personas yet." appears in `empty.svg` only through the tests (the approved `empty.svg` predates it, so it is not compared); the persona identity in the model is the persona's name (two personas with the same name draw as one, as the spec notes); there is no JSON API endpoint (out of scope).
