import re
import xml.etree.ElementTree as ET
from uuid import uuid4

import pytest

from archimaid.adapters.web import resources as r
from archimaid.domain.errors import NotFound

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


def test_diagram_tab_centres_a_wide_diagram_on_load(client, services):
    app = scenario(services)
    html = client.get(f"/ui/applications/{app.id}/tabs/diagram").text
    assert (
        'onload="var d=this.parentElement; d.scrollLeft=(d.scrollWidth-d.clientWidth)/2"' in html
    )
    assert re.search(
        rf'data="/ui/applications/{app.id}/diagram.svg" width="(\d+)" height="(\d+)"', html
    )


@pytest.mark.parametrize(
    ("query", "attachment", "status"),
    [
        ("?download=1", True, 200),
        ("?download=true", True, 200),
        ("?download=0", False, 200),
        ("?download=false", False, 200),
        ("", False, 200),
        ("?download=2", False, 422),
        ("?download=maybe", False, 422),
    ],
)
def test_download_flag_is_a_strict_boolean(client, services, query, attachment, status):
    app = make_app(services)
    response = client.get(f"/ui/applications/{app.id}/diagram.svg{query}")
    assert response.status_code == status
    if status == 200:
        assert ("content-disposition" in response.headers) is attachment
    else:
        assert "<html" in response.text


def test_a_neighbour_vanishing_mid_request_gives_an_html_404(client, services, monkeypatch, hx):
    app = scenario(services)

    def gone(*args, **kwargs):
        raise NotFound("gone")

    monkeypatch.setattr(services.data_types, "get", gone)
    svg = client.get(f"/ui/applications/{app.id}/diagram.svg")
    assert svg.status_code == 404
    assert "<html" in svg.text and svg.headers["content-type"].startswith("text/html")
    tab = client.get(f"/ui/applications/{app.id}/tabs/diagram", headers=hx)
    assert tab.status_code == 404
    assert tab.headers["HX-Retarget"] == "#flash"
