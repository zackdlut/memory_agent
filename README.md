# 🧠 类人级 Memory System Agent

把**人类记忆系统**完整映射成一个可运行的 **Agent 架构**：从对话中持续沉淀「人 + 关系 + 偏好 + 行为模式」，做到**理解人**并**预测人的行为**（Theory of Mind）。

基于 [`human_memory_system_prd.md`](human_memory_system_prd.md) 实现。

---

## 人类记忆 → Agent 映射

| 人类记忆系统 | 本项目实现 | 代码位置 |
|---|---|---|
| 感觉记忆 / 工作记忆 | 输入解析 + 检索拼装的 context | `app/perception/` `app/retrieval/` |
| 情景记忆 (Episodic) | FAISS 向量库 | `app/memory/episodic.py` |
| 语义记忆 (Semantic) | NetworkX 知识图谱 | `app/memory/semantic.py` |
| 程序记忆 (Procedural) | Skills 注册表 | `app/memory/skills.py` |
| 人格模型 (Persona) | SQLite 人物模型 | `app/memory/persona.py` |
| 自进化 / 遗忘 | 重复·情绪·任务 三信号 + replace/merge/weight/decay | `app/evolution/evolver.py` |

## 运行时流水线

```
对话输入
  → 感知层 (speaker/NER/分句)        app/perception
  → 编码层 (LLM 结构化抽取)          app/encoding
  → 多层记忆写入 + 自进化            app/memory + app/evolution
提问 / 情境
  → 检索层 (FAISS+Graph+Persona → LLM 重排)   app/retrieval
  → 推理层 (带人物理解作答)          app/reasoning
  → 行为预测 (persona+pattern→action) app/prediction
```

---

## 快速开始

### 1. 配置环境

复制 `.env.example` 为 `.env` 并按需修改（默认已指向本地 Ollama）：

```bash
cp .env.example .env
```

关键变量：

- `ANTHROPIC_BASE_URL` / `LLM_BASE_URL`：Ollama 地址（默认 `http://10.67.34.44:11434`）
- `ANTHROPIC_MODEL` / `CHAT_MODEL`：对话模型（默认 `qwen3.5:9b`）
- `EMBED_MODEL`：向量模型（默认 `nomic-embed-text:latest`，768 维）

> 系统调用 Ollama 原生 `/api/chat` 与 `/api/embeddings`。请确保 Ollama 已拉取上述模型。

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 启动服务

```bash
python run.py
```

打开浏览器访问 <http://localhost:8000>。

### 4. （可选）灌入示例数据 / 跑指标

```bash
python -m scripts.seed   # 写入一段多人对话，立即可演示
python -m scripts.eval   # 计算 entity / recall / prediction 三项指标
```

---

## Web 界面

- **与三叶虫聊天**：和 AI 助手「三叶虫」对话。新建会话后它会先问"你是谁"，绑定身份后每轮把「你 + 三叶虫」的对话整段摄入记忆；右侧边栏实时展示「三叶虫对你的理解」（特质/偏好/关系/行为模式）+「行为预测」+「本轮用到的记忆」。支持为多个不同的人分别新建会话，互不串档，持久化保存。
- **摄入记忆**：粘贴 `Alice: ...` 形式的多人对话，查看抽取出的人物/关系/行为模式与自进化结果
- **理解 / 问答**：提问并查看答案 + 命中的记忆来源（可解释）
- **行为预测**：选人 + 输入情境，得到最可能行为、置信度与依据
- **人格档案**：查看每个人的特质/偏好/关系/行为模式（带权重）
- **知识图谱**：vis-network 可视化语义记忆

## HTTP API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/ingest` | 摄入对话，返回抽取结果 + 自进化 |
| POST | `/api/ask` | 提问，返回答案 + 命中记忆 |
| POST | `/api/predict` | 行为预测 |
| GET | `/api/persons` `/api/person/{name}` | 人格档案 |
| POST | `/api/person/merge` | 合并重复人物（`{source, target}`） |
| PATCH | `/api/person/{name}` | 编辑人格档案（改摘要 / 删特质·偏好·行为 / 加别名） |
| GET | `/api/self` | 三叶虫自我档案（进化特质/偏好/自我记忆/认识的人） |
| GET | `/api/graph` | 知识图谱节点/边 |
| GET | `/api/memories?q=` | 情景记忆检索/列举 |
| GET | `/api/stats` `/health` | 统计 / 健康检查 |
| POST | `/api/decay` | 触发一次遗忘衰减 |
| POST | `/api/chat/session` | 新建聊天会话，返回 `session_id` + 三叶虫开场白 |
| GET | `/api/chat/sessions` | 会话列表（支持多人多会话） |
| GET | `/api/chat/session/{id}` | 会话详情 + 全部消息 |
| POST | `/api/chat/message` | 发消息，返回回复 + 理解 + 行为预测 + 命中记忆 |
| DELETE | `/api/chat/session/{id}` | 删除会话 |

## 三叶虫聊天助手

「三叶虫」是建立在记忆系统之上的对话助手：

- 每个会话绑定一个人，开场先问对方身份；
- 对话被持续摄入记忆，因此它会越聊越懂你（特质、偏好、行为模式都会沉淀到人格档案与知识图谱）；
- 助手本身不会被建模为普通"人物"（不会出现在人格档案/人物列表里），但它拥有**会成长的自我记忆与社交关系**：
  - 有一份固定的固有人设作种子（温暖、好奇、记性好、善于倾听、真诚…），但**每聊一次就会反思自己**：抽取它此刻流露的特质/偏好并加权沉淀，再用第一人称记下一句感受（如"我陪 zack 聊了考研焦虑，他挺信任我"）。这些会随对话进化、也会随 `/api/decay` 淡化，持久化在 `data/self.json`。
  - 它认识哪些人（聊过天就会记住），在知识图谱中以独立的星形节点出现，并连出"认识"边；它进化出的特质/偏好也会作为边挂到该节点上（与拥有同款特质的人物天然相连）。
  - 聊天时会自然体现「它现在的特质 + 最近的感受 + 它和你的关系/熟悉度」，并在合适时提起「你认识、它也认识的共同熟人」（如对 zack 提到他同学阿杰）。
- 侧边栏会显示「三叶虫与TA」的熟悉度与「共同认识」的人；「三叶虫档案」标签页完整展示它的进化特质、偏好、自我记忆与社交圈。

可通过 `.env` 的 `ASSISTANT_NAME` 修改助手名字。

---

## 设计要点

- **可解释**：每条检索结果都带 `source`（episodic/semantic/persona），UI 直接展示「答案用到了哪些记忆」。
- **自进化**：相似度高的新情景会**合并强化**已有记忆而非重复存储；情绪强烈、任务相关、重复出现都会提升权重；`/api/decay` 提供遗忘机制。
- **鲁棒**：LLM 抽取走严格 JSON + 解析重试 + 兜底规则，单次抽取失败不会让流水线崩溃。
- **可替换**：编码层 `app/encoding/encoder.py` 是唯一的抽取 seam，后续可替换为 PRD §9 的 LoRA 微调小模型。

## 数据持久化

全部落在 `DATA_DIR`（默认 `./data/`）：

- `episodic.index`：FAISS 索引
- `memory.db`：SQLite（episodes + personas）
- `graph.json`：语义图谱快照
- `self.json`：三叶虫的自我档案（进化特质/偏好/自我记忆）

删除 `data/` 即可重置全部记忆。

## 技术栈

Python 3.10+ · FastAPI · FAISS · NetworkX · SQLite · Ollama (qwen3.5:9b + nomic-embed-text) · vis-network
