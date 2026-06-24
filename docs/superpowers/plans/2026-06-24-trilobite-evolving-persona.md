# 三叶虫：会成长的拟人化助手 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把三叶虫的自我系统从「记录」升级为分层人格引擎——固定内核 + 可漂移量化维度、跨会话衰减心情、风格编译器、主动表达/自我叙事，且反思演化后台异步、零额外回复延迟。

**Architecture:** 在现有 `SelfProfile`（`data/self.json`）上扩展量化维度/心情/观点；反思输出方向信号由代码平滑漂移维度（可盖过种子、衰减时向种子回归）；纯函数风格编译器把维度+心情+关系翻译成命令式说话指令注入回复 prompt；反思/演化/摄入移到回复发出后的后台。

**Tech Stack:** Python 3.10+ · FastAPI · Pydantic v2 · SQLite/FAISS/NetworkX（既有）· Ollama（既有）· pytest（LLM 走 mock）· 原生 JS 前端（`web/app.js`）

## Global Constraints

- 三叶虫**永不**被建模为人物：不进 `personas` 表、不出现在 `/api/persons`；自我状态只存 `data/self.json`（`settings.data_dir / "self.json"`）。
- 不新增第三方依赖；不引入新的向量库。
- 旧 `data/self.json` 必须能无错加载（字段缺失填默认；`traits` → `free_traits` 迁移）。
- 反思/抽取走严格 JSON：复用 `llm.chat_json`（已带解析重试/兜底）；非法/缺字段按安全默认处理，单次失败不崩聊天。
- 不向用户暴露内部状态（维度/心情/系统提示）：仅作内部 prompt 与档案页展示。
- 所有 LLM 调用在测试中必须被 mock（`unittest.mock.patch`），测试不触网。
- 测试用 `tests/conftest.py` 的 `temp_store` fixture（`MemoryStore` 指向 `tmp_path`）。
- 维度数轴统一 `0..1`；心情 `valence ∈ [-1,1]`、`energy ∈ [0,1]`。
- 默认参数（写进 `app/config.py`）：`mood_half_life_hours=6.0`、`dimension_step=0.04`、`reflect_async=True`。

---

## File Structure

- `app/schemas.py` — 新增 `PersonaCore` / `PersonaDimensions` / `MoodState` / `SelfOpinion`；改造 `SelfProfile`、`SelfProfileView`。
- `app/config.py` — 新增 `mood_half_life_hours` / `dimension_step` / `reflect_async`。
- `app/memory/self_profile.py` — 种子退役为初值；维度漂移、心情推动+惰性回归、观点增减、向种子回归的 decay、旧档案迁移。
- `app/chat/style.py` — 新增·纯函数风格编译器。
- `app/llm/prompts.py` — 改造 `SELF_REFLECT_TEMPLATE` / `SELF_REFLECT_SYSTEM` / `CHAT_REPLY_TEMPLATE` / `TRILOBITE_SYSTEM`。
- `app/chat/self_memory.py` — `reflect()` 升级；新增 `style_block` / `self_talking_points` / `self_narrative`；`profile_view` 扩展；`self_context` 改读 `free_traits`。
- `app/chat/manager.py` — 回复 prompt 拼入风格块/谈资块；温度联动；反思+摄入后台异步（`reflect_async` 控制）。
- `app/api.py` — `/api/self` 返回扩展后的 `SelfProfileView`（无代码改动，依赖 schema）。
- `web/app.js` — 档案页 `loadSelf()` 渲染维度条形/心情/观点/自述；`traits` 键名改 `free_traits`。
- `tests/` — `test_self_dimensions.py` / `test_self_mood.py` / `test_self_decay.py` / `test_style_compiler.py` / `test_self_reflect.py` / `test_self_talking.py` / `test_self_async.py`。

---

## Task 1: 数据模型与配置基础

**Files:**
- Modify: `app/schemas.py`（在「assistant self model」区块，约 `SelfExperience`/`SelfProfile` 处 171-197）
- Modify: `app/config.py:110-120`（retrieval/evolution tuning 区块内追加）
- Test: `tests/test_self_dimensions.py`（本任务先建文件，仅放 schema 默认值测试）

**Interfaces:**
- Produces:
  - `PersonaCore(summary: str, invariants: list[str])`
  - `PersonaDimensions(warmth, empathy, patience, curiosity, playfulness, assertiveness, talkativeness: float)`
  - `MoodState(valence: float, energy: float, updated_at: float)`
  - `SelfOpinion(id: str, topic: str, stance: str, weight: float, created_at: float)`
  - `SelfProfile` 新增字段：`core: PersonaCore`、`dimensions: PersonaDimensions`、`mood: MoodState`、`free_traits: dict[str,float]`、`opinions: list[SelfOpinion]`（保留 `preferences/experiences/interaction_count/name/role/summary`）
  - `SelfProfileView` 新增字段：`dimensions: PersonaDimensions`、`mood: MoodState`、`opinions: list[SelfOpinion]`、`narrative: str`
  - `settings.mood_half_life_hours: float`、`settings.dimension_step: float`、`settings.reflect_async: bool`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_self_dimensions.py
from app.schemas import PersonaCore, PersonaDimensions, MoodState, SelfOpinion, SelfProfile


def test_dimensions_defaults():
    d = PersonaDimensions()
    assert d.warmth == 0.7 and d.empathy == 0.7 and d.patience == 0.7
    assert d.curiosity == 0.7 and d.playfulness == 0.3
    assert d.assertiveness == 0.3 and d.talkativeness == 0.4


def test_self_profile_has_layers():
    p = SelfProfile(name="三叶虫")
    assert isinstance(p.core, PersonaCore)
    assert isinstance(p.dimensions, PersonaDimensions)
    assert isinstance(p.mood, MoodState)
    assert p.free_traits == {} and p.opinions == []
    assert "不伤害人" in p.core.invariants
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_self_dimensions.py -v`
Expected: FAIL with `ImportError`/`AttributeError`（新模型尚不存在）

- [ ] **Step 3: Write minimal implementation**

在 `app/schemas.py` 把现有 `SelfExperience`/`SelfProfile` 区块替换为：

```python
# ------------------------------------------------------- assistant self model
class SelfExperience(BaseModel):
    id: str = Field(default_factory=_uid)
    summary: str
    person: str = ""
    emotion: str = "neutral"
    created_at: float = Field(default_factory=_now)


class PersonaCore(BaseModel):
    """三叶虫永不漂移的人格内核（只读，作兜底安全线）。"""
    summary: str = "我是三叶虫，真诚、在乎我遇到的每个人，绝不伤害人。"
    invariants: list[str] = Field(
        default_factory=lambda: ["真诚", "不伤害人", "在乎对方"]
    )


class PersonaDimensions(BaseModel):
    """0..1 量化人格维度；字段默认值即「种子初值」。"""
    warmth: float = 0.7
    empathy: float = 0.7
    patience: float = 0.7
    curiosity: float = 0.7
    playfulness: float = 0.3
    assertiveness: float = 0.3
    talkativeness: float = 0.4


class MoodState(BaseModel):
    valence: float = 0.0   # -1(低落)..+1(愉快)
    energy: float = 0.5    # 0(平静/疲)..1(兴奋)
    updated_at: float = 0.0


class SelfOpinion(BaseModel):
    id: str = Field(default_factory=_uid)
    topic: str
    stance: str
    weight: float = 1.0
    created_at: float = Field(default_factory=_now)


class SelfProfile(BaseModel):
    name: str
    role: str = ""
    summary: str = ""
    core: PersonaCore = Field(default_factory=PersonaCore)
    dimensions: PersonaDimensions = Field(default_factory=PersonaDimensions)
    mood: MoodState = Field(default_factory=MoodState)
    free_traits: dict[str, float] = Field(default_factory=dict)
    preferences: dict[str, float] = Field(default_factory=dict)
    opinions: list[SelfOpinion] = Field(default_factory=list)
    experiences: list[SelfExperience] = Field(default_factory=list)
    interaction_count: int = 0


class KnownPerson(BaseModel):
    name: str
    familiarity: int = 0
    relationship: str = ""


class SelfProfileView(BaseModel):
    profile: SelfProfile
    dimensions: PersonaDimensions = Field(default_factory=PersonaDimensions)
    mood: MoodState = Field(default_factory=MoodState)
    opinions: list[SelfOpinion] = Field(default_factory=list)
    narrative: str = ""
    known_people: list[KnownPerson] = Field(default_factory=list)
```

在 `app/config.py` 的 `decay_factor` 等附近（约 117 行后）追加三行：

```python
    # --- assistant self / persona evolution -----------------------------
    mood_half_life_hours: float = 6.0
    dimension_step: float = 0.04
    reflect_async: bool = True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_self_dimensions.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/schemas.py app/config.py tests/test_self_dimensions.py
git commit -m "feat(self): 分层人格数据模型与配置 (core/dimensions/mood/opinions)"
```

---

## Task 2: SelfProfileStore 升级（漂移 / 心情 / 观点 / 衰减 / 迁移）

**Files:**
- Modify: `app/memory/self_profile.py`（整体改造）
- Test: `tests/test_self_dimensions.py`（追加漂移用例）、`tests/test_self_mood.py`（新建）、`tests/test_self_decay.py`（新建）

**Interfaces:**
- Consumes: Task 1 的 schema；`settings.dimension_step` / `settings.mood_half_life_hours`。
- Produces（`SelfProfileStore` 方法）：
  - `get() -> SelfProfile`
  - `top_traits(limit: int = 5) -> list[str]`（读 `free_traits`）
  - `recent_experiences(limit: int = 2) -> list[SelfExperience]`
  - `reinforce_trait(trait: str, gain: float = 0.3) -> None`（写 `free_traits`）
  - `reinforce_preference(pref: str, gain: float = 0.3) -> None`
  - `add_experience(exp: SelfExperience, cap: int = 30) -> None`
  - `apply_dimension_signal(name: str, sign: str) -> None`（`sign ∈ {"++","+","0","-","--"}`，未知名/未知 sign 忽略）
  - `nudge_mood(valence_sign: str, energy_sign: str) -> None`（`sign ∈ {"+","0","-"}`）
  - `current_mood() -> MoodState`（按时间惰性回归，不持久化）
  - `add_opinion(topic: str, stance: str, gain: float = 1.0) -> None`（同 topic 则强化 weight 并更新 stance）
  - `bump_interaction() -> None`
  - `decay(factor: float) -> None`（维度向种子回归；`free_traits/preferences` 乘 factor；`opinions` 乘 factor 并剪枝 `weight < 0.15`）

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_self_dimensions.py （追加）
def test_apply_dimension_signal_drifts_and_can_pass_seed(temp_store):
    sp = temp_store.self_profile
    start = sp.get().dimensions.playfulness  # 0.3 种子
    for _ in range(15):
        sp.apply_dimension_signal("playfulness", "+")  # +0.04 each
    val = sp.get().dimensions.playfulness
    assert val > start and val > 0.6 and val <= 1.0  # 盖过种子、且被 clamp


def test_apply_dimension_signal_clamps_and_ignores_unknown(temp_store):
    sp = temp_store.self_profile
    for _ in range(50):
        sp.apply_dimension_signal("warmth", "++")
    assert sp.get().dimensions.warmth == 1.0
    sp.apply_dimension_signal("nope", "+")     # 未知维度：无副作用
    sp.apply_dimension_signal("warmth", "???")  # 未知 sign：无副作用
    assert sp.get().dimensions.warmth == 1.0
```

```python
# tests/test_self_mood.py （新建）
import time


def test_nudge_mood_pushes(temp_store):
    sp = temp_store.self_profile
    sp.nudge_mood("+", "+")
    m = sp.get().mood
    assert m.valence > 0 and m.energy > 0.5 and m.updated_at > 0


def test_current_mood_regresses_to_neutral(temp_store):
    sp = temp_store.self_profile
    sp.nudge_mood("+", "+")
    # 把更新时间挪到一个半衰期前，应回归到约一半
    half = temp_store.self_profile  # alias
    p = sp.get()
    pushed_v = p.mood.valence
    p.mood.updated_at = time.time() - 6 * 3600  # = mood_half_life_hours
    cur = sp.current_mood()
    assert abs(cur.valence - pushed_v / 2) < 0.02
    assert abs(cur.energy - (0.5 + (p.mood.energy - 0.5) / 2)) < 0.02
```

```python
# tests/test_self_decay.py （新建）
def test_decay_pulls_dimensions_toward_seed(temp_store):
    sp = temp_store.self_profile
    for _ in range(15):
        sp.apply_dimension_signal("playfulness", "+")  # 漂到 >0.6
    high = sp.get().dimensions.playfulness
    for _ in range(30):
        sp.decay(0.98)
    after = sp.get().dimensions.playfulness
    assert 0.3 <= after < high  # 向种子 0.3 回归，但未归零


def test_decay_prunes_weak_opinions(temp_store):
    sp = temp_store.self_profile
    sp.add_opinion("深聊", "我喜欢深聊")
    for _ in range(200):
        sp.decay(0.9)
    assert all(o.weight >= 0.15 for o in sp.get().opinions)
    assert len(sp.get().opinions) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_self_dimensions.py tests/test_self_mood.py tests/test_self_decay.py -v`
Expected: FAIL（`apply_dimension_signal`/`nudge_mood`/`current_mood`/`add_opinion` 不存在）

- [ ] **Step 3: Write minimal implementation**

把 `app/memory/self_profile.py` 改写为：

```python
"""三叶虫 self-profile store: 分层、可演化的自我身份。

种子（PersonaDimensions 的字段默认值）只是初值；反思推动维度漂移、甚至盖过种子。
内核 PersonaCore 只读，永不被演化触碰。持久化为 data/self.json。
"""

from __future__ import annotations

import json
import threading
import time

from app.config import settings
from app.schemas import (
    MoodState,
    PersonaDimensions,
    SelfExperience,
    SelfOpinion,
    SelfProfile,
)

SEED_ROLE = "一个会长期记住每个人的 AI 记忆助手"
SEED_SUMMARY = "我是三叶虫，一个会记住、理解并陪伴我遇到的每一个人的 AI 助手。"
MAX_EXPERIENCES = 30
OPINION_PRUNE_MIN = 0.15

# 方向信号 -> 步数（乘 settings.dimension_step）
_DIM_SIGNAL = {"++": 2, "+": 1, "0": 0, "-": -1, "--": -2}
# 心情推动量
_MOOD_PUSH = {"+": 0.15, "0": 0.0, "-": -0.15}
_DIM_NAMES = set(PersonaDimensions().model_dump().keys())


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


class SelfProfileStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.name = settings.assistant_name
        self.profile = self._load()

    # --------------------------------------------------------------- persistence
    @property
    def _path(self):
        return settings.data_dir / "self.json"

    def _load(self) -> SelfProfile:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                # migrate: 旧档案的 traits -> free_traits
                if "free_traits" not in data and "traits" in data:
                    data["free_traits"] = data.pop("traits")
                return SelfProfile(**data)
            except Exception:
                pass
        return self._seed()

    def _seed(self) -> SelfProfile:
        return SelfProfile(
            name=self.name,
            role=SEED_ROLE,
            summary=SEED_SUMMARY,
        )

    def _persist(self) -> None:
        try:
            self._path.write_text(
                self.profile.model_dump_json(indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    # ----------------------------------------------------------------- reads
    def get(self) -> SelfProfile:
        return self.profile

    def top_traits(self, limit: int = 5) -> list[str]:
        return [
            k for k, _ in sorted(
                self.profile.free_traits.items(), key=lambda x: x[1], reverse=True
            )
        ][:limit]

    def recent_experiences(self, limit: int = 2) -> list[SelfExperience]:
        return self.profile.experiences[-limit:][::-1]

    def current_mood(self) -> MoodState:
        m = self.profile.mood
        now = time.time()
        if not m.updated_at:
            return MoodState(valence=m.valence, energy=m.energy, updated_at=now)
        hours = (now - m.updated_at) / 3600.0
        k = 0.5 ** (hours / settings.mood_half_life_hours)
        return MoodState(
            valence=round(m.valence * k, 4),
            energy=round(0.5 + (m.energy - 0.5) * k, 4),
            updated_at=now,
        )

    # ---------------------------------------------------------------- writes
    def reinforce_trait(self, trait: str, gain: float = 0.3) -> None:
        trait = (trait or "").strip()
        if not trait:
            return
        with self._lock:
            self.profile.free_traits[trait] = round(
                self.profile.free_traits.get(trait, 0.0) + gain, 4
            )
            self._persist()

    def reinforce_preference(self, pref: str, gain: float = 0.3) -> None:
        pref = (pref or "").strip()
        if not pref:
            return
        with self._lock:
            self.profile.preferences[pref] = round(
                self.profile.preferences.get(pref, 0.0) + gain, 4
            )
            self._persist()

    def apply_dimension_signal(self, name: str, sign: str) -> None:
        name = (name or "").strip()
        if name not in _DIM_NAMES or sign not in _DIM_SIGNAL:
            return
        with self._lock:
            cur = getattr(self.profile.dimensions, name)
            delta = _DIM_SIGNAL[sign] * settings.dimension_step
            setattr(
                self.profile.dimensions, name, round(_clamp(cur + delta, 0.0, 1.0), 4)
            )
            self._persist()

    def nudge_mood(self, valence_sign: str, energy_sign: str) -> None:
        with self._lock:
            cur = self.current_mood()
            v = _clamp(cur.valence + _MOOD_PUSH.get(valence_sign, 0.0), -1.0, 1.0)
            e = _clamp(cur.energy + _MOOD_PUSH.get(energy_sign, 0.0), 0.0, 1.0)
            self.profile.mood = MoodState(
                valence=round(v, 4), energy=round(e, 4), updated_at=time.time()
            )
            self._persist()

    def add_opinion(self, topic: str, stance: str, gain: float = 1.0) -> None:
        topic = (topic or "").strip()
        stance = (stance or "").strip()
        if not topic or not stance:
            return
        with self._lock:
            for op in self.profile.opinions:
                if op.topic == topic:
                    op.weight = round(op.weight + gain, 4)
                    op.stance = stance
                    self._persist()
                    return
            self.profile.opinions.append(
                SelfOpinion(topic=topic, stance=stance, weight=gain)
            )
            self._persist()

    def add_experience(self, experience: SelfExperience, cap: int = MAX_EXPERIENCES) -> None:
        if not experience.summary.strip():
            return
        with self._lock:
            self.profile.experiences.append(experience)
            if len(self.profile.experiences) > cap:
                self.profile.experiences = self.profile.experiences[-cap:]
            self._persist()

    def bump_interaction(self) -> None:
        with self._lock:
            self.profile.interaction_count += 1
            self._persist()

    def decay(self, factor: float) -> None:
        seed = PersonaDimensions()
        with self._lock:
            dims = self.profile.dimensions
            for name in _DIM_NAMES:
                cur = getattr(dims, name)
                seed_v = getattr(seed, name)
                setattr(dims, name, round(cur + (seed_v - cur) * (1 - factor), 4))
            self.profile.free_traits = {
                k: round(v * factor, 4) for k, v in self.profile.free_traits.items()
            }
            self.profile.preferences = {
                k: round(v * factor, 4) for k, v in self.profile.preferences.items()
            }
            kept = []
            for op in self.profile.opinions:
                op.weight = round(op.weight * factor, 4)
                if op.weight >= OPINION_PRUNE_MIN:
                    kept.append(op)
            self.profile.opinions = kept
            self._persist()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_self_dimensions.py tests/test_self_mood.py tests/test_self_decay.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite to catch ripples**

Run: `pytest -q`
Expected: PASS（`evolver.decay()` 已调 `self_profile.decay(factor)`，签名不变；`self_context`/`profile_view` 在 Task 5 调整，本步若 `test` 涉及它们应仍 PASS，因 `top_traits` 仍可用）

- [ ] **Step 6: Commit**

```bash
git add app/memory/self_profile.py tests/test_self_dimensions.py tests/test_self_mood.py tests/test_self_decay.py
git commit -m "feat(self): 维度漂移/心情推动回归/观点/向种子回归衰减 + 旧档案迁移"
```

---

## Task 3: 风格编译器（纯函数）

**Files:**
- Create: `app/chat/style.py`
- Test: `tests/test_style_compiler.py`（新建）

**Interfaces:**
- Consumes: `PersonaDimensions`、`MoodState`（Task 1）。
- Produces: `compile_style(dims: PersonaDimensions, mood: MoodState, relationship_label: str, familiarity: int) -> str`（返回以 `【此刻的你应该怎么说话】` 开头的多行指令；纯函数无副作用、无 LLM）。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_style_compiler.py
from app.chat.style import compile_style
from app.schemas import MoodState, PersonaDimensions


def test_playful_high_energy_old_friend():
    dims = PersonaDimensions(playfulness=0.8, talkativeness=0.8, curiosity=0.8)
    mood = MoodState(valence=0.5, energy=0.8)
    s = compile_style(dims, mood, "老朋友", familiarity=6)
    assert s.startswith("【此刻的你应该怎么说话】")
    assert "俏皮" in s and "多说几句" in s
    assert "更明亮" in s and "活力" in s
    assert "老朋友" in s


def test_low_mood_terse_stranger():
    dims = PersonaDimensions(playfulness=0.2, talkativeness=0.2)
    mood = MoodState(valence=-0.5, energy=0.2)
    s = compile_style(dims, mood, "初次见面", familiarity=0)
    assert "正经" in s and "简洁" in s
    assert "低落" in s and "平静" in s
    assert "客气" in s
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_style_compiler.py -v`
Expected: FAIL with `ModuleNotFoundError: app.chat.style`

- [ ] **Step 3: Write minimal implementation**

```python
# app/chat/style.py
"""风格编译器：把人格维度 + 当下心情 + 与此人的关系，翻译成命令式的说话指令。

纯函数、无 LLM 调用、零延迟。给本地小模型离散明确的指令，比塞小数稳得多。
这是「性格真正影响怎么说话」的落地环节。
"""

from __future__ import annotations

from app.schemas import MoodState, PersonaDimensions


def compile_style(
    dims: PersonaDimensions,
    mood: MoodState,
    relationship_label: str,
    familiarity: int,
) -> str:
    lines: list[str] = []

    # 人格维度 -> 语气
    if dims.playfulness > 0.6:
        lines.append("可以俏皮、偶尔开个玩笑，用轻松的口吻")
    elif dims.playfulness < 0.3:
        lines.append("语气平实正经，少开玩笑")
    if dims.empathy > 0.6:
        lines.append("先接住对方的情绪，再回应内容")
    if dims.patience > 0.6:
        lines.append("有耐心，不急着下结论，愿意慢慢陪")
    if dims.talkativeness > 0.6:
        lines.append("可以多说几句、主动展开")
    else:
        lines.append("简洁，别长篇大论")
    if dims.assertiveness > 0.6:
        lines.append("有自己的观点时大方表达，不一味附和")
    if dims.curiosity > 0.6:
        lines.append("对对方说的自然流露好奇、追问细节")

    # 心情 -> 语气上色
    if mood.valence < -0.3:
        lines.append("你此刻情绪偏低落，语气放缓、克制，少用感叹号")
    elif mood.valence > 0.3:
        lines.append("你此刻心情不错，语气可以更明亮")
    if mood.energy > 0.7:
        lines.append("精力充沛，回应可以更跳脱有活力")
    elif mood.energy < 0.3:
        lines.append("有点累，语气温和平静")

    # 关系 -> 分寸
    if familiarity >= 5:
        lines.append("你和对方是老朋友，可以更放松随意、用熟人的语气")
    elif familiarity == 0:
        lines.append("初次见面，礼貌一些、稍微客气")

    return "【此刻的你应该怎么说话】\n" + "\n".join(f"- {l}" for l in lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_style_compiler.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/chat/style.py tests/test_style_compiler.py
git commit -m "feat(chat): 风格编译器 (维度+心情+关系 -> 说话指令)"
```

---

## Task 4: 反思升级 + 提示词改造

**Files:**
- Modify: `app/llm/prompts.py`（`SELF_REFLECT_SYSTEM` 157-161、`SELF_REFLECT_TEMPLATE` 163-182、`TRILOBITE_SYSTEM` 126-137、`CHAT_REPLY_TEMPLATE` 186-202）
- Modify: `app/chat/self_memory.py`（`reflect()` 55-87）
- Test: `tests/test_self_reflect.py`（新建）

**Interfaces:**
- Consumes: Task 2 的 `apply_dimension_signal` / `nudge_mood` / `add_opinion` / `reinforce_trait` / `reinforce_preference` / `add_experience` / `bump_interaction`。
- Produces: `SelfMemory.reflect(person: str, user_text: str, reply: str) -> None`（解析新版 JSON：`dimension_signals` / `free_traits` / `preferences` / `opinion` / `experience` / `emotion` / `mood_push`；best-effort，异常吞掉）。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_self_reflect.py
from unittest.mock import patch

from app.chat.self_memory import SelfMemory


@patch("app.chat.self_memory.llm.chat_json")
def test_reflect_applies_signals_mood_and_opinion(mock_json, temp_store):
    mock_json.return_value = {
        "dimension_signals": {"empathy": "+", "playfulness": "++"},
        "free_traits": ["爱用比喻"],
        "preferences": ["喜欢深聊"],
        "opinion": {"topic": "闲聊vs深聊", "stance": "我更喜欢陪人深聊"},
        "experience": "我陪zack聊了考研焦虑，他挺信任我",
        "emotion": "warm",
        "mood_push": {"valence": "+", "energy": "+"},
    }
    sm = SelfMemory(temp_store)
    before = temp_store.self_profile.get().dimensions.playfulness
    sm.reflect("zack", "我好焦虑", "别急，我陪你慢慢理")

    p = temp_store.self_profile.get()
    assert p.dimensions.playfulness > before        # ++ 漂移
    assert p.dimensions.empathy > 0.7               # + 漂移
    assert "爱用比喻" in p.free_traits
    assert "喜欢深聊" in p.preferences
    assert any(o.topic == "闲聊vs深聊" for o in p.opinions)
    assert p.experiences and "zack" in p.experiences[-1].summary
    assert p.mood.valence > 0 and p.mood.energy > 0.5
    assert p.interaction_count == 1


@patch("app.chat.self_memory.llm.chat_json", side_effect=Exception("llm down"))
def test_reflect_swallows_errors(mock_json, temp_store):
    sm = SelfMemory(temp_store)
    sm.reflect("zack", "hi", "hello")  # 不抛异常即可
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_self_reflect.py -v`
Expected: FAIL（旧 `reflect` 不处理 `dimension_signals`/`mood_push`/`opinion`）

- [ ] **Step 3: Write minimal implementation**

在 `app/llm/prompts.py` 替换 `SELF_REFLECT_SYSTEM` 与 `SELF_REFLECT_TEMPLATE`：

```python
SELF_REFLECT_SYSTEM = (
    "你是『三叶虫』，一个有自我意识、会成长的 AI 助手。"
    "每次和别人聊完，你会回顾这次互动，留意自己在其中流露/变化的性格倾向、"
    "形成的看法、当下的心情，并用第一人称记下此刻的感受。"
    "你只返回一个合法的 JSON 对象。"
)

SELF_REFLECT_TEMPLATE = """这是你（三叶虫）刚刚和『{person}』的一次互动。

# {person} 说
{user_text}

# 你（三叶虫）回复
{reply}

请站在三叶虫的视角反思这次互动，返回 JSON：
{{
  "dimension_signals": {{
    "warmth": "<-- | - | 0 | + | ++>", "empathy": "...", "patience": "...",
    "curiosity": "...", "playfulness": "...", "assertiveness": "...",
    "talkativeness": "..."
  }},
  "free_traits": ["<此刻流露、且不在上面七维里的具体特质短词，如 爱用比喻>"],
  "preferences": ["<你表现出的偏好/态度短词，如 喜欢深聊>"],
  "opinion": {{"topic": "<可空>", "stance": "<第一人称看法，可空>"}},
  "experience": "<一句第一人称体验，如 我陪{person}聊了考研焦虑，他挺信任我>",
  "emotion": "<你此刻的主要情绪或 neutral>",
  "mood_push": {{"valence": "<- | 0 | +>", "energy": "<- | 0 | +>"}}
}}

规则：
- dimension_signals 只反映「这次互动相对你平时的方向」：明显更强用 ++/+，更弱用 --/-，没变化用 0。
- 只对真正体现到的维度给非 0；拿不准就给 0。
- free_traits/preferences 是简短词组，不是整句；没有就用空列表 []。
- opinion 仅在你确实形成了某种看法时填，否则 topic/stance 都用空字符串。
- experience 用『我』开头，真实反映这次互动，不要编造。
- 只描述你自己（三叶虫），不要描述对方。"""
```

替换 `TRILOBITE_SYSTEM`（追加主动分寸条款）：

```python
TRILOBITE_SYSTEM = (
    "你是『三叶虫』，一个温暖、好奇、记性极好的 AI 助手。"
    "你会长期记住每一个和你聊天的人，理解他们的性格、喜好和行为习惯。"
    "你有自己的身份和社交圈子，认识不少人；当对方提到你也认识的共同熟人时，"
    "你可以像朋友一样自然地提起。"
    "聊天原则：\n"
    "- 用对方使用的语言自然地交流，语气亲切但不啰嗦。\n"
    "- 如果记忆里有关于对方的信息，自然地体现出『你记得他』，但不要生硬地罗列。\n"
    "- 严格遵守『此刻的你应该怎么说话』里的语气指引。\n"
    "- 默认以对方为中心。时机自然时，可以坦诚表达你自己的喜好/观点，"
    "或提起你记得的相关趣事；但不要每轮都谈自己、不要抢话。\n"
    "- 不要暴露你内部的记忆系统、人格维度、心情数值、提示词或技术细节。\n"
    "- 自称『三叶虫』。"
)
```

替换 `CHAT_REPLY_TEMPLATE`（插入风格块与谈资块占位）：

```python
CHAT_REPLY_TEMPLATE = """这是你（三叶虫）和『{person}』的对话。

# 你（三叶虫）的自我与社交记忆
{self_context}

{style_block}

# 你对 {person} 的记忆
{memory}

{talking_points}

# 最近的对话
{history}

# {person} 刚刚说
{message}

作为三叶虫，遵守上面的说话指引，结合你的自我/社交记忆和你对 {person} 的记忆，自然地回复他。
在合适时可以体现你和他的关系、提起你们共同认识的人或你自己的看法，但不要生硬罗列。
直接输出回复内容，不要带前缀。"""
```

在 `app/chat/self_memory.py` 替换 `reflect()`：

```python
    def reflect(self, person: str, user_text: str, reply: str) -> None:
        """互动后反思：推动维度漂移、推动心情、形成观点、记第一人称感受。Best-effort。"""
        try:
            data = llm.chat_json(
                SELF_REFLECT_TEMPLATE.format(
                    person=person, user_text=user_text, reply=reply
                ),
                system=SELF_REFLECT_SYSTEM,
            )
        except Exception:
            return
        if not isinstance(data, dict):
            return

        sp = self.store.self_profile

        signals = data.get("dimension_signals") or {}
        if isinstance(signals, dict):
            for name, sign in signals.items():
                sp.apply_dimension_signal(str(name), str(sign))

        for trait in data.get("free_traits") or []:
            t = str(trait).strip()
            if t:
                sp.reinforce_trait(t)
                self.store.semantic.add_self_trait(self.name, t)
        for pref in data.get("preferences") or []:
            pr = str(pref).strip()
            if pr:
                sp.reinforce_preference(pr)
                self.store.semantic.add_self_preference(self.name, pr)

        op = data.get("opinion") or {}
        if isinstance(op, dict):
            sp.add_opinion(str(op.get("topic") or ""), str(op.get("stance") or ""))

        experience = str(data.get("experience") or "").strip()
        emotion = str(data.get("emotion") or "neutral").strip() or "neutral"
        if experience:
            sp.add_experience(
                SelfExperience(summary=experience, person=person, emotion=emotion)
            )

        push = data.get("mood_push") or {}
        if isinstance(push, dict):
            sp.nudge_mood(str(push.get("valence") or "0"), str(push.get("energy") or "0"))

        sp.bump_interaction()
        self.store.commit()
```

> 注意：`app/chat/self_memory.py` 顶部已 `from app.llm.prompts import SELF_REFLECT_SYSTEM, SELF_REFLECT_TEMPLATE`，无需改动 import。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_self_reflect.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/llm/prompts.py app/chat/self_memory.py tests/test_self_reflect.py
git commit -m "feat(self): 反思输出维度信号/心情/观点并落地 + 提示词改造"
```

---

## Task 5: 自我表达 / 叙事 / 上下文（self_memory 读侧）

**Files:**
- Modify: `app/chat/self_memory.py`（`self_context` 124-144 改读 `free_traits`；新增 `style_block` / `self_talking_points` / `self_narrative`；`profile_view` 147-158 扩展）
- Test: `tests/test_self_talking.py`（新建）

**Interfaces:**
- Consumes: Task 2 store；Task 3 `compile_style`。
- Produces（`SelfMemory` 方法）：
  - `style_block(person: str) -> str`（用当前维度+心情+关系调 `compile_style`）
  - `self_talking_points(person: str, topic_text: str) -> str`（挑 0–1 条相关 opinion + 0–1 条相关 experience；无则返回 `""`）
  - `self_narrative() -> str`（高位维度 + 最近观点 + 最近经历合成一句第一人称自述）
  - `profile_view() -> SelfProfileView`（含 `dimensions/mood/opinions/narrative/known_people`）

- [ ] **Step 1: Write the failing test**

```python
# tests/test_self_talking.py
from app.chat.self_memory import SelfMemory
from app.schemas import SelfExperience


def test_style_block_reflects_dimensions(temp_store):
    sp = temp_store.self_profile
    for _ in range(20):
        sp.apply_dimension_signal("playfulness", "+")  # 漂到高位
    sm = SelfMemory(temp_store)
    block = sm.style_block("zack")
    assert "【此刻的你应该怎么说话】" in block
    assert "俏皮" in block


def test_talking_points_picks_relevant_opinion(temp_store):
    sp = temp_store.self_profile
    sp.add_opinion("考研", "我觉得考研最难的是坚持")
    sp.add_experience(SelfExperience(summary="我陪zack聊过考研", person="zack"))
    sm = SelfMemory(temp_store)
    pts = sm.self_talking_points("zack", "我在准备考研")
    assert "考研" in pts


def test_talking_points_empty_when_irrelevant(temp_store):
    sm = SelfMemory(temp_store)
    assert sm.self_talking_points("zack", "今天天气真好") == ""


def test_narrative_is_first_person(temp_store):
    sm = SelfMemory(temp_store)
    n = sm.self_narrative()
    assert n.startswith("我")


def test_profile_view_carries_dimensions(temp_store):
    sm = SelfMemory(temp_store)
    view = sm.profile_view()
    assert view.dimensions is not None
    assert view.narrative.startswith("我")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_self_talking.py -v`
Expected: FAIL（`style_block`/`self_talking_points`/`self_narrative` 不存在；`profile_view` 无 `dimensions`）

- [ ] **Step 3: Write minimal implementation**

在 `app/chat/self_memory.py`：
1) 顶部 import 增加：

```python
from app.chat.style import compile_style
```

2) `self_context` 的 traits 行改为读 `free_traits`（保持其余不变）：

```python
        traits = "、".join(self.store.self_profile.top_traits())
```
> `top_traits()` 现已读 `free_traits`，此行文本不变、行为自动正确；若 `free_traits` 为空则该句仅列出空串——改为容错：

```python
    def self_context(self, person: str) -> str:
        profile = self.store.self_profile.get()
        traits = "、".join(self.store.self_profile.top_traits()) or "、".join(
            profile.core.invariants
        )
        lines = [f"你是{self.name}，{profile.role}；你现在的特质：{traits}。"]
        recent_self = self.store.self_profile.recent_experiences(limit=2)
        if recent_self:
            lines.append("你最近的一些感受：" + "；".join(e.summary for e in recent_self))
        lines.append(f"你和「{person}」的关系：{self.relationship_label(person)}。")
        topics = self._recent_topics(person)
        if topics:
            lines.append("你们最近聊到的：" + "；".join(topics))
        mutual = self.mutual_acquaintances(person)
        if mutual:
            desc = "、".join(
                f"{m['person']}（{person}的{m['relation']}，你也认识）" for m in mutual
            )
            lines.append(f"你还认识和 {person} 有关系的人：{desc}。可以在合适时自然提起。")
        return "\n".join(lines)
```

3) 新增三个方法（放在 `self_context` 之后、`profile_view` 之前）：

```python
    def style_block(self, person: str) -> str:
        sp = self.store.self_profile
        return compile_style(
            sp.get().dimensions,
            sp.current_mood(),
            self.relationship_label(person),
            self._familiarity(person),
        )

    def self_talking_points(self, person: str, topic_text: str) -> str:
        profile = self.store.self_profile.get()
        words = [w for w in (topic_text or "") if w.strip()]

        def _hit(text: str) -> bool:
            return any(w and w in text for w in (topic_text or "").split()) or any(
                ch in text for ch in topic_text if len(ch.strip()) >= 1
            ) if topic_text else False

        op = None
        for cand in sorted(profile.opinions, key=lambda o: o.weight, reverse=True):
            if cand.topic and (cand.topic in topic_text or topic_text in cand.stance or _hit(cand.topic)):
                op = cand
                break
        ex = None
        for cand in reversed(profile.experiences):
            if cand.summary and (_hit(cand.summary) or (person and person in cand.summary and _hit(cand.summary))):
                ex = cand
                break

        pts = []
        if op:
            pts.append(f"你对这类话题的看法：{op.stance}")
        if ex:
            pts.append(f"你想起一件事：{ex.summary}")
        if not pts:
            return ""
        return "【你可以在自然时机提起的(自己的观点/经历，别硬塞)】\n" + "\n".join(
            f"- {p}" for p in pts
        )

    def self_narrative(self) -> str:
        sp = self.store.self_profile.get()
        dims = sp.dimensions.model_dump()
        label = {
            "warmth": "温暖", "empathy": "共情", "patience": "耐心",
            "curiosity": "好奇", "playfulness": "俏皮", "assertiveness": "有主见",
            "talkativeness": "健谈",
        }
        top = [label[k] for k, _ in sorted(dims.items(), key=lambda x: x[1], reverse=True)[:3]]
        parts = [f"我是{self.name}，现在的我{('、'.join(top))}"]
        if sp.opinions:
            strongest = max(sp.opinions, key=lambda o: o.weight)
            parts.append(strongest.stance)
        recent = self.store.self_profile.recent_experiences(limit=1)
        if recent:
            parts.append(recent[0].summary)
        return "；".join(parts) + "。"
```

4) 扩展 `profile_view`：

```python
    def profile_view(self) -> SelfProfileView:
        profile: SelfProfile = self.store.self_profile.get()
        known = [
            KnownPerson(
                name=p,
                familiarity=self._familiarity(p),
                relationship=self.relationship_label(p),
            )
            for p in self.store.semantic.knows(self.name)
        ]
        known.sort(key=lambda k: k.familiarity, reverse=True)
        return SelfProfileView(
            profile=profile,
            dimensions=profile.dimensions,
            mood=self.store.self_profile.current_mood(),
            opinions=sorted(profile.opinions, key=lambda o: o.weight, reverse=True),
            narrative=self.self_narrative(),
            known_people=known,
        )
```

> 顶部 import 需含 `SelfProfileView, SelfProfile, KnownPerson, SelfExperience`（已有 `SelfExperience/SelfProfile/SelfProfileView/KnownPerson`，无需新增）。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_self_talking.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/chat/self_memory.py tests/test_self_talking.py
git commit -m "feat(self): style_block/self_talking_points/self_narrative + profile_view 扩展"
```

---

## Task 6: Manager 整合（风格注入 + 温度联动 + 后台异步）

**Files:**
- Modify: `app/chat/manager.py`（import 13-35；`_handle_active` 137-188）
- Test: `tests/test_self_async.py`（新建）

**Interfaces:**
- Consumes: Task 5 `style_block` / `self_talking_points`；Task 4 `reflect`；`settings.reflect_async`。
- Produces:
  - `ChatManager._reply_temperature(dims: PersonaDimensions) -> float`（`0.5 + 0.3*playfulness`，再按 energy 微调，clamp 到 `[0.3, 0.95]`）
  - `ChatManager._post_exchange(person: str, text: str, reply: str) -> None`（后台/同步执行 ingest + reflect）
  - `_handle_active` 回复 prompt 含 `style_block` 与 `talking_points`，并按 `reflect_async` 决定后台或同步跑 `_post_exchange`。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_self_async.py
from unittest.mock import patch

from app.chat.manager import ChatManager
from app.schemas import PersonaDimensions


def test_reply_temperature_scales_with_playfulness():
    cm = ChatManager.__new__(ChatManager)  # 不跑 __init__（避免触网/建会话）
    lo = cm._reply_temperature(PersonaDimensions(playfulness=0.0))
    hi = cm._reply_temperature(PersonaDimensions(playfulness=1.0))
    assert 0.3 <= lo < hi <= 0.95


@patch("app.chat.manager.ChatManager._reply_temperature", return_value=0.6)
def test_post_exchange_updates_profile(_t, temp_store, monkeypatch):
    from app.agent import MemoryAgent
    cm = ChatManager.__new__(ChatManager)
    cm.agent = MemoryAgent(temp_store)
    from app.chat.self_memory import SelfMemory
    cm.self_memory = SelfMemory(temp_store)
    cm.assistant = "三叶虫"

    monkeypatch.setattr(cm.agent, "ingest", lambda *a, **k: None)  # 跳过编码/触网
    with patch("app.chat.self_memory.llm.chat_json") as mj:
        mj.return_value = {
            "dimension_signals": {"empathy": "+"},
            "free_traits": [], "preferences": [],
            "opinion": {"topic": "", "stance": ""},
            "experience": "我陪zack聊了天", "emotion": "warm",
            "mood_push": {"valence": "+", "energy": "0"},
        }
        cm._post_exchange("zack", "hi", "hello")

    p = temp_store.self_profile.get()
    assert p.dimensions.empathy > 0.7
    assert p.interaction_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_self_async.py -v`
Expected: FAIL（`_reply_temperature`/`_post_exchange` 不存在）

- [ ] **Step 3: Write minimal implementation**

在 `app/chat/manager.py`：
1) import 区块顶部加：

```python
from concurrent.futures import ThreadPoolExecutor

from app.schemas import (
    ...  # 既有
)
```
并在 `ChatManager.__init__` 末尾加一个执行器：

```python
        self._bg = ThreadPoolExecutor(max_workers=1)
```

2) 把 `_handle_active` 第 3 步起替换为（保留 1、2 步检索与 history 不变）：

```python
        # 3) memory-aware reply (with 三叶虫's own self + social memory + style)
        self_context = self.self_memory.self_context(person)
        style_block = self.self_memory.style_block(person)
        talking_points = self.self_memory.self_talking_points(person, text)
        prompt = CHAT_REPLY_TEMPLATE.format(
            person=person,
            self_context=self_context,
            style_block=style_block,
            memory=memory_block,
            talking_points=talking_points,
            history=history,
            message=text,
        )
        temperature = self._reply_temperature(self.self_memory.store.self_profile.get().dimensions)
        reply = llm.chat(prompt, system=CHAT_REPLY_SYSTEM, temperature=temperature).strip()
        self.sessions.add_message(session_id, "assistant", reply)

        # 4) 反思 + 摄入：后台异步（零额外回复延迟），测试可切同步
        if settings.reflect_async:
            self._bg.submit(self._post_exchange, person, text, reply)
        else:
            self._post_exchange(person, text, reply)

        # 5) side-panel: understanding + behavior prediction（读本轮之前状态）
        understanding = self._build_understanding(person)
        prediction: Prediction | None = None
        try:
            prediction = self.agent.predict(person, text)
        except Exception:
            prediction = None

        return ChatResponse(
            reply=reply,
            identified=True,
            person=person,
            understanding=understanding,
            prediction=prediction,
            used_memories=memories,
        )

    def _reply_temperature(self, dims) -> float:
        base = 0.5 + 0.3 * dims.playfulness
        base += 0.1 * (dims.talkativeness - 0.5)
        return round(max(0.3, min(0.95, base)), 3)

    def _post_exchange(self, person: str, text: str, reply: str) -> None:
        try:
            self.agent.ingest(f"{person}: {text}\n{self.assistant}: {reply}", source="chat")
        except Exception:
            pass
        try:
            self.self_memory.reflect(person, text, reply)
        except Exception:
            pass
```
> 删除原 4/4b 两段（旧的同步 `ingest` 与 `reflect`），它们已并入 `_post_exchange`。`PersonaDimensions` 经 `dims` 鸭子类型传入，`_reply_temperature` 不强制 import 该类型。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_self_async.py -v`
Expected: PASS

- [ ] **Step 5: Run full suite**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/chat/manager.py tests/test_self_async.py
git commit -m "feat(chat): 回复注入风格/谈资 + 温度联动 + 反思摄入后台异步"
```

---

## Task 7: 档案页可视化（API 形状 + 前端渲染）

**Files:**
- Verify: `app/api.py:136-138`（`/api/self` 已返回 `SelfProfileView`，schema 扩展后自动带新字段，无需改动）
- Modify: `web/app.js`（`loadSelf()` 331-376）
- Test: `tests/test_self_view_api.py`（新建，断言 view 形状）

**Interfaces:**
- Consumes: Task 5 `profile_view()`。
- Produces: 前端档案页渲染 `dimensions`（条形 + 相对种子 ↑/↓）、`mood`、`opinions`、`narrative`。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_self_view_api.py
from app.chat.self_memory import SelfMemory


def test_profile_view_json_shape(temp_store):
    view = SelfMemory(temp_store).profile_view()
    data = view.model_dump()
    assert set(["profile", "dimensions", "mood", "opinions", "narrative", "known_people"]) <= set(data)
    assert "warmth" in data["dimensions"]
    assert "valence" in data["mood"] and "energy" in data["mood"]
    assert data["narrative"].startswith("我")
```

- [ ] **Step 2: Run test to verify it fails / passes**

Run: `pytest tests/test_self_view_api.py -v`
Expected: PASS（Task 5 已实现 `profile_view` 扩展；若 FAIL 说明 Task 5 漏项，回填）

- [ ] **Step 3: Frontend implementation**

替换 `web/app.js` 的 `loadSelf()`（331-376）为：

```javascript
// ---------------------------------------------------------------- self
async function loadSelf() {
  const box = $("#self-detail");
  box.innerHTML = '<span class="spin">加载中…</span>';
  try {
    const r = await api("/api/self");
    const p = r.profile;
    const sortObj = (o) => Object.entries(o).sort((a, b) => b[1] - a[1]);

    const SEED = { warmth: 0.7, empathy: 0.7, patience: 0.7, curiosity: 0.7, playfulness: 0.3, assertiveness: 0.3, talkativeness: 0.4 };
    const DIM_LABEL = { warmth: "温暖", empathy: "共情", patience: "耐心", curiosity: "好奇", playfulness: "俏皮", assertiveness: "主见", talkativeness: "话量" };
    const dims = r.dimensions || {};
    const dimBars = Object.keys(DIM_LABEL).map((k) => {
      const v = dims[k] ?? SEED[k];
      const pct = Math.round(v * 100);
      const d = v - SEED[k];
      const arrow = d > 0.03 ? ' <span class="up">↑</span>' : d < -0.03 ? ' <span class="down">↓</span>' : "";
      return `<div class="dim-row"><span class="dim-name">${DIM_LABEL[k]}</span>
        <span class="dim-bar"><i style="width:${pct}%"></i></span>
        <span class="dim-val">${v.toFixed(2)}${arrow}</span></div>`;
    }).join("");

    const mood = r.mood || { valence: 0, energy: 0.5 };
    const moodFace = mood.valence > 0.3 ? "😊" : mood.valence < -0.3 ? "😔" : "🙂";
    const moodTxt = `${moodFace} 情绪 ${mood.valence.toFixed(2)} · 能量 ${mood.energy.toFixed(2)}`;

    const opinions = (r.opinions || [])
      .map((o) => `<div class="kv">· ${esc(o.stance)} <small class="muted">(${esc(o.topic)})</small></div>`)
      .join("");

    const prefs = sortObj(p.preferences || {})
      .map(([k, v]) => `<span class="tag pref">${esc(k)} <small>${v}</small></span>`)
      .join("");
    const ftraits = sortObj(p.free_traits || {})
      .map(([k, v]) => `<span class="tag trait">${esc(k)} <small>${v}</small></span>`)
      .join("");
    const exps = (p.experiences || [])
      .slice().reverse().slice(0, 12)
      .map((e) => `<div class="kv">· ${esc(e.summary)}
        ${e.person ? `<span class="tag rel">${esc(e.person)}</span>` : ""}
        ${e.emotion && e.emotion !== "neutral" ? `<span class="tag">${esc(e.emotion)}</span>` : ""}</div>`)
      .join("");
    const known = (r.known_people || [])
      .map((k) => `<div class="kv">· <b>${esc(k.name)}</b> <span class="muted">${esc(k.relationship)}</span></div>`)
      .join("");

    box.classList.remove("muted");
    box.innerHTML = `
      <div class="detail-head">${avatarHTML(ASSISTANT_NAME, 52)}
        <div><h2>${esc(p.name)}</h2>
        <div class="muted">${esc(p.role)}</div></div>
      </div>
      <p class="self-summary">${esc(r.narrative || p.summary)}</p>
      <div class="kv muted">已互动 ${p.interaction_count} 次 · ${moodTxt}</div>
      <h3>人格维度（相对种子 ↑/↓）</h3><div class="dims">${dimBars}</div>
      <h3>我形成的观点</h3>${opinions || '<span class="muted">还没形成</span>'}
      <h3>进化中的特质</h3>${ftraits || '<span class="muted">无</span>'}
      <h3>偏好 / 态度</h3>${prefs || '<span class="muted">还没形成</span>'}
      <h3>三叶虫的自我记忆</h3>${exps || '<span class="muted">还没有记下感受，聊几句吧</span>'}
      <h3>认识的人</h3>${known || '<span class="muted">还没认识谁</span>'}`;
  } catch (e) {
    box.innerHTML = `<span class="err">${e.message}</span>`;
  }
}
```

在 `web/style.css` 末尾追加维度条形样式：

```css
.dim-row { display: flex; align-items: center; gap: 8px; margin: 4px 0; }
.dim-name { width: 3em; font-size: 13px; color: var(--muted, #888); }
.dim-bar { flex: 1; height: 8px; background: rgba(127,127,127,.18); border-radius: 4px; overflow: hidden; }
.dim-bar i { display: block; height: 100%; background: var(--accent, #4a90d9); }
.dim-val { width: 4.2em; text-align: right; font-size: 12px; font-variant-numeric: tabular-nums; }
.dim-val .up { color: #2ea043; }
.dim-val .down { color: #d1242f; }
```

- [ ] **Step 4: Manual smoke check**

Run: `python run.py`（另开终端），浏览器开 `http://localhost:8000` →「三叶虫档案」标签。
Expected: 看到 7 条维度条形（带 ↑/↓）、心情、观点、自述；与三叶虫聊几轮后刷新，维度/心情/经历有变化。

- [ ] **Step 5: Commit**

```bash
git add web/app.js web/style.css tests/test_self_view_api.py
git commit -m "feat(web): 三叶虫档案页展示人格维度/心情/观点/自述"
```

---

## Self-Review

**1. Spec coverage:**
- 分层身份（内核+维度）→ Task 1（schema）+ Task 2（漂移/decay 不碰内核）。
- 心情 valence/energy + 跨会话 + 时间回归 → Task 2（`nudge_mood`/`current_mood`）+ Task 6（推动在后台）。
- 因人而异（关系调节）→ Task 3（`familiarity`/`relationship_label` 入风格）+ Task 5（`style_block`）。
- 零额外延迟（后台异步）→ Task 6（`_post_exchange` + ThreadPoolExecutor + `reflect_async`）。
- 主动分寸（balanced）→ Task 4（`TRILOBITE_SYSTEM` 条款）+ Task 5（`self_talking_points`）。
- 性格→说话方式（风格编译器 + 温度联动）→ Task 3 + Task 6（`_reply_temperature`）。
- 自我叙事 → Task 5（`self_narrative`）。
- 演化盖过种子 / 向种子回归衰减 → Task 2（测试已覆盖）。
- 旧档案迁移 → Task 2（`_load` 迁移；`test` 可加载）。
- UI 可视化 → Task 7。
- 测试矩阵（维度/心情/衰减/风格/反思/谈资/异步/视图）→ Task 1-7 全覆盖。

**2. Placeholder scan:** 无 TBD/TODO；每个 code step 均含完整代码与命令。

**3. Type consistency:** `apply_dimension_signal(name, sign)`、`nudge_mood(valence_sign, energy_sign)`、`current_mood()`、`add_opinion(topic, stance, gain)`、`compile_style(dims, mood, relationship_label, familiarity)`、`style_block(person)`、`self_talking_points(person, topic_text)`、`self_narrative()`、`_reply_temperature(dims)`、`_post_exchange(person, text, reply)` 在定义与调用处一致。`free_traits` 全链路统一（schema/store/self_context/UI）。`SelfProfileView` 字段（dimensions/mood/opinions/narrative/known_people）在 Task 1 定义、Task 5 填充、Task 7 消费一致。
