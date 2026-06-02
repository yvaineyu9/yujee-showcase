import os

import pytest


@pytest.fixture(autouse=True)
def _set_secret(monkeypatch):
    monkeypatch.setenv("AGENT_SHARED_SECRET", "test_secret")
    monkeypatch.setenv("AGENT_PIPELINE_MODE", "mock")
    monkeypatch.setenv("AGENT_ENV", "development")
    # Force settings to re-read env on each test
    from src import settings as s
    s.reset_settings_cache()
    yield
    s.reset_settings_cache()
