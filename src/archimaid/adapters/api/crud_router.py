from collections.abc import Callable, Mapping
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from archimaid.application.crud import CrudService
from archimaid.domain.entities import Entity
from archimaid.domain.errors import InvalidEntity, NotFound


def _no_parent() -> None:
    return None


def crud_router[T: Entity](
    *,
    service: CrudService[T],
    in_model: type[BaseModel],
    out_model: type[BaseModel],
    parent_field: str | None = None,
    parent_dependency: Callable[..., UUID] | None = None,
    filters: Mapping[str, type] | None = None,
) -> APIRouter:
    """CRUD routes for one entity.

    For a nested resource pass ``parent_field`` (the entity's id field for the parent) and a
    ``parent_dependency`` that declares the path parameter, checks the parent exists (404) and
    returns its id. ``filters`` maps query-parameter names to a converter (e.g. ``UUID``).
    """
    router = APIRouter()
    parent_dep = parent_dependency or _no_parent
    query_filters = filters or {}

    def present(entities: list[T]) -> list[BaseModel]:
        return [out_model.model_validate(item) for item in service.present_many(entities)]

    def scoped(entity_id: UUID, parent: UUID | None) -> T:
        entity = service.get(entity_id)
        if parent_field is not None and getattr(entity, parent_field) != parent:
            raise NotFound(f"{type(entity).__name__} {entity_id} not found")
        return entity

    @router.get("", response_model=list[out_model])  # type: ignore[valid-type]  # dynamic model
    def list_items(request: Request, parent: UUID | None = Depends(parent_dep)):
        selected: dict[str, Any] = {}
        for name, convert in query_filters.items():
            if name in request.query_params:
                try:
                    selected[name] = convert(request.query_params[name])
                except ValueError as exc:
                    raise InvalidEntity(f"invalid value for {name}") from exc
        if parent_field is not None:
            selected[parent_field] = parent
        return present(service.list(**selected))

    @router.post("", status_code=201, response_model=out_model)
    def create_item(body: in_model, parent: UUID | None = Depends(parent_dep)):  # type: ignore[valid-type]
        data = body.model_dump()  # type: ignore[attr-defined]
        if parent_field is not None:
            data[parent_field] = parent
        return present([service.create(data)])[0]

    @router.get("/{entity_id}", response_model=out_model)
    def get_item(entity_id: UUID, parent: UUID | None = Depends(parent_dep)):
        return present([scoped(entity_id, parent)])[0]

    @router.put("/{entity_id}", response_model=out_model)
    def replace_item(
        entity_id: UUID,
        body: in_model,  # type: ignore[valid-type]
        parent: UUID | None = Depends(parent_dep),
    ):
        scoped(entity_id, parent)
        return present([service.update(entity_id, body.model_dump())])[0]  # type: ignore[attr-defined]

    @router.delete("/{entity_id}", status_code=204)
    def delete_item(entity_id: UUID, parent: UUID | None = Depends(parent_dep)):
        scoped(entity_id, parent)
        service.delete(entity_id)
        return Response(status_code=204)

    return router
