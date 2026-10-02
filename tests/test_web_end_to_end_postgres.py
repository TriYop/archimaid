import re

import pytest
from fastapi.testclient import TestClient

from archimaid.adapters.api.app import create_app
from archimaid.adapters.persistence.catalog import PostgresReferenceCatalog
from archimaid.adapters.persistence.repository import build_repositories
from archimaid.application.services import build_services

pytestmark = pytest.mark.postgres


@pytest.fixture
def client(engine):
    services = build_services(build_repositories(engine), PostgresReferenceCatalog(engine))
    return TestClient(create_app(services))


def row_id(html, prefix):
    return re.search(rf'<tr id="{prefix}-([0-9a-f-]+)"', html).group(1)


def test_web_ui_scenario_over_real_postgres(client):
    hx = {"HX-Request": "true"}

    team = row_id(client.post("/ui/teams?table=teams", data={"name": "Payments"}).text, "team")
    app_a = row_id(
        client.post(
            "/ui/applications?table=applications",
            data={"team_id": team, "name": "Billing", "availability_level": "SERIOUS"},
        ).text,
        "application",
    )
    app_b = row_id(
        client.post(
            "/ui/applications?table=applications",
            data={"team_id": team, "name": "Ledger"},
        ).text,
        "application",
    )
    assert "4 h / 0 h" in client.get(f"/ui/teams/{team}").text

    function = client.post(
        f"/ui/applications/{app_a}/functions?table=functions",
        data={"name": "Invoice", "category": "BUSINESS"},
    )
    assert function.status_code == 201
    data_type = row_id(
        client.post(
            f"/ui/applications/{app_a}/data-types?table=data-types",
            data={"name": "Invoice", "confidentiality_level": "LOW"},
        ).text,
        "data-type",
    )
    flow = client.post(
        "/ui/data-flows?table=outgoing",
        data={
            "source_application_id": app_a,
            "target_application_id": app_b,
            "data_type_id": data_type,
            "usage_mode": "SOURCE",
        },
    )
    assert flow.status_code == 201
    overview = client.get("/ui/data-flows").text
    assert "Billing" in overview and "Ledger" in overview

    # blocked deletes are flash messages with no Postgres text
    blocked_team = client.delete(f"/ui/teams/{team}", headers=hx)
    assert blocked_team.status_code == 409 and blocked_team.headers["HX-Retarget"] == "#flash"
    blocked_app = client.delete(f"/ui/applications/{app_b}", headers=hx)
    assert blocked_app.status_code == 409
    for body in (blocked_team.text, blocked_app.text):
        assert "violates" not in body and "_fkey" not in body

    # hostile input is a 422, never a 500
    assert client.post("/ui/teams?table=teams", data={"name": "x\u0000"}).status_code == 422
    assert client.post(
        "/ui/reference/integrity_level?table=reference",
        data={"code": "BIG", "label": "Big", "rank": str(2**40)},
    ).status_code == 422
    assert client.post(
        "/ui/reference/usage_mode?table=reference", data={"code": "A/B", "label": "x"}
    ).status_code == 422

    # renaming a catalog code shows the new label in the application rows
    renamed = client.put(
        "/ui/reference/availability_level/SERIOUS",
        data={
            "code": "HIGH",
            "label": "High",
            "description": "",
            "rank": "3",
            "rpo_hours": "4",
            "rto_hours": "0",
        },
    )
    assert renamed.status_code == 200
    team_page = client.get(f"/ui/teams/{team}").text
    assert "High" in team_page and "4 h / 0 h" in team_page
    assert client.delete("/ui/reference/availability_level/HIGH", headers=hx).status_code == 409

    # deleting from the application's own page redirects to the team
    flow_id = row_id(client.get(f"/ui/applications/{app_a}/tabs/data-flows").text, "data-flow")
    assert client.delete(f"/ui/data-flows/{flow_id}").status_code == 200
    own_page = {"HX-Current-URL": f"http://testserver/ui/applications/{app_a}?tab=details"}
    deleted = client.delete(f"/ui/applications/{app_a}", headers=own_page)
    assert deleted.headers["HX-Redirect"] == f"/ui/teams/{team}"
    assert client.get(f"/ui/applications/{app_a}").status_code == 404
