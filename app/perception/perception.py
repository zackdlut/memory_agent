"""Perception layer: the agent's "sensory memory" + working buffer.

Turns raw input text into a lightly structured form:
  - splits speaker turns (``Alice: ...`` / ``Alice：...``)
  - segments sentences
  - collects a cheap set of candidate named entities (capitalised tokens and
    the detected speakers) as a hint for the encoder.

This stage is intentionally cheap and deterministic; the heavy lifting of
semantic extraction happens in the encoding layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# "Name: utterance" or full-width colon "Name：utterance"
_SPEAKER_RE = re.compile(r"^\s*([\w\u4e00-\u9fff][\w\u4e00-\u9fff .'-]{0,30}?)\s*[:：]\s*(.+)$")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。！？])\s+|\n+")
# capitalised latin words or CJK 2-4 char sequences as naive entity hints
_ENTITY_HINT = re.compile(r"\b[A-Z][a-zA-Z]+\b|[\u4e00-\u9fff]{2,4}")

_STOP_HINTS = {
    "The", "A", "An", "I", "We", "You", "He", "She", "They", "It",
    "This", "That", "And", "But", "OK", "Okay",
}


@dataclass
class Turn:
    speaker: str | None
    text: str


@dataclass
class PerceivedInput:
    raw: str
    turns: list[Turn] = field(default_factory=list)
    speakers: list[str] = field(default_factory=list)
    sentences: list[str] = field(default_factory=list)
    entity_hints: list[str] = field(default_factory=list)


def perceive(text: str) -> PerceivedInput:
    raw = text.strip()
    turns: list[Turn] = []
    speakers: list[str] = []

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _SPEAKER_RE.match(line)
        if m:
            speaker = m.group(1).strip()
            utterance = m.group(2).strip()
            turns.append(Turn(speaker=speaker, text=utterance))
            if speaker not in speakers:
                speakers.append(speaker)
        else:
            turns.append(Turn(speaker=None, text=line))

    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(raw) if s.strip()]

    hints: list[str] = list(speakers)
    for token in _ENTITY_HINT.findall(raw):
        if token in _STOP_HINTS:
            continue
        if token not in hints:
            hints.append(token)

    return PerceivedInput(
        raw=raw,
        turns=turns,
        speakers=speakers,
        sentences=sentences,
        entity_hints=hints,
    )
