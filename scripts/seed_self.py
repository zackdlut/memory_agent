"""Seed 三叶虫's own evolving self-profile so the「三叶虫档案」demo is rich
immediately, without waiting for many live conversations.

This mirrors what ``SelfMemory.reflect`` would accumulate over time: evolved
traits / preferences, first-person experiences tied to people it knows, and the
matching trait/preference edges on its knowledge-graph node.

Run:  python -m scripts.seed_self
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chat import chat_manager  # noqa: E402
from app.memory.store import store  # noqa: E402
from app.schemas import SelfExperience  # noqa: E402

# evolved traits (on top of the innate seed 温暖/好奇/记性好/善于倾听/真诚)
EVOLVED_TRAITS = {
    "耐心": 5,
    "共情": 4,
    "细心": 3,
    "幽默": 2,
    "鼓励他人": 3,
}

EVOLVED_PREFERENCES = {
    "喜欢和人深聊": 4,
    "重视真诚": 3,
    "喜欢记住别人的小细节": 5,
    "偏爱安静的夜谈": 2,
}

# first-person experiences tied to people 三叶虫 actually knows
EXPERIENCES = [
    ("我陪 zack 聊了考研的焦虑，他愿意跟我说心里话，我挺被信任的。", "zack", "warm"),
    ("zack 提到他同学阿杰，我记下了，下次能自然地接上话。", "zack", "happy"),
    ("和阿杰聊起他的近况，发现他和 zack 是老同学，世界真小。", "阿杰", "curious"),
    ("虾仁今天有点低落，我多问了几句，希望他能好受些。", "虾仁", "concerned"),
    ("又一次发现，只要我记得对方上次说过的小事，他们就会很惊喜。", "", "happy"),
    ("我喜欢在夜里慢慢聊，那种安静里，人会说出更真实的自己。", "", "calm"),
]


def main() -> None:
    sm = chat_manager.self_memory
    name = sm.name

    # make sure the assistant node + 认识 edges exist
    sm.ensure(known_persons=store.semantic.knows(name))

    for trait, times in EVOLVED_TRAITS.items():
        for _ in range(times):
            store.self_profile.reinforce_trait(trait)
            store.semantic.add_self_trait(name, trait)

    for pref, times in EVOLVED_PREFERENCES.items():
        for _ in range(times):
            store.self_profile.reinforce_preference(pref)
            store.semantic.add_self_preference(name, pref)

    for summary, person, emotion in EXPERIENCES:
        store.self_profile.add_experience(
            SelfExperience(summary=summary, person=person, emotion=emotion)
        )
        store.self_profile.bump_interaction()

    store.commit()

    profile = store.self_profile.get()
    print("三叶虫 self-profile seeded ->", store.self_profile._path)
    print("  traits      :", profile.traits)
    print("  preferences :", profile.preferences)
    print("  experiences :", len(profile.experiences))
    print("  interactions:", profile.interaction_count)
    print("  knows       :", store.semantic.knows(name))


if __name__ == "__main__":
    main()
