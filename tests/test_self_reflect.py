from unittest.mock import patch

from app.chat.self_memory import SelfMemory


@patch("app.chat.self_memory.llm.chat_json")
def test_reflect_applies_signals_mood_and_opinion(mock_json, temp_store):
    mock_json.return_value = {
        "dimension_signals": {"empathy": "+", "playfulness": "++"},
        "free_traits": ["爱用比喻"],
        "preferences": ["喜欢深聊"],
        "opinion": {"topic": "闲聊vs深聊", "stance": "我更喜欢陪人深聊"},
        "experience": "我陪zack聊了考研焦虑，他挺信任我",
        "emotion": "warm",
        "mood_push": {"valence": "+", "energy": "+"},
    }
    sm = SelfMemory(temp_store)
    before = temp_store.self_profile.get().dimensions.playfulness
    sm.reflect("zack", "我好焦虑", "别急，我陪你慢慢理")

    p = temp_store.self_profile.get()
    assert p.dimensions.playfulness > before        # ++ 漂移
    assert p.dimensions.empathy > 0.7               # + 漂移
    assert "爱用比喻" in p.free_traits
    assert "喜欢深聊" in p.preferences
    assert any(o.topic == "闲聊vs深聊" for o in p.opinions)
    assert p.experiences and "zack" in p.experiences[-1].summary
    assert p.mood.valence > 0 and p.mood.energy > 0.5
    assert p.interaction_count == 1


@patch("app.chat.self_memory.llm.chat_json", side_effect=Exception("llm down"))
def test_reflect_swallows_errors(mock_json, temp_store):
    sm = SelfMemory(temp_store)
    sm.reflect("zack", "hi", "hello")  # 不抛异常即可
