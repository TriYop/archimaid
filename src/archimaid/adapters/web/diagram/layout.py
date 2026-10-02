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
