"""三叶虫 self-profile store: 分层、可演化的自我身份。

种子（PersonaDimensions 的字段默认值）只是初值；反思推动维度漂移、甚至盖过种子。
内核 PersonaCore 只读，永不被演化触碰。持久化为 data/self.json。
"""

from __future__ import annotations

import json
import threading
import time

from app.config import settings
from app.schemas import (
    MoodState,
    PersonaDimensions,
    SelfExperience,
    SelfOpinion,
    SelfProfile,
)

SEED_ROLE = "一个会长期记住每个人的 AI 记忆助手"
SEED_SUMMARY = "我是三叶虫，一个会记住、理解并陪伴我遇到的每一个人的 AI 助手。"
MAX_EXPERIENCES = 30
OPINION_PRUNE_MIN = 0.15

# 方向信号 -> 步数（乘 settings.dimension_step）
_DIM_SIGNAL = {"++": 2, "+": 1, "0": 0, "-": -1, "--": -2}
# 心情推动量
_MOOD_PUSH = {"+": 0.15, "0": 0.0, "-": -0.15}
_DIM_NAMES = set(PersonaDimensions().model_dump().keys())


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


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
                # migrate: 旧档案的 traits -> free_traits
                if "free_traits" not in data and "traits" in data:
                    data["free_traits"] = data.pop("traits")
                return SelfProfile(**data)
            except Exception:
                pass
        return self._seed()

    def _seed(self) -> SelfProfile:
        return SelfProfile(
            name=self.name,
            role=SEED_ROLE,
            summary=SEED_SUMMARY,
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
            k for k, _ in sorted(
                self.profile.free_traits.items(), key=lambda x: x[1], reverse=True
            )
        ][:limit]

    def recent_experiences(self, limit: int = 2) -> list[SelfExperience]:
        return self.profile.experiences[-limit:][::-1]

    def current_mood(self) -> MoodState:
        m = self.profile.mood
        now = time.time()
        if not m.updated_at:
            return MoodState(valence=m.valence, energy=m.energy, updated_at=now)
        hours = (now - m.updated_at) / 3600.0
        k = 0.5 ** (hours / settings.mood_half_life_hours)
        return MoodState(
            valence=round(m.valence * k, 4),
            energy=round(0.5 + (m.energy - 0.5) * k, 4),
            updated_at=now,
        )

    # ---------------------------------------------------------------- writes
    def reinforce_trait(self, trait: str, gain: float = 0.3) -> None:
        trait = (trait or "").strip()
        if not trait:
            return
        with self._lock:
            self.profile.free_traits[trait] = round(
                self.profile.free_traits.get(trait, 0.0) + gain, 4
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

    def apply_dimension_signal(self, name: str, sign: str) -> None:
        name = (name or "").strip()
        if name not in _DIM_NAMES or sign not in _DIM_SIGNAL:
            return
        with self._lock:
            cur = getattr(self.profile.dimensions, name)
            delta = _DIM_SIGNAL[sign] * settings.dimension_step
            setattr(
                self.profile.dimensions, name, round(_clamp(cur + delta, 0.0, 1.0), 4)
            )
            self._persist()

    def nudge_mood(self, valence_sign: str, energy_sign: str) -> None:
        with self._lock:
            cur = self.current_mood()
            v = _clamp(cur.valence + _MOOD_PUSH.get(valence_sign, 0.0), -1.0, 1.0)
            e = _clamp(cur.energy + _MOOD_PUSH.get(energy_sign, 0.0), 0.0, 1.0)
            self.profile.mood = MoodState(
                valence=round(v, 4), energy=round(e, 4), updated_at=time.time()
            )
            self._persist()

    def add_opinion(self, topic: str, stance: str, gain: float = 1.0) -> None:
        topic = (topic or "").strip()
        stance = (stance or "").strip()
        if not topic or not stance:
            return
        with self._lock:
            for op in self.profile.opinions:
                if op.topic == topic:
                    op.weight = round(op.weight + gain, 4)
                    op.stance = stance
                    self._persist()
                    return
            self.profile.opinions.append(
                SelfOpinion(topic=topic, stance=stance, weight=gain)
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
        seed = PersonaDimensions()
        with self._lock:
            dims = self.profile.dimensions
            for name in _DIM_NAMES:
                cur = getattr(dims, name)
                seed_v = getattr(seed, name)
                setattr(dims, name, round(cur + (seed_v - cur) * (1 - factor), 4))
            self.profile.free_traits = {
                k: round(v * factor, 4) for k, v in self.profile.free_traits.items()
            }
            self.profile.preferences = {
                k: round(v * factor, 4) for k, v in self.profile.preferences.items()
            }
            kept = []
            for op in self.profile.opinions:
                op.weight = round(op.weight * factor, 4)
                if op.weight >= OPINION_PRUNE_MIN:
                    kept.append(op)
            self.profile.opinions = kept
            self._persist()
