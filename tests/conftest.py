import app.config as config_module
import pytest
from app.memory.store import MemoryStore


@pytest.fixture
def temp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    return MemoryStore()
