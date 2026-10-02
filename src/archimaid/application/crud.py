from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from archimaid.domain.entities import Entity
from archimaid.domain.errors import DanglingReference, InvalidReferenceCode, NotFound
from archimaid.ports.reference_catalog import ReferenceCatalog
from archimaid.ports.repository import Repository


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ParentLink:
    """An id field of the entity that must exist in ``repository``."""

    field: str
    repository: Repository[Any]


class CrudService[T: Entity]:
    def __init__(
        self,
        entity_cls: type[T],
        repository: Repository[T],
        catalog: ReferenceCatalog,
        *,
        reference_fields: Mapping[str, str] | None = None,
        parents: Sequence[ParentLink] = (),
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._entity_cls = entity_cls
        self._repo = repository
        self._catalog = catalog
        self._reference_fields = dict(reference_fields or {})
        self._parents = tuple(parents)
        self._clock = clock

    def create(self, data: Mapping[str, Any]) -> T:
        now = self._clock()
        entity = self._entity_cls(id=uuid4(), created_at=now, updated_at=now, **data)
        self._check(entity)
        self._repo.add(entity)
        return entity

    def get(self, entity_id: UUID) -> T:
        entity = self._repo.get(entity_id)
        if entity is None:
            raise NotFound(f"{self._entity_cls.__name__} {entity_id} not found")
        return entity

    def list(self, **filters: Any) -> list[T]:
        return self._repo.list(**filters)

    def update(self, entity_id: UUID, data: Mapping[str, Any]) -> T:
        existing = self.get(entity_id)
        updated = replace(existing, **data, updated_at=self._clock())
        self._check(updated)
        self._repo.update(updated)
        return updated

    def delete(self, entity_id: UUID) -> None:
        self.get(entity_id)
        self._repo.delete(entity_id)

    def present_many(self, entities: Sequence[T]) -> Sequence[Any]:
        """Objects handed to the API layer. Subclasses may add derived fields."""
        return list(entities)

    def _check(self, entity: T) -> None:
        entity.validate()
        for field, kind in self._reference_fields.items():
            code = getattr(entity, field)
            if code is not None and not self._catalog.exists(kind, code):
                raise InvalidReferenceCode(f"{code!r} is not a valid {kind}")
        for link in self._parents:
            parent_id = getattr(entity, link.field)
            if parent_id is not None and link.repository.get(parent_id) is None:
                raise DanglingReference(f"{link.field} {parent_id} does not exist")
