"""The orchestrator that wires the whole human-like memory pipeline together.

  ingest : perception -> encoding -> store + self-evolution
  ask    : retrieval  -> reasoning
  predict: retrieval  -> behavior prediction
"""

from __future__ import annotations

from app.encoding import encode
from app.entity import EntityResolver
from app.evolution import Evolver
from app.evolution.hooks import refresh_person_summaries
from app.memory.store import MemoryStore, store
from app.perception import perceive
from app.prediction import Predictor
from app.reasoning import Reasoner
from app.retrieval import Retriever
from app.schemas import (
    AskResponse,
    IngestResponse,
    Prediction,
)


class MemoryAgent:
    def __init__(self, memory: MemoryStore | None = None) -> None:
        self.store = memory or store
        self.resolver = EntityResolver(self.store)
        self.evolver = Evolver(self.store)
        self.retriever = Retriever(self.store, self.resolver)
        self.reasoner = Reasoner()
        self.predictor = Predictor(self.store, self.retriever)

    # ---------------------------------------------------------------- ingest
    def ingest(self, text: str, source: str = "chat") -> IngestResponse:
        perceived = perceive(text)
        result = encode(perceived, source=source, store=self.store)
        result = self.resolver.normalize_extraction(result)
        report = self.evolver.ingest(result)
        updated_persons = [e.name for e in result.entities]
        traits_changed = {e.name: bool(e.traits or e.preferences) for e in result.entities}
        refresh_person_summaries(self.store, updated_persons, traits_changed)
        return IngestResponse(
            episode=result.episode,
            entities=result.entities,
            relations=result.relations,
            behavior_patterns=result.behavior_patterns,
            evolution={
                "action": report.action,
                "weight": report.weight,
                "signals": report.signals,
                "merged_into": report.merged_into,
            },
        )

    # ------------------------------------------------------------------- ask
    def ask(self, query: str) -> AskResponse:
        memories = self.retriever.retrieve(query, rerank=True)
        answer = self.reasoner.answer(query, memories)
        return AskResponse(answer=answer, used_memories=memories)

    # --------------------------------------------------------------- predict
    def predict(self, person: str, situation: str) -> Prediction:
        return self.predictor.predict(person, situation)


agent = MemoryAgent()
