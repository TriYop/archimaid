"""Initial schema: configuration tables and entity tables."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

CATALOGS = {
    "confidentiality_level": ("rank",),
    "integrity_level": ("rank",),
    "availability_level": ("rank", "rpo_hours", "rto_hours"),
    "traceability_level": ("rank",),
    "function_category": (),
    "usage_mode": (),
    "technology_type": (),
    "tech_standard_status": (),
}

ENTITY_TABLES = (
    "data_flow",
    "technology",
    "data_type",
    "function",
    "persona",
    "application",
    "team_member",
    "team",
)


def _id():
    return sa.Column("id", sa.Uuid, primary_key=True)


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _text(name, nullable=True):
    return sa.Column(name, sa.Text, nullable=nullable)


def _code_ref(column, kind):
    return sa.Column(
        column,
        sa.Text,
        sa.ForeignKey(f"{kind}.code", onupdate="CASCADE", ondelete="RESTRICT"),
    )


def _id_ref(column, table, ondelete, nullable=False):
    return sa.Column(
        column, sa.Uuid, sa.ForeignKey(f"{table}.id", ondelete=ondelete), nullable=nullable
    )


def upgrade() -> None:
    for name, extra in CATALOGS.items():
        op.create_table(
            name,
            sa.Column("code", sa.Text, primary_key=True),
            sa.Column("label", sa.Text, nullable=False),
            sa.Column("description", sa.Text),
            *[sa.Column(column, sa.Integer, nullable=False) for column in extra],
        )

    op.create_table(
        "team",
        _id(),
        _text("name", nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        *_timestamps(),
    )
    op.create_table(
        "team_member",
        _id(),
        _id_ref("team_id", "team", "CASCADE"),
        _text("user_id", nullable=False),
        _text("name", nullable=False),
        *_timestamps(),
    )
    op.create_table(
        "application",
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
    op.create_table(
        "persona",
        _id(),
        _text("name", nullable=False),
        _text("description"),
        _text("category"),
        *_timestamps(),
    )
    op.create_table(
        "function",
        _id(),
        _id_ref("application_id", "application", "CASCADE"),
        _id_ref("persona_id", "persona", "RESTRICT", nullable=True),
        _text("name", nullable=False),
        _text("description"),
        _code_ref("category", "function_category"),
        *_timestamps(),
    )
    op.create_table(
        "data_type",
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
    op.create_table(
        "data_flow",
        _id(),
        _id_ref("source_application_id", "application", "RESTRICT"),
        _id_ref("target_application_id", "application", "RESTRICT"),
        _id_ref("data_type_id", "data_type", "RESTRICT"),
        _code_ref("usage_mode", "usage_mode"),
        _text("usage_explanation"),
        *_timestamps(),
    )
    op.create_table(
        "technology",
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


def downgrade() -> None:
    for name in ENTITY_TABLES:
        op.drop_table(name)
    for name in CATALOGS:
        op.drop_table(name)
