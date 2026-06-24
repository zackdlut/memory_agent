from app.chat.self_memory import SelfMemory
from app.schemas import SelfExperience


def test_style_block_reflects_dimensions(temp_store):
    sp = temp_store.self_profile
    for _ in range(20):
        sp.apply_dimension_signal("playfulness", "+")  # 漂到高位
    sm = SelfMemory(temp_store)
    block = sm.style_block("zack")
    assert "【此刻的你应该怎么说话】" in block
    assert "俏皮" in block


def test_talking_points_picks_relevant_opinion(temp_store):
    sp = temp_store.self_profile
    sp.add_opinion("考研", "我觉得考研最难的是坚持")
    sp.add_experience(SelfExperience(summary="我陪zack聊过考研", person="zack"))
    sm = SelfMemory(temp_store)
    pts = sm.self_talking_points("zack", "我在准备考研")
    assert "考研" in pts


def test_talking_points_empty_when_irrelevant(temp_store):
    sm = SelfMemory(temp_store)
    assert sm.self_talking_points("zack", "今天天气真好") == ""


def test_talking_points_no_false_match_with_existing_memories(temp_store):
    sp = temp_store.self_profile
    sp.add_opinion("考研", "我觉得考研最难的是坚持")
    sp.add_experience(SelfExperience(summary="我陪zack聊过考研", person="zack"))
    sm = SelfMemory(temp_store)
    assert sm.self_talking_points("zack", "今天天气真好") == ""


def test_talking_points_ignores_generic_opinion_query_bigrams(temp_store):
    sp = temp_store.self_profile
    sp.add_opinion("观察", "我在很多话题里都会先观察")
    sm = SelfMemory(temp_store)
    assert sm.self_talking_points("zack", "我在准备考研") == ""


def test_talking_points_format_and_caps(temp_store):
    sp = temp_store.self_profile
    sp.add_opinion("考研", "我觉得考研最难的是坚持")
    sp.add_experience(SelfExperience(summary="我陪zack聊过考研", person="zack"))
    sm = SelfMemory(temp_store)
    out = sm.self_talking_points("zack", "我在准备考研")
    assert out.startswith("【你可以在自然时机提起的(自己的观点/经历，别硬塞)】")
    assert "你对这类话题的看法：" in out
    assert "你想起一件事：" in out
    assert out.count("- ") == 2


def test_narrative_is_first_person(temp_store):
    sm = SelfMemory(temp_store)
    n = sm.self_narrative()
    assert n.startswith("我")


def test_profile_view_carries_dimensions(temp_store):
    sm = SelfMemory(temp_store)
    view = sm.profile_view()
    assert view.dimensions is not None
    assert view.narrative.startswith("我")
