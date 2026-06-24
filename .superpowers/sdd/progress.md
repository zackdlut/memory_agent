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

## 三叶虫：会成长的拟人化助手 (2026-06-24)

Plan: docs/superpowers/plans/2026-06-24-trilobite-evolving-persona.md
Branch: main

| Task | Status | Notes |
|------|--------|-------|
| Task 1: 数据模型与配置 | complete | commits cc4224d..3d534ef, review clean |
| Task 2: SelfProfileStore 升级 | complete | commits 3d534ef..3e00bfb, review clean (minors fixed) |
| Task 3: 风格编译器 | complete | commit ec22c29, review clean |
| Task 4: 反思升级 + 提示词 | complete | commit adc8a05, review clean (⚠️ style_block/talking_points 由 Task 6 接线) |
| Task 5: 自我表达/叙事 | complete | commits adc8a05..14f0dde, review clean (matcher 收紧后通过) |
| Task 6: Manager 整合(异步) | complete | commit ff6d237, review clean (并发安全已核, minors: 测试多余 patch / episodic 读锁外区域-既有) |
| Task 7: 档案页可视化 | complete | commit 672654b, review clean |
| Final whole-branch review | complete | opus 评审; Important(语义读锁)已修 641ea67; minors 记录如下 |

### 最终评审遗留 Minor（不阻塞合并，供后续清理）
- 前端 SEED 种子常量与后端 PersonaDimensions 默认值重复硬编码（web/app.js）——改 schema 默认值时档案页 ↑/↓ 基线会静默错位。
- 温度联动用 talkativeness（plan Task 6 如此），spec 文字写的是 energy；energy 实际未进温度公式（无害，措辞不一致）。
- ThreadPoolExecutor 无优雅 shutdown；进程退出时 in-flight 的 reflect/ingest 可能丢失。
- SelfProfileView 顶层 dimensions/opinions 与嵌套 profile 字段冗余（mood 顶层是回归后值，部分合理）。
- episodic.search() 取行在 FAISS 锁释放后（既有代码，_row_ids append-only，安全）。
