from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from archimaid.domain.entities import (
    Application,
    DataFlow,
    DataType,
    Entity,
    Function,
    Persona,
    Team,
    TeamMember,
    Technology,
)


class Repository[T: Entity](Protocol):
    def add(self, entity: T) -> None: ...

    def get(self, entity_id: UUID) -> T | None: ...

    def list(self, **filters: Any) -> list[T]:
        """Return entities whose attributes equal every given filter value."""
        ...

    def update(self, entity: T) -> None: ...

    def delete(self, entity_id: UUID) -> None:
        """Delete the entity. Raises ReferenceInUse if other rows still reference it."""
        ...


@dataclass
class Repositories:
    teams: Repository[Team]
    members: Repository[TeamMember]
    applications: Repository[Application]
    functions: Repository[Function]
    data_types: Repository[DataType]
    data_flows: Repository[DataFlow]
    technologies: Repository[Technology]
    personas: Repository[Persona]
