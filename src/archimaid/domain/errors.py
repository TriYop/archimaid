class DomainError(Exception):
    """Base class for all domain errors."""


class NotFound(DomainError):
    """The requested entity, catalog kind or catalog value does not exist."""


class InvalidEntity(DomainError):
    """An entity or value object violates a domain rule (e.g. blank required text)."""


class InvalidReferenceCode(DomainError):
    """A field holds a code that is not in its configuration table."""


class DanglingReference(DomainError):
    """An id field points to a row that does not exist."""


class ReferenceInUse(DomainError):
    """The row cannot be deleted because other rows still reference it."""


class AlreadyExists(DomainError):
    """A configuration value with that code already exists."""
