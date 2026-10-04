from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class TeamIn(BaseModel):
    name: str
    description: str = ""


class TeamOut(_Out, TeamIn):
    pass


class TeamMemberIn(BaseModel):
    user_id: str
    name: str


class TeamMemberOut(_Out, TeamMemberIn):
    team_id: UUID


class ApplicationIn(BaseModel):
    team_id: UUID
    name: str
    golden_app_id: str | None = None
    auid: str | None = None
    description: str | None = None
    asset_cmdb: str | None = None
    shortname: str | None = None
    owner_uid: str | None = None
    confidentiality_level: str | None = None
    integrity_level: str | None = None
    availability_level: str | None = None
    traceability_level: str | None = None


class ApplicationOut(_Out, ApplicationIn):
    rpo: int | None = None  # hours, derived from availability_level
    rto: int | None = None  # hours, derived from availability_level


class FunctionIn(BaseModel):
    name: str
    description: str | None = None
    category: str | None = None
    persona_id: UUID | None = None


class FunctionOut(_Out, FunctionIn):
    application_id: UUID


class DataTypeIn(BaseModel):
    name: str
    definition: str | None = None
    specificity: str | None = None
    confidentiality_level: str | None = None
    golden_source: str | None = None
    golden_replica: str | None = None


class DataTypeOut(_Out, DataTypeIn):
    application_id: UUID


class DataFlowIn(BaseModel):
    source_application_id: UUID
    target_application_id: UUID
    data_type_id: UUID
    source_function_id: UUID | None = None
    target_function_id: UUID | None = None
    usage_mode: str | None = None
    usage_explanation: str | None = None


class DataFlowOut(_Out, DataFlowIn):
    pass


class TechnologyIn(BaseModel):
    name: str
    version: str | None = None
    family: str | None = None
    type: str | None = None
    standard_status: str | None = None
    standard_status_details: str | None = None
    tech_standards_link: str | None = None
    action_plan: str | None = None


class TechnologyOut(_Out, TechnologyIn):
    application_id: UUID


class PersonaIn(BaseModel):
    name: str
    description: str | None = None
    category: str | None = None


class PersonaOut(_Out, PersonaIn):
    pass
