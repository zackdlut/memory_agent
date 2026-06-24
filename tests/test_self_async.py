from unittest.mock import patch

from app.chat.manager import ChatManager
from app.schemas import PersonaDimensions


def test_reply_temperature_scales_with_playfulness():
    cm = ChatManager.__new__(ChatManager)  # 不跑 __init__（避免触网/建会话）
    lo = cm._reply_temperature(PersonaDimensions(playfulness=0.0))
    hi = cm._reply_temperature(PersonaDimensions(playfulness=1.0))
    assert 0.3 <= lo < hi <= 0.95


@patch("app.chat.manager.ChatManager._reply_temperature", return_value=0.6)
def test_post_exchange_updates_profile(_t, temp_store, monkeypatch):
    from app.agent import MemoryAgent
    cm = ChatManager.__new__(ChatManager)
    cm.agent = MemoryAgent(temp_store)
    from app.chat.self_memory import SelfMemory
    cm.self_memory = SelfMemory(temp_store)
    cm.assistant = "三叶虫"

    monkeypatch.setattr(cm.agent, "ingest", lambda *a, **k: None)  # 跳过编码/触网
    with patch("app.chat.self_memory.llm.chat_json") as mj:
        mj.return_value = {
            "dimension_signals": {"empathy": "+"},
            "free_traits": [], "preferences": [],
            "opinion": {"topic": "", "stance": ""},
            "experience": "我陪zack聊了天", "emotion": "warm",
            "mood_push": {"valence": "+", "energy": "0"},
        }
        cm._post_exchange("zack", "hi", "hello")

    p = temp_store.self_profile.get()
    assert p.dimensions.empathy > 0.7
    assert p.interaction_count == 1
