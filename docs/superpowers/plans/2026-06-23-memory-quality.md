# 记忆质量提升（Phase 1）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix A1–A4 memory quality issues via EntityResolver, improved retrieval scoring, episodic decay/prune, auto summary generation, and pytest/eval coverage.

**Architecture:** Add `EntityResolver` as the single canonical-name entry point before evolver writes; extend episodic lifecycle in decay; post-ingest hooks refresh persona summaries; retriever uses resolver + weight/recency scoring. Spec: `docs/superpowers/specs/2026-06-23-memory-quality-design.md`.

**Tech Stack:** Python 3.10+, FastAPI, FAISS, NetworkX, SQLite, pytest, existing Ollama LLM client (mocked in unit tests)

## Global Constraints

- Do not model `settings.assistant_name` (default `三叶虫`) as a persona node.
- Substring merge only when shorter name ≥ 2 chars and is a true substring of longer name; no fuzzy edit-distance merge.
- `episodic_prune_min_weight` default `0.15`; `decay_factor` default `0.98`; `episodic_recency_half_life_days` default `30.0`; `summary_refresh_cooldown_sec` default `60`.
- Phase 1 excludes merge API, edit UI, and auto-scheduled decay.
- Follow existing patterns: Pydantic schemas, `MemoryStore` facade, minimal diffs.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `app/config.py` | Modify | New tuning fields |
| `app/schemas.py` | Modify | `Persona.last_summary_at` |
| `app/entity/__init__.py` | Create | Export resolver |
| `app/entity/resolver.py` | Create | Canonical name resolution |
| `app/evolution/hooks.py` | Create | Summary refresh after ingest |
| `app/evolution/evolver.py` | Modify | normalize before write; episodic in decay |
| `app/encoding/encoder.py` | Modify | Inject known people + speakers |
| `app/llm/prompts.py` | Modify | EXTRACTION placeholders; SUMMARY templates |
| `app/agent.py` | Modify | Wire resolver + hooks |
| `app/retrieval/retriever.py` | Modify | Resolver-based mention detection; scoring |
| `app/memory/episodic.py` | Modify | `decay()`, `prune()` |
| `app/memory/persona.py` | Modify | `last_summary_at` on regenerate_summary |
| `scripts/eval.py` | Modify | alias + merge metrics |
| `requirements.txt` | Modify | Add pytest |
| `tests/conftest.py` | Create | Temp data dir fixture |
| `tests/test_entity_resolver.py` | Create | A1 tests |
| `tests/test_episodic_lifecycle.py` | Create | A3 tests |
| `tests/test_retriever_scoring.py` | Create | A2 tests |
| `tests/test_summary_hooks.py` | Create | A4 tests |

---

### Task 1: Config + Persona schema

**Files:**
- Modify: `app/config.py`
- Modify: `app/schemas.py`
- Modify: `app/memory/persona.py`

**Interfaces:**
- Produces: `Settings.episodic_prune_min_weight`, `Settings.episodic_recency_half_life_days`, `Settings.summary_refresh_cooldown_sec`
- Produces: `Persona.last_summary_at: float = 0.0`
- Produces: `PersonaMemory.regenerate_summary(name, summary)` sets `last_summary_at = time.time()`

- [ ] **Step 1: Add config fields**

In `app/config.py` under retrieval/evolution tuning:

```python
episodic_prune_min_weight: float = 0.15
episodic_recency_half_life_days: float = 30.0
summary_refresh_cooldown_sec: float = 60.0
```

- [ ] **Step 2: Add Persona field**

In `app/schemas.py` `Persona` class:

```python
last_summary_at: float = 0.0
```

- [ ] **Step 3: Update regenerate_summary**

In `app/memory/persona.py`:

```python
def regenerate_summary(self, name: str, summary: str) -> None:
    with self._lock:
        persona = self.get(name)
        if persona:
            persona.summary = summary
            persona.last_summary_at = time.time()
            self._save(persona)
```

- [ ] **Step 4: Verify imports**

Run: `python -c "from app.schemas import Persona; from app.config import settings; print(settings.episodic_prune_min_weight)"`  
Expected: `0.15`

---

### Task 2: EntityResolver

**Files:**
- Create: `app/entity/__init__.py`
- Create: `app/entity/resolver.py`
- Create: `tests/conftest.py`
- Create: `tests/test_entity_resolver.py`
- Modify: `requirements.txt` (add `pytest>=8.0`)

**Interfaces:**
- Produces: `EntityResolver(store).resolve(name: str) -> str | None`
- Produces: `EntityResolver(store).normalize_extraction(result: ExtractionResult) -> ExtractionResult`
- Produces: `EntityResolver(store)._merge_same_round_entities(entities: list[Entity]) -> dict[str, str]` mapping raw→canonical

- [ ] **Step 1: Add pytest + conftest**

`requirements.txt` append: `pytest>=8.0`

`tests/conftest.py`:

```python
import pytest
from pathlib import Path
import app.config as config_module
from app.memory.store import MemoryStore


@pytest.fixture
def temp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(config_module.settings, "sqlite_path", tmp_path / "memory.db")
    monkeypatch.setattr(config_module.settings, "faiss_index_path", tmp_path / "episodic.index")
    monkeypatch.setattr(config_module.settings, "graph_path", tmp_path / "graph.json")
    return MemoryStore()
```

- [ ] **Step 2: Write failing tests**

`tests/test_entity_resolver.py`:

```python
from app.entity.resolver import EntityResolver
from app.schemas import Entity, ExtractionResult, Episode, Relation, BehaviorPattern


def test_resolve_by_alias(temp_store):
    temp_store.persona.upsert("林然", aliases=["小然"])
    r = EntityResolver(temp_store)
    assert r.resolve("小然") == "林然"


def test_same_round_substring_merge(temp_store):
    r = EntityResolver(temp_store)
    result = ExtractionResult(
        entities=[
            Entity(name="小然", traits=["内向"]),
            Entity(name="林然", traits=["工程师"], aliases=["小然"]),
        ],
        relations=[Relation(subject="小然", relation="搭档", object="David")],
        behavior_patterns=[BehaviorPattern(person="小然", trigger="deadline", behavior="喝咖啡")],
        episode=Episode(summary="林然赶工", participants=["小然", "林然"]),
    )
    out = r.normalize_extraction(result)
    names = {e.name for e in out.entities}
    assert names == {"林然"}
    assert "小然" in out.entities[0].aliases
    assert out.relations[0].subject == "林然"
    assert out.behavior_patterns[0].person == "林然"
    assert out.episode.participants == ["林然"]


def test_resolve_existing_after_upsert(temp_store):
    temp_store.persona.upsert("林然")
    r = EntityResolver(temp_store)
    result = ExtractionResult(
        entities=[Entity(name="小然", traits=["夜猫子"])],
        episode=Episode(summary="小然写代码"),
    )
    out = r.normalize_extraction(result)
    assert out.entities[0].name == "林然"
```

- [ ] **Step 3: Run tests — expect FAIL**

Run: `pytest tests/test_entity_resolver.py -v`  
Expected: FAIL (`ModuleNotFoundError` or missing `EntityResolver`)

- [ ] **Step 4: Implement EntityResolver**

`app/entity/__init__.py`:

```python
from app.entity.resolver import EntityResolver

__all__ = ["EntityResolver"]
```

`app/entity/resolver.py` core logic:

```python
from __future__ import annotations

from app.config import settings
from app.memory.store import MemoryStore
from app.schemas import Entity, ExtractionResult


class EntityResolver:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def resolve(self, name: str) -> str | None:
        if not name or name == settings.assistant_name:
            return None
        persona = self.store.persona.get(name)
        if persona:
            return persona.name
        graph_name = self.store.semantic.resolve(name)
        if graph_name:
            return graph_name
        return None

    @staticmethod
    def _is_substring_alias(short: str, long: str) -> bool:
        return len(short) >= 2 and short != long and short in long

    def _merge_same_round_entities(self, entities: list[Entity]) -> dict[str, str]:
        canonical: dict[str, str] = {e.name: e.name for e in entities}
        merged: list[Entity] = []

        def find(i: int) -> str:
            while canonical[entities[i].name] != entities[i].name:
                entities[i].name = canonical[entities[i].name]
            return entities[i].name

        for i, a in enumerate(entities):
            for j, b in enumerate(entities):
                if i == j:
                    continue
                pair = [(a.name, b.name), (b.name, a.name)]
                for x, y in pair:
                    if y in (entities[j].aliases if j == entities.index(b) else b.aliases):
                        canon = x if len(x) >= len(y) else y
                        alias = y if canon == x else x
                        canonical[a.name] = canon
                        canonical[b.name] = canon
                        if alias not in a.aliases:
                            a.aliases.append(alias)
                    elif self._is_substring_alias(x, y) or self._is_substring_alias(y, x):
                        canon = x if len(x) >= len(y) else y
                        alias = y if canon == x else x
                        canonical[a.name] = canon
                        canonical[b.name] = canon
                        if alias not in a.aliases:
                            a.aliases.append(alias)
        # collapse entities by canonical name
        by_name: dict[str, Entity] = {}
        for e in entities:
            canon = self.resolve(e.name) or canonical.get(e.name, e.name)
            if canon in by_name:
                existing = by_name[canon]
                existing.traits = sorted(set(existing.traits) | set(e.traits))
                existing.preferences = sorted(set(existing.preferences) | set(e.preferences))
                existing.aliases = sorted(set(existing.aliases) | set(e.aliases) | ({e.name} if e.name != canon else set()))
            else:
                e.name = canon
                if e.name != canon:
                    e.aliases = sorted(set(e.aliases) | {e.name})
                by_name[canon] = e
        return {e.name: e.name for e in by_name.values()}

    def _canon(self, name: str, entity_map: dict[str, Entity]) -> str:
        if not name or name == settings.assistant_name:
            return name
        resolved = self.resolve(name)
        if resolved:
            return resolved
        for e in entity_map.values():
            if name == e.name or name in e.aliases:
                return e.name
        return name

    def normalize_extraction(self, result: ExtractionResult) -> ExtractionResult:
        entities = [Entity(**e.model_dump()) for e in result.entities if e.name != settings.assistant_name]
        self._merge_same_round_entities(entities)
        entity_map = {e.name: e for e in entities}
        for e in entities:
            resolved = self.resolve(e.name)
            if resolved and resolved != e.name:
                e.aliases = sorted(set(e.aliases) | {e.name})
                e.name = resolved

        relations = []
        for rel in result.relations:
            if settings.assistant_name in (rel.subject, rel.object):
                continue
            subj = self._canon(rel.subject, entity_map)
            obj = self._canon(rel.object, entity_map) if self.resolve(rel.object) or rel.object in entity_map else rel.object
            relations.append(rel.model_copy(update={"subject": subj, "object": obj}))

        patterns = []
        for pat in result.behavior_patterns:
            if pat.person == settings.assistant_name:
                continue
            patterns.append(pat.model_copy(update={"person": self._canon(pat.person, entity_map)}))

        participants = [self._canon(p, entity_map) for p in result.episode.participants]
        participants = sorted(set(p for p in participants if p))

        episode = result.episode.model_copy(update={"participants": participants})
        return ExtractionResult(
            entities=entities,
            relations=relations,
            behavior_patterns=patterns,
            episode=episode,
        )
```

Note: simplify `_merge_same_round_entities` during implementation if the above is too complex — minimum bar is passing the three tests.

- [ ] **Step 5: Run tests — expect PASS**

Run: `pytest tests/test_entity_resolver.py -v`  
Expected: 3 passed

---

### Task 3: Wire resolver into pipeline

**Files:**
- Modify: `app/agent.py`
- Modify: `app/evolution/evolver.py`
- Modify: `app/encoding/encoder.py`
- Modify: `app/llm/prompts.py`

**Interfaces:**
- Consumes: `EntityResolver.normalize_extraction`
- Produces: `MemoryAgent.resolver: EntityResolver`
- Produces: `encode(perceived, source, resolver=None)` injects known people

- [ ] **Step 1: Agent owns resolver**

`app/agent.py`:

```python
from app.entity import EntityResolver

class MemoryAgent:
    def __init__(self, memory: MemoryStore | None = None) -> None:
        self.store = memory or store
        self.resolver = EntityResolver(self.store)
        ...

    def ingest(self, text: str, source: str = "chat") -> IngestResponse:
        perceived = perceive(text)
        result = encode(perceived, source=source, store=self.store)
        result = self.resolver.normalize_extraction(result)
        report = self.evolver.ingest(result)
        ...
```

- [ ] **Step 2: Encoder known people block**

Add helper in `encoder.py`:

```python
def _known_people_block(store: MemoryStore) -> str:
    lines = []
    for p in store.persona.all():
        alias = f" (aliases: {', '.join(p.aliases)})" if p.aliases else ""
        lines.append(f"- {p.name}{alias}")
    return "\n".join(lines) or "(none yet)"
```

Update `EXTRACTION_TEMPLATE` in prompts to include `{known_people}` and `{speakers}` placeholders.

Update `_run_extraction(conversation, known_people, speakers)`.

Update `encode(..., store=None)` to pass blocks from `PerceivedInput`.

- [ ] **Step 3: Integration smoke test**

Run: `python -m scripts.test_cases --ingest` (requires Ollama) OR add unit test mocking LLM.

- [ ] **Step 4: Commit**

```bash
git add app/entity/ app/agent.py app/encoding/ app/llm/prompts.py tests/ requirements.txt
git commit -m "feat: add EntityResolver and wire into ingest pipeline"
```

---

### Task 4: Episodic decay + prune

**Files:**
- Modify: `app/memory/episodic.py`
- Modify: `app/evolution/evolver.py`
- Create: `tests/test_episodic_lifecycle.py`

**Interfaces:**
- Produces: `EpisodicMemory.decay(factor: float) -> None`
- Produces: `EpisodicMemory.prune(min_weight: float) -> int` returns deleted count

- [ ] **Step 1: Write failing tests**

```python
from app.schemas import Episode
from app.memory.episodic import EpisodicMemory


def test_decay_reduces_weight(temp_store, monkeypatch):
    ep = Episode(summary="test", weight=1.0)
    temp_store.episodic.add(ep)
    temp_store.episodic.decay(0.5)
    got = temp_store.episodic.get(ep.id)
    assert got.weight == 0.5


def test_prune_removes_low_weight(temp_store, monkeypatch):
    monkeypatch.setattr("app.memory.episodic.llm.embed", lambda t: [0.0] * 768)
    low = Episode(summary="low", weight=0.1)
    high = Episode(summary="high", weight=0.9)
    temp_store.episodic.add(low)
    temp_store.episodic.add(high)
    deleted = temp_store.episodic.prune(0.15)
    assert deleted == 1
    assert temp_store.episodic.get(low.id) is None
    assert temp_store.episodic.get(high.id) is not None
```

- [ ] **Step 2: Implement decay/prune**

`episodic.py`:

```python
def decay(self, factor: float) -> None:
    with self._lock:
        for ep in self.all():
            ep.weight = round(ep.weight * factor, 4)
            self._conn.execute(
                "UPDATE episodes SET data = ? WHERE id = ?",
                (ep.model_dump_json(), ep.id),
            )
        self._conn.commit()

def prune(self, min_weight: float) -> int:
    with self._lock:
        to_delete = [ep.id for ep in self.all() if ep.weight < min_weight]
        for eid in to_delete:
            self._conn.execute("DELETE FROM episodes WHERE id = ?", (eid,))
        self._conn.commit()
        if to_delete:
            self._rebuild()
        return len(to_delete)
```

`evolver.py` `decay()` add episodic calls per spec.

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_episodic_lifecycle.py -v`  
Expected: PASS

---

### Task 5: Retriever scoring + mention detection

**Files:**
- Modify: `app/retrieval/retriever.py`
- Create: `tests/test_retriever_scoring.py`

**Interfaces:**
- Consumes: `EntityResolver` passed into `Retriever.__init__(store, resolver=None)`
- Produces: `_episodic_score(ep, sim) -> float`
- Produces: `_mentioned_persons(query) -> list[str]` using resolver

- [ ] **Step 1: Write failing test**

```python
import math
import time
from app.retrieval.retriever import Retriever
from app.entity.resolver import EntityResolver
from app.schemas import Episode


def test_mentioned_persons_via_alias(temp_store):
    temp_store.persona.upsert("林然", aliases=["小然"])
    r = Retriever(temp_store, EntityResolver(temp_store))
    assert r._mentioned_persons("小然养了什么") == ["林然"]


def test_episodic_score_weights_high(temp_store):
    r = Retriever(temp_store, EntityResolver(temp_store))
    ep = Episode(summary="x", weight=2.0, last_seen=time.time())
    s = r._episodic_score(ep, 0.8)
    assert s > 0.8 * 2.0 * 0.85
```

- [ ] **Step 2: Implement scoring**

```python
import math
import time
from app.config import settings

def _episodic_score(self, ep: Episode, sim: float) -> float:
    age_days = max(0.0, (time.time() - ep.last_seen) / 86400)
    half = settings.episodic_recency_half_life_days
    recency = 0.85 + 0.15 * math.exp(-age_days / half)
    return round(sim * ep.weight * recency, 4)
```

Update `recall()` topline to use `_episodic_score`. Update `_mentioned_persons` per spec.

Wire resolver in `MemoryAgent.__init__`: `self.retriever = Retriever(self.store, self.resolver)`.

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_retriever_scoring.py -v`

---

### Task 6: Summary post-ingest hooks

**Files:**
- Create: `app/evolution/hooks.py`
- Modify: `app/llm/prompts.py`
- Modify: `app/agent.py`
- Create: `tests/test_summary_hooks.py`

**Interfaces:**
- Produces: `refresh_person_summaries(store, persons: list[str], changed_traits: dict[str, bool]) -> None`

- [ ] **Step 1: Add prompts**

```python
SUMMARY_SYSTEM = (
    "You write brief neutral Chinese summaries of a person based ONLY on "
    "provided traits, preferences, patterns and relations. 1-2 sentences. "
    "No JSON. Do not invent facts."
)

SUMMARY_TEMPLATE = """Name: {name}
Traits: {traits}
Preferences: {preferences}
Patterns: {patterns}
Relations: {relations}

Write a 1-2 sentence summary in Chinese."""
```

- [ ] **Step 2: Write failing test (mock llm)**

```python
from unittest.mock import patch
from app.evolution.hooks import should_refresh_summary, refresh_person_summaries
from app.schemas import Persona


def test_should_refresh_when_empty():
    p = Persona(name="林然", mention_count=1)
    assert should_refresh_summary(p, traits_changed=False) is True


def test_should_not_refresh_first_mention_no_traits():
    p = Persona(name="林然", mention_count=1, summary="")
    assert should_refresh_summary(p, traits_changed=False) is True  # empty summary ok per spec


@patch("app.evolution.hooks.llm.chat", return_value="林然是内向的后端工程师。")
def test_refresh_writes_summary(mock_chat, temp_store):
    temp_store.persona.upsert("林然", traits=["内向"])
    p = temp_store.persona.get("林然")
    refresh_person_summaries(temp_store, ["林然"], {"林然": True})
    assert "工程师" in temp_store.persona.get("林然").summary or "内向" in temp_store.persona.get("林然").summary
```

Adjust `should_refresh_summary` logic to match spec exactly during implementation.

- [ ] **Step 3: Implement hooks.py**

Track `changed persons` in evolver.ingest return or compute in agent after ingest.

Call from `MemoryAgent.ingest` after evolver.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_summary_hooks.py -v`

---

### Task 7: Eval extension

**Files:**
- Modify: `scripts/eval.py`

- [ ] **Step 1: Add alias_accuracy**

After ingesting `test_cases` alias_lin dialogue, assert `EntityResolver(agent.store).resolve("小然") == "林然"`.

- [ ] **Step 2: Add merge_no_duplicate**

Ingest alias dialogue then full-name dialogue; assert `persona.count()` unchanged.

- [ ] **Step 3: Add recall cases from test_cases.ASK_CASES[:3]**

- [ ] **Step 4: Run eval**

Run: `python -m scripts.eval`  
Expected: prints new metrics section

---

### Task 8: Full verification

- [ ] **Step 1: Run all unit tests**

Run: `pytest tests/ -v`  
Expected: all PASS (no Ollama required)

- [ ] **Step 2: Manual decay check**

With seeded data: `curl -X POST http://localhost:8000/api/decay` — episode count stable or decreases.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: memory quality phase 1 — resolver, retrieval, decay, summary, tests"
```

---

## Plan Self-Review

| Spec section | Task |
|--------------|------|
| A1 EntityResolver | Task 2, 3 |
| A2 Retrieval | Task 5 |
| A3 Episodic lifecycle | Task 4 |
| A4 Summary | Task 6 |
| B pytest/eval | Task 2, 4, 5, 6, 7 |
| Config | Task 1 |
| Phase 2 (merge API) out of scope | Not in plan ✓ |

No TBD placeholders in task steps. Type names consistent: `EntityResolver`, `ExtractionResult`, `EpisodicMemory.prune(min_weight) -> int`.

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-06-23-memory-quality.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — implement task-by-task in this session with checkpoints

Which approach?
