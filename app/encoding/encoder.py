"""Memory encoding layer.

Transforms perceived input into structured knowledge (entities, traits,
relations, behavior patterns, episode) using the LLM with a strict-JSON
prompt. Includes a deterministic fallback so the pipeline still produces an
episode even if the LLM output is unusable.

This module is deliberately the single seam where a fine-tuned extraction
model (e.g. a LoRA "text -> structured knowledge" model, PRD section 9) could
be swapped in later: only ``_run_extraction`` would change.
"""

from __future__ import annotations

from app.llm import llm
from app.llm.prompts import EXTRACTION_SYSTEM, EXTRACTION_TEMPLATE
from app.memory.store import MemoryStore
from app.perception import PerceivedInput
from app.schemas import (
    BehaviorPattern,
    Entity,
    Episode,
    ExtractionResult,
    Relation,
)


def _coerce_str_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value)]


def _known_people_block(store: MemoryStore) -> str:
    lines = []
    for p in store.persona.all():
        alias = f" (aliases: {', '.join(p.aliases)})" if p.aliases else ""
        lines.append(f"- {p.name}{alias}")
    return "\n".join(lines) or "(none yet)"


def _run_extraction(conversation: str, known_people: str, speakers: str) -> dict:
    prompt = EXTRACTION_TEMPLATE.format(
        conversation=conversation,
        known_people=known_people,
        speakers=speakers or "(unknown)",
    )
    return llm.chat_json(prompt, system=EXTRACTION_SYSTEM)


def _fallback_result(perceived: PerceivedInput) -> ExtractionResult:
    summary = perceived.sentences[0] if perceived.sentences else perceived.raw[:120]
    entities = [Entity(name=s) for s in perceived.speakers]
    episode = Episode(
        summary=summary or "(empty)",
        topic="general",
        participants=perceived.speakers,
        text=perceived.raw,
    )
    return ExtractionResult(entities=entities, episode=episode)


def encode(
    perceived: PerceivedInput,
    source: str = "chat",
    store: MemoryStore | None = None,
) -> ExtractionResult:
    """Encode perceived input into a structured :class:`ExtractionResult`."""
    known_people = _known_people_block(store) if store else "(none yet)"
    speakers = ", ".join(perceived.speakers) if perceived.speakers else "(unknown)"
    try:
        data = _run_extraction(perceived.raw, known_people, speakers)
    except Exception:
        return _fallback_result(perceived)

    if not isinstance(data, dict):
        return _fallback_result(perceived)

    # entities
    entities: list[Entity] = []
    for e in data.get("entities", []) or []:
        if not isinstance(e, dict) or not e.get("name"):
            continue
        entities.append(
            Entity(
                name=str(e["name"]).strip(),
                aliases=_coerce_str_list(e.get("aliases")),
                traits=_coerce_str_list(e.get("traits")),
                preferences=_coerce_str_list(e.get("preferences")),
            )
        )

    # relations
    relations: list[Relation] = []
    for r in data.get("relations", []) or []:
        if not isinstance(r, dict):
            continue
        subj, rel, obj = r.get("subject"), r.get("relation"), r.get("object")
        if subj and rel and obj:
            relations.append(
                Relation(subject=str(subj).strip(), relation=str(rel).strip(), object=str(obj).strip())
            )

    # behavior patterns
    patterns: list[BehaviorPattern] = []
    for p in data.get("behavior_patterns", []) or []:
        if not isinstance(p, dict):
            continue
        person, behavior = p.get("person"), p.get("behavior")
        if person and behavior:
            patterns.append(
                BehaviorPattern(
                    person=str(person).strip(),
                    trigger=str(p.get("trigger", "")).strip(),
                    behavior=str(behavior).strip(),
                )
            )

    # episode
    ep_raw = data.get("episode") or {}
    if not isinstance(ep_raw, dict):
        ep_raw = {}
    try:
        intensity = float(ep_raw.get("emotion_intensity", 0.0) or 0.0)
    except (TypeError, ValueError):
        intensity = 0.0
    episode = Episode(
        summary=str(ep_raw.get("summary") or (perceived.sentences[0] if perceived.sentences else perceived.raw[:120])),
        topic=str(ep_raw.get("topic") or "general"),
        participants=_coerce_str_list(ep_raw.get("participants")) or [e.name for e in entities],
        emotion=str(ep_raw.get("emotion") or "neutral"),
        emotion_intensity=max(0.0, min(1.0, intensity)),
        task_related=bool(ep_raw.get("task_related", False)),
        text=perceived.raw,
        source=source,
    )

    return ExtractionResult(
        entities=entities,
        relations=relations,
        behavior_patterns=patterns,
        episode=episode,
    )
