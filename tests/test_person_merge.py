from app.entity.resolver import EntityResolver
from app.schemas import BehaviorPattern


def test_persona_merge_combines_traits_and_aliases(temp_store):
    temp_store.persona.upsert("林然", traits=["内向"], preferences=["安静"])
    temp_store.persona.upsert("小然", traits=["内向", "夜猫子"], aliases=["阿然"])
    merged = temp_store.persona.merge("小然", "林然")
    assert merged is not None
    assert merged.name == "林然"
    assert temp_store.persona.get_exact("小然") is None
    assert "小然" in merged.aliases
    assert "阿然" in merged.aliases
    assert merged.traits["内向"] > temp_store.persona.get("林然").traits.get("夜猫子", 0) - 1
    assert "夜猫子" in merged.traits


def test_persona_merge_sums_mention_count(temp_store):
    temp_store.persona.upsert("林然")  # mention_count 1
    temp_store.persona.upsert("小然")  # mention_count 1
    merged = temp_store.persona.merge("小然", "林然")
    assert merged.mention_count == 2


def test_persona_merge_dedupes_patterns(temp_store):
    pat = BehaviorPattern(person="林然", trigger="deadline", behavior="喝咖啡")
    temp_store.persona.upsert("林然", patterns=[pat])
    temp_store.persona.upsert("小然", patterns=[pat])
    merged = temp_store.persona.merge("小然", "林然")
    assert len(merged.patterns) == 1


def test_semantic_merge_redirects_edges(temp_store):
    temp_store.semantic.add_trait("小然", "内向")
    temp_store.semantic.add_relation("小然", "搭档", "David")
    temp_store.semantic.add_person("林然")
    temp_store.semantic.merge_person("小然", "林然")
    assert not temp_store.semantic.g.has_node("小然")
    neighbors = temp_store.semantic.neighbors("林然")
    labels = {t["target"] for t in neighbors["traits"]}
    rel_targets = {r["target"] for r in neighbors["relations"]}
    assert "内向" in labels
    assert "David" in rel_targets


def test_resolver_merge_person_end_to_end(temp_store):
    temp_store.persona.upsert("林然", traits=["内向"])
    temp_store.persona.upsert("小然", traits=["夜猫子"])
    temp_store.semantic.add_trait("小然", "夜猫子")
    temp_store.semantic.add_person("林然")
    r = EntityResolver(temp_store)
    r.merge_person("小然", "林然")
    assert temp_store.persona.get_exact("小然") is None
    assert temp_store.persona.count() == 1
