from dataclasses import asdict

from sqlalchemy import Engine, Table, delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from archimaid.adapters.persistence.pg_errors import is_foreign_key_violation, is_unique_violation
from archimaid.adapters.persistence.tables import REFERENCE_TABLES
from archimaid.domain.errors import AlreadyExists, NotFound, ReferenceInUse
from archimaid.domain.reference import REFERENCE_KINDS, ReferenceValue


class PostgresReferenceCatalog:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def exists(self, kind: str, code: str) -> bool:
        table = self._table(kind)
        with self._engine.connect() as conn:
            return conn.execute(select(table.c.code).where(table.c.code == code)).first() is not None

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
            rows = conn.execute(select(table).order_by(table.c.code)).all()
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
        if matched == 0:
            raise NotFound(f"{kind} {code!r} not found")

    def _table(self, kind: str) -> Table:
        try:
            return REFERENCE_TABLES[kind]
        except KeyError:
            raise NotFound(f"unknown reference kind {kind!r}") from None
