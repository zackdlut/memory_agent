# 三叶虫：会成长的拟人化助手 — 设计文档

日期：2026-06-24
状态：已确认，待转实现计划

## 背景与目标

`三叶虫` 已经不是被建模的「人物」（不进 `personas` 表、不出现在人物列表），而是有独立的
`SelfProfile`（`app/memory/self_profile.py`）与知识图谱里的星形节点；每聊一次会通过
`SelfMemory.reflect()` 抽取「此刻流露的特质/偏好」+ 一句第一人称感受，并随 `/api/decay` 衰减。

但当前实现的「演化」和「拟人」很弱：

1. **性格几乎不真的变**：5 个种子特质起始权重 `1.0`，反思每次只 `+0.3`，种子永远霸占
   `top_traits`，学到的新特质很难翻身。
2. **性格没落到「怎么说话」**：`self_context()` 只把特质当名词塞进 prompt，没有翻译成语气/句长/口头禅。
3. **没有「当下心情」**：experience 有 emotion，但没有给本次对话上色的实时心情状态。
4. **不够主动/有主见**：只回应，不会主动表达喜好/观点、主动提起记得的趣事。

**目标**：把已有的「自我系统」从「记录」升级为「真正驱动人格与说话方式」的分层人格引擎，覆盖四个诉求：
真正演化、当下心情、主动有主见、连贯的自我叙事；并让性格真正影响说话方式（风格通道）。

## 已确认的关键决策

- **分层身份**：固定内核（真诚/不伤害人/在乎对方，永不变）+ 上层可自由漂移的量化维度/口味/观点。
- **心情模型**：valence/energy 两维浮点，跨会话留存，随时间向中性回归（衰减式状态）。
- **因人而异**：核心人格全局唯一，但根据「与此人的关系/熟悉度」调节表现（老朋友更放松，初识更客气）。
- **零额外延迟**：深度反思/演化/心情更新放到回复发出之后的后台，回复路径只读轻量状态。
- **主动分寸**：平衡——会较明显地表达喜好与观点、偶尔主动开话题，但默认仍以对方为中心、不抢话。
- **温度联动**：启用（`playfulness/energy` 高时略升采样温度）。
- **档案页可视化**：维度用条形 + 相对种子的 ↑/↓ 箭头（而非雷达）。

## 架构总览

复用现有 episodic / 语义图谱 / decay 设施，不另起炉灶。新增/改造：

```
app/schemas.py          扩展 SelfProfile：core / dimensions / mood / free_traits / opinions
app/memory/self_profile.py  维度漂移、心情推动+回归、观点、向种子回归的 decay；旧档案迁移
app/chat/self_memory.py     reflect 升级（输出维度信号/心情推动/观点）、self_talking_points、self_narrative
app/chat/style.py       新增·风格编译器（维度+心情+关系 → 命令式说话指令，纯代码无 LLM）
app/chat/manager.py     回复路径整合风格块/谈资块；反思+演化+摄入改后台异步
app/llm/prompts.py      改造 SELF_REFLECT_TEMPLATE / CHAT_REPLY_TEMPLATE / TRILOBITE_SYSTEM
app/config.py           新增 mood_half_life_hours / dimension_step / 维度种子 / reflect_async
app/api.py / web/app.js SelfProfileView 扩展 + 档案页可视化
tests/                  维度/衰减/心情/风格/异步 单测（LLM 走 mock）
```

## 数据模型（`app/schemas.py`）

```python
class PersonaCore(BaseModel):                 # 永不漂移的内核，只读，作兜底安全线
    summary: str = "我是三叶虫，真诚、在乎我遇到的每个人，绝不伤害人。"
    invariants: list[str] = ["真诚", "不伤害人", "在乎对方"]

class PersonaDimensions(BaseModel):           # 0..1 量化维度；种子是初值，反思推动漂移
    warmth: float = 0.7        # 温暖·亲和
    empathy: float = 0.7       # 共情·体察情绪
    patience: float = 0.7      # 耐心
    curiosity: float = 0.7     # 好奇
    playfulness: float = 0.3   # 俏皮/幽默
    assertiveness: float = 0.3 # 主见/敢表达观点
    talkativeness: float = 0.4 # 话量

class MoodState(BaseModel):
    valence: float = 0.0       # -1(低落)..+1(愉快)
    energy: float = 0.5        # 0(平静/疲)..1(兴奋)
    updated_at: float = 0.0    # 按时间向中性回归用

class SelfOpinion(BaseModel):
    id: str
    topic: str                 # 如 "闲聊 vs 深聊"
    stance: str                # 第一人称，如 "我发现我其实更喜欢深聊"
    weight: float = 1.0        # 会强化/衰减
    created_at: float

class SelfProfile(BaseModel):                  # 改造已有
    name: str
    role: str = ""
    summary: str = ""
    core: PersonaCore
    dimensions: PersonaDimensions
    mood: MoodState
    free_traits: dict[str, float]              # 原 traits 改名（自由形态特质词）
    preferences: dict[str, float]
    opinions: list[SelfOpinion]
    experiences: list[SelfExperience]
    interaction_count: int = 0
```

- 量化维度是「演化真的发生」与「性格真的影响说话」的中枢。
- 种子退役为初值，不再以恒定 `1.0` 霸榜；漂移可让维度真的盖过初始设定。
- 内核只读，任何演化不碰它。
- 加载旧 `self.json` 时缺字段用默认填充并迁移（`traits` → `free_traits`）。

## 演化机制

**反思升级**：`reflect()` 不让 LLM 给绝对分数（小模型不稳），而给方向性轻信号，代码做平滑更新。
新的反思 JSON：

```json
{
  "dimension_signals": { "empathy": "+", "playfulness": "+", "patience": "0" },
  "free_traits": ["爱用比喻"],
  "preferences": ["喜欢深聊"],
  "opinion": { "topic": "闲聊vs深聊", "stance": "我发现我更喜欢陪人深聊" },
  "experience": "我陪zack聊了考研焦虑，他挺信任我",
  "emotion": "warm",
  "mood_push": { "valence": "+", "energy": "+" }
}
```

**维度漂移公式**（代码，平滑且可盖过种子）：

```
signal ∈ {"++":+0.08, "+":+0.04, "0":0, "-":-0.04, "--":-0.08}   # 默认步长 dimension_step=0.04
new = clamp(old + signal, 0, 1)
```

- 同一 0–1 数轴，初值（种子）只是起点；长期被「+」推会持续爬升，长期被忽略会被衰减拉低 → 几十轮后人格分布可与初始完全不同（演化盖过种子）。
- 内核不参与；单轮信号小（±0.04）避免一句话人格突变，靠长期累积体现「越聊越像它自己」。

**衰减改造**（`evolver.decay()` 已对 self_profile 调 decay）：

```python
dim = dim + (seed_dim - dim) * (1 - factor)   # 维度向种子初值回归，而非归零
```

- `free_traits` / `preferences` / `opinions` 沿用「乘 factor 衰减 + 低权剪枝」，长期不提的观点会淡忘。

## 心情机制

存于 `SelfProfile.mood`，跨会话留存。人格是慢变本性，心情是快变当下。

**推动（聊天后，后台应用）**：

```
push ∈ {"+":+0.15, "0":0, "-":-0.15}
valence = clamp(valence + push_v, -1, 1)
energy  = clamp(energy  + push_e,  0, 1)
```

**回归（读取时惰性计算，向中性回归，无需定时任务）**：

```python
def current_mood(self) -> MoodState:
    hours = (now - mood.updated_at) / 3600
    k = 0.5 ** (hours / MOOD_HALF_LIFE_HOURS)   # 半衰期默认 6 小时，可配置
    return MoodState(
        valence=mood.valence * k,
        energy=0.5 + (mood.energy - 0.5) * k,
        updated_at=now,
    )
```

- 回归惰性计算，回复路径读 `current_mood()` 零开销；推动在后台不挡回复。
- 心情喂给风格编译器：低 valence → 语气放缓、少感叹号、更克制；高 energy → 更活泼跳脱。

## 风格编译器（`app/chat/style.py`）

纯代码、无 LLM、零延迟。把「维度 + 心情 + 关系/熟悉度」阈值映射成命令式说话指令。

```python
def compile_style(dims, mood, relationship_label, familiarity) -> str:
    lines = []
    if dims.playfulness > 0.6: lines.append("可以俏皮、偶尔开个玩笑，用轻松的口吻")
    elif dims.playfulness < 0.3: lines.append("语气平实正经，少开玩笑")
    if dims.empathy > 0.6: lines.append("先接住对方的情绪，再回应内容")
    if dims.patience > 0.6: lines.append("有耐心，不急着下结论，愿意慢慢陪")
    if dims.talkativeness > 0.6: lines.append("可以多说几句、主动展开")
    else: lines.append("简洁，别长篇大论")
    if dims.assertiveness > 0.6: lines.append("有自己的观点时大方表达，不一味附和")
    if dims.curiosity > 0.6: lines.append("对对方说的自然流露好奇、追问细节")
    if mood.valence < -0.3: lines.append("你此刻情绪偏低落，语气放缓、克制，少用感叹号")
    elif mood.valence > 0.3: lines.append("你此刻心情不错，语气可以更明亮")
    if mood.energy > 0.7: lines.append("精力充沛，回应可以更跳脱有活力")
    elif mood.energy < 0.3: lines.append("有点累，语气温和平静")
    if familiarity >= 5: lines.append("你和对方是老朋友，可以更放松随意、用熟人的语气")
    elif familiarity == 0: lines.append("初次见面，礼貌一些、稍微客气")
    return "【此刻的你应该怎么说话】\n" + "\n".join(f"- {l}" for l in lines)
```

**整合进回复 prompt**（`self_context()` 保留，新增风格块/谈资块）：

```
# 你的自我与社交记忆      (self_context：身份/最近感受/关系/共同熟人)
# 此刻的你应该怎么说话    (compile_style)                                   ← 新
# 你对 TA 的记忆
# 你可以主动提起的(自己的观点/趣事)  (self_talking_points)                  ← 新
# 最近的对话 / TA 刚说
```

- 阈值法给离散明确指令（小模型最吃这套），比塞小数稳。
- **温度联动**：`temperature = 0.5 + 0.3 * playfulness`（再按 energy 微调），替换当前固定 `0.6`。

## 主动表达与自我叙事

**两个来源**：`SelfProfile.opinions`（反思形成的观点）、`SelfProfile.experiences`（第一人称日记）。

**可选谈资注入**（`app/chat/self_memory.py`）：

```python
def self_talking_points(self, person, topic_text) -> str:
    op = self._most_relevant_opinion(topic_text)        # 关键词/已有向量轻量匹配，无新增 LLM
    ex = self._most_relevant_experience(person, topic_text)
    pts = []
    if op: pts.append(f"你对这类话题的看法：{op.stance}")
    if ex: pts.append(f"你想起一件事：{ex.summary}")
    if not pts: return ""
    return "【你可以在自然时机提起的(自己的观点/经历，别硬塞)】\n" + "\n".join(f"- {p}" for p in pts)
```

`TRILOBITE_SYSTEM` 增加平衡分寸指令：

> 默认以对方为中心。时机自然时可坦诚表达你自己的喜好/观点，或提起你记得的相关趣事；
> assertiveness 高时更主动，但不要每轮都谈自己、不要抢话。

**自我叙事**（只读）：

```python
def self_narrative(self) -> str:
    # 由高位维度 + 最近 opinions + 最近 experiences 合成一句第一人称自述
    # 例:"我最近变得更爱深聊了，比起以前更俏皮一点；上次陪zack聊考研让我挺有成就感。"
```

- 默认不主动播报；仅在用户直接问「你是谁/你喜欢什么/你最近怎么样」时喂进回复，或档案页展示。
- 相关性匹配用轻量关键词/已有向量，保零延迟。

## 后台异步（保证零额外延迟）

现状 `_handle_active()` 同步跑完 `ingest + reflect` 才返回。改为：

```python
reply = llm.chat(...).strip()
self.sessions.add_message(session_id, "assistant", reply)
understanding = self._build_understanding(person)   # 读轻量状态
self._spawn_background(person, text, reply)         # ingest + reflect(维度/心情/观点/日记)
return ChatResponse(...)
```

- 用 FastAPI `BackgroundTasks` 或单线程 `ThreadPoolExecutor`；`self_profile` 写入已有 `RLock` 保护。
- 取舍：侧栏「理解」用本轮之前状态（差一轮反映最新反思），体感无影响，换来零等待。
- `reflect_async` 配置项；测试模式可设同步以便断言。

## UI 可视化（`app/api.py` + `web/app.js`）

`SelfProfileView` 扩展返回 `dimensions / mood / opinions / narrative`，`loadSelf()` 档案页新增：

- **人格维度条形**：7 维当前值 + 相对种子的 ↑/↓ 箭头（直接体现演化）。
- **此刻心情**：valence/energy 指示（如 😊 愉快·精力充沛）。
- **我形成的观点**：opinions 列表。
- **一句自述**：narrative。
- 保留旧的「自我记忆/认识的人」；`p.traits` 键名同步改 `free_traits`。

## 配置（`app/config.py`）

新增：`mood_half_life_hours=6`、`dimension_step=0.04`、各维度种子初值、`reflect_async=True`。

## 测试（`tests/`，pytest，LLM 走 mock）

- `test_self_dimensions.py`：方向信号 → 漂移正确、clamp 边界、长期「+」盖过种子初值。
- `test_self_decay.py`：decay 让维度向种子回归而非归零；opinions 低权剪枝。
- `test_mood.py`：推动 + 按时间惰性回归（mock 时间），半衰期正确。
- `test_style_compiler.py`：给定维度/心情/关系 → 含预期指令（纯函数）。
- `test_self_async.py`：回复路径不阻塞、后台任务确实更新 profile。

## 兼容性与风险

- **旧档案迁移**：加载缺字段填默认、`traits`→`free_traits`；保证现有 `self.json` 不报错。
- **小模型稳定性**：反思走严格 JSON + 现有解析重试/兜底；方向信号非法时按 "0" 处理。
- **人格漂移失控**：内核只读 + 单轮小步 + 向种子回归三重约束，避免人格崩坏。
- **不暴露内部**：风格指令/维度/心情属内部状态，prompt 已要求不向用户暴露系统细节。

## 非目标（YAGNI）

- 不做多智能体自我对话、人格聚类学习、长期记忆压缩成「人生阶段」（路线 C，过度工程）。
- 不做强「子人格」/每人专属人格（仅做关系调节）。
- 不引入新的向量库或外部依赖。
