from datetime import UTC, datetime, timedelta
from itertools import count
from uuid import uuid4

import pytest

from archimaid.application.crud import CrudService, ParentLink
from archimaid.domain.entities import Application, Team
from archimaid.domain.errors import (
    DanglingReference,
    InvalidEntity,
    InvalidReferenceCode,
    NotFound,
    ReferenceInUse,
)
from tests.fakes import InMemoryRepository, default_catalog

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def ticking_clock():
    ticks = count()
    return lambda: NOW + timedelta(minutes=next(ticks))


@pytest.fixture
def team_repo():
    return InMemoryRepository[Team]()


@pytest.fixture
def app_repo():
    return InMemoryRepository[Application]()


@pytest.fixture
def apps(team_repo, app_repo):
    return CrudService(
        Application,
        app_repo,
        default_catalog(),
        reference_fields={"availability_level": "availability_level"},
        parents=[ParentLink("team_id", team_repo)],
        clock=ticking_clock(),
    )


@pytest.fixture
def team(team_repo):
    t = Team(id=uuid4(), name="Payments", created_at=NOW, updated_at=NOW)
    team_repo.add(t)
    return t


def test_create_assigns_id_and_timestamps_and_stores(apps, app_repo, team):
    app = apps.create({"team_id": team.id, "name": "Billing"})
    assert app_repo.get(app.id) == app
    assert app.created_at == app.updated_at


@pytest.mark.parametrize("name", ["", "   "])
def test_create_rejects_blank_name_and_stores_nothing(apps, app_repo, team, name):
    # Review Focus test (1)
    with pytest.raises(InvalidEntity):
        apps.create({"team_id": team.id, "name": name})
    assert app_repo.list() == []


def test_create_rejects_unknown_reference_code(apps, team):
    with pytest.raises(InvalidReferenceCode):
        apps.create({"team_id": team.id, "name": "Billing", "availability_level": "NOPE"})


def test_create_accepts_known_and_null_reference_codes(apps, team):
    assert apps.create(
        {"team_id": team.id, "name": "A", "availability_level": "SERIOUS"}
    ).availability_level == "SERIOUS"
    assert apps.create(
        {"team_id": team.id, "name": "B", "availability_level": None}
    ).availability_level is None


def test_create_rejects_unknown_parent_id(apps, app_repo):
    # Review Focus test (4)
    with pytest.raises(DanglingReference):
        apps.create({"team_id": uuid4(), "name": "Billing"})
    assert app_repo.list() == []


def test_get_missing_raises_not_found(apps):
    with pytest.raises(NotFound):
        apps.get(uuid4())


def test_list_filters(apps, team):
    apps.create({"team_id": team.id, "name": "A"})
    apps.create({"team_id": team.id, "name": "B"})
    assert [a.name for a in apps.list(name="B")] == ["B"]
    assert len(apps.list()) == 2


def test_update_replaces_fields_keeps_created_at_and_bumps_updated_at(apps, team):
    app = apps.create({"team_id": team.id, "name": "Billing"})
    updated = apps.update(app.id, {"team_id": team.id, "name": "Billing v2"})
    assert updated.name == "Billing v2"
    assert updated.created_at == app.created_at
    assert updated.updated_at > app.created_at


def test_update_that_fails_validation_leaves_stored_entity_untouched(apps, team):
    app = apps.create({"team_id": team.id, "name": "Billing"})
    with pytest.raises(InvalidEntity):  # Review Focus test (1), PUT path
        apps.update(app.id, {"team_id": team.id, "name": " "})
    with pytest.raises(DanglingReference):  # Review Focus test (4), PUT path
        apps.update(app.id, {"team_id": uuid4(), "name": "x"})
    assert apps.get(app.id).name == "Billing"


def test_update_missing_raises_not_found(apps, team):
    with pytest.raises(NotFound):
        apps.update(uuid4(), {"team_id": team.id, "name": "x"})


def test_delete_removes_and_missing_raises(apps, team):
    app = apps.create({"team_id": team.id, "name": "Billing"})
    apps.delete(app.id)
    with pytest.raises(NotFound):
        apps.get(app.id)
    with pytest.raises(NotFound):
        apps.delete(app.id)


def test_delete_propagates_reference_in_use(apps, app_repo, team):
    app = apps.create({"team_id": team.id, "name": "Billing"})
    app_repo.mark_in_use(app.id)
    with pytest.raises(ReferenceInUse):
        apps.delete(app.id)
