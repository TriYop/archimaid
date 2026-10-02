from typing import Protocol

from archimaid.domain.reference import ReferenceValue


class ReferenceCatalog(Protocol):
    """Access to the configuration tables. An unknown ``kind`` raises NotFound."""

    def exists(self, kind: str, code: str) -> bool: ...

    def get(self, kind: str, code: str) -> ReferenceValue: ...

    def list(self, kind: str) -> list[ReferenceValue]: ...

    def create(self, kind: str, value: ReferenceValue) -> ReferenceValue:
        """Raises AlreadyExists if the code is taken."""
        ...

    def update(self, kind: str, code: str, value: ReferenceValue) -> ReferenceValue:
        """Replace the value. A different ``value.code`` renames it (and cascades).

        Raises NotFound if ``code`` is unknown, AlreadyExists if the new code is taken.
        """
        ...

    def delete(self, kind: str, code: str) -> None:
        """Raises NotFound, or ReferenceInUse if entities still reference the value."""
        ...
