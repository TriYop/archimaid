from typing import Any
from uuid import UUID

from archimaid.domain.entities import Entity
from archimaid.domain.errors import AlreadyExists, NotFound, ReferenceInUse
from archimaid.domain.reference import (
    REFERENCE_KINDS,
    AvailabilityLevel,
    ConfidentialityLevel,
    FunctionCategory,
    IntegrityLevel,
    ReferenceValue,
    TechnologyType,
    TechStandardStatus,
    TraceabilityLevel,
    UsageMode,
)
from archimaid.ports.repository import Repositories


class InMemoryRepository[T: Entity]:
    def __init__(self) -> None:
        self._items: dict[UUID, T] = {}
        self._in_use: set[UUID] = set()

    def mark_in_use(self, entity_id: UUID) -> None:
        self._in_use.add(entity_id)

    def add(self, entity: T) -> None:
        self._items[entity.id] = entity

    def get(self, entity_id: UUID) -> T | None:
        return self._items.get(entity_id)

    def list(self, **filters: Any) -> list[T]:
        return [
            item
            for item in self._items.values()
            if all(getattr(item, name) == value for name, value in filters.items())
        ]

    def update(self, entity: T) -> None:
        self._items[entity.id] = entity

    def delete(self, entity_id: UUID) -> None:
        if entity_id in self._in_use:
            raise ReferenceInUse(f"{entity_id} is still referenced")
        del self._items[entity_id]


class InMemoryReferenceCatalog:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, ReferenceValue]] = {kind: {} for kind in REFERENCE_KINDS}
        self._in_use: set[tuple[str, str]] = set()

    def mark_in_use(self, kind: str, code: str) -> None:
        self._in_use.add((kind, code))

    def _table(self, kind: str) -> dict[str, ReferenceValue]:
        try:
            return self._data[kind]
        except KeyError:
            raise NotFound(f"unknown reference kind {kind!r}") from None

    def exists(self, kind: str, code: str) -> bool:
        return code in self._table(kind)

    def get(self, kind: str, code: str) -> ReferenceValue:
        try:
            return self._table(kind)[code]
        except KeyError:
            raise NotFound(f"{kind} {code!r} not found") from None

    def list(self, kind: str) -> list[ReferenceValue]:
        table = self._table(kind)
        return [table[code] for code in sorted(table)]

    def create(self, kind: str, value: ReferenceValue) -> ReferenceValue:
        table = self._table(kind)
        if value.code in table:
            raise AlreadyExists(f"{kind} {value.code!r} already exists")
        table[value.code] = value
        return value

    def update(self, kind: str, code: str, value: ReferenceValue) -> ReferenceValue:
        table = self._table(kind)
        if code not in table:
            raise NotFound(f"{kind} {code!r} not found")
        if value.code != code and value.code in table:
            raise AlreadyExists(f"{kind} {value.code!r} already exists")
        del table[code]
        table[value.code] = value
        return value

    def delete(self, kind: str, code: str) -> None:
        table = self._table(kind)
        if code not in table:
            raise NotFound(f"{kind} {code!r} not found")
        if (kind, code) in self._in_use:
            raise ReferenceInUse(f"{kind} {code!r} is still referenced")
        del table[code]


def default_catalog() -> InMemoryReferenceCatalog:
    """A catalog seeded with the values the unit tests rely on."""
    catalog = InMemoryReferenceCatalog()
    levels = (("EXTREME", 4), ("SERIOUS", 3), ("MODERATE", 2), ("LOW", 1))
    for kind, cls in (
        ("confidentiality_level", ConfidentialityLevel),
        ("integrity_level", IntegrityLevel),
        ("traceability_level", TraceabilityLevel),
    ):
        for code, rank in levels:
            catalog.create(kind, cls(code=code, label=code.title(), rank=rank))
    rpo_rto = {"EXTREME": (2, 0), "SERIOUS": (4, 0), "MODERATE": (24, 24), "LOW": (72, 24)}
    for code, rank in levels:
        rpo, rto = rpo_rto[code]
        catalog.create(
            "availability_level",
            AvailabilityLevel(
                code=code, label=code.title(), rank=rank, rpo_hours=rpo, rto_hours=rto
            ),
        )
    for code in ("COMMON", "BUSINESS", "EXCHANGE", "DATA"):
        catalog.create("function_category", FunctionCategory(code=code, label=code.title()))
    for code in ("SOURCE", "CONSUMER", "PROXY"):
        catalog.create("usage_mode", UsageMode(code=code, label=code.title()))
    catalog.create("technology_type", TechnologyType(code="DATABASE", label="Database"))
    catalog.create("tech_standard_status", TechStandardStatus(code="REFERENCE", label="Reference"))
    return catalog


def fake_repositories() -> Repositories:
    return Repositories(
        teams=InMemoryRepository(),
        members=InMemoryRepository(),
        applications=InMemoryRepository(),
        functions=InMemoryRepository(),
        data_types=InMemoryRepository(),
        data_flows=InMemoryRepository(),
        technologies=InMemoryRepository(),
        personas=InMemoryRepository(),
    )
