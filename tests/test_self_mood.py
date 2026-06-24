import time


def test_nudge_mood_pushes(temp_store):
    sp = temp_store.self_profile
    sp.nudge_mood("+", "+")
    m = sp.get().mood
    assert m.valence > 0 and m.energy > 0.5 and m.updated_at > 0


def test_current_mood_regresses_to_neutral(temp_store):
    sp = temp_store.self_profile
    sp.nudge_mood("+", "+")
    # 把更新时间挪到一个半衰期前，应回归到约一半
    p = sp.get()
    pushed_v = p.mood.valence
    p.mood.updated_at = time.time() - 6 * 3600  # = mood_half_life_hours
    cur = sp.current_mood()
    assert abs(cur.valence - pushed_v / 2) < 0.02
    assert abs(cur.energy - (0.5 + (p.mood.energy - 0.5) / 2)) < 0.02
