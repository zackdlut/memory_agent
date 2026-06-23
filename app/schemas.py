"""Pydantic data models shared across the pipeline and API."""

from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic import BaseModel, Field


def _now() -> float:
    return time.time()


def _uid() -> str:
    return uuid.uuid4().hex[:12]


# --------------------------------------------------------------------- inputs
class IngestRequest(BaseModel):
    text: str
    source: str = "chat"


class AskRequest(BaseModel):
    query: str


class PredictRequest(BaseModel):
    person: str
    situation: str


class MergeRequest(BaseModel):
    source: str
    target: str


class PersonEditRequest(BaseModel):
    summary: str | None = None
    remove_traits: list[str] = Field(default_factory=list)
    remove_preferences: list[str] = Field(default_factory=list)
    remove_pattern_indices: list[int] = Field(default_factory=list)
    add_aliases: list[str] = Field(default_factory=list)


# --------------------------------------------------------------- core records
class Entity(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    traits: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)


class Relation(BaseModel):
    subject: str
    relation: str
    object: str


class BehaviorPattern(BaseModel):
    person: str
    trigger: str
    behavior: str


class Episode(BaseModel):
    id: str = Field(default_factory=_uid)
    summary: str
    topic: str = "general"
    participants: list[str] = Field(default_factory=list)
    emotion: str = "neutral"
    emotion_intensity: float = 0.0
    task_related: bool = False
    text: str = ""  # raw source snippet
    source: str = "chat"
    weight: float = 1.0
    created_at: float = Field(default_factory=_now)
    last_seen: float = Field(default_factory=_now)


class ExtractionResult(BaseModel):
    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    behavior_patterns: list[BehaviorPattern] = Field(default_factory=list)
    episode: Episode


# ------------------------------------------------------------------ persona
class Persona(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    summary: str = ""
    traits: dict[str, float] = Field(default_factory=dict)  # trait -> weight
    preferences: dict[str, float] = Field(default_factory=dict)
    patterns: list[BehaviorPattern] = Field(default_factory=list)
    mention_count: int = 0
    last_seen: float = Field(default_factory=_now)
    last_summary_at: float = 0.0


# ----------------------------------------------------------------- retrieval
class RetrievedItem(BaseModel):
    id: str
    source: str  # "episodic" | "semantic" | "persona"
    text: str
    score: float = 0.0
    meta: dict[str, Any] = Field(default_factory=dict)


class IngestResponse(BaseModel):
    episode: Episode
    entities: list[Entity]
    relations: list[Relation]
    behavior_patterns: list[BehaviorPattern]
    evolution: dict[str, Any] = Field(default_factory=dict)


class AskResponse(BaseModel):
    answer: str
    used_memories: list[RetrievedItem] = Field(default_factory=list)


class Prediction(BaseModel):
    person: str
    situation: str
    predicted_action: str
    confidence: float = 0.0
    reasoning: str = ""
    alternatives: list[str] = Field(default_factory=list)
    used_memories: list[RetrievedItem] = Field(default_factory=list)


# -------------------------------------------------------------------- chat
class ChatMessage(BaseModel):
    id: str = Field(default_factory=_uid)
    session_id: str
    role: str  # "user" | "assistant"
    content: str
    created_at: float = Field(default_factory=_now)


class ChatSession(BaseModel):
    id: str = Field(default_factory=_uid)
    person: str | None = None
    title: str = "新会话"
    state: str = "awaiting_identity"  # "awaiting_identity" | "active"
    created_at: float = Field(default_factory=_now)
    last_active: float = Field(default_factory=_now)


class TraitWeight(BaseModel):
    name: str
    weight: float


class Understanding(BaseModel):
    name: str
    summary: str = ""
    traits: list[TraitWeight] = Field(default_factory=list)
    preferences: list[TraitWeight] = Field(default_factory=list)
    patterns: list[BehaviorPattern] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)
    mention_count: int = 0
    assistant_relationship: str = ""
    mutual_acquaintances: list[str] = Field(default_factory=list)


# ------------------------------------------------------- assistant self model
class SelfExperience(BaseModel):
    id: str = Field(default_factory=_uid)
    summary: str  # first-person reflection, e.g. "我陪 zack 聊了考研焦虑"
    person: str = ""
    emotion: str = "neutral"
    created_at: float = Field(default_factory=_now)


class SelfProfile(BaseModel):
    name: str
    role: str = ""
    summary: str = ""
    traits: dict[str, float] = Field(default_factory=dict)
    preferences: dict[str, float] = Field(default_factory=dict)
    experiences: list[SelfExperience] = Field(default_factory=list)
    interaction_count: int = 0


class KnownPerson(BaseModel):
    name: str
    familiarity: int = 0
    relationship: str = ""


class SelfProfileView(BaseModel):
    profile: SelfProfile
    known_people: list[KnownPerson] = Field(default_factory=list)


class CreateSessionResponse(BaseModel):
    session_id: str
    greeting: str


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    identified: bool = False
    person: str | None = None
    understanding: Understanding | None = None
    prediction: Prediction | None = None
    used_memories: list[RetrievedItem] = Field(default_factory=list)


class SessionSummary(BaseModel):
    id: str
    person: str | None = None
    title: str
    state: str
    last_active: float
    last_message: str = ""


class SessionDetail(BaseModel):
    session: ChatSession
    messages: list[ChatMessage] = Field(default_factory=list)
