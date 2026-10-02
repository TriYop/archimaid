from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from archimaid.adapters.api.app import create_app


def boom(*args, **kwargs):
    raise RuntimeError("boom")


@pytest.fixture
def failing(services):
    return TestClient(create_app(services), raise_server_exceptions=False)


def test_unexpected_error_on_a_ui_page_is_a_generic_error_page(failing, services):
    services.teams.list = boom
    response = failing.get("/ui/teams")
    assert response.status_code == 500
    assert "<html" in response.text and "Something went wrong" in response.text
    assert "boom" not in response.text


def test_unexpected_error_on_an_htmx_request_is_retargeted_to_the_flash(failing, services, hx):
    services.teams.get = boom
    response = failing.get(f"/ui/teams/{uuid4()}/row", headers=hx)
    assert response.status_code == 500
    assert response.headers["HX-Retarget"] == "#flash"
    assert response.headers["HX-Reswap"] == "innerHTML"
    assert "Something went wrong" in response.text and "boom" not in response.text
    assert "<html" not in response.text


def test_unexpected_error_on_the_json_api_is_unchanged(failing, services):
    services.teams.list = boom
    response = failing.get("/teams")
    assert response.status_code == 500
    assert response.text == "Internal Server Error"


def test_malformed_uuid_in_a_ui_path_is_a_flash_for_htmx(failing, hx):
    response = failing.get("/ui/teams/not-a-uuid/row", headers=hx)
    assert response.status_code == 422
    assert response.headers["HX-Retarget"] == "#flash"
    assert "not valid" in response.text
    assert "{" not in response.text and '"detail"' not in response.text


def test_malformed_uuid_in_a_ui_path_is_an_error_page_otherwise(failing):
    response = failing.get("/ui/teams/not-a-uuid/row")
    assert response.status_code == 422
    assert "<html" in response.text and "not valid" in response.text


def test_json_api_validation_errors_are_still_json(failing):
    response = failing.get("/teams/not-a-uuid")
    assert response.status_code == 422
    assert '"detail"' in response.text
