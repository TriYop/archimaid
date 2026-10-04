from datetime import UTC, datetime
from uuid import uuid4

import pytest

from archimaid.domain.entities import (
    Application,
    DataFlow,
    Function,
    Persona,
    Team,
    TeamMember,
    Technology,
)
from archimaid.domain.errors import InvalidEntity

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def meta():
    return {"id": uuid4(), "created_at": NOW, "updated_at": NOW}


def test_valid_team_validates_to_true():
    assert Team(name="Payments", **meta()).validate() is True


@pytest.mark.parametrize("name", ["", "   "])
def test_blank_name_is_rejected(name):  # Review Focus test (1)
    with pytest.raises(InvalidEntity):
        Team(name=name, **meta()).validate()


@pytest.mark.parametrize(
    "build",
    [
        lambda name: Application(team_id=uuid4(), name=name, **meta()),
        lambda name: Function(application_id=uuid4(), name=name, **meta()),
        lambda name: Technology(application_id=uuid4(), name=name, **meta()),
        lambda name: Persona(name=name, **meta()),
    ],
)
def test_every_named_entity_rejects_blank_name(build):
    with pytest.raises(InvalidEntity):
        build(" ").validate()


def test_team_member_requires_user_id_and_name():
    with pytest.raises(InvalidEntity):
        TeamMember(team_id=uuid4(), user_id=" ", name="Ann", **meta()).validate()
    with pytest.raises(InvalidEntity):
        TeamMember(team_id=uuid4(), user_id="u1", name="", **meta()).validate()


def test_optional_fields_default_to_none():
    app = Application(team_id=uuid4(), name="Billing", **meta())
    assert app.golden_app_id is None
    assert app.availability_level is None


def test_rpo_and_rto_are_not_stored_on_application():
    app = Application(team_id=uuid4(), name="Billing", **meta())
    assert not hasattr(app, "rpo")
    assert not hasattr(app, "rto")


def test_data_flow_has_usage_mode_and_no_required_text():
    flow = DataFlow(
        source_application_id=uuid4(),
        target_application_id=uuid4(),
        data_type_id=uuid4(),
        usage_mode="SOURCE",
        **meta(),
    )
    assert flow.validate() is True


def test_data_flow_function_ends_default_to_none():
    flow = DataFlow(
        source_application_id=uuid4(),
        target_application_id=uuid4(),
        data_type_id=uuid4(),
        **meta(),
    )
    assert flow.source_function_id is None and flow.target_function_id is None
