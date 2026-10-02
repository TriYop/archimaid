import pytest

from archimaid.main import build_app


def test_build_app_without_database_url_gives_a_clear_error(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        build_app()
