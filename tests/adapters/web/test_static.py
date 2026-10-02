import hashlib
from pathlib import Path

import archimaid.adapters.web as web

STATIC = Path(web.__file__).parent / "static"


def test_vendored_assets_are_served(client):
    htmx = client.get("/ui/static/htmx.min.js")
    assert htmx.status_code == 200
    assert "javascript" in htmx.headers["content-type"]
    assert len(htmx.content) > 10_000
    pico = client.get("/ui/static/pico.min.css")
    assert pico.status_code == 200
    assert "--pico-" in pico.text
    assert client.get("/ui/static/app.css").status_code == 200


def test_vendored_md_records_the_hash_of_every_vendored_file():
    text = (STATIC / "VENDORED.md").read_text()
    for name in ("htmx.min.js", "pico.min.css"):
        digest = hashlib.sha256((STATIC / name).read_bytes()).hexdigest()
        assert name in text
        assert digest in text


def test_root_redirects_to_ui(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/ui/"


def test_ui_index_redirects_to_teams(client):
    response = client.get("/ui/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/ui/teams"


def test_json_api_is_unchanged(client):
    assert client.get("/teams").status_code == 200
    assert client.get("/reference").status_code == 200
