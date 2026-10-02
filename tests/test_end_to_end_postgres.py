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


def test_scenario_over_real_postgres(client):
    team = client.post("/teams", json={"name": "Payments"}).json()
    app = client.post(
        "/applications",
        json={"team_id": team["id"], "name": "Billing", "availability_level": "SERIOUS"},
    ).json()
    assert (app["rpo"], app["rto"]) == (4, 0)

    function = client.post(
        f"/applications/{app['id']}/functions", json={"name": "Invoice", "category": "BUSINESS"}
    )
    assert function.status_code == 201

    # referenced rows cannot be deleted
    assert client.delete(f"/teams/{team['id']}").status_code == 409
    assert client.delete("/reference/availability_level/SERIOUS").status_code == 409

    # unknown codes and ids are 422, not 500
    assert client.post(
        "/applications",
        json={"team_id": team["id"], "name": "X", "availability_level": "NOPE"},
    ).status_code == 422
    assert client.post(
        "/applications",
        json={"team_id": "00000000-0000-0000-0000-000000000000", "name": "X"},
    ).status_code == 422

    # editing the catalog changes the derived values immediately
    edited = client.put(
        "/reference/availability_level/SERIOUS",
        json={"code": "SERIOUS", "label": "Serious", "rank": 3, "rpo_hours": 1, "rto_hours": 1},
    )
    assert edited.status_code == 200
    assert client.get(f"/applications/{app['id']}").json()["rpo"] == 1

    # renaming a code cascades to the applications that use it
    renamed = client.put(
        "/reference/availability_level/SERIOUS",
        json={"code": "HIGH", "label": "High", "rank": 3, "rpo_hours": 1, "rto_hours": 1},
    )
    assert renamed.status_code == 200
    assert client.get(f"/applications/{app['id']}").json()["availability_level"] == "HIGH"

    # deleting the application removes its functions; then the team can go
    assert client.delete(f"/applications/{app['id']}").status_code == 204
    assert client.get(f"/applications/{app['id']}/functions").status_code == 404
    assert client.delete(f"/teams/{team['id']}").status_code == 204


def test_values_postgres_rejects_are_422_never_500(client):
    assert client.post("/teams", json={"name": "x\u0000"}).status_code == 422
    assert client.post(
        "/reference/function_category", json={"code": "NUL", "label": "x\u0000"}
    ).status_code == 422
    assert client.post(
        "/reference/integrity_level", json={"code": "BIG", "label": "B", "rank": 2**40}
    ).status_code == 422
    assert client.post(
        "/reference/availability_level",
        json={"code": "BIG", "label": "B", "rank": 1, "rpo_hours": 2**40, "rto_hours": 0},
    ).status_code == 422
    assert client.get("/teams").json() == []


def test_blocked_delete_and_dangling_reference_bodies_have_no_postgres_text(client):
    team = client.post("/teams", json={"name": "Payments"}).json()
    client.post("/applications", json={"team_id": team["id"], "name": "Billing"})
    blocked = client.delete(f"/teams/{team['id']}")
    dangling = client.post(
        "/applications",
        json={"team_id": "00000000-0000-0000-0000-000000000000", "name": "X"},
    )
    assert (blocked.status_code, dangling.status_code) == (409, 422)
    for response in (blocked, dangling):
        assert not any(w in response.text for w in ("violates", "constraint", "_fkey"))
