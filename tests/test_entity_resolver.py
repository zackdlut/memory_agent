from app.entity.resolver import EntityResolver
from app.schemas import BehaviorPattern, Entity, Episode, ExtractionResult, Relation


def test_resolve_by_alias(temp_store):
    temp_store.persona.upsert("林然", aliases=["小然"])
    r = EntityResolver(temp_store)
    assert r.resolve("小然") == "林然"


def test_same_round_substring_merge(temp_store):
    r = EntityResolver(temp_store)
    result = ExtractionResult(
        entities=[
            Entity(name="小然", traits=["内向"]),
            Entity(name="林然", traits=["工程师"], aliases=["小然"]),
        ],
        relations=[Relation(subject="小然", relation="搭档", object="David")],
        behavior_patterns=[
            BehaviorPattern(person="小然", trigger="deadline", behavior="喝咖啡")
        ],
        episode=Episode(summary="林然赶工", participants=["小然", "林然"]),
    )
    out = r.normalize_extraction(result)
    names = {e.name for e in out.entities}
    assert names == {"林然"}
    assert "小然" in out.entities[0].aliases
    assert out.relations[0].subject == "林然"
    assert out.behavior_patterns[0].person == "林然"
    assert out.episode.participants == ["林然"]


def test_resolve_existing_after_upsert(temp_store):
    temp_store.persona.upsert("林然")
    r = EntityResolver(temp_store)
    result = ExtractionResult(
        entities=[Entity(name="小然", traits=["夜猫子"])],
        episode=Episode(summary="小然写代码"),
    )
    out = r.normalize_extraction(result)
    assert out.entities[0].name == "林然"
