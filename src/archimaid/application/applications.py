from collections.abc import Sequence
from dataclasses import fields
from typing import Any

from archimaid.application.crud import CrudService
from archimaid.domain.entities import Application
from archimaid.domain.reference import AvailabilityLevel


class ApplicationService(CrudService[Application]):
    def present_many(self, entities: Sequence[Application]) -> list[Any]:
        """Entity fields plus ``rpo``/``rto`` read from the availability_level catalog."""
        levels = {
            value.code: value
            for value in self._catalog.list("availability_level")
            if isinstance(value, AvailabilityLevel)
        }
        rows: list[Any] = []
        for app in entities:
            row = {f.name: getattr(app, f.name) for f in fields(app)}
            level = levels.get(app.availability_level) if app.availability_level else None
            row["rpo"] = level.rpo_hours if level else None
            row["rto"] = level.rto_hours if level else None
            rows.append(row)
        return rows
