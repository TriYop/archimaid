from datetime import UTC, datetime
from uuid import uuid4

import pytest

from archimaid.adapters.persistence.repository import build_repositories
from archimaid.domain.entities import (
    Application,
    DataFlow,
    DataType,
    Function,
    Persona,
    Team,
    TeamMember,
    Technology,
)
from archimaid.domain.errors import DanglingReference, ReferenceInUse

pytestmark = pytest.mark.postgres

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def meta():
    return {"id": uuid4(), "created_at": NOW, "updated_at": NOW}


@pytest.fixture
def repos(engine):
    return build_repositories(engine)


def add_team(repos):
    team = Team(name="Payments", description="d", **meta())
    repos.teams.add(team)
    return team


def add_app(repos, team, name="Billing"):
    app = Application(team_id=team.id, name=name, **meta())
    repos.applications.add(app)
    return app


def test_application_round_trips_every_field(repos):
    team = add_team(repos)
    app = Application(
        team_id=team.id,
        name="Billing",
        golden_app_id="G1",
        auid="A1",
        description="d",
        asset_cmdb="C",
        shortname="bil",
        owner_uid="u1",
        confidentiality_level="LOW",
        integrity_level="MODERATE",
        availability_level="SERIOUS",
        traceability_level="EXTREME",
        **meta(),
    )
    repos.applications.add(app)
    assert repos.applications.get(app.id) == app


def test_all_other_entities_round_trip(repos):
    team = add_team(repos)
    app = add_app(repos, team)
    persona = Persona(name="Accountant", description="d", category="finance", **meta())
    repos.personas.add(persona)
    member = TeamMember(team_id=team.id, user_id="u1", name="Ann", **meta())
    repos.members.add(member)
    function = Function(
        application_id=app.id, name="Invoice", description="d", category="DATA",
        persona_id=persona.id, **meta(),
    )
    repos.functions.add(function)
    data_type = DataType(
        application_id=app.id, name="Invoice", definition="d", specificity="s",
        confidentiality_level="LOW", golden_source="gs", golden_replica="gr", **meta(),
    )
    repos.data_types.add(data_type)
    flow = DataFlow(
        source_application_id=app.id, target_application_id=app.id, data_type_id=data_type.id,
        usage_mode="SOURCE", usage_explanation="why", **meta(),
    )
    repos.data_flows.add(flow)
    tech = Technology(
        application_id=app.id, name="PG", version="16", family="sql", type="DATABASE",
        standard_status="REFERENCE", standard_status_details="d", tech_standards_link="http://x",
        action_plan="none", **meta(),
    )
    repos.technologies.add(tech)
    assert repos.teams.get(team.id) == team
    assert repos.personas.get(persona.id) == persona
    assert repos.members.get(member.id) == member
    assert repos.functions.get(function.id) == function
    assert repos.data_types.get(data_type.id) == data_type
    assert repos.data_flows.get(flow.id) == flow
    assert repos.technologies.get(tech.id) == tech


def test_get_missing_returns_none(repos):
    assert repos.teams.get(uuid4()) is None


def test_list_filters_by_column(repos):
    team = add_team(repos)
    other = add_team(repos)
    a = add_app(repos, team, "A")
    add_app(repos, other, "B")
    assert repos.applications.list(team_id=team.id) == [a]
    assert len(repos.applications.list()) == 2


def test_update_persists_changes(repos):
    team = add_team(repos)
    app = add_app(repos, team)
    app.name = "Billing v2"
    app.availability_level = "LOW"
    repos.applications.update(app)
    assert repos.applications.get(app.id) == app


def test_add_with_unknown_parent_or_code_is_a_dangling_reference(repos):
    # Review Focus test (4), database backstop
    with pytest.raises(DanglingReference):
        repos.applications.add(Application(team_id=uuid4(), name="X", **meta()))
    team = add_team(repos)
    with pytest.raises(DanglingReference):
        repos.applications.add(
            Application(team_id=team.id, name="X", availability_level="NOPE", **meta())
        )


def test_delete_team_with_applications_is_blocked(repos):  # Review Focus test (3)
    team = add_team(repos)
    add_app(repos, team)
    with pytest.raises(ReferenceInUse):
        repos.teams.delete(team.id)


def test_delete_team_cascades_to_members(repos):
    team = add_team(repos)
    member = TeamMember(team_id=team.id, user_id="u1", name="Ann", **meta())
    repos.members.add(member)
    repos.teams.delete(team.id)
    assert repos.members.get(member.id) is None


def test_delete_application_cascades_to_its_children(repos):  # Review Focus test (3)
    team = add_team(repos)
    app = add_app(repos, team)
    function = Function(application_id=app.id, name="Invoice", **meta())
    data_type = DataType(application_id=app.id, name="Invoice", **meta())
    tech = Technology(application_id=app.id, name="PG", **meta())
    repos.functions.add(function)
    repos.data_types.add(data_type)
    repos.technologies.add(tech)
    repos.applications.delete(app.id)
    assert repos.functions.get(function.id) is None
    assert repos.data_types.get(data_type.id) is None
    assert repos.technologies.get(tech.id) is None


def test_delete_application_used_as_flow_source_or_target_is_blocked(repos):
    # Review Focus test (3)
    team = add_team(repos)
    source, target = add_app(repos, team, "S"), add_app(repos, team, "T")
    data_type = DataType(application_id=source.id, name="Invoice", **meta())
    repos.data_types.add(data_type)
    repos.data_flows.add(
        DataFlow(
            source_application_id=source.id, target_application_id=target.id,
            data_type_id=data_type.id, **meta(),
        )
    )
    with pytest.raises(ReferenceInUse):
        repos.applications.delete(target.id)
    with pytest.raises(ReferenceInUse):
        repos.applications.delete(source.id)  # cascades to data_type, which the flow blocks
    assert repos.applications.get(source.id) is not None


def test_delete_data_type_used_by_flow_is_blocked(repos):  # Review Focus test (3)
    team = add_team(repos)
    app = add_app(repos, team)
    data_type = DataType(application_id=app.id, name="Invoice", **meta())
    repos.data_types.add(data_type)
    repos.data_flows.add(
        DataFlow(
            source_application_id=app.id, target_application_id=app.id,
            data_type_id=data_type.id, **meta(),
        )
    )
    with pytest.raises(ReferenceInUse):
        repos.data_types.delete(data_type.id)


def test_delete_persona_used_by_function_is_blocked(repos):  # Review Focus test (3)
    team = add_team(repos)
    app = add_app(repos, team)
    persona = Persona(name="Accountant", **meta())
    repos.personas.add(persona)
    repos.functions.add(
        Function(application_id=app.id, name="Invoice", persona_id=persona.id, **meta())
    )
    with pytest.raises(ReferenceInUse):
        repos.personas.delete(persona.id)
