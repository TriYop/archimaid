from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from archimaid.adapters.api.app import create_app
from archimaid.application.services import build_services
from tests.fakes import default_catalog, fake_repositories


@pytest.fixture
def catalog():
    return default_catalog()


@pytest.fixture
def repos():
    return fake_repositories()


@pytest.fixture
def client(repos, catalog):
    return TestClient(create_app(build_services(repos, catalog)))


def post(client, url, body, status=201):
    response = client.post(url, json=body)
    assert response.status_code == status, response.text
    return response.json()


def make_team(client, name="Payments"):
    return post(client, "/teams", {"name": name})


def make_app(client, team=None, **extra):
    team = team or make_team(client)
    return post(client, "/applications", {"team_id": team["id"], "name": "Billing", **extra})


# ---------------------------------------------------------------- teams / generic CRUD


def test_team_crud_round_trip(client):
    team = make_team(client)
    assert client.get(f"/teams/{team['id']}").json()["name"] == "Payments"
    assert [t["id"] for t in client.get("/teams").json()] == [team["id"]]
    put = client.put(f"/teams/{team['id']}", json={"name": "Billing", "description": "d"})
    assert put.status_code == 200
    assert put.json()["name"] == "Billing"
    assert client.delete(f"/teams/{team['id']}").status_code == 204
    assert client.get(f"/teams/{team['id']}").status_code == 404


@pytest.mark.parametrize("name", ["", "   "])
def test_blank_name_is_422_on_create_and_put(client, repos, name):  # Review Focus test (1)
    assert client.post("/teams", json={"name": name}).status_code == 422
    assert repos.teams.list() == []
    team = make_team(client)
    assert client.put(f"/teams/{team['id']}", json={"name": name}).status_code == 422
    assert client.get(f"/teams/{team['id']}").json()["name"] == "Payments"


def test_missing_required_field_is_422(client):
    assert client.post("/teams", json={}).status_code == 422


def test_malformed_uuid_in_path_is_422(client):
    assert client.get("/teams/not-a-uuid").status_code == 422


def test_delete_of_a_referenced_entity_is_409(client, repos):
    team = make_team(client)
    repos.teams.mark_in_use(UUID(team["id"]))
    assert client.delete(f"/teams/{team['id']}").status_code == 409


def test_team_members_are_nested_under_their_team(client):
    team = make_team(client)
    member = post(client, f"/teams/{team['id']}/members", {"user_id": "u1", "name": "Ann"})
    assert member["team_id"] == team["id"]
    assert len(client.get(f"/teams/{team['id']}/members").json()) == 1
    assert client.get(f"/teams/{make_team(client, 'B')['id']}/members").json() == []


# ---------------------------------------------------------------- applications


def test_application_exposes_derived_rpo_rto(client):
    app = make_app(client, availability_level="SERIOUS")
    assert (app["rpo"], app["rto"]) == (4, 0)
    fetched = client.get(f"/applications/{app['id']}").json()
    assert (fetched["rpo"], fetched["rto"]) == (4, 0)
    assert client.get("/applications").json()[0]["rpo"] == 4


def test_application_without_availability_has_null_rpo_rto(client):
    app = make_app(client)
    assert app["rpo"] is None and app["rto"] is None


def test_rpo_rto_in_the_request_body_are_ignored(client):
    app = make_app(client, rpo=999, rto=999)
    assert app["rpo"] is None


def test_application_with_unknown_level_code_is_422(client):
    team = make_team(client)
    response = client.post(
        "/applications",
        json={"team_id": team["id"], "name": "A", "availability_level": "NOPE"},
    )
    assert response.status_code == 422


def test_application_with_unknown_team_is_422_not_500(client):  # Review Focus test (4)
    response = client.post("/applications", json={"team_id": str(uuid4()), "name": "A"})
    assert response.status_code == 422
    team = make_team(client)
    app = make_app(client, team)
    response = client.put(
        f"/applications/{app['id']}", json={"team_id": str(uuid4()), "name": "A"}
    )
    assert response.status_code == 422


def test_applications_can_be_filtered_by_team(client):
    team_a, team_b = make_team(client, "A"), make_team(client, "B")
    app_a = make_app(client, team_a)
    make_app(client, team_b)
    ids = [a["id"] for a in client.get(f"/applications?team_id={team_a['id']}").json()]
    assert ids == [app_a["id"]]
    assert client.get("/applications?team_id=nope").status_code == 422


# ---------------------------------------------------------------- nested resources


def test_functions_are_scoped_to_their_application(client):
    app_a, app_b = make_app(client), make_app(client)
    fn = post(client, f"/applications/{app_a['id']}/functions",
              {"name": "Invoice", "category": "BUSINESS"})
    assert fn["application_id"] == app_a["id"]
    assert len(client.get(f"/applications/{app_a['id']}/functions").json()) == 1
    assert client.get(f"/applications/{app_b['id']}/functions").json() == []


def test_reaching_a_nested_resource_through_the_wrong_parent_is_404(client):
    # Review Focus test (5)
    app_a, app_b = make_app(client), make_app(client)
    fn = post(client, f"/applications/{app_a['id']}/functions", {"name": "Invoice"})
    wrong = f"/applications/{app_b['id']}/functions/{fn['id']}"
    assert client.get(wrong).status_code == 404
    assert client.put(wrong, json={"name": "x"}).status_code == 404
    assert client.delete(wrong).status_code == 404
    assert client.get(f"/applications/{app_a['id']}/functions/{fn['id']}").status_code == 200


def test_nested_routes_under_a_missing_parent_are_404(client):
    ghost = uuid4()
    assert client.get(f"/applications/{ghost}/functions").status_code == 404
    response = client.post(f"/applications/{ghost}/technologies", json={"name": "PG"})
    assert response.status_code == 404
    assert client.get(f"/teams/{ghost}/members").status_code == 404


def test_function_with_unknown_persona_is_422(client):  # Review Focus test (4)
    app = make_app(client)
    response = client.post(
        f"/applications/{app['id']}/functions",
        json={"name": "Invoice", "persona_id": str(uuid4())},
    )
    assert response.status_code == 422
    persona = post(client, "/personas", {"name": "Accountant"})
    ok = post(client, f"/applications/{app['id']}/functions",
              {"name": "Invoice", "persona_id": persona["id"]})
    assert ok["persona_id"] == persona["id"]


def test_data_types_and_technologies_crud(client):
    app = make_app(client)
    dt = post(client, f"/applications/{app['id']}/data-types",
              {"name": "Invoice", "confidentiality_level": "LOW", "golden_source": "ERP"})
    assert dt["golden_source"] == "ERP"
    tech = post(client, f"/applications/{app['id']}/technologies",
                {"name": "PG", "type": "DATABASE", "standard_status": "REFERENCE"})
    assert tech["type"] == "DATABASE"
    bad = client.post(f"/applications/{app['id']}/technologies",
                      json={"name": "PG", "type": "NOPE"})
    assert bad.status_code == 422


def test_data_flows_accept_and_validate_function_ends(client):
    source, target = make_app(client), make_app(client)
    dt = post(client, f"/applications/{source['id']}/data-types", {"name": "Invoice"})
    sender = post(client, f"/applications/{source['id']}/functions", {"name": "Send"})
    receiver = post(client, f"/applications/{target['id']}/functions", {"name": "Post"})
    body = {
        "source_application_id": source["id"],
        "target_application_id": target["id"],
        "data_type_id": dt["id"],
    }
    flow = post(
        client,
        "/data-flows",
        {**body, "source_function_id": sender["id"], "target_function_id": receiver["id"]},
    )
    assert flow["source_function_id"] == sender["id"]
    assert flow["target_function_id"] == receiver["id"]
    plain = post(client, "/data-flows", body)
    assert plain["source_function_id"] is None and plain["target_function_id"] is None
    swapped = client.post("/data-flows", json={**body, "source_function_id": receiver["id"]})
    assert swapped.status_code == 422
    ghost = client.post("/data-flows", json={**body, "target_function_id": str(uuid4())})
    assert ghost.status_code == 422
    cleared = client.put(
        f"/data-flows/{flow['id']}", json={**body, "source_function_id": sender["id"]}
    )
    assert cleared.status_code == 200
    assert cleared.json()["target_function_id"] is None


def test_data_flows_validate_references_and_filter(client):
    source, target = make_app(client), make_app(client)
    dt = post(client, f"/applications/{source['id']}/data-types", {"name": "Invoice"})
    body = {
        "source_application_id": source["id"],
        "target_application_id": target["id"],
        "data_type_id": dt["id"],
        "usage_mode": "SOURCE",
        "usage_explanation": "billing export",
    }
    flow = post(client, "/data-flows", body)
    assert flow["usage_mode"] == "SOURCE"
    response = client.post("/data-flows", json={**body, "data_type_id": str(uuid4())})
    assert response.status_code == 422
    assert client.post("/data-flows", json={**body, "usage_mode": "NOPE"}).status_code == 422
    found = client.get(f"/data-flows?source_application_id={source['id']}").json()
    assert [f["id"] for f in found] == [flow["id"]]
    assert client.get(f"/data-flows?source_application_id={target['id']}").json() == []


# ---------------------------------------------------------------- reference admin API


def test_reference_kinds_and_values_are_listed(client):
    assert "availability_level" in client.get("/reference").json()
    codes = [v["code"] for v in client.get("/reference/usage_mode").json()]
    assert codes == ["CONSUMER", "PROXY", "SOURCE"]
    serious = client.get("/reference/availability_level/SERIOUS").json()
    assert (serious["rpo_hours"], serious["rto_hours"], serious["rank"]) == (4, 0, 3)


def test_unknown_reference_kind_is_404_even_with_a_bad_body(client):
    assert client.get("/reference/nope").status_code == 404
    assert client.get("/reference/nope/X").status_code == 404
    assert client.post("/reference/nope", json={"junk": 1}).status_code == 404
    assert client.delete("/reference/nope/X").status_code == 404


def test_reference_create_update_delete(client):
    created = post(client, "/reference/function_category", {"code": "EXTRA", "label": "Extra"})
    assert created["code"] == "EXTRA"
    put = client.put("/reference/function_category/EXTRA",
                     json={"code": "EXTRA", "label": "Extra 2", "description": "d"})
    assert put.status_code == 200 and put.json()["label"] == "Extra 2"
    assert client.delete("/reference/function_category/EXTRA").status_code == 204
    assert client.get("/reference/function_category/EXTRA").status_code == 404


def test_reference_body_must_match_the_kind(client):
    # availability needs rank + rpo/rto; plain kinds reject extra fields
    assert client.post("/reference/availability_level",
                       json={"code": "T", "label": "T", "rank": 1}).status_code == 422
    assert client.post("/reference/function_category",
                       json={"code": "T", "label": "T", "rank": 1}).status_code == 422
    assert client.post("/reference/integrity_level",
                       json={"code": "T", "label": "T"}).status_code == 422
    ok = post(client, "/reference/availability_level",
              {"code": "TINY", "label": "Tiny", "rank": 0, "rpo_hours": 1, "rto_hours": 1})
    assert ok["rpo_hours"] == 1


def test_reference_blank_code_is_422(client):
    assert client.post("/reference/usage_mode", json={"code": " ", "label": "x"}).status_code == 422


def test_reference_duplicate_code_is_409(client):  # Review Focus test (2)
    response = client.post("/reference/usage_mode", json={"code": "SOURCE", "label": "x"})
    assert response.status_code == 409
    response = client.put("/reference/usage_mode/PROXY", json={"code": "SOURCE", "label": "x"})
    assert response.status_code == 409


def test_reference_delete_in_use_is_409(client, catalog):
    catalog.mark_in_use("usage_mode", "PROXY")
    assert client.delete("/reference/usage_mode/PROXY").status_code == 409


def test_reference_update_of_unknown_code_is_404(client):
    response = client.put("/reference/usage_mode/NOPE", json={"code": "NOPE", "label": "x"})
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("kind", "body"),
    [
        ("integrity_level", {"code": "T", "label": "T", "rank": 2**40}),
        ("integrity_level", {"code": "T", "label": "T", "rank": -(2**40)}),
        ("availability_level",
         {"code": "T", "label": "T", "rank": 1, "rpo_hours": 2**40, "rto_hours": 0}),
        ("availability_level",
         {"code": "T", "label": "T", "rank": 1, "rpo_hours": 0, "rto_hours": 2**40}),
    ],
)
def test_reference_out_of_range_integers_are_422(client, kind, body):
    assert client.post(f"/reference/{kind}", json=body).status_code == 422
    assert client.put(f"/reference/{kind}/LOW", json=body).status_code == 422


@pytest.mark.parametrize("code", ["A/B", " PAD ", "lower"])
def test_reference_code_with_a_bad_format_is_422_and_not_stored(client, code):
    before = client.get("/reference/usage_mode").json()
    response = client.post("/reference/usage_mode", json={"code": code, "label": "x"})
    assert response.status_code == 422
    assert client.get("/reference/usage_mode").json() == before
    put = client.put("/reference/usage_mode/PROXY", json={"code": code, "label": "x"})
    assert put.status_code == 422


def test_ranked_reference_values_are_listed_by_rank(client):
    codes = [v["code"] for v in client.get("/reference/integrity_level").json()]
    assert codes == ["EXTREME", "SERIOUS", "MODERATE", "LOW"]


# ---------------------------------------------------------------- PUT on nested resources


def test_function_put_changes_fields_and_keeps_the_parent(client):
    app = make_app(client)
    fn = post(client, f"/applications/{app['id']}/functions", {"name": "Invoice"})
    url = f"/applications/{app['id']}/functions/{fn['id']}"
    put = client.put(url, json={"name": "Invoicing", "category": "BUSINESS"})
    assert put.status_code == 200
    assert (put.json()["name"], put.json()["category"]) == ("Invoicing", "BUSINESS")
    assert put.json()["application_id"] == app["id"]
    assert client.get(url).json()["name"] == "Invoicing"


def test_function_put_cannot_move_it_to_another_application(client):
    app, other = make_app(client), make_app(client)
    fn = post(client, f"/applications/{app['id']}/functions", {"name": "Invoice"})
    url = f"/applications/{app['id']}/functions/{fn['id']}"
    put = client.put(url, json={"name": "Invoice", "application_id": other["id"]})
    assert put.status_code == 200
    assert put.json()["application_id"] == app["id"]
    assert client.get(url).json()["application_id"] == app["id"]
    assert client.get(f"/applications/{other['id']}/functions").json() == []


def test_data_type_put_changes_fields_and_keeps_the_parent(client):
    app = make_app(client)
    dt = post(client, f"/applications/{app['id']}/data-types", {"name": "Invoice"})
    put = client.put(
        f"/applications/{app['id']}/data-types/{dt['id']}",
        json={"name": "Invoice", "golden_source": "ERP", "confidentiality_level": "LOW"},
    )
    assert put.status_code == 200
    assert (put.json()["golden_source"], put.json()["application_id"]) == ("ERP", app["id"])


def test_technology_put_changes_fields_and_keeps_the_parent(client):
    app = make_app(client)
    tech = post(client, f"/applications/{app['id']}/technologies", {"name": "PG"})
    put = client.put(
        f"/applications/{app['id']}/technologies/{tech['id']}",
        json={"name": "PG", "version": "16", "type": "DATABASE"},
    )
    assert put.status_code == 200
    assert (put.json()["version"], put.json()["application_id"]) == ("16", app["id"])
    bad = client.put(
        f"/applications/{app['id']}/technologies/{tech['id']}",
        json={"name": "PG", "type": "NOPE"},
    )
    assert bad.status_code == 422


def test_team_member_put_changes_fields_and_keeps_the_parent(client):
    team = make_team(client)
    member = post(client, f"/teams/{team['id']}/members", {"user_id": "u1", "name": "Ann"})
    put = client.put(
        f"/teams/{team['id']}/members/{member['id']}", json={"user_id": "u1", "name": "Anne"}
    )
    assert put.status_code == 200
    assert (put.json()["name"], put.json()["team_id"]) == ("Anne", team["id"])


def test_data_flow_put_changes_fields_and_validates_references(client):
    source, target = make_app(client), make_app(client)
    dt = post(client, f"/applications/{source['id']}/data-types", {"name": "Invoice"})
    body = {
        "source_application_id": source["id"],
        "target_application_id": target["id"],
        "data_type_id": dt["id"],
        "usage_mode": "SOURCE",
    }
    flow = post(client, "/data-flows", body)
    put = client.put(
        f"/data-flows/{flow['id']}",
        json={**body, "usage_mode": "PROXY", "usage_explanation": "relay"},
    )
    assert put.status_code == 200
    assert (put.json()["usage_mode"], put.json()["usage_explanation"]) == ("PROXY", "relay")
    assert client.put(
        f"/data-flows/{flow['id']}", json={**body, "usage_mode": "NOPE"}
    ).status_code == 422
    assert client.put(
        f"/data-flows/{flow['id']}", json={**body, "target_application_id": str(uuid4())}
    ).status_code == 422


def test_rpo_rto_in_an_application_put_body_are_ignored(client):
    app = make_app(client, availability_level="SERIOUS")
    put = client.put(
        f"/applications/{app['id']}",
        json={
            "team_id": app["team_id"], "name": "Billing",
            "availability_level": "SERIOUS", "rpo": 999, "rto": 999,
        },
    )
    assert put.status_code == 200
    assert (put.json()["rpo"], put.json()["rto"]) == (4, 0)
