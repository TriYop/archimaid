from uuid import uuid4

import pytest

from archimaid.application.services import build_services
from archimaid.domain.errors import (
    AlreadyExists,
    DanglingReference,
    InvalidEntity,
    InvalidReferenceCode,
    NotFound,
    ReferenceInUse,
)
from archimaid.domain.reference import AvailabilityLevel
from tests.fakes import default_catalog, fake_repositories


@pytest.fixture
def catalog():
    return default_catalog()


@pytest.fixture
def services(catalog):
    return build_services(fake_repositories(), catalog)


def make_app(services, **extra):
    team = services.teams.create({"name": "Payments"})
    return services.applications.create({"team_id": team.id, "name": "Billing", **extra})


def test_application_view_exposes_derived_rpo_and_rto(services):
    app = make_app(services, availability_level="SERIOUS")
    [row] = services.applications.present_many([app])
    assert (row["rpo"], row["rto"]) == (4, 0)
    assert row["name"] == "Billing"
    assert row["availability_level"] == "SERIOUS"


def test_application_without_availability_has_null_rpo_and_rto(services):
    [row] = services.applications.present_many([make_app(services)])
    assert row["rpo"] is None
    assert row["rto"] is None


def test_rpo_and_rto_follow_catalog_edits(services, catalog):
    app = make_app(services, availability_level="SERIOUS")
    catalog.update(
        "availability_level",
        "SERIOUS",
        AvailabilityLevel(code="SERIOUS", label="Serious", rank=3, rpo_hours=1, rto_hours=2),
    )
    [row] = services.applications.present_many([app])
    assert (row["rpo"], row["rto"]) == (1, 2)


def test_application_rejects_unknown_level_code(services):
    team = services.teams.create({"name": "Payments"})
    with pytest.raises(InvalidReferenceCode):
        services.applications.create(
            {"team_id": team.id, "name": "A", "integrity_level": "NOPE"}
        )


def test_team_member_requires_existing_team(services):
    with pytest.raises(DanglingReference):
        services.members.create({"team_id": uuid4(), "user_id": "u1", "name": "Ann"})


def test_function_requires_existing_persona(services):
    app = make_app(services)
    with pytest.raises(DanglingReference):
        services.functions.create(
            {"application_id": app.id, "name": "Invoice", "persona_id": uuid4()}
        )
    persona = services.personas.create({"name": "Accountant"})
    fn = services.functions.create(
        {"application_id": app.id, "name": "Invoice", "persona_id": persona.id, "category": "DATA"}
    )
    assert fn.persona_id == persona.id


def test_data_flow_requires_existing_apps_and_data_type(services):
    source, target = make_app(services), make_app(services)
    data_type = services.data_types.create({"application_id": source.id, "name": "Invoice"})
    flow = {
        "source_application_id": source.id,
        "target_application_id": target.id,
        "data_type_id": data_type.id,
        "usage_mode": "SOURCE",
    }
    assert services.data_flows.create(flow).usage_mode == "SOURCE"
    for field in ("source_application_id", "target_application_id", "data_type_id"):
        with pytest.raises(DanglingReference):
            services.data_flows.create({**flow, field: uuid4()})
    with pytest.raises(InvalidReferenceCode):
        services.data_flows.create({**flow, "usage_mode": "NOPE"})


def test_technology_validates_both_codes(services):
    app = make_app(services)
    with pytest.raises(InvalidReferenceCode):
        services.technologies.create({"application_id": app.id, "name": "PG", "type": "NOPE"})
    with pytest.raises(InvalidReferenceCode):
        services.technologies.create(
            {"application_id": app.id, "name": "PG", "standard_status": "NOPE"}
        )
    tech = services.technologies.create(
        {"application_id": app.id, "name": "PG", "type": "DATABASE", "standard_status": "REFERENCE"}
    )
    assert tech.type == "DATABASE"


def test_reference_admin_lists_kinds_and_values(services):
    assert "availability_level" in services.reference.kinds()
    assert [v.code for v in services.reference.list("usage_mode")] == [
        "CONSUMER",
        "PROXY",
        "SOURCE",
    ]


def test_reference_admin_create_get_update_delete(services):
    created = services.reference.create(
        "function_category", {"code": "EXTRA", "label": "Extra"}
    )
    assert services.reference.get("function_category", "EXTRA") == created
    updated = services.reference.update(
        "function_category", "EXTRA", {"code": "EXTRA", "label": "Extra 2"}
    )
    assert updated.label == "Extra 2"
    services.reference.delete("function_category", "EXTRA")
    with pytest.raises(NotFound):
        services.reference.get("function_category", "EXTRA")


def test_reference_admin_builds_the_kind_specific_value(services):
    value = services.reference.create(
        "availability_level",
        {"code": "TINY", "label": "Tiny", "rank": 0, "rpo_hours": 1, "rto_hours": 1},
    )
    assert isinstance(value, AvailabilityLevel)


def test_reference_admin_errors(services, catalog):
    with pytest.raises(NotFound):
        services.reference.list("nope")
    with pytest.raises(AlreadyExists):
        services.reference.create("usage_mode", {"code": "SOURCE", "label": "Source"})
    with pytest.raises(InvalidEntity):
        services.reference.create("usage_mode", {"code": " ", "label": "x"})
    catalog.mark_in_use("usage_mode", "PROXY")
    with pytest.raises(ReferenceInUse):
        services.reference.delete("usage_mode", "PROXY")
