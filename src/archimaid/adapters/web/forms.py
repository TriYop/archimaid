from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from fastapi import Request

from archimaid.adapters.web.resources import Field


async def form_data(request: Request) -> dict[str, str]:
    """FastAPI dependency: the submitted form as plain strings."""
    form = await request.form()
    return {key: value for key, value in form.items() if isinstance(value, str)}


def parse_form(
    form: Mapping[str, str],
    fields: Sequence[Field],
    *,
    uuid_fields: Sequence[str] = (),
) -> tuple[dict[str, Any], list[str]]:
    """Turn submitted strings into the dict a service expects, plus problem messages."""
    data: dict[str, Any] = {}
    problems: list[str] = []
    for field in fields:
        if field.widget == "readonly":
            continue
        raw = form.get(field.name, "").strip()
        try:
            data[field.name] = _convert(field, raw)
        except ValueError as exc:
            problems.append(f"{field.label}: {exc}")
    for name in uuid_fields:
        try:
            data[name] = UUID(form.get(name, "").strip())
        except ValueError:
            problems.append(f"{name} is missing or not a valid id")
    return data, problems


def _convert(field: Field, raw: str) -> Any:
    if field.widget in ("text", "textarea"):
        if raw or field.required or not field.nullable:
            return raw
        return None
    if field.widget == "number":
        if not raw:
            if field.required:
                raise ValueError("is required")
            return None
        try:
            return int(raw)
        except ValueError:
            raise ValueError("must be a whole number") from None
    if field.widget == "select_entity":
        if not raw:
            if field.required:
                raise ValueError("is required")
            return None
        try:
            return UUID(raw)
        except ValueError:
            raise ValueError("is not a valid choice") from None
    if not raw:  # select_ref
        if field.required:
            raise ValueError("is required")
        return None
    return raw
