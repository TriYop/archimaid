from typing import Any
from uuid import UUID

from fastapi import FastAPI
from pydantic import BaseModel

from archimaid.adapters.api import schemas
from archimaid.adapters.api.crud_router import crud_router
from archimaid.adapters.api.errors import install_error_handlers
from archimaid.adapters.api.reference_router import reference_router
from archimaid.adapters.web.app import install_web
from archimaid.application.crud import CrudService
from archimaid.application.services import Services


def create_app(services: Services) -> FastAPI:
    app = FastAPI(title="Archimaid")
    install_error_handlers(app)

    def team_parent(team_id: UUID) -> UUID:
        services.teams.get(team_id)  # 404 if the team does not exist
        return team_id

    def application_parent(application_id: UUID) -> UUID:
        services.applications.get(application_id)  # 404 if the application does not exist
        return application_id

    app.include_router(
        crud_router(service=services.teams, in_model=schemas.TeamIn, out_model=schemas.TeamOut),
        prefix="/teams",
        tags=["teams"],
    )
    app.include_router(
        crud_router(
            service=services.members,
            in_model=schemas.TeamMemberIn,
            out_model=schemas.TeamMemberOut,
            parent_field="team_id",
            parent_dependency=team_parent,
        ),
        prefix="/teams/{team_id}/members",
        tags=["teams"],
    )
    app.include_router(
        crud_router(
            service=services.applications,
            in_model=schemas.ApplicationIn,
            out_model=schemas.ApplicationOut,
            filters={"team_id": UUID},
        ),
        prefix="/applications",
        tags=["applications"],
    )
    nested: tuple[tuple[str, CrudService[Any], type[BaseModel], type[BaseModel]], ...] = (
        ("functions", services.functions, schemas.FunctionIn, schemas.FunctionOut),
        ("data-types", services.data_types, schemas.DataTypeIn, schemas.DataTypeOut),
        ("technologies", services.technologies, schemas.TechnologyIn, schemas.TechnologyOut),
    )
    for segment, service, in_model, out_model in nested:
        app.include_router(
            crud_router(
                service=service,
                in_model=in_model,
                out_model=out_model,
                parent_field="application_id",
                parent_dependency=application_parent,
            ),
            prefix=f"/applications/{{application_id}}/{segment}",
            tags=["applications"],
        )
    app.include_router(
        crud_router(
            service=services.data_flows,
            in_model=schemas.DataFlowIn,
            out_model=schemas.DataFlowOut,
            filters={
                "source_application_id": UUID,
                "target_application_id": UUID,
                "data_type_id": UUID,
            },
        ),
        prefix="/data-flows",
        tags=["data-flows"],
    )
    app.include_router(
        crud_router(
            service=services.personas,
            in_model=schemas.PersonaIn,
            out_model=schemas.PersonaOut,
        ),
        prefix="/personas",
        tags=["personas"],
    )
    app.include_router(reference_router(services.reference))
    install_web(app, services)
    return app
