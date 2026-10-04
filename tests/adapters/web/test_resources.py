from dataclasses import fields as dc_fields

import pytest

from archimaid.adapters.web import resources as r
from archimaid.application.services import Services
from archimaid.domain import entities as e
from archimaid.domain.reference import REFERENCE_KINDS

ENTITY_OF = {
    r.TEAM: e.Team,
    r.MEMBER: e.TeamMember,
    r.APPLICATION: e.Application,
    r.FUNCTION: e.Function,
    r.DATA_TYPE: e.DataType,
    r.TECHNOLOGY: e.Technology,
    r.DATA_FLOW: e.DataFlow,
    r.PERSONA: e.Persona,
}


def test_all_resources_lists_the_eight_entities():
    assert set(r.ALL_RESOURCES) == set(ENTITY_OF)


@pytest.mark.parametrize("resource", r.ALL_RESOURCES, ids=lambda x: x.slug)
def test_resource_matches_services_and_entity(resource):
    assert resource.service_name in {f.name for f in dc_fields(Services)}
    entity_fields = {f.name for f in dc_fields(ENTITY_OF[resource])}
    for field in resource.fields:
        if field.widget != "readonly":
            assert field.name in entity_fields, field.name
    assert set(resource.hidden_uuid) <= entity_fields
    if resource.parent_field:
        assert resource.parent_field in entity_fields


@pytest.mark.parametrize("resource", r.ALL_RESOURCES, ids=lambda x: x.slug)
def test_widgets_have_what_they_need(resource):
    for field in resource.fields:
        if field.widget == "select_ref":
            assert field.kind in REFERENCE_KINDS
        if field.widget == "select_entity":
            assert field.source in {"personas", "applications", "data_types", "functions"}


@pytest.mark.parametrize("resource", r.ALL_RESOURCES, ids=lambda x: x.slug)
def test_form_fields_are_a_subset_of_columns(resource):
    columns = {f.name for f in resource.columns()}
    assert {f.name for f in resource.form()} <= columns
    assert all(f.widget != "readonly" for f in resource.form())


def test_application_table_is_narrower_than_its_details_form():
    names = [f.name for f in r.APPLICATION.columns()]
    assert names == [
        "name", "shortname", "confidentiality_level", "integrity_level",
        "availability_level", "traceability_level", "rpo_rto",
    ]
    editable = [f.name for f in r.APPLICATION.editable()]
    assert "golden_app_id" in editable and "description" in editable
    assert "rpo_rto" not in editable
    assert r.APPLICATION.field("rpo_rto").widget == "readonly"


def test_urls_and_confirm_text():
    assert r.MEMBER.url({"team_id": "t1"}) == "/ui/teams/t1/members"
    assert r.APPLICATION.url({}) == "/ui/applications"
    assert "functions, data types and technologies" in r.APPLICATION.confirm_delete()
    assert r.PERSONA.confirm_delete() == "Delete this persona?"


def test_team_description_is_not_nullable():
    assert r.TEAM.field("description").nullable is False


def test_reference_resource_columns_follow_the_kind():
    plain = [f.name for f in r.reference_resource("usage_mode").fields]
    assert plain == ["code", "label", "description"]
    ranked = [f.name for f in r.reference_resource("integrity_level").fields]
    assert ranked == ["code", "label", "description", "rank"]
    avail = r.reference_resource("availability_level")
    assert [f.name for f in avail.fields][-3:] == ["rank", "rpo_hours", "rto_hours"]
    assert avail.base == "/ui/reference/availability_level"
    assert avail.slug == "ref-availability_level"
