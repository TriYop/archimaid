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
