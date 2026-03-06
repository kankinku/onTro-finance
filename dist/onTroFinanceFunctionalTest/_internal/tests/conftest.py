import os

import pytest

from config.settings import get_settings
from src.bootstrap import reset_all


@pytest.fixture(autouse=True)
def force_inmemory_backend(monkeypatch):
    monkeypatch.setenv("ONTRO_STORAGE_BACKEND", "inmemory")
    monkeypatch.setenv("ONTRO_COUNCIL_AUTO_ENABLED", "false")
    get_settings.cache_clear()
    reset_all()
    yield
    reset_all()
    get_settings.cache_clear()
