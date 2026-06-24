import pytest
from pydantic import ValidationError

from app.config import settings
from app.schemas import PersonaCore, PersonaDimensions, MoodState, SelfOpinion, SelfProfile


def test_dimensions_defaults():
    d = PersonaDimensions()
    assert d.warmth == 0.7 and d.empathy == 0.7 and d.patience == 0.7
    assert d.curiosity == 0.7 and d.playfulness == 0.3
    assert d.assertiveness == 0.3 and d.talkativeness == 0.4


def test_mood_defaults():
    m = MoodState()
    assert m.valence == 0.0 and m.energy == 0.5 and m.updated_at == 0.0


def test_config_defaults():
    assert settings.mood_half_life_hours == 6.0
    assert settings.dimension_step == 0.04
    assert settings.reflect_async is True


def test_dimensions_rejects_out_of_range():
    with pytest.raises(ValidationError):
        PersonaDimensions(warmth=2)


def test_self_profile_has_layers():
    p = SelfProfile(name="三叶虫")
    assert isinstance(p.core, PersonaCore)
    assert isinstance(p.dimensions, PersonaDimensions)
    assert isinstance(p.mood, MoodState)
    assert p.free_traits == {} and p.opinions == []
    assert "不伤害人" in p.core.invariants


def test_apply_dimension_signal_drifts_and_can_pass_seed(temp_store):
    sp = temp_store.self_profile
    start = sp.get().dimensions.playfulness  # 0.3 种子
    for _ in range(15):
        sp.apply_dimension_signal("playfulness", "+")  # +0.04 each
    val = sp.get().dimensions.playfulness
    assert val > start and val > 0.6 and val <= 1.0  # 盖过种子、且被 clamp


def test_apply_dimension_signal_clamps_and_ignores_unknown(temp_store):
    sp = temp_store.self_profile
    for _ in range(50):
        sp.apply_dimension_signal("warmth", "++")
    assert sp.get().dimensions.warmth == 1.0
    sp.apply_dimension_signal("nope", "+")     # 未知维度：无副作用
    sp.apply_dimension_signal("warmth", "???")  # 未知 sign：无副作用
    assert sp.get().dimensions.warmth == 1.0
