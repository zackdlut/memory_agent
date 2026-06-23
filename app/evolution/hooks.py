"""Post-ingest hooks: persona summary refresh."""

from __future__ import annotations

import time

from app.config import settings
from app.llm import llm
from app.llm.prompts import SUMMARY_SYSTEM, SUMMARY_TEMPLATE
from app.memory.store import MemoryStore
from app.schemas import Persona


def should_refresh_summary(persona: Persona, traits_changed: bool) -> bool:
    if persona.summary == "":
        return True
    if traits_changed:
        return True
    if persona.mention_count >= 2:
        return True
    return False


def _cooldown_ok(persona: Persona) -> bool:
    if persona.last_summary_at <= 0:
        return True
    return (time.time() - persona.last_summary_at) >= settings.summary_refresh_cooldown_sec


def _format_summary_input(store: MemoryStore, name: str) -> str:
    persona = store.persona.get(name)
    if persona is None:
        return ""
    traits = sorted(persona.traits, key=persona.traits.get, reverse=True)[:8]
    prefs = sorted(persona.preferences, key=persona.preferences.get, reverse=True)[:8]
    patterns = [
        f"when {p.trigger or 'general'}: {p.behavior}" for p in persona.patterns[:6]
    ]
    graph = store.semantic.neighbors(name)
    rels = [
        f"{r['label']} {r['target']}" for r in graph.get("relations", [])[:6]
    ]
    return SUMMARY_TEMPLATE.format(
        name=persona.name,
        traits=", ".join(traits) or "none",
        preferences=", ".join(prefs) or "none",
        patterns="; ".join(patterns) or "none",
        relations=", ".join(rels) or "none",
    )


def refresh_person_summaries(
    store: MemoryStore,
    persons: list[str],
    traits_changed: dict[str, bool],
) -> None:
    for name in persons:
        if not name or name == settings.assistant_name:
            continue
        persona = store.persona.get(name)
        if persona is None:
            continue
        changed = traits_changed.get(name, False)
        if not should_refresh_summary(persona, changed):
            continue
        if not _cooldown_ok(persona):
            continue
        prompt = _format_summary_input(store, name)
        if not prompt:
            continue
        try:
            text = llm.chat(prompt, system=SUMMARY_SYSTEM, temperature=0.3).strip()
        except Exception:
            continue
        if text:
            store.persona.regenerate_summary(name, text)
