def test_decay_pulls_dimensions_toward_seed(temp_store):
    sp = temp_store.self_profile
    for _ in range(15):
        sp.apply_dimension_signal("playfulness", "+")  # 漂到 >0.6
    high = sp.get().dimensions.playfulness
    for _ in range(30):
        sp.decay(0.98)
    after = sp.get().dimensions.playfulness
    assert 0.3 <= after < high  # 向种子 0.3 回归，但未归零


def test_decay_prunes_weak_opinions(temp_store):
    sp = temp_store.self_profile
    sp.add_opinion("深聊", "我喜欢深聊")
    for _ in range(200):
        sp.decay(0.9)
    assert all(o.weight >= 0.15 for o in sp.get().opinions)
    assert len(sp.get().opinions) == 0
