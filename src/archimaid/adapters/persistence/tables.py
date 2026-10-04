from dataclasses import fields
from typing import Any

from sqlalchemy import Column, DateTime, ForeignKey, Integer, MetaData, Table, Text, Uuid

from archimaid.domain.entities import (
    Application,
    DataFlow,
    DataType,
    Entity,
    Function,
    Persona,
    Team,
    TeamMember,
    Technology,
)
from archimaid.domain.reference import REFERENCE_KINDS, ReferenceValue

metadata = MetaData()


def _catalog_table(kind: str, cls: type[ReferenceValue]) -> Table:
    base = {"code", "label", "description"}
    columns: list[Column[Any]] = [
        Column("code", Text, primary_key=True),
        Column("label", Text, nullable=False),
        Column("description", Text),
    ]
    columns += [Column(f.name, Integer, nullable=False) for f in fields(cls) if f.name not in base]
    return Table(kind, metadata, *columns)


REFERENCE_TABLES: dict[str, Table] = {
    kind: _catalog_table(kind, cls) for kind, cls in REFERENCE_KINDS.items()
}


def _id() -> Column:
    return Column("id", Uuid, primary_key=True)


def _timestamps() -> list[Column]:
    return [
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
    ]


def _text(name: str, nullable: bool = True) -> Column:
    return Column(name, Text, nullable=nullable)


def _code_ref(column: str, kind: str) -> Column:
    return Column(
        column,
        Text,
        ForeignKey(f"{kind}.code", onupdate="CASCADE", ondelete="RESTRICT"),
    )


def _id_ref(column: str, table: str, ondelete: str, nullable: bool = False) -> Column:
    return Column(column, Uuid, ForeignKey(f"{table}.id", ondelete=ondelete), nullable=nullable)


team = Table(
    "team",
    metadata,
    _id(),
    _text("name", nullable=False),
    Column("description", Text, nullable=False, server_default=""),
    *_timestamps(),
)

team_member = Table(
    "team_member",
    metadata,
    _id(),
    _id_ref("team_id", "team", "CASCADE"),
    _text("user_id", nullable=False),
    _text("name", nullable=False),
    *_timestamps(),
)

application = Table(
    "application",
    metadata,
    _id(),
    _id_ref("team_id", "team", "RESTRICT"),
    _text("name", nullable=False),
    _text("golden_app_id"),
    _text("auid"),
    _text("description"),
    _text("asset_cmdb"),
    _text("shortname"),
    _text("owner_uid"),
    _code_ref("confidentiality_level", "confidentiality_level"),
    _code_ref("integrity_level", "integrity_level"),
    _code_ref("availability_level", "availability_level"),
    _code_ref("traceability_level", "traceability_level"),
    *_timestamps(),
)

persona = Table(
    "persona",
    metadata,
    _id(),
    _text("name", nullable=False),
    _text("description"),
    _text("category"),
    *_timestamps(),
)

function = Table(
    "function",
    metadata,
    _id(),
    _id_ref("application_id", "application", "CASCADE"),
    _id_ref("persona_id", "persona", "RESTRICT", nullable=True),
    _text("name", nullable=False),
    _text("description"),
    _code_ref("category", "function_category"),
    *_timestamps(),
)

data_type = Table(
    "data_type",
    metadata,
    _id(),
    _id_ref("application_id", "application", "CASCADE"),
    _text("name", nullable=False),
    _text("definition"),
    _text("specificity"),
    _code_ref("confidentiality_level", "confidentiality_level"),
    _text("golden_source"),
    _text("golden_replica"),
    *_timestamps(),
)

data_flow = Table(
    "data_flow",
    metadata,
    _id(),
    _id_ref("source_application_id", "application", "RESTRICT"),
    _id_ref("target_application_id", "application", "RESTRICT"),
    _id_ref("data_type_id", "data_type", "RESTRICT"),
    _id_ref("source_function_id", "function", "SET NULL", nullable=True),
    _id_ref("target_function_id", "function", "SET NULL", nullable=True),
    _code_ref("usage_mode", "usage_mode"),
    _text("usage_explanation"),
    *_timestamps(),
)

technology = Table(
    "technology",
    metadata,
    _id(),
    _id_ref("application_id", "application", "CASCADE"),
    _text("name", nullable=False),
    _text("version"),
    _text("family"),
    _code_ref("type", "technology_type"),
    _code_ref("standard_status", "tech_standard_status"),
    _text("standard_status_details"),
    _text("tech_standards_link"),
    _text("action_plan"),
    *_timestamps(),
)

ENTITY_TABLES: dict[type[Entity], Table] = {
    Team: team,
    TeamMember: team_member,
    Application: application,
    Function: function,
    DataType: data_type,
    DataFlow: data_flow,
    Technology: technology,
    Persona: persona,
}
