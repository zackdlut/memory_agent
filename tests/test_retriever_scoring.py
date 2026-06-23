import time

from app.entity.resolver import EntityResolver
from app.retrieval.retriever import Retriever
from app.schemas import Episode


def test_mentioned_persons_via_alias(temp_store):
    temp_store.persona.upsert("林然", aliases=["小然"])
    r = Retriever(temp_store, EntityResolver(temp_store))
    assert r._mentioned_persons("小然养了什么") == ["林然"]


def test_episodic_score_weights_high(temp_store):
    r = Retriever(temp_store, EntityResolver(temp_store))
    ep = Episode(summary="x", weight=2.0, last_seen=time.time())
    s = r._episodic_score(ep, 0.8)
    assert s > 0.8 * 2.0 * 0.85
