from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar
from uuid import UUID

from archimaid.domain.errors import InvalidEntity


@dataclass(kw_only=True)
class Entity:
    id: UUID
    created_at: datetime
    updated_at: datetime

    required_text: ClassVar[tuple[str, ...]] = ("name",)

    def validate(self) -> bool:
        """Return True, or raise InvalidEntity if a required text field is blank."""
        for attr in self.required_text:
            value = getattr(self, attr)
            if not value or not value.strip():
                raise InvalidEntity(f"{attr} must not be blank")
        return True


@dataclass(kw_only=True)
class Team(Entity):
    name: str
    description: str = ""


@dataclass(kw_only=True)
class TeamMember(Entity):
    required_text: ClassVar[tuple[str, ...]] = ("user_id", "name")

    team_id: UUID
    user_id: str
    name: str


@dataclass(kw_only=True)
class Application(Entity):
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


@dataclass(kw_only=True)
class Function(Entity):
    application_id: UUID
    name: str
    description: str | None = None
    category: str | None = None
    persona_id: UUID | None = None


@dataclass(kw_only=True)
class DataType(Entity):
    application_id: UUID
    name: str
    definition: str | None = None
    specificity: str | None = None
    confidentiality_level: str | None = None
    golden_source: str | None = None
    golden_replica: str | None = None


@dataclass(kw_only=True)
class DataFlow(Entity):
    required_text: ClassVar[tuple[str, ...]] = ()

    source_application_id: UUID
    target_application_id: UUID
    data_type_id: UUID
    source_function_id: UUID | None = None
    target_function_id: UUID | None = None
    usage_mode: str | None = None
    usage_explanation: str | None = None


@dataclass(kw_only=True)
class Technology(Entity):
    application_id: UUID
    name: str
    version: str | None = None
    family: str | None = None
    type: str | None = None
    standard_status: str | None = None
    standard_status_details: str | None = None
    tech_standards_link: str | None = None
    action_plan: str | None = None


@dataclass(kw_only=True)
class Persona(Entity):
    name: str
    description: str | None = None
    category: str | None = None
