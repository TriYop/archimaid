import pytest
from fastapi.testclient import TestClient

from archimaid.adapters.api.app import create_app
from archimaid.application.services import build_services
from tests.fakes import default_catalog, fake_repositories


@pytest.fixture
def catalog():
    return default_catalog()


@pytest.fixture
def repos():
    return fake_repositories()


@pytest.fixture
def services(repos, catalog):
    return build_services(repos, catalog)


@pytest.fixture
def client(services):
    return TestClient(create_app(services))


@pytest.fixture
def hx():
    """Headers an HTMX request sends."""
    return {"HX-Request": "true"}
