"""Procedural memory = a small registry of callable skills.

Mirrors human "procedural memory" (knowing how to do things). The reasoning
layer can look up and invoke these by name. Kept intentionally small for the
MVP; new skills register with the ``@skill`` decorator.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Skill:
    name: str
    description: str
    fn: Callable


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, name: str, description: str):
        def deco(fn: Callable) -> Callable:
            self._skills[name] = Skill(name=name, description=description, fn=fn)
            return fn

        return deco

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def list(self) -> list[dict]:
        return [{"name": s.name, "description": s.description} for s in self._skills.values()]

    def run(self, name: str, **kwargs):
        skill = self.get(name)
        if not skill:
            raise KeyError(f"unknown skill: {name}")
        return skill.fn(**kwargs)


registry = SkillRegistry()


def install_default_skills(store) -> None:
    """Register the built-in skills, bound to a MemoryStore instance."""

    @registry.register("summarize_person", "Summarize what we know about a person")
    def summarize_person(person: str) -> dict:
        persona = store.persona.get(person)
        graph = store.semantic.neighbors(person)
        return {"persona": persona.model_dump() if persona else None, "graph": graph}

    @registry.register("compare_preferences", "Compare two people's preferences")
    def compare_preferences(person_a: str, person_b: str) -> dict:
        pa = store.persona.get(person_a)
        pb = store.persona.get(person_b)
        prefs_a = set((pa.preferences if pa else {}).keys())
        prefs_b = set((pb.preferences if pb else {}).keys())
        return {
            "shared": sorted(prefs_a & prefs_b),
            f"{person_a}_only": sorted(prefs_a - prefs_b),
            f"{person_b}_only": sorted(prefs_b - prefs_a),
        }

    @registry.register("list_relations", "List a person's known relations")
    def list_relations(person: str) -> dict:
        return {"relations": store.semantic.neighbors(person).get("relations", [])}
