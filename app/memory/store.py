"""Unified memory store: the single facade over the four memory subsystems.

  - episodic  (FAISS vector store)
  - semantic  (NetworkX knowledge graph)
  - persona   (SQLite person models)
  - skills    (procedural registry)

All persistence is handled by the individual stores; this facade just wires
them together and exposes convenience helpers used by the agent pipeline.
"""

from __future__ import annotations

from app.memory.episodic import EpisodicMemory
from app.memory.persona import PersonaMemory
from app.memory.self_profile import SelfProfileStore
from app.memory.semantic import SemanticMemory
from app.memory.skills import install_default_skills, registry


class MemoryStore:
    def __init__(self) -> None:
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()
        self.persona = PersonaMemory()
        self.self_profile = SelfProfileStore()
        self.skills = registry
        install_default_skills(self)

    def stats(self) -> dict:
        return {
            "episodes": self.episodic.count(),
            "persons": self.persona.count(),
            "graph_nodes": self.semantic.g.number_of_nodes(),
            "graph_edges": self.semantic.g.number_of_edges(),
            "skills": len(self.skills.list()),
            "self_interactions": self.self_profile.get().interaction_count,
        }

    def commit(self) -> None:
        self.semantic.commit()


store = MemoryStore()
