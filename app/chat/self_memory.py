"""三叶虫 self-memory: an evolving identity + social relationships.

The assistant is deliberately NOT stored as a tracked person (it never enters
the personas table nor the ``persons`` list). Instead it gets its own evolving
self-model:
  - a persisted :class:`SelfProfile` (seeded with an innate identity, then grown
    via :meth:`reflect` after every exchange) — see ``app/memory/self_profile``
  - an ``assistant`` node in the knowledge graph carrying its evolving
    traits/preferences plus explicit "认识" edges to everyone it has chatted with

``self_context`` assembles a short block injected into the chat reply prompt so
三叶虫 can naturally reflect (a) who it is right now, (b) its familiarity/topics
with the current person, and (c) mutual acquaintances it shares with them.
"""

from __future__ import annotations

from app.config import settings
from app.llm import llm
from app.llm.prompts import SELF_REFLECT_SYSTEM, SELF_REFLECT_TEMPLATE
from app.memory.store import MemoryStore
from app.schemas import (
    KnownPerson,
    SelfExperience,
    SelfProfile,
    SelfProfileView,
)


class SelfMemory:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store
        self.name = settings.assistant_name

    # ----------------------------------------------------------------- setup
    def ensure(self, known_persons: list[str] | None = None) -> None:
        """Create the assistant graph node, mirror its seeded traits onto the
        graph, and backfill 认识 edges for everyone 三叶虫 already chatted with."""
        self.store.semantic.add_self(self.name)
        profile = self.store.self_profile.get()
        for trait in profile.traits:
            self.store.semantic.add_self_trait(self.name, trait, gain=0.0)
        for person in known_persons or []:
            if person and person != self.name:
                self.store.semantic.add_self_relation(self.name, "认识", person)
        self.store.commit()

    def record_acquaintance(self, person: str) -> None:
        if not person or person == self.name:
            return
        self.store.semantic.add_self_relation(self.name, "认识", person)
        self.store.commit()

    # --------------------------------------------------------------- evolve
    def reflect(self, person: str, user_text: str, reply: str) -> None:
        """互动后反思：推动维度漂移、推动心情、形成观点、记第一人称感受。Best-effort。"""
        try:
            data = llm.chat_json(
                SELF_REFLECT_TEMPLATE.format(
                    person=person, user_text=user_text, reply=reply
                ),
                system=SELF_REFLECT_SYSTEM,
            )
        except Exception:
            return
        if not isinstance(data, dict):
            return

        sp = self.store.self_profile

        signals = data.get("dimension_signals") or {}
        if isinstance(signals, dict):
            for name, sign in signals.items():
                sp.apply_dimension_signal(str(name), str(sign))

        for trait in data.get("free_traits") or []:
            t = str(trait).strip()
            if t:
                sp.reinforce_trait(t)
                self.store.semantic.add_self_trait(self.name, t)
        for pref in data.get("preferences") or []:
            pr = str(pref).strip()
            if pr:
                sp.reinforce_preference(pr)
                self.store.semantic.add_self_preference(self.name, pr)

        op = data.get("opinion") or {}
        if isinstance(op, dict):
            sp.add_opinion(str(op.get("topic") or ""), str(op.get("stance") or ""))

        experience = str(data.get("experience") or "").strip()
        emotion = str(data.get("emotion") or "neutral").strip() or "neutral"
        if experience:
            sp.add_experience(
                SelfExperience(summary=experience, person=person, emotion=emotion)
            )

        push = data.get("mood_push") or {}
        if isinstance(push, dict):
            sp.nudge_mood(str(push.get("valence") or "0"), str(push.get("energy") or "0"))

        sp.bump_interaction()
        self.store.commit()

    # -------------------------------------------------------------- read side
    def _familiarity(self, person: str) -> int:
        """How many times 三叶虫 has reinforced knowing this person."""
        for rel in self.store.semantic.neighbors(self.name).get("relations", []):
            if rel.get("target") == person:
                return int(rel.get("count", 1))
        return 0

    def _recent_topics(self, person: str, limit: int = 2) -> list[str]:
        try:
            hits = self.store.episodic.search(f"{self.name} {person}", top_k=limit)
        except Exception:
            return []
        return [ep.summary for ep, _ in hits][:limit]

    def mutual_acquaintances(self, person: str) -> list[dict]:
        """People linked to ``person`` that 三叶虫 also knows."""
        known = set(self.store.semantic.knows(self.name))
        out = []
        for link in self.store.semantic.social_links(person):
            other = link["person"]
            if other in known and other != person:
                out.append({"person": other, "relation": link["relation"]})
        return out

    def relationship_label(self, person: str) -> str:
        fam = self._familiarity(person)
        if fam >= 5:
            return f"老朋友（已聊过约 {fam} 次）"
        if fam >= 2:
            return f"熟识（聊过 {fam} 次）"
        if fam == 1:
            return "刚认识"
        return "初次见面"

    def self_context(self, person: str) -> str:
        profile = self.store.self_profile.get()
        traits = "、".join(self.store.self_profile.top_traits())
        lines = [f"你是{self.name}，{profile.role}；你现在的特质：{traits}。"]

        recent_self = self.store.self_profile.recent_experiences(limit=2)
        if recent_self:
            lines.append("你最近的一些感受：" + "；".join(e.summary for e in recent_self))

        lines.append(f"你和「{person}」的关系：{self.relationship_label(person)}。")

        topics = self._recent_topics(person)
        if topics:
            lines.append("你们最近聊到的：" + "；".join(topics))

        mutual = self.mutual_acquaintances(person)
        if mutual:
            desc = "、".join(f"{m['person']}（{person}的{m['relation']}，你也认识）" for m in mutual)
            lines.append(f"你还认识和 {person} 有关系的人：{desc}。可以在合适时自然提起。")

        return "\n".join(lines)

    # ------------------------------------------------------------- profile view
    def profile_view(self) -> SelfProfileView:
        profile: SelfProfile = self.store.self_profile.get()
        known = [
            KnownPerson(
                name=p,
                familiarity=self._familiarity(p),
                relationship=self.relationship_label(p),
            )
            for p in self.store.semantic.knows(self.name)
        ]
        known.sort(key=lambda k: k.familiarity, reverse=True)
        return SelfProfileView(profile=profile, known_people=known)
