"""Memory retrieval: multi-source recall + LLM rerank."""

from __future__ import annotations

import math
import re
import time

from app.config import settings
from app.entity.resolver import EntityResolver
from app.llm import llm
from app.llm.prompts import RERANK_SYSTEM, RERANK_TEMPLATE
from app.memory.store import MemoryStore
from app.schemas import Episode, RetrievedItem

_CJK_TOKEN = re.compile(r"[\u4e00-\u9fff]{2,4}")


class Retriever:
    def __init__(self, store: MemoryStore, resolver: EntityResolver | None = None) -> None:
        self.store = store
        self.resolver = resolver or EntityResolver(store)

    def _episodic_score(self, ep: Episode, sim: float) -> float:
        age_days = max(0.0, (time.time() - ep.last_seen) / 86400)
        half = settings.episodic_recency_half_life_days
        recency = 0.85 + 0.15 * math.exp(-age_days / half)
        return round(sim * ep.weight * recency, 4)

    def _mentioned_persons(self, query: str) -> list[str]:
        hits: list[str] = []
        q_lower = query.lower()

        for persona in self.store.persona.all():
            if persona.name and persona.name.lower() in q_lower:
                if persona.name not in hits:
                    hits.append(persona.name)
            for alias in persona.aliases:
                if alias and alias.lower() in q_lower and persona.name not in hits:
                    hits.append(persona.name)

        for token in _CJK_TOKEN.findall(query):
            resolved = self.resolver.resolve(token)
            if resolved and resolved not in hits:
                hits.append(resolved)

        return hits

    def recall(self, query: str, top_k: int | None = None) -> list[RetrievedItem]:
        top_k = top_k or settings.episodic_top_k
        items: list[RetrievedItem] = []

        for ep, sim in self.store.episodic.search(query, top_k=top_k):
            score = self._episodic_score(ep, sim)
            items.append(
                RetrievedItem(
                    id=f"epi:{ep.id}",
                    source="episodic",
                    text=ep.summary,
                    score=score,
                    meta={
                        "topic": ep.topic,
                        "participants": ep.participants,
                        "emotion": ep.emotion,
                        "weight": ep.weight,
                        "sim": round(sim, 4),
                    },
                )
            )

        for name in self._mentioned_persons(query):
            persona = self.store.persona.get(name)
            if persona:
                traits = ", ".join(sorted(persona.traits, key=persona.traits.get, reverse=True)[:5])
                prefs = ", ".join(
                    sorted(persona.preferences, key=persona.preferences.get, reverse=True)[:5]
                )
                items.append(
                    RetrievedItem(
                        id=f"per:{name}",
                        source="persona",
                        text=f"{name} — traits: {traits or 'n/a'}; prefers: {prefs or 'n/a'}",
                        score=1.0,
                        meta={"mention_count": persona.mention_count},
                    )
                )
            graph = self.store.semantic.neighbors(name)
            for rel in graph["relations"][:5]:
                items.append(
                    RetrievedItem(
                        id=f"sem:{name}:{rel['label']}:{rel['target']}",
                        source="semantic",
                        text=f"{name} {rel['label']} {rel['target']}",
                        score=round(min(1.0, rel["weight"]), 4),
                        meta={"weight": rel["weight"]},
                    )
                )
        return items

    def _rerank(self, query: str, candidates: list[RetrievedItem]) -> list[RetrievedItem]:
        if len(candidates) <= settings.rerank_keep:
            return candidates
        listing = "\n".join(f"- {c.id}: {c.text}" for c in candidates)
        try:
            data = llm.chat_json(
                RERANK_TEMPLATE.format(query=query, candidates=listing),
                system=RERANK_SYSTEM,
            )
            keep_ids = data.get("relevant_ids", []) if isinstance(data, dict) else []
        except Exception:
            keep_ids = []
        if not keep_ids:
            return sorted(candidates, key=lambda c: c.score, reverse=True)[: settings.rerank_keep]
        order = {cid: i for i, cid in enumerate(keep_ids)}
        kept = [c for c in candidates if c.id in order]
        kept.sort(key=lambda c: order[c.id])
        return kept[: settings.rerank_keep]

    def retrieve(self, query: str, rerank: bool = True) -> list[RetrievedItem]:
        candidates = self.recall(query)
        if not candidates:
            return []
        if rerank:
            return self._rerank(query, candidates)
        return sorted(candidates, key=lambda c: c.score, reverse=True)[: settings.rerank_keep]
