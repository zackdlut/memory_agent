from unittest.mock import patch

from app.evolution.hooks import refresh_person_summaries, should_refresh_summary
from app.schemas import Persona


def test_should_refresh_when_empty():
    p = Persona(name="林然", mention_count=1)
    assert should_refresh_summary(p, traits_changed=False) is True


def test_should_refresh_when_mention_count_high():
    p = Persona(name="林然", mention_count=2, summary="已有摘要")
    assert should_refresh_summary(p, traits_changed=False) is True


@patch("app.evolution.hooks.llm.chat", return_value="林然是内向的后端工程师。")
def test_refresh_writes_summary(mock_chat, temp_store):
    temp_store.persona.upsert("林然", traits=["内向"])
    refresh_person_summaries(temp_store, ["林然"], {"林然": True})
    summary = temp_store.persona.get("林然").summary
    assert "工程师" in summary or "内向" in summary
