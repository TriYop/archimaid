from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

import archimaid.adapters.persistence.migrate as migrate_module

pytestmark = pytest.mark.postgres


def _config(url: str) -> Config:
    config = Config()
    config.set_main_option(
        "script_location", str(Path(migrate_module.__file__).parent / "migrations")
    )
    config.set_main_option("sqlalchemy.url", url)
    return config


def _columns(engine) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns("data_flow")}


def test_existing_flows_survive_the_upgrade_and_downgrade_removes_the_columns(postgres_url):
    # Review Focus test (6)
    engine = create_engine(postgres_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    config = _config(postgres_url)
    command.upgrade(config, "0002")
    assert "source_function_id" not in _columns(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO team (id, name, description, created_at, updated_at) "
                "VALUES ('00000000-0000-0000-0000-000000000001', 'T', '', now(), now())"
            )
        )
        conn.execute(
            text(
                "INSERT INTO application (id, team_id, name, created_at, updated_at) "
                "VALUES ('00000000-0000-0000-0000-000000000002', "
                "'00000000-0000-0000-0000-000000000001', 'A', now(), now())"
            )
        )
        conn.execute(
            text(
                "INSERT INTO data_type (id, application_id, name, created_at, updated_at) "
                "VALUES ('00000000-0000-0000-0000-000000000003', "
                "'00000000-0000-0000-0000-000000000002', 'D', now(), now())"
            )
        )
        conn.execute(
            text(
                "INSERT INTO data_flow (id, source_application_id, target_application_id, "
                "data_type_id, created_at, updated_at) VALUES "
                "('00000000-0000-0000-0000-000000000004', "
                "'00000000-0000-0000-0000-000000000002', "
                "'00000000-0000-0000-0000-000000000002', "
                "'00000000-0000-0000-0000-000000000003', now(), now())"
            )
        )
    command.upgrade(config, "head")
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT source_function_id, target_function_id FROM data_flow")
        ).one()
    assert tuple(row) == (None, None)
    command.downgrade(config, "0002")
    assert "source_function_id" not in _columns(engine)
    assert "target_function_id" not in _columns(engine)
    engine.dispose()
