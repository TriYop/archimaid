import os

from fastapi import FastAPI
from sqlalchemy import create_engine

from archimaid.adapters.api.app import create_app
from archimaid.adapters.persistence.catalog import PostgresReferenceCatalog
from archimaid.adapters.persistence.repository import build_repositories
from archimaid.application.services import build_services


def build_app() -> FastAPI:
    """ASGI factory. Needs DATABASE_URL, e.g. postgresql+psycopg://user:pw@host/db."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set, e.g. postgresql+psycopg://user:pw@host:5432/db"
        )
    engine = create_engine(url)
    services = build_services(build_repositories(engine), PostgresReferenceCatalog(engine))
    return create_app(services)
