import os
from pathlib import Path

import pytest


def _load_dotenv() -> None:
    path = Path(__file__).resolve().parent.parent / ".env"
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key:
            os.environ.setdefault(key, value)


_load_dotenv()


@pytest.fixture(scope="session")
def postgres_url():
    try:
        from testcontainers.community.postgres import PostgresContainer

        container = PostgresContainer("postgres:16-alpine", driver="psycopg")
        container.start()
    except Exception as exc:  # Docker missing or not running
        pytest.skip(f"Docker/Postgres unavailable: {exc}")
    yield container.get_connection_url()
    import docker.errors

    try:
        container.stop()
    except docker.errors.APIError:
        # podman 5.x returns HTTP 500 after it has already removed the container and volume
        pass


@pytest.fixture
def engine(postgres_url):
    from sqlalchemy import create_engine, text

    from archimaid.adapters.persistence.migrate import run_migrations

    engine = create_engine(postgres_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    run_migrations(postgres_url)
    yield engine
    engine.dispose()
