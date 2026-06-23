"""Self-evolution: how memories get written, strengthened, merged and decayed.

Implements the PRD's three salience signals and three update strategies:

Signals (what makes a memory "stick"):
  - repetition       -> a near-duplicate episode already exists
  - emotional intensity
  - task relevance

Strategies:
  - Merge   : a strongly-similar prior episode is reinforced instead of stored
  - Weight  : episode weight is boosted by the salience signals
  - Replace : (graph/persona) repeated facts strengthen edges; global decay
              gradually erodes stale, unreinforced memories
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.memory.store import MemoryStore
from app.schemas import ExtractionResult


# similarity above which a new episode is treated as a repeat of an old one
MERGE_THRESHOLD = 0.92


@dataclass
class EvolutionReport:
    action: str  # "stored" | "merged"
    episode_id: str
    weight: float
    signals: dict
    merged_into: str | None = None


class Evolver:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def _salience(self, result: ExtractionResult, repeat: bool) -> tuple[float, dict]:
        ep = result.episode
        weight = 1.0
        signals = {"repetition": repeat, "emotion": 0.0, "task_related": ep.task_related}
        # emotional intensity
        if ep.emotion_intensity > 0:
            gain = settings.emotion_weight_gain * ep.emotion_intensity
            weight += gain
            signals["emotion"] = round(ep.emotion_intensity, 3)
        # task relevance
        if ep.task_related:
            weight += settings.task_weight_gain
        # repetition
        if repeat:
            weight += settings.repeat_weight_gain
        return round(weight, 4), signals

    def ingest(self, result: ExtractionResult) -> EvolutionReport:
        ep = result.episode

        # --- detect repetition against episodic memory --------------------
        repeat_match = None
        hits = self.store.episodic.search(ep.summary, top_k=1)
        if hits and hits[0][1] >= MERGE_THRESHOLD:
            repeat_match = hits[0][0]

        weight, signals = self._salience(result, repeat=repeat_match is not None)
        ep.weight = weight

        # --- write / merge episodic ---------------------------------------
        if repeat_match is not None:
            # MERGE: reinforce the existing episode rather than duplicate it
            repeat_match.weight = round(repeat_match.weight + settings.repeat_weight_gain, 4)
            repeat_match.last_seen = ep.last_seen
            self.store.episodic.update(repeat_match)
            report = EvolutionReport(
                action="merged",
                episode_id=repeat_match.id,
                weight=repeat_match.weight,
                signals=signals,
                merged_into=repeat_match.id,
            )
        else:
            self.store.episodic.add(ep)
            report = EvolutionReport(
                action="stored", episode_id=ep.id, weight=ep.weight, signals=signals
            )

        # --- update semantic graph + persona (Replace/Weight via bumps) ---
        # edges/traits get +gain each time they recur -> repeated facts win
        # the AI assistant itself is a conversation participant, not a person
        # to be modelled, so we never build a persona/graph node for it.
        emotion_boost = 1.0 + ep.emotion_intensity
        for entity in result.entities:
            if entity.name == settings.assistant_name:
                continue
            self.store.semantic.add_person(entity.name, aliases=entity.aliases)
            for trait in entity.traits:
                self.store.semantic.add_trait(entity.name, trait, gain=0.3 * emotion_boost)
            for pref in entity.preferences:
                self.store.semantic.add_preference(entity.name, pref, gain=0.3 * emotion_boost)
            self.store.persona.upsert(
                entity.name,
                aliases=entity.aliases,
                traits=entity.traits,
                preferences=entity.preferences,
                trait_gain=0.3 * emotion_boost,
                pref_gain=0.3 * emotion_boost,
            )

        for rel in result.relations:
            if settings.assistant_name in (rel.subject, rel.object):
                continue
            self.store.semantic.add_relation(rel.subject, rel.relation, rel.object)

        # behavior patterns -> attach to persona
        patterns_by_person: dict[str, list] = {}
        for pat in result.behavior_patterns:
            if pat.person == settings.assistant_name:
                continue
            patterns_by_person.setdefault(pat.person, []).append(pat)
        for person, pats in patterns_by_person.items():
            self.store.persona.upsert(person, patterns=pats)

        self.store.commit()
        return report

    def decay(self) -> None:
        """Periodic forgetting: erode unreinforced semantic/persona weights."""
        factor = settings.decay_factor
        self.store.semantic.decay(factor)
        self.store.persona.decay(factor)
        self.store.self_profile.decay(factor)
        self.store.episodic.decay(factor)
        self.store.episodic.prune(settings.episodic_prune_min_weight)
        self.store.commit()
