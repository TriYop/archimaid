import pytest
from sqlalchemy import inspect, text

from archimaid.adapters.persistence.tables import metadata

pytestmark = pytest.mark.postgres

LEVELS = {"EXTREME", "SERIOUS", "MODERATE", "LOW"}
SEEDED = {
    "confidentiality_level": LEVELS,
    "integrity_level": LEVELS,
    "availability_level": LEVELS,
    "traceability_level": LEVELS,
    "function_category": {"COMMON", "BUSINESS", "EXCHANGE", "DATA"},
    "usage_mode": {"SOURCE", "CONSUMER", "PROXY"},
    "technology_type": {
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
    },
    "tech_standard_status": {
        "EMERGING",
        "UPCOMING",
        "REFERENCE",
        "CONFINED",
        "TO_BE_PHASED_OUT",
        "DECOMMISSIONED",
        "REJECTED",
    },
}


def test_every_catalog_is_seeded_with_the_original_enum_values(engine):
    with engine.connect() as conn:
        for kind, codes in SEEDED.items():
            rows = conn.execute(text(f"SELECT code FROM {kind}")).all()
            assert {r[0] for r in rows} == codes, kind


def test_availability_levels_carry_the_rpo_rto_mapping(engine):
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT code, rpo_hours, rto_hours FROM availability_level")
        ).all()
    assert {r[0]: (r[1], r[2]) for r in rows} == {
        "LOW": (72, 24),
        "MODERATE": (24, 24),
        "SERIOUS": (4, 0),
        "EXTREME": (2, 0),
    }


def test_rank_orders_levels_from_extreme_to_low(engine):
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT code FROM integrity_level ORDER BY rank DESC")).all()
    assert [r[0] for r in rows] == ["EXTREME", "SERIOUS", "MODERATE", "LOW"]


def test_sqlalchemy_metadata_matches_the_migrated_schema(engine):
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) - {"alembic_version"} == set(metadata.tables)
    for table in metadata.tables.values():
        db_columns = {c["name"] for c in inspector.get_columns(table.name)}
        assert {c.name for c in table.columns} == db_columns, table.name
