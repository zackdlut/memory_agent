from app.schemas import PersonaCore, PersonaDimensions, MoodState, SelfOpinion, SelfProfile


def test_dimensions_defaults():
    d = PersonaDimensions()
    assert d.warmth == 0.7 and d.empathy == 0.7 and d.patience == 0.7
    assert d.curiosity == 0.7 and d.playfulness == 0.3
    assert d.assertiveness == 0.3 and d.talkativeness == 0.4


def test_self_profile_has_layers():
    p = SelfProfile(name="三叶虫")
    assert isinstance(p.core, PersonaCore)
    assert isinstance(p.dimensions, PersonaDimensions)
    assert isinstance(p.mood, MoodState)
    assert p.free_traits == {} and p.opinions == []
    assert "不伤害人" in p.core.invariants
