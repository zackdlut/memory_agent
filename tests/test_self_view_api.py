from app.chat.self_memory import SelfMemory


def test_profile_view_json_shape(temp_store):
    view = SelfMemory(temp_store).profile_view()
    data = view.model_dump()
    assert set(["profile", "dimensions", "mood", "opinions", "narrative", "known_people"]) <= set(data)
    assert "warmth" in data["dimensions"]
    assert "valence" in data["mood"] and "energy" in data["mood"]
    assert data["narrative"].startswith("我")
