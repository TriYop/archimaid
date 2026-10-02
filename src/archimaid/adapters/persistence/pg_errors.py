from psycopg import errors
from sqlalchemy.exc import IntegrityError


def is_foreign_key_violation(exc: IntegrityError) -> bool:
    return isinstance(exc.orig, errors.ForeignKeyViolation | errors.RestrictViolation)


def is_unique_violation(exc: IntegrityError) -> bool:
    return isinstance(exc.orig, errors.UniqueViolation)
