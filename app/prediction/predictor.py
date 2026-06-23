"""Behavior prediction: Theory-of-Mind style action prediction.

Combines a person's persona (traits, preferences, patterns) with relevant past
episodes to predict what they will most likely do in a new situation.
"""

from __future__ import annotations

from app.llm import llm
from app.llm.prompts import PREDICTION_SYSTEM, PREDICTION_TEMPLATE
from app.memory.store import MemoryStore
from app.retrieval import Retriever
from app.schemas import Prediction, RetrievedItem


def _format_persona(persona, graph) -> str:
    if persona is None:
        return "(no persona on record)"
    traits = sorted(persona.traits, key=persona.traits.get, reverse=True)[:8]
    prefs = sorted(persona.preferences, key=persona.preferences.get, reverse=True)[:8]
    lines = [
        f"Name: {persona.name}",
        f"Aliases: {', '.join(persona.aliases) or 'none'}",
        f"Traits: {', '.join(traits) or 'unknown'}",
        f"Preferences: {', '.join(prefs) or 'unknown'}",
    ]
    if persona.patterns:
        lines.append("Behavior patterns:")
        for p in persona.patterns[:8]:
            lines.append(f"  - when {p.trigger or 'in general'}: {p.behavior}")
    rels = graph.get("relations", []) if graph else []
    if rels:
        lines.append("Relations: " + ", ".join(f"{r['label']} {r['target']}" for r in rels[:6]))
    return "\n".join(lines)


class Predictor:
    def __init__(self, store: MemoryStore, retriever: Retriever) -> None:
        self.store = store
        self.retriever = retriever

    def predict(self, person: str, situation: str) -> Prediction:
        persona = self.store.persona.get(person)
        graph = self.store.semantic.neighbors(person)
        persona_text = _format_persona(persona, graph)

        # recall episodes relevant to this person + situation
        memories = self.retriever.recall(f"{person} {situation}", top_k=6)
        episodes_text = "\n".join(f"- {m.text}" for m in memories) or "(none)"

        prompt = PREDICTION_TEMPLATE.format(
            persona=persona_text, episodes=episodes_text, situation=situation
        )
        try:
            data = llm.chat_json(prompt, system=PREDICTION_SYSTEM, temperature=0.3)
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}

        try:
            confidence = float(data.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0

        alts = data.get("alternatives", []) or []
        if not isinstance(alts, list):
            alts = [str(alts)]

        return Prediction(
            person=person,
            situation=situation,
            predicted_action=str(data.get("predicted_action", "")) or "(unable to predict)",
            confidence=max(0.0, min(1.0, confidence)),
            reasoning=str(data.get("reasoning", "")),
            alternatives=[str(a) for a in alts],
            used_memories=memories,
        )
