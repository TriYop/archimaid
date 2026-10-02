import logging
from dataclasses import fields
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, Table, delete, insert, select, update
from sqlalchemy.exc import DataError, IntegrityError

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
from archimaid.domain.errors import DanglingReference, InvalidEntity, ReferenceInUse
from archimaid.ports.repository import Repositories

logger = logging.getLogger(__name__)


class SqlRepository[T: Entity]:
    def __init__(self, engine: Engine, table: Table, entity_cls: type[T]) -> None:
        self._engine = engine
        self._table = table
        self._entity_cls = entity_cls

    def add(self, entity: T) -> None:
        values = {f.name: getattr(entity, f.name) for f in fields(entity)}
        self._write(insert(self._table).values(**values), entity.id, deleting=False)

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
        self._write(statement, entity.id, deleting=False)

    def delete(self, entity_id: UUID) -> None:
        self._write(
            delete(self._table).where(self._table.c.id == entity_id), entity_id, deleting=True
        )

    def _write(self, statement: Any, entity_id: UUID, *, deleting: bool) -> None:
        name = self._entity_cls.__name__
        try:
            with self._engine.begin() as conn:
                conn.execute(statement)
        except IntegrityError as exc:
            if not is_foreign_key_violation(exc):
                raise
            logger.debug("foreign key violation on %s %s: %s", name, entity_id, exc.orig)
            if deleting:
                raise ReferenceInUse(
                    f"{name} {entity_id} is still referenced by other records"
                ) from exc
            raise DanglingReference(f"{name} references a row that does not exist") from exc
        except DataError as exc:
            logger.debug("data error on %s %s: %s", name, entity_id, exc.orig)
            raise InvalidEntity(f"{name} contains a value the database cannot store") from exc


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
