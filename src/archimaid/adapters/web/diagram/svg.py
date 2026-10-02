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
