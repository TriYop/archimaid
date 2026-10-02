import os
from pathlib import Path

from alembic import command
from alembic.config import Config


def run_migrations(url: str) -> None:
    """Upgrade the database at ``url`` to the latest revision."""
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")


if __name__ == "__main__":
    run_migrations(os.environ["DATABASE_URL"])
