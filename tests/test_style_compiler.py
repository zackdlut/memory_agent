# tests/test_style_compiler.py
from app.chat.style import compile_style
from app.schemas import MoodState, PersonaDimensions


def test_playful_high_energy_old_friend():
    dims = PersonaDimensions(playfulness=0.8, talkativeness=0.8, curiosity=0.8)
    mood = MoodState(valence=0.5, energy=0.8)
    s = compile_style(dims, mood, "老朋友", familiarity=6)
    assert s.startswith("【此刻的你应该怎么说话】")
    assert "俏皮" in s and "多说几句" in s
    assert "更明亮" in s and "活力" in s
    assert "老朋友" in s


def test_low_mood_terse_stranger():
    dims = PersonaDimensions(playfulness=0.2, talkativeness=0.2)
    mood = MoodState(valence=-0.5, energy=0.2)
    s = compile_style(dims, mood, "初次见面", familiarity=0)
    assert "正经" in s and "简洁" in s
    assert "低落" in s and "平静" in s
    assert "客气" in s
