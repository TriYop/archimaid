"""Seed the configuration tables with the original enum values."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

LEVELS = (("EXTREME", 4), ("SERIOUS", 3), ("MODERATE", 2), ("LOW", 1))
RPO_RTO_HOURS = {"EXTREME": (2, 0), "SERIOUS": (4, 0), "MODERATE": (24, 24), "LOW": (72, 24)}
PLAIN = {
    "function_category": ("COMMON", "BUSINESS", "EXCHANGE", "DATA"),
    "usage_mode": ("SOURCE", "CONSUMER", "PROXY"),
    "technology_type": (
        "OPERATING_SYSTEM",
        "FRAMEWORK_LIBRARY",
        "WEB_SERVER",
        "APPLICATION_SERVER",
        "DATABASE",
        "SOFTWARE",
        "SAAS_SERVICE",
        "RUNTIME_INTERPRETER",
        "CI_CD",
        "DEV_LANG",
        "ETL",
    ),
    "tech_standard_status": (
        "EMERGING",
        "UPCOMING",
        "REFERENCE",
        "CONFINED",
        "TO_BE_PHASED_OUT",
        "DECOMMISSIONED",
        "REJECTED",
    ),
}
RANKED = ("confidentiality_level", "integrity_level", "traceability_level")


def _label(code: str) -> str:
    return code.replace("_", " ").capitalize()


def upgrade() -> None:
    for name in RANKED:
        table = sa.table(name, sa.column("code"), sa.column("label"), sa.column("rank"))
        op.bulk_insert(
            table, [{"code": c, "label": _label(c), "rank": r} for c, r in LEVELS]
        )

    availability = sa.table(
        "availability_level",
        sa.column("code"),
        sa.column("label"),
        sa.column("rank"),
        sa.column("rpo_hours"),
        sa.column("rto_hours"),
    )
    op.bulk_insert(
        availability,
        [
            {
                "code": c,
                "label": _label(c),
                "rank": r,
                "rpo_hours": RPO_RTO_HOURS[c][0],
                "rto_hours": RPO_RTO_HOURS[c][1],
            }
            for c, r in LEVELS
        ],
    )

    for name, codes in PLAIN.items():
        table = sa.table(name, sa.column("code"), sa.column("label"))
        op.bulk_insert(table, [{"code": c, "label": _label(c)} for c in codes])


def downgrade() -> None:
    for name in (*RANKED, "availability_level", *PLAIN):
        op.execute(sa.text(f"DELETE FROM {name}"))
