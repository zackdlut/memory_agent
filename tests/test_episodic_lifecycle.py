import time

from app.schemas import Episode


def test_decay_reduces_weight(temp_store, monkeypatch):
    monkeypatch.setattr("app.memory.episodic.llm.embed", lambda t: [0.1] * 768)
    ep = Episode(summary="test", weight=1.0)
    temp_store.episodic.add(ep)
    temp_store.episodic.decay(0.5)
    got = temp_store.episodic.get(ep.id)
    assert got is not None
    assert got.weight == 0.5


def test_prune_removes_low_weight(temp_store, monkeypatch):
    monkeypatch.setattr("app.memory.episodic.llm.embed", lambda t: [0.0] * 768)
    low = Episode(summary="low", weight=0.1)
    high = Episode(summary="high", weight=0.9)
    temp_store.episodic.add(low)
    temp_store.episodic.add(high)
    deleted = temp_store.episodic.prune(0.15)
    assert deleted == 1
    assert temp_store.episodic.get(low.id) is None
    assert temp_store.episodic.get(high.id) is not None
