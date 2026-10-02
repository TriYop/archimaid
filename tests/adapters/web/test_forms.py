from uuid import UUID, uuid4

import pytest

from archimaid.adapters.web.forms import parse_form
from archimaid.adapters.web.resources import Field


def f(name="x", widget="text", **kw):
    return Field(name, name.title(), widget, **kw)


def test_text_is_stripped_and_blank_optional_becomes_none():
    data, problems = parse_form({"x": "  hello "}, [f()])
    assert (data, problems) == ({"x": "hello"}, [])
    assert parse_form({"x": "   "}, [f()]) == ({"x": None}, [])
    assert parse_form({}, [f()]) == ({"x": None}, [])


def test_blank_required_text_stays_empty_so_the_domain_reports_it():
    assert parse_form({"x": " "}, [f(required=True)]) == ({"x": ""}, [])


def test_blank_non_nullable_text_stays_empty_string():
    assert parse_form({"x": ""}, [f(widget="textarea", nullable=False)]) == ({"x": ""}, [])


def test_number_parses_ints_and_reports_bad_values():
    assert parse_form({"x": " 42 "}, [f(widget="number")]) == ({"x": 42}, [])
    assert parse_form({"x": ""}, [f(widget="number")]) == ({"x": None}, [])
    data, problems = parse_form({"x": "12.5"}, [f(widget="number")])
    assert problems == ["X: must be a whole number"]
    _, required = parse_form({"x": ""}, [f(widget="number", required=True)])
    assert required == ["X: is required"]


def test_select_ref_blank_is_none_otherwise_the_code():
    field = f("level", "select_ref", kind="integrity_level")
    assert parse_form({"level": ""}, [field]) == ({"level": None}, [])
    assert parse_form({"level": "LOW"}, [field]) == ({"level": "LOW"}, [])


def test_select_entity_parses_uuids():
    field = f("persona_id", "select_entity", source="personas")
    some = uuid4()
    assert parse_form({"persona_id": str(some)}, [field]) == ({"persona_id": some}, [])
    assert parse_form({"persona_id": ""}, [field]) == ({"persona_id": None}, [])
    _, problems = parse_form({"persona_id": "nope"}, [field])
    assert problems == ["Persona_Id: is not a valid choice"]
    _, required = parse_form(
        {"persona_id": ""},
        [f("persona_id", "select_entity", source="personas", required=True)],
    )
    assert required == ["Persona_Id: is required"]


def test_readonly_fields_are_skipped():
    assert parse_form({"x": "1"}, [f(widget="readonly")]) == ({}, [])


def test_uuid_fields_are_required_hidden_inputs():
    team = uuid4()
    data, problems = parse_form({"team_id": str(team)}, [], uuid_fields=("team_id",))
    assert data == {"team_id": UUID(str(team))} and problems == []
    _, missing = parse_form({}, [], uuid_fields=("team_id",))
    assert missing == ["team_id is missing or not a valid id"]


@pytest.mark.parametrize("raw", ["x\u0000y", "<b>bold</b>", "\"quoted\""])
def test_hostile_text_is_passed_through_unchanged(raw):
    # escaping is the template's job and rejecting NUL is the domain/persistence's job
    assert parse_form({"x": raw}, [f()]) == ({"x": raw}, [])
