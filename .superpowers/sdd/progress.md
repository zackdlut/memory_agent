# SDD Progress — memory-quality Phase 1

| Task | Status | Notes |
|------|--------|-------|
| Task 1: Config + Persona schema | complete | config, schemas, persona |
| Task 2: EntityResolver + tests | complete | suffix nickname match for 小然/林然 |
| Task 3: Wire resolver into pipeline | complete | agent, encoder, prompts |
| Task 4: Episodic decay + prune | complete | episodic, evolver |
| Task 5: Retriever scoring | complete | retriever |
| Task 6: Summary hooks | complete | hooks, agent |
| Task 7: Eval extension | complete | alias + merge metrics |
| Task 8: Full verification | complete | pytest 10/10 |

## Phase 2

| Task | Status | Notes |
|------|--------|-------|
| P1: Persona merge/edit primitives | complete | get_exact, delete, update, merge |
| P2: Semantic merge/remove primitives | complete | merge_person, remove_trait/pref, _copy_edge |
| P3: Resolver orchestration + schemas | complete | merge_person; Merge/Edit request models |
| P4: API merge + edit endpoints | complete | POST /api/person/merge, PATCH /api/person/{name} |
| P5: Migration script | complete | scripts/migrate_duplicate_persons.py (dry-run/--apply) |
| P6: Frontend inline edit + merge UI | complete | persona detail editing in web/app.js + style.css |
| P7: Tests + verification | complete | pytest 20/20; migration dry-run verified |
