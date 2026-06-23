"""Reasoning layer: answer questions with person-aware understanding."""

from __future__ import annotations

from app.llm import llm
from app.llm.prompts import REASONING_SYSTEM, REASONING_TEMPLATE
from app.schemas import RetrievedItem


def _format_context(items: list[RetrievedItem]) -> str:
    if not items:
        return "(no relevant memories found)"
    lines = []
    for it in items:
        lines.append(f"[{it.source}] {it.text}")
    return "\n".join(lines)


class Reasoner:
    def answer(self, query: str, memories: list[RetrievedItem]) -> str:
        context = _format_context(memories)
        prompt = REASONING_TEMPLATE.format(context=context, query=query)
        return llm.chat(prompt, system=REASONING_SYSTEM, temperature=0.3).strip()
