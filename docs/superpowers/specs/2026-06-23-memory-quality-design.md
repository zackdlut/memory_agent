# 记忆质量提升（A1–A4 + B Phase 1）设计规格

**日期:** 2026-06-23  
**状态:** 已批准  
**范围:** Phase 1（质量 + 测试）；Phase 2（编辑 UI + 存量迁移）另立规格

---

## 1. 背景与目标

### 1.1 问题陈述

用户在使用类人记忆系统时遇到四类核心痛点：

| ID | 痛点 | 根因 |
|----|------|------|
| A1 | 同一人被拆成多个节点（如「林然」「小然」） | 写入路径未 canonicalize；alias 仅在读取时 resolve |
| A2 | 检索/问答漏掉或答非所问 | 人物识别用脆弱子串匹配；episodic 未计 weight/recency |
| A3 | 记忆只增不减，噪声累积 | `decay()` 不含 episodic；无 prune |
| A4 | 侧边栏 summary 长期空白 | `regenerate_summary()` 存在但从未调用 |

### 1.2 目标

Phase 1 交付后应满足：

1. 新 ingest **不再产生**重复 persona/graph 节点（A1）
2. 昵称 query 能命中 canonical 人物的 persona + graph（A2）
3. 手动 `/api/decay` 同时衰减并 prune 低权重 episode（A3）
4. mention_count ≥ 2 或 traits 变化后自动生成 persona summary（A4）
5. pytest 覆盖 resolver / scoring / lifecycle；eval 扩展 alias 与 merge 指标（B）

### 1.3 非目标（Phase 1）

- Skills 接入推理层
- LoRA 抽取模型
- 人格档案 inline 编辑 UI（Phase 2）
- 存量重复节点自动迁移（Phase 2 提供 merge API）
- 自动定时 decay（仅 config 预留，默认关闭）

---

## 2. 架构

### 2.1 流水线变更

```
对话输入 → perceive → encode → normalize_extraction → evolver.ingest → post_ingest_hooks
                                      ↑                                        ↓
                               EntityResolver                          refresh_summary(person)

提问 → retrieve(resolve_query) → rerank → reason
```

### 2.2 新增模块

| 模块 | 路径 | 职责 |
|------|------|------|
| EntityResolver | `app/entity/resolver.py` | 人名 canonical 解析；normalize ExtractionResult |
| post-ingest hooks | `app/evolution/hooks.py` | summary 刷新；decay 触发计数（可选） |

### 2.3 修改模块

| 模块 | 变更 |
|------|------|
| `app/evolution/evolver.py` | ingest 前 normalize；decay 串联 episodic |
| `app/retrieval/retriever.py` | 人物识别走 resolver；episodic 综合评分 |
| `app/memory/episodic.py` | `decay()` + `prune()` + lazy rebuild |
| `app/memory/persona.py` | 可选 `last_summary_at` 字段 |
| `app/encoding/encoder.py` | 注入 known people + speakers |
| `app/llm/prompts.py` | EXTRACTION 模板占位符；SUMMARY 模板 |
| `app/config.py` | 新 tuning 参数 |
| `app/agent.py` | 注入 resolver 到 pipeline |
| `scripts/eval.py` | 扩展指标 |

---

## 3. A1 — EntityResolver

### 3.1 API

```python
class EntityResolver:
    def __init__(self, store: MemoryStore): ...

    def resolve(self, name: str) -> str | None:
        """Return canonical persona name, or None if unknown."""

    def normalize_extraction(self, result: ExtractionResult) -> ExtractionResult:
        """Rewrite all person references to canonical names."""

    def merge_person(self, source: str, target: str) -> None:
        """Phase 2: merge duplicate nodes (not Phase 1 deliverable)."""
```

### 3.2 解析优先级

1. 精确匹配 `persona.name`
2. 匹配 `persona.aliases` 或 graph node `aliases`（via `semantic.resolve()`）
3. 同轮抽取内合并（见 3.3）
4. 未命中 → 以 LLM 给的 name 新建

### 3.3 同轮抽取合并规则

对同一 `ExtractionResult.entities` 中任意 A、B：

- 若 `A.name in B.aliases` 或 `B.name in A.aliases` → 合并
- 若较短名 ≥ 2 字且为较长名的**真子串**（如「小然」⊂「林然」）→ canonical 取较长名，较短名写入 aliases
- **不做**模糊匹配；「王磊」「王雷」不自动合并

合并后：traits/preferences 并集；被合并名加入 aliases。

### 3.4 normalize 范围

重写以下字段中的 person 名：

- `entities[].name`
- `relations[].subject`；`relations[].object` 仅当 object 已是 known person
- `behavior_patterns[].person`
- `episode.participants`

跳过 `settings.assistant_name`。

### 3.5 Prompt 增强

`EXTRACTION_TEMPLATE` 增加段：

```
Known people (use canonical name, put nicknames in aliases):
{known_people}
Speakers in this turn: {speakers}
```

`known_people` 来自 `persona.all()` 格式化；`speakers` 来自 `PerceivedInput.speakers`。

---

## 4. A2 — 检索改进

### 4.1 人物识别

`_mentioned_persons(query)` 新逻辑：

1. 对每个 canonical person：name 或 alias 在 query 中（case-insensitive）→ 加入
2. 对 query 切分出的 2–4 字中文 token 调 `resolver.resolve(token)`
3. 去重返回 canonical 列表

### 4.2 Episodic 综合评分

```
score = sim × episode.weight × recency_boost
recency_boost = 0.85 + 0.15 × exp(-age_days / episodic_recency_half_life_days)
age_days = (now - episode.last_seen) / 86400
```

默认 `episodic_recency_half_life_days = 30.0`。

Persona 条目 score 不变（1.0）。Semantic 边 score 仍为 `min(1.0, weight)`。

### 4.3 Rerank fallback

LLM rerank 失败或返回空时，按新 score 降序取 top `rerank_keep`。

---

## 5. A3 — Episodic 遗忘

### 5.1 decay

`EpisodicMemory.decay(factor)`：

- 所有 episode：`weight *= factor`（默认 factor = 0.98，与 persona 一致）
- 仅更新 SQLite JSON；不修改 FAISS 向量

### 5.2 prune

`EpisodicMemory.prune(min_weight)`：

- 删除 `weight < min_weight` 的 episode（默认 `min_weight = 0.15`）
- 从 SQLite 删除；若 `index.ntotal != db_count` 则在下次 `add()`/`search()` 时 `_rebuild()`

### 5.3 evolver.decay 串联

```python
def decay(self):
    factor = settings.decay_factor
    self.store.semantic.decay(factor)
    self.store.persona.decay(factor)
    self.store.self_profile.decay(factor)
    self.store.episodic.decay(factor)
    self.store.episodic.prune(settings.episodic_prune_min_weight)
    self.store.commit()
```

### 5.4 自动 decay（预留，默认 off）

```python
auto_decay_on_ingest: bool = False
auto_decay_episode_threshold: int = 500
```

Phase 1 仅定义 config，不实现自动触发，除非实现成本 < 30 行。

---

## 6. A4 — Summary 自动生成

### 6.1 触发条件（post_ingest_hooks）

对每个本次 ingest 更新的 person：

```python
should_refresh = (
    persona.summary == ""
    or persona.mention_count >= 2
    or traits_or_prefs_changed_this_round
)
and (now - last_summary_at) >= 60  # 防抖
```

mention_count == 1 且 summary 为空：**不生成**（信息不足）。

### 6.2 实现

- 新 prompt：`SUMMARY_SYSTEM` + `SUMMARY_TEMPLATE` in `app/llm/prompts.py`
- 输入：name, top traits/prefs/patterns, relations
- 输出：1–2 句中文纯文本
- 调用 `persona.regenerate_summary(name, text)`；更新 `last_summary_at`

### 6.3 失败处理

LLM 异常或空返回 → 保留旧 summary；不阻塞 ingest 响应。

---

## 7. B — 测试与评估（Phase 1）

### 7.1 pytest 布局

```
tests/
  conftest.py                 # MemoryStore fixture (temp DATA_DIR)
  test_entity_resolver.py
  test_retriever_scoring.py
  test_episodic_lifecycle.py
  test_summary_hooks.py
```

测试不依赖真实 Ollama（mock `llm.chat` / `llm.embed`）。

### 7.2 eval 扩展

| 指标 | 说明 |
|------|------|
| alias_accuracy | ingest alias_lin 后 resolve「小然」→「林然」 |
| merge_no_duplicate | 连续 ingest 原名+昵称对话，persona count 不增 |
| recall (+3) | `test_cases.ASK_CASES` 前三条 |

### 7.3 依赖

`requirements.txt` 增加 `pytest>=8.0`（dev 可选注释）。

---

## 8. 配置项

| 键 | 默认 | 说明 |
|----|------|------|
| `decay_factor` | 0.98 | 全局衰减系数 |
| `episodic_prune_min_weight` | 0.15 | prune 阈值 |
| `episodic_recency_half_life_days` | 30.0 | 检索 recency 半衰 |
| `summary_refresh_cooldown_sec` | 60 | summary 防抖秒数 |

---

## 9. Phase 2 预览（本规格不实现）

- `POST /api/person/merge` — 合并存量重复节点
- 人格档案页 inline 编辑 trait / pref / summary
- `scripts/migrate_duplicate_persons.py` — 扫描并建议 merge 对

---

## 10. 成功标准

1. `pytest tests/` 全部通过（无 Ollama）
2. `python -m scripts.eval` alias_accuracy ≥ 1.0；merge_no_duplicate 通过
3. 手动测试：ingest「小然」对话后再 ingest「林然」对话 → 图谱仅一个 person 节点
4. `POST /api/decay` 后 episode count 下降（存在 weight < 0.15 的 episode 时）
5. 聊天 3 轮后侧边栏出现非空 summary

---

## 11. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 子串误合并 | 仅真子串 + ≥2 字；不做 edit distance |
| prune 误删重要记忆 | merge 强化 weight；prune 阈值保守 0.15 |
| summary LLM 幻觉 | prompt 要求仅基于已有 traits；mention_count < 2 不生成 |
| FAISS rebuild 性能 | lazy rebuild；prune 批量后一次性 rebuild |
