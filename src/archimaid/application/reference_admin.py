from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from archimaid.domain.errors import NotFound
from archimaid.domain.reference import REFERENCE_KINDS, ReferenceValue
from archimaid.ports.reference_catalog import ReferenceCatalog


class ReferenceAdminService:
    def __init__(self, catalog: ReferenceCatalog) -> None:
        self._catalog = catalog

    def kinds(self) -> list[str]:
        return list(REFERENCE_KINDS)

    def list(self, kind: str) -> list[ReferenceValue]:
        self._require(kind)
        return self._catalog.list(kind)

    def get(self, kind: str, code: str) -> ReferenceValue:
        self._require(kind)
        return self._catalog.get(kind, code)

    def create(self, kind: str, data: Mapping[str, Any]) -> ReferenceValue:
        value = self._build(kind, data)
        return self._catalog.create(kind, value)

    def update(self, kind: str, code: str, data: Mapping[str, Any]) -> ReferenceValue:
        value = self._build(kind, data)
        return self._catalog.update(kind, code, value)

    def delete(self, kind: str, code: str) -> None:
        self._require(kind)
        self._catalog.delete(kind, code)

    def _require(self, kind: str) -> type[ReferenceValue]:
        try:
            return REFERENCE_KINDS[kind]
        except KeyError:
            raise NotFound(f"unknown reference kind {kind!r}") from None

    def _build(self, kind: str, data: Mapping[str, Any]) -> ReferenceValue:
        return self._require(kind)(**data)
