from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from archimaid.application.applications import ApplicationService
from archimaid.application.crud import CrudService, ParentLink, utc_now
from archimaid.application.reference_admin import ReferenceAdminService
from archimaid.domain.entities import (
    Application,
    DataFlow,
    DataType,
    Function,
    Persona,
    Team,
    TeamMember,
    Technology,
)
from archimaid.ports.reference_catalog import ReferenceCatalog
from archimaid.ports.repository import Repositories


@dataclass
class Services:
    teams: CrudService[Team]
    members: CrudService[TeamMember]
    applications: ApplicationService
    functions: CrudService[Function]
    data_types: CrudService[DataType]
    data_flows: CrudService[DataFlow]
    technologies: CrudService[Technology]
    personas: CrudService[Persona]
    reference: ReferenceAdminService


def build_services(
    repos: Repositories,
    catalog: ReferenceCatalog,
    clock: Callable[[], datetime] = utc_now,
) -> Services:
    return Services(
        teams=CrudService(Team, repos.teams, catalog, clock=clock),
        members=CrudService(
            TeamMember,
            repos.members,
            catalog,
            parents=[ParentLink("team_id", repos.teams)],
            clock=clock,
        ),
        applications=ApplicationService(
            Application,
            repos.applications,
            catalog,
            reference_fields={
                "confidentiality_level": "confidentiality_level",
                "integrity_level": "integrity_level",
                "availability_level": "availability_level",
                "traceability_level": "traceability_level",
            },
            parents=[ParentLink("team_id", repos.teams)],
            clock=clock,
        ),
        functions=CrudService(
            Function,
            repos.functions,
            catalog,
            reference_fields={"category": "function_category"},
            parents=[
                ParentLink("application_id", repos.applications),
                ParentLink("persona_id", repos.personas),
            ],
            clock=clock,
        ),
        data_types=CrudService(
            DataType,
            repos.data_types,
            catalog,
            reference_fields={"confidentiality_level": "confidentiality_level"},
            parents=[ParentLink("application_id", repos.applications)],
            clock=clock,
        ),
        data_flows=CrudService(
            DataFlow,
            repos.data_flows,
            catalog,
            reference_fields={"usage_mode": "usage_mode"},
            parents=[
                ParentLink("source_application_id", repos.applications),
                ParentLink("target_application_id", repos.applications),
                ParentLink("data_type_id", repos.data_types),
            ],
            clock=clock,
        ),
        technologies=CrudService(
            Technology,
            repos.technologies,
            catalog,
            reference_fields={
                "type": "technology_type",
                "standard_status": "tech_standard_status",
            },
            parents=[ParentLink("application_id", repos.applications)],
            clock=clock,
        ),
        personas=CrudService(Persona, repos.personas, catalog, clock=clock),
        reference=ReferenceAdminService(catalog),
    )
