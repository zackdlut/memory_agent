# 记忆质量提升（Phase 2）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox tracking.

**Goal:** Let users correct memory — merge duplicate person nodes, edit/delete persona fields, and migrate existing duplicates.

**Architecture:** Add merge + edit primitives to `PersonaMemory` and `SemanticMemory`, orchestrate via `EntityResolver.merge_person`, expose `POST /api/person/merge` and `PATCH /api/person/{name}`, add a migration script, and an inline-edit persona UI.

**Tech Stack:** Python 3.10+, FastAPI, NetworkX, SQLite, pytest, vanilla JS frontend.

## Global Constraints

- Merge is additive: traits/preferences weights sum; aliases union (+ source name); patterns deduped; `mention_count` summed; source node deleted.
- Editing a trait/preference must remove it from BOTH persona (SQLite) and semantic graph.
- Never merge a node into itself; never model `settings.assistant_name`.
- Migration script is dry-run by default; `--apply` performs merges.
- Follow existing patterns (Pydantic schemas, MemoryStore facade, minimal diffs).

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `app/memory/persona.py` | Modify | `get_exact`, `delete`, `merge`, `update` |
| `app/memory/semantic.py` | Modify | `merge_person`, `remove_trait`, `remove_preference`, `_copy_edge` |
| `app/entity/resolver.py` | Modify | `merge_person` orchestration |
| `app/schemas.py` | Modify | `MergeRequest`, `PersonEditRequest` |
| `app/api.py` | Modify | merge + edit endpoints |
| `scripts/migrate_duplicate_persons.py` | Create | scan + optionally apply merges |
| `web/app.js` | Modify | inline edit + merge UI |
| `web/style.css` | Modify | edit affordance styles |
| `tests/test_person_merge.py` | Create | merge persona + graph |
| `tests/test_person_edit.py` | Create | edit/delete fields |

---

### Task 1: Persona merge/edit primitives
- `get_exact(name)` (PK only), `delete(name)`, `merge(source, target)`, `update(...)`.

### Task 2: Semantic merge/remove primitives
- `_copy_edge`, `merge_person(source, target)`, `remove_trait`, `remove_preference`.

### Task 3: Resolver orchestration + schemas
- `EntityResolver.merge_person`; `MergeRequest`, `PersonEditRequest`.

### Task 4: API endpoints
- `POST /api/person/merge`, `PATCH /api/person/{name}`.

### Task 5: Migration script
- `scripts/migrate_duplicate_persons.py` (dry-run / --apply).

### Task 6: Frontend inline edit + merge.

### Task 7: Tests + verification.
