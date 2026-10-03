import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from archimaid.adapters.web.diagram import Diagram, draw
from archimaid.adapters.web.diagram.layout import compute_layout
from archimaid.adapters.web.diagram.model import (
    DiagramFlow,
    DiagramFunction,
    DiagramModel,
    DiagramNeighbour,
)
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


@pytest.mark.parametrize(
    "nasty",
    [
        "x\ud800y\x00z\x1f",
        "<script>alert(1)</script>&\"'",
        "]]><!-- -->",
        "‮ rtl ￾￿",
        "😀 日本語",
    ],
)
def test_hostile_text_in_every_field_still_gives_a_safe_document(nasty):
    model = DiagramModel(
        application=nasty,
        functions=(DiagramFunction(nasty, nasty),),
        targets=(DiagramNeighbour(nasty, (DiagramFlow(nasty, nasty, nasty),)),),
        sources=(DiagramNeighbour(nasty, (DiagramFlow(nasty, nasty, nasty),)),),
    )
    svg = draw(model).svg
    parse(svg)
    svg.encode("utf-8")
    for marker in ("<script", "<!--", "]]>"):
        assert marker not in svg
