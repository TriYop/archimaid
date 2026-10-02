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
