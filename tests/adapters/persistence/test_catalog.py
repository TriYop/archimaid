from datetime import UTC, datetime
from uuid import uuid4

import pytest

from archimaid.adapters.persistence.catalog import PostgresReferenceCatalog
from archimaid.adapters.persistence.repository import build_repositories
from archimaid.domain.entities import Application, Team
from archimaid.domain.errors import AlreadyExists, InvalidEntity, NotFound, ReferenceInUse
from archimaid.domain.reference import AvailabilityLevel, FunctionCategory

pytestmark = pytest.mark.postgres

NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def catalog(engine):
    return PostgresReferenceCatalog(engine)


def application_using(engine, availability_level):
    repos = build_repositories(engine)
    team = Team(id=uuid4(), name="T", created_at=NOW, updated_at=NOW)
    repos.teams.add(team)
    app = Application(
        id=uuid4(), team_id=team.id, name="A", availability_level=availability_level,
        created_at=NOW, updated_at=NOW,
    )
    repos.applications.add(app)
    return repos, app


def test_get_returns_the_kind_specific_value_object(catalog):
    value = catalog.get("availability_level", "SERIOUS")
    assert isinstance(value, AvailabilityLevel)
    assert (value.rpo_hours, value.rto_hours, value.rank) == (4, 0, 3)


def test_list_and_exists(catalog):
    assert [v.code for v in catalog.list("usage_mode")] == ["CONSUMER", "PROXY", "SOURCE"]
    assert catalog.exists("usage_mode", "SOURCE")
    assert not catalog.exists("usage_mode", "NOPE")


def test_ranked_kinds_list_by_rank_descending(catalog):
    expected = ["EXTREME", "SERIOUS", "MODERATE", "LOW"]
    assert [v.code for v in catalog.list("integrity_level")] == expected
    assert [v.code for v in catalog.list("availability_level")] == expected


def test_unknown_kind_and_unknown_code_are_not_found(catalog):
    with pytest.raises(NotFound):
        catalog.list("nope")
    with pytest.raises(NotFound):
        catalog.get("usage_mode", "NOPE")


def test_create_then_delete_unreferenced_value(catalog):
    created = catalog.create("function_category", FunctionCategory(code="EXTRA", label="Extra"))
    assert catalog.get("function_category", "EXTRA") == created
    catalog.delete("function_category", "EXTRA")
    assert not catalog.exists("function_category", "EXTRA")


def test_create_with_existing_code_is_already_exists(catalog):  # Review Focus test (2)
    with pytest.raises(AlreadyExists):
        catalog.create("function_category", FunctionCategory(code="DATA", label="Dup"))


def test_update_changes_columns(catalog):
    catalog.update(
        "availability_level", "SERIOUS",
        AvailabilityLevel(code="SERIOUS", label="Serious", rank=3, rpo_hours=1, rto_hours=2),
    )
    value = catalog.get("availability_level", "SERIOUS")
    assert (value.rpo_hours, value.rto_hours) == (1, 2)


def test_update_unknown_code_is_not_found(catalog):
    with pytest.raises(NotFound):
        catalog.update("function_category", "NOPE", FunctionCategory(code="NOPE", label="x"))


def test_rename_cascades_to_referencing_rows(engine, catalog):
    repos, app = application_using(engine, "SERIOUS")
    catalog.update(
        "availability_level", "SERIOUS",
        AvailabilityLevel(code="HIGH", label="High", rank=3, rpo_hours=4, rto_hours=0),
    )
    assert repos.applications.get(app.id).availability_level == "HIGH"
    assert not catalog.exists("availability_level", "SERIOUS")


def test_rename_onto_an_existing_code_is_already_exists(catalog):  # Review Focus test (2)
    with pytest.raises(AlreadyExists):
        catalog.update(
            "function_category", "DATA", FunctionCategory(code="COMMON", label="x")
        )
    assert catalog.exists("function_category", "DATA")


def test_delete_value_in_use_is_blocked_and_value_stays(engine, catalog):
    application_using(engine, "LOW")
    with pytest.raises(ReferenceInUse):
        catalog.delete("availability_level", "LOW")
    assert catalog.exists("availability_level", "LOW")


def test_delete_unknown_code_is_not_found(catalog):
    with pytest.raises(NotFound):
        catalog.delete("function_category", "NOPE")


def test_nul_character_in_code_or_label_is_an_invalid_entity(catalog):
    # NUL passes the code format only via the label; build the code check separately
    with pytest.raises(InvalidEntity):
        catalog.create("function_category", FunctionCategory(code="NULL_LABEL", label="a\u0000"))
    with pytest.raises(InvalidEntity):
        catalog.update(
            "function_category", "DATA", FunctionCategory(code="DATA", label="a\u0000")
        )
    assert catalog.get("function_category", "DATA").label == "Data"
    assert not catalog.exists("function_category", "NULL_LABEL")


def test_out_of_range_integer_is_an_invalid_entity(catalog):
    with pytest.raises(InvalidEntity):
        catalog.create(
            "availability_level",
            AvailabilityLevel(code="HUGE", label="Huge", rank=1, rpo_hours=2**40, rto_hours=0),
        )
    with pytest.raises(InvalidEntity):
        catalog.update(
            "availability_level", "LOW",
            AvailabilityLevel(code="LOW", label="Low", rank=2**40, rpo_hours=1, rto_hours=1),
        )


def test_nul_character_in_a_delete_code_is_an_invalid_entity(catalog):
    with pytest.raises(InvalidEntity):
        catalog.delete("function_category", "A\u0000")
