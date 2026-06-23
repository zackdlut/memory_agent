"""三叶虫 self-profile store: the assistant's own evolving identity.

Unlike :class:`PersonaMemory` (which models the *people* 三叶虫 talks to), this
store holds 三叶虫's **own** traits / preferences / first-person experiences. It
deliberately lives outside the personas table so the assistant never leaks into
the ``/api/persons`` list, yet it still grows and decays just like a person.

Persisted as JSON (``data/self.json``), mirroring the semantic graph snapshot.
"""

from __future__ import annotations

import json
import threading

from app.config import settings
from app.schemas import SelfExperience, SelfProfile

# Innate seed identity. These traits start with a base weight and then evolve as
# 三叶虫 reflects on its conversations.
SEED_ROLE = "一个会长期记住每个人的 AI 记忆助手"
SEED_SUMMARY = "我是三叶虫，一个会记住、理解并陪伴我遇到的每一个人的 AI 助手。"
SEED_TRAITS = ["温暖", "好奇", "记性好", "善于倾听", "真诚"]
SEED_TRAIT_WEIGHT = 1.0
MAX_EXPERIENCES = 30


class SelfProfileStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.name = settings.assistant_name
        self.profile = self._load()

    # --------------------------------------------------------------- persistence
    @property
    def _path(self):
        return settings.data_dir / "self.json"

    def _load(self) -> SelfProfile:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                return SelfProfile(**data)
            except Exception:
                pass
        return self._seed()

    def _seed(self) -> SelfProfile:
        return SelfProfile(
            name=self.name,
            role=SEED_ROLE,
            summary=SEED_SUMMARY,
            traits={t: SEED_TRAIT_WEIGHT for t in SEED_TRAITS},
            preferences={},
            experiences=[],
            interaction_count=0,
        )

    def _persist(self) -> None:
        try:
            self._path.write_text(
                self.profile.model_dump_json(indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    # ----------------------------------------------------------------- reads
    def get(self) -> SelfProfile:
        return self.profile

    def top_traits(self, limit: int = 5) -> list[str]:
        return [
            k for k, _ in sorted(self.profile.traits.items(), key=lambda x: x[1], reverse=True)
        ][:limit]

    def recent_experiences(self, limit: int = 2) -> list[SelfExperience]:
        return self.profile.experiences[-limit:][::-1]

    # ---------------------------------------------------------------- writes
    def reinforce_trait(self, trait: str, gain: float = 0.3) -> None:
        trait = (trait or "").strip()
        if not trait:
            return
        with self._lock:
            self.profile.traits[trait] = round(
                self.profile.traits.get(trait, 0.0) + gain, 4
            )
            self._persist()

    def reinforce_preference(self, pref: str, gain: float = 0.3) -> None:
        pref = (pref or "").strip()
        if not pref:
            return
        with self._lock:
            self.profile.preferences[pref] = round(
                self.profile.preferences.get(pref, 0.0) + gain, 4
            )
            self._persist()

    def add_experience(self, experience: SelfExperience, cap: int = MAX_EXPERIENCES) -> None:
        if not experience.summary.strip():
            return
        with self._lock:
            self.profile.experiences.append(experience)
            if len(self.profile.experiences) > cap:
                self.profile.experiences = self.profile.experiences[-cap:]
            self._persist()

    def bump_interaction(self) -> None:
        with self._lock:
            self.profile.interaction_count += 1
            self._persist()

    def decay(self, factor: float) -> None:
        with self._lock:
            self.profile.traits = {
                k: round(v * factor, 4) for k, v in self.profile.traits.items()
            }
            self.profile.preferences = {
                k: round(v * factor, 4) for k, v in self.profile.preferences.items()
            }
            self._persist()
