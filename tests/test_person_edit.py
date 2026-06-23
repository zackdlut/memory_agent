from app.schemas import BehaviorPattern


def test_update_summary(temp_store):
    temp_store.persona.upsert("林然", traits=["内向"])
    p = temp_store.persona.update("林然", summary="内向的工程师")
    assert p.summary == "内向的工程师"
    assert p.last_summary_at > 0


def test_remove_trait_from_persona_and_graph(temp_store):
    temp_store.persona.upsert("林然", traits=["内向", "外向"])
    temp_store.semantic.add_trait("林然", "内向")
    temp_store.semantic.add_trait("林然", "外向")
    temp_store.persona.update("林然", remove_traits=["外向"])
    temp_store.semantic.remove_trait("林然", "外向")
    p = temp_store.persona.get("林然")
    assert "外向" not in p.traits
    assert "内向" in p.traits
    trait_labels = {t["target"] for t in temp_store.semantic.neighbors("林然")["traits"]}
    assert "外向" not in trait_labels
    assert "内向" in trait_labels


def test_remove_preference(temp_store):
    temp_store.persona.upsert("林然", preferences=["咖啡", "安静"])
    temp_store.persona.update("林然", remove_preferences=["咖啡"])
    p = temp_store.persona.get("林然")
    assert "咖啡" not in p.preferences
    assert "安静" in p.preferences


def test_remove_pattern_by_index(temp_store):
    pats = [
        BehaviorPattern(person="林然", trigger="deadline", behavior="喝咖啡"),
        BehaviorPattern(person="林然", trigger="周末", behavior="撸猫"),
    ]
    temp_store.persona.upsert("林然", patterns=pats)
    temp_store.persona.update("林然", remove_pattern_indices=[0])
    p = temp_store.persona.get("林然")
    assert len(p.patterns) == 1
    assert p.patterns[0].behavior == "撸猫"


def test_add_aliases(temp_store):
    temp_store.persona.upsert("林然")
    temp_store.persona.update("林然", add_aliases=["小然"])
    assert "小然" in temp_store.persona.get("林然").aliases
