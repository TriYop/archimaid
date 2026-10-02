from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, ValidationError

from archimaid.application.reference_admin import ReferenceAdminService
from archimaid.domain.errors import NotFound
from archimaid.domain.reference import REFERENCE_KINDS, AvailabilityLevel, RankedValue


class ReferenceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    label: str
    description: str | None = None


class RankedReferenceIn(ReferenceIn):
    rank: int


class AvailabilityReferenceIn(RankedReferenceIn):
    rpo_hours: int
    rto_hours: int


def _model_for(kind: str) -> type[BaseModel]:
    cls = REFERENCE_KINDS.get(kind)
    if cls is None:
        raise NotFound(f"unknown reference kind {kind!r}")
    if issubclass(cls, AvailabilityLevel):
        return AvailabilityReferenceIn
    if issubclass(cls, RankedValue):
        return RankedReferenceIn
    return ReferenceIn


def _validated(kind: str, body: dict[str, Any]) -> dict[str, Any]:
    model = _model_for(kind)  # unknown kind -> 404 before body validation
    try:
        return model.model_validate(body).model_dump()
    except ValidationError as exc:
        raise RequestValidationError(
            exc.errors(include_url=False, include_context=False)
        ) from exc


def reference_router(service: ReferenceAdminService) -> APIRouter:
    router = APIRouter(prefix="/reference", tags=["reference"])

    @router.get("")
    def list_kinds():
        return service.kinds()

    @router.get("/{kind}")
    def list_values(kind: str):
        return [asdict(value) for value in service.list(kind)]

    @router.post("/{kind}", status_code=201)
    def create_value(kind: str, body: dict[str, Any]):
        return asdict(service.create(kind, _validated(kind, body)))

    @router.get("/{kind}/{code}")
    def get_value(kind: str, code: str):
        return asdict(service.get(kind, code))

    @router.put("/{kind}/{code}")
    def replace_value(kind: str, code: str, body: dict[str, Any]):
        return asdict(service.update(kind, code, _validated(kind, body)))

    @router.delete("/{kind}/{code}", status_code=204)
    def delete_value(kind: str, code: str):
        service.delete(kind, code)
        return Response(status_code=204)

    return router
