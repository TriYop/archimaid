from datetime import UTC, datetime
from uuid import uuid4

import pytest

from archimaid.domain.entities import Team
from archimaid.domain.errors import AlreadyExists, NotFound, ReferenceInUse
from archimaid.domain.reference import FunctionCategory
from tests.fakes import InMemoryRepository, default_catalog

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def team(name="Payments"):
    return Team(id=uuid4(), name=name, created_at=NOW, updated_at=NOW)


def test_repository_add_get_update_delete():
    repo = InMemoryRepository[Team]()
    t = team()
    repo.add(t)
    assert repo.get(t.id) == t
    t.name = "Billing"
    repo.update(t)
    assert repo.get(t.id).name == "Billing"
    repo.delete(t.id)
    assert repo.get(t.id) is None


def test_repository_list_filters_by_attribute():
    repo = InMemoryRepository[Team]()
    a, b = team("A"), team("B")
    repo.add(a)
    repo.add(b)
    assert repo.list(name="B") == [b]
    assert len(repo.list()) == 2


def test_repository_delete_of_referenced_row_is_blocked():
    repo = InMemoryRepository[Team]()
    t = team()
    repo.add(t)
    repo.mark_in_use(t.id)
    with pytest.raises(ReferenceInUse):
        repo.delete(t.id)


def test_default_catalog_is_seeded():
    catalog = default_catalog()
    assert catalog.exists("availability_level", "SERIOUS")
    assert catalog.get("availability_level", "SERIOUS").rpo_hours == 4
    assert not catalog.exists("function_category", "NOPE")


def test_catalog_unknown_kind_is_not_found():
    with pytest.raises(NotFound):
        default_catalog().exists("nope", "X")


def test_catalog_create_duplicate_and_delete():
    catalog = default_catalog()
    value = FunctionCategory(code="EXTRA", label="Extra")
    catalog.create("function_category", value)
    with pytest.raises(AlreadyExists):
        catalog.create("function_category", value)
    catalog.delete("function_category", "EXTRA")
    with pytest.raises(NotFound):
        catalog.get("function_category", "EXTRA")


def test_catalog_rename_and_rename_conflict():
    catalog = default_catalog()
    catalog.update("function_category", "BUSINESS", FunctionCategory(code="BIZ", label="Biz"))
    assert catalog.exists("function_category", "BIZ")
    assert not catalog.exists("function_category", "BUSINESS")
    with pytest.raises(AlreadyExists):
        catalog.update("function_category", "BIZ", FunctionCategory(code="COMMON", label="x"))


def test_catalog_delete_of_value_in_use_is_blocked():
    catalog = default_catalog()
    catalog.mark_in_use("function_category", "BUSINESS")
    with pytest.raises(ReferenceInUse):
        catalog.delete("function_category", "BUSINESS")
