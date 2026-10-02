from dataclasses import fields
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, Table, delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from archimaid.adapters.persistence.pg_errors import is_foreign_key_violation
from archimaid.adapters.persistence.tables import ENTITY_TABLES
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
from archimaid.domain.errors import DanglingReference, DomainError, ReferenceInUse
from archimaid.ports.repository import Repositories


class SqlRepository[T: Entity]:
    def __init__(self, engine: Engine, table: Table, entity_cls: type[T]) -> None:
        self._engine = engine
        self._table = table
        self._entity_cls = entity_cls

    def add(self, entity: T) -> None:
        values = {f.name: getattr(entity, f.name) for f in fields(entity)}
        self._write(insert(self._table).values(**values), DanglingReference)

    def get(self, entity_id: UUID) -> T | None:
        with self._engine.connect() as conn:
            row = conn.execute(select(self._table).where(self._table.c.id == entity_id)).first()
        return self._entity_cls(**row._mapping) if row else None

    def list(self, **filters: Any) -> list[T]:
        statement = select(self._table).order_by(self._table.c.created_at, self._table.c.id)
        for name, value in filters.items():
            statement = statement.where(self._table.c[name] == value)
        with self._engine.connect() as conn:
            rows = conn.execute(statement).all()
        return [self._entity_cls(**row._mapping) for row in rows]

    def update(self, entity: T) -> None:
        values = {
            f.name: getattr(entity, f.name)
            for f in fields(entity)
            if f.name not in ("id", "created_at")
        }
        statement = update(self._table).where(self._table.c.id == entity.id).values(**values)
        self._write(statement, DanglingReference)

    def delete(self, entity_id: UUID) -> None:
        self._write(delete(self._table).where(self._table.c.id == entity_id), ReferenceInUse)

    def _write(self, statement: Any, on_fk_violation: type[DomainError]) -> None:
        try:
            with self._engine.begin() as conn:
                conn.execute(statement)
        except IntegrityError as exc:
            if is_foreign_key_violation(exc):
                raise on_fk_violation(str(exc.orig).splitlines()[0]) from exc
            raise


def build_repositories(engine: Engine) -> Repositories:
    def repo[E: Entity](entity_cls: type[E]) -> SqlRepository[E]:
        return SqlRepository(engine, ENTITY_TABLES[entity_cls], entity_cls)

    return Repositories(
        teams=repo(Team),
        members=repo(TeamMember),
        applications=repo(Application),
        functions=repo(Function),
        data_types=repo(DataType),
        data_flows=repo(DataFlow),
        technologies=repo(Technology),
        personas=repo(Persona),
    )
