from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from archimaid.domain.reference import REFERENCE_KINDS

Widget = Literal["text", "textarea", "number", "select_ref", "select_entity", "readonly"]


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    widget: Widget = "text"
    required: bool = False
    nullable: bool = True
    kind: str | None = None  # select_ref: the catalog kind
    source: str | None = None  # select_entity: "personas" | "applications" | "data_types"


@dataclass(frozen=True)
class Resource:
    slug: str  # id prefix in the HTML, e.g. "team"
    title: str  # singular noun used in buttons and messages
    base: str  # URL template, e.g. "/ui/applications/{application_id}/functions"
    service_name: str  # attribute of Services that handles it
    fields: tuple[Field, ...]
    table_fields: tuple[str, ...] | None = None  # columns shown (default: all)
    form_fields: tuple[str, ...] | None = None  # fields in add/edit forms (default: editable)
    parent_field: str | None = None  # nested: entity field set from the path
    hidden_uuid: tuple[str, ...] = ()  # extra UUID inputs accepted on add (sent hidden)
    page: str | None = None  # "/ui/teams/{id}": the record's own page
    after_delete: str | None = None  # where to go after deleting it from its own page
    delete_warning: str | None = None

    def field(self, name: str) -> Field:
        return next(f for f in self.fields if f.name == name)

    def columns(self) -> tuple[Field, ...]:
        if self.table_fields is None:
            return self.fields
        return tuple(self.field(name) for name in self.table_fields)

    def editable(self) -> tuple[Field, ...]:
        return tuple(f for f in self.fields if f.widget != "readonly")

    def form(self) -> tuple[Field, ...]:
        if self.form_fields is None:
            return self.editable()
        return tuple(self.field(name) for name in self.form_fields)

    def url(self, ctx: Mapping[str, Any]) -> str:
        return self.base.format(**ctx)

    def confirm_delete(self) -> str:
        return self.delete_warning or f"Delete this {self.title.lower()}?"


def _level(name: str, label: str) -> Field:
    return Field(name, label, "select_ref", kind=name)


TEAM = Resource(
    slug="team",
    title="Team",
    base="/ui/teams",
    service_name="teams",
    fields=(
        Field("name", "Name", required=True),
        Field("description", "Description", "textarea", nullable=False),
    ),
    page="/ui/teams/{id}",
    after_delete="/ui/teams",
    delete_warning="Delete this team?",
)

MEMBER = Resource(
    slug="member",
    title="Member",
    base="/ui/teams/{team_id}/members",
    service_name="members",
    fields=(
        Field("user_id", "User id", required=True),
        Field("name", "Name", required=True),
    ),
    parent_field="team_id",
)

APPLICATION = Resource(
    slug="application",
    title="Application",
    base="/ui/applications",
    service_name="applications",
    fields=(
        Field("name", "Name", required=True),
        Field("shortname", "Short name"),
        Field("golden_app_id", "Golden app id"),
        Field("auid", "AUID"),
        Field("asset_cmdb", "Asset CMDB"),
        Field("owner_uid", "Owner uid"),
        Field("description", "Description", "textarea"),
        _level("confidentiality_level", "Confidentiality"),
        _level("integrity_level", "Integrity"),
        _level("availability_level", "Availability"),
        _level("traceability_level", "Traceability"),
        Field("rpo_rto", "RPO / RTO", "readonly"),
    ),
    table_fields=(
        "name",
        "shortname",
        "confidentiality_level",
        "integrity_level",
        "availability_level",
        "traceability_level",
        "rpo_rto",
    ),
    form_fields=(
        "name",
        "shortname",
        "confidentiality_level",
        "integrity_level",
        "availability_level",
        "traceability_level",
    ),
    hidden_uuid=("team_id",),
    page="/ui/applications/{id}",
    after_delete="/ui/teams/{team_id}",
    delete_warning="Delete this application and its functions, data types and technologies?",
)

FUNCTION = Resource(
    slug="function",
    title="Function",
    base="/ui/applications/{application_id}/functions",
    service_name="functions",
    fields=(
        Field("name", "Name", required=True),
        Field("description", "Description", "textarea"),
        Field("category", "Category", "select_ref", kind="function_category"),
        Field("persona_id", "Persona", "select_entity", source="personas"),
    ),
    parent_field="application_id",
)

DATA_TYPE = Resource(
    slug="data-type",
    title="Data type",
    base="/ui/applications/{application_id}/data-types",
    service_name="data_types",
    fields=(
        Field("name", "Name", required=True),
        Field("definition", "Definition", "textarea"),
        Field("specificity", "Specificity"),
        _level("confidentiality_level", "Confidentiality"),
        Field("golden_source", "Golden source"),
        Field("golden_replica", "Golden replica"),
    ),
    parent_field="application_id",
)

TECHNOLOGY = Resource(
    slug="technology",
    title="Technology",
    base="/ui/applications/{application_id}/technologies",
    service_name="technologies",
    fields=(
        Field("name", "Name", required=True),
        Field("version", "Version"),
        Field("family", "Family"),
        Field("type", "Type", "select_ref", kind="technology_type"),
        Field("standard_status", "Standard status", "select_ref", kind="tech_standard_status"),
        Field("standard_status_details", "Status details", "textarea"),
        Field("tech_standards_link", "Standards link"),
        Field("action_plan", "Action plan", "textarea"),
    ),
    parent_field="application_id",
)

DATA_FLOW = Resource(
    slug="data-flow",
    title="Data flow",
    base="/ui/data-flows",
    service_name="data_flows",
    fields=(
        Field("source_application_id", "Source application", "select_entity", required=True, source="applications"),
        Field("target_application_id", "Target application", "select_entity", required=True, source="applications"),
        Field("data_type_id", "Data type", "select_entity", required=True, source="data_types"),
        Field("usage_mode", "Usage mode", "select_ref", kind="usage_mode"),
        Field("usage_explanation", "Usage explanation"),
    ),
)

PERSONA = Resource(
    slug="persona",
    title="Persona",
    base="/ui/personas",
    service_name="personas",
    fields=(
        Field("name", "Name", required=True),
        Field("description", "Description", "textarea"),
        Field("category", "Category"),
    ),
)

ALL_RESOURCES = (TEAM, MEMBER, APPLICATION, FUNCTION, DATA_TYPE, TECHNOLOGY, DATA_FLOW, PERSONA)

TABS = (
    ("details", "Details"),
    ("functions", "Functions"),
    ("data-types", "Data types"),
    ("technologies", "Technologies"),
    ("data-flows", "Data flows"),
)


def reference_resource(kind: str) -> Resource:
    """The editable table for one configuration catalog; its columns follow the value object."""
    names = {f.name for f in dataclasses.fields(REFERENCE_KINDS[kind])}
    fields = [
        Field("code", "Code", required=True),
        Field("label", "Label", required=True),
        Field("description", "Description", "textarea"),
    ]
    if "rank" in names:
        fields.append(Field("rank", "Rank", "number", required=True))
    if "rpo_hours" in names:
        fields.append(Field("rpo_hours", "RPO (hours)", "number", required=True))
        fields.append(Field("rto_hours", "RTO (hours)", "number", required=True))
    return Resource(
        slug=f"ref-{kind}",
        title="Value",
        base=f"/ui/reference/{kind}",
        service_name="reference",
        fields=tuple(fields),
    )
