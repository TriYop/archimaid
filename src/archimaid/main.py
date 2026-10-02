import os

from fastapi import FastAPI
from sqlalchemy import create_engine

from archimaid.adapters.api.app import create_app
from archimaid.adapters.persistence.catalog import PostgresReferenceCatalog
from archimaid.adapters.persistence.repository import build_repositories
from archimaid.application.services import build_services


def build_app() -> FastAPI:
    """ASGI factory. Needs DATABASE_URL, e.g. postgresql+psycopg://user:pw@host/db."""
    engine = create_engine(os.environ["DATABASE_URL"])
    services = build_services(build_repositories(engine), PostgresReferenceCatalog(engine))
    return create_app(services)
