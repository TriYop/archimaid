import logging
from dataclasses import asdict
from typing import Any

from sqlalchemy import Engine, Table, delete, insert, select, update
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.sql.expression import ColumnElement

from archimaid.adapters.persistence.pg_errors import is_foreign_key_violation, is_unique_violation
from archimaid.adapters.persistence.tables import REFERENCE_TABLES
from archimaid.domain.errors import AlreadyExists, InvalidEntity, NotFound, ReferenceInUse
from archimaid.domain.reference import REFERENCE_KINDS, ReferenceValue

logger = logging.getLogger(__name__)


class PostgresReferenceCatalog:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def exists(self, kind: str, code: str) -> bool:
        table = self._table(kind)
        with self._engine.connect() as conn:
            found = conn.execute(select(table.c.code).where(table.c.code == code)).first()
        return found is not None

    def get(self, kind: str, code: str) -> ReferenceValue:
        table = self._table(kind)
        with self._engine.connect() as conn:
            row = conn.execute(select(table).where(table.c.code == code)).first()
        if row is None:
            raise NotFound(f"{kind} {code!r} not found")
        return REFERENCE_KINDS[kind](**row._mapping)

    def list(self, kind: str) -> list[ReferenceValue]:
        table = self._table(kind)
        with self._engine.connect() as conn:
            rows = conn.execute(select(table).order_by(*self._ordering(table))).all()
        return [REFERENCE_KINDS[kind](**row._mapping) for row in rows]

    def create(self, kind: str, value: ReferenceValue) -> ReferenceValue:
        table = self._table(kind)
        try:
            with self._engine.begin() as conn:
                conn.execute(insert(table).values(**asdict(value)))
        except IntegrityError as exc:
            if is_unique_violation(exc):
                raise AlreadyExists(f"{kind} {value.code!r} already exists") from exc
            raise
        except DataError as exc:
            raise self._invalid(kind, exc) from exc
        return value

    def update(self, kind: str, code: str, value: ReferenceValue) -> ReferenceValue:
        table = self._table(kind)
        statement = update(table).where(table.c.code == code).values(**asdict(value))
        try:
            with self._engine.begin() as conn:
                matched = conn.execute(statement).rowcount
        except IntegrityError as exc:
            if is_unique_violation(exc):
                raise AlreadyExists(f"{kind} {value.code!r} already exists") from exc
            raise
        except DataError as exc:
            raise self._invalid(kind, exc) from exc
        if matched == 0:
            raise NotFound(f"{kind} {code!r} not found")
        return value

    def delete(self, kind: str, code: str) -> None:
        table = self._table(kind)
        try:
            with self._engine.begin() as conn:
                matched = conn.execute(delete(table).where(table.c.code == code)).rowcount
        except IntegrityError as exc:
            if is_foreign_key_violation(exc):
                raise ReferenceInUse(f"{kind} {code!r} is still referenced") from exc
            raise
        except DataError as exc:
            raise self._invalid(kind, exc) from exc
        if matched == 0:
            raise NotFound(f"{kind} {code!r} not found")

    @staticmethod
    def _ordering(table: Table) -> tuple[ColumnElement[Any], ...]:
        if "rank" in table.c:
            return (table.c.rank.desc(), table.c.code)
        return (table.c.code,)

    @staticmethod
    def _invalid(kind: str, exc: DataError) -> InvalidEntity:
        logger.debug("data error on %s: %s", kind, exc.orig)
        return InvalidEntity(f"{kind} contains a value the database cannot store")

    def _table(self, kind: str) -> Table:
        try:
            return REFERENCE_TABLES[kind]
        except KeyError:
            raise NotFound(f"unknown reference kind {kind!r}") from None
