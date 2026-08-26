# SkillMap 阶段 7 详细实施计划 — 长期记忆与 Middleware

> 对应：《SkillMap_个人技术栈成长智能体_项目计划书》阶段 7"长期记忆与 Middleware"
> 版本：V1.0
> 风格：模块解耦 + 契约先行 + 并行开发（与阶段 4/5/6 详细计划保持一致的行文规范）

---

## 1. 阶段定位与目标

**一句话目标**：让系统从"每次重新认识用户"升级为能够**跨会话（跨 thread）长期理解用户**的成长智能体——用三类长期记忆（Semantic / Episodic / Procedural）沉淀"技能画像事实、学习经历、学习偏好"，再用 Summarization / PII / HITL 三个中间件处理"超长上下文压缩、敏感信息脱敏、必要节点人工确认"。

**为什么必须先做阶段 7**：阶段 3~6 已把"画像→缺口→计划→实践→评估→再规划"跑通，但所有记忆都**按 thread 走 Checkpointer** 或散在各业务表里，换一个会话 Agent 就"不认识用户"了。已有基座（见下）只解决了"单会话内上下文恢复"，没有"跨会话长期记忆"这一层。阶段 7 补两种记忆：

1. **长期事实记忆（Semantic）**：把对话/事件中提取出的用户长期事实（技术栈、目标、项目背景、关键偏好）以"namespace + key + 语义向量"持久化，供新会话 `recall`。
2. **经历记忆（Episodic）**：把每次「画像更新 / 缺口报告 / 计划生成 / 实践创建 / 评估完成 / 计划重规划」沉淀为可查询的 Episode，形成用户成长轨迹。
3. **程序性记忆（Procedural）**：把"怎么学"的偏好（学习风格 / 每周可用时长 / 长期目标）跨会话长期保留，让 Planner 每次都能读到一致的学习方式。

再叠加三个中间件，补齐产品级健壮性：**摘要压缩**（超长对话不丢上下文）、**PII 脱敏**（敏感信息不入长期记忆）、**HITL**（关键/破坏性操作暂停人工确认）。

**一个工程硬约束**（计划书明文要求）：memory 建表、建索引、embedding 索引等 setup **只在应用启动 / 迁移阶段执行**（对齐现有 `checkpointer.setup()`），绝不放在业务写入路径。

**本阶段核心目标拆解**

| # | 目标 | 验收可测性 |
| --- | --- | --- |
| G1 | Memory Namespaces | `semantic / episodic / procedural / summary` 四类命名空间落库、可按 user 隔离 |
| G2 | 语义记忆存取 | 事实可写入 + 向量/关键词可召回，供新会话 `recall` |
| G3 | 经历沉淀为 Episode | 阶段 3~6 的关键动作可写入带 ref 的 Episode 并可回查 |
| G4 | 程序性记忆 | 学习偏好长期保留，跨 thread 读取一致 |
| G5 | 跨 thread 长期记忆 | 新 thread 能经 `memory_context` 读到历史画像/偏好事实（改正当前"只记 session"） |
| G6 | 上下文摘要压缩 | 超过阈值消息轮数时生成并复用摘要，不丢关键上下文 |
| G7 | PII 脱敏 | 邮箱/电话/身份证等敏感内容写入前脱敏（可开关） |
| G8 | HITL 人工确认 | 守卫型操作可 pause→确认/否决，未确认不执行（可开关） |
| G9 | setup 仅启动/迁移执行 | 建表/索引在 `init_db.py`，业务路径零 DDL |

---

## 2. 范围边界

### 2.1 本阶段做什么（In Scope）

- 建表：`memories` / `memory_events` / `pending_actions`（幂等；程序性记忆复用阶段 3 既有 `user_preferences`）
- `Memory Manager`：`remember` / `recall` / `search` / `record_event` 的统一入口（按命名空间分派）
- Semantic Memory：事实写入（embedding + 可向量化 text）、跨会话召回、top-k
- Episodic Memory：事件 append-only、按 user + event_type 回查
- Procedural Memory：学习偏好（学习风格/时长/目标）长期读写（复用 `user_preferences`）
- `SummarizationMiddleware`：超长对话摘要（LLM 润色 + 模板兜底）
- `PIIMiddleware`：写入记忆前的敏感信息脱敏（正则为主，可开关）
- `HITLMiddleware`：守卫型操作 pause + 确认接口（决策落库）
- Or：`/api/v1/memory/*` 接口
- Orchestrator/chat 接入：invoke 前注入 `memory_context`（跨 thread 召回）
- 阶段 3~6 路由在成功后 best-effort 写入 Episode（失败不阻断）
- 契约文档 + 集成测试（TC-M1~M12）

### 2.2 本阶段明确不做（Out of Scope）

| 不做 | 原因 | 何时做 |
| --- | --- | --- |
| 完整知识图谱记忆（实体关系推理） | MVP 用"namespace + key + 向量"足够支撑需求 | 后续迭代 |
| 自动跑 LLM 摘要之外的复杂对话压缩（对话树剪枝） | 压缩用"生成摘要并优先注入"父方案 | 后续迭代 |
| PII 全量 LLM 语义识别 | 正则覆盖常见敏感格式即可，LLM 识别可选增强 | 后续迭代 |
| HITL 覆盖所有节点 | MVP 只挂 1 个代表性子场景 + 通用 seam，其余节点可套用 | 阶段 8 编排收口 |
| 直接把 Checkpointer 历史改写/裁剪 | 长上下文压缩靠"摘要沉淀 + 优先注入"，不破坏单会话恢复 | 后续迭代 |
| 前端记忆/压测/演示页 | 后端契约先行 | 阶段 8 |

> 边界原则（对齐计划书）：跨 thread 记忆必须**可复用已有基座**（阶段 2 embedding/pgvector、阶段 3 `user_preferences`、Checkpointer），不重复造轮子；三个中间件都带**开关 + 失败兜底**，永不因记忆写入失败而阻断主流程。

---

## 3. 技术选型与工程结构

### 3.1 技术栈（阶段 1~6 基础上，无新增依赖）

| 项 | 选型 | 说明 |
| --- | --- | --- |
| 存储 | PostgreSQL（复用 `psycopg` 直连 `persistence/db.py`） | 沿用既有风格 |
| 语义向量 | 复用阶段 2 `pgvector ` + `EmbeddingClient`（`vector(1024)` 对齐 `rag_chunks`） | 不自建 embedding 层 |
| 偏好存储 | 阶段 3 `user_preferences`（key-value JSONB） | 程序性记忆复用 |
| 摘要/PII | 规则为主 + 可选 LLM 润色/识别，复用阶段 1 `LLMClient` 风格 | 失败走模板/降级 |
| Middleware | 纯 Python 函数式编排（调用方显式调用，挂进 chat 流程） | 不新增框架 |
| setup | `scripts/init_db.py` 迁移阶段建表+索引 | 对齐 `checkpointer.setup()` |

> 关键复用：
> - **阶段 1**：`persistence/checkpointer.get_checkpointer`（setup 只在启动执行）、LangGraph `State`、`chat` 入口。
> - **阶段 2**：`EmbeddingClient`（语义记忆向量化）、`vectorstore`（pgvector 读写/相似度搜索写法）。
> - **阶段 3**：`user_preferences`（程序性记忆）、`store.load_profile`（AC1 画像召回）。
> - **阶段 5/6**：route 成功回调写入 Episode 的接线点。

### 3.2 工程结构（新增/修改点）

```
app/
├── config.py                    # 修改：新增 MEMORY_* / MEMORY_SUMMARY / MEMORY_PII / MEMORY_HITL 配置
├── api/routes/
│   ├── memory.py                # 新增：/api/v1/memory/* 接口
│   └── __init__.py              # 修改：注册 memory_bp
├── memory/                      # 新增：【Memory Manager + 三个 Middleware】不感知 HTTP
│   ├── __init__.py
│   ├── schemas.py               # 契约：Namespace / MemoryItem / MemorySearch / Episode / PendingAction
│   ├── store.py                 # 持久化：memories CRUD+向量检索 · memory_events 追加 · pending_actions
│   ├── semantic.py              # 事实记忆：remember（embedding+text）/ recall / search
│   ├── episodic.py              # 经历记忆：record_event / query_events
│   ├── procedural.py            # 偏好记忆：读/写 learning_style/available_hours/goal（包 user_preferences）
│   ├── service.py               # Memory Manager 总入口：按 source 分派 + ENSABLE 门控 + 失败兜底
│   └── middleware/
│       ├── __init__.py
│       ├── summary.py           # SummarizationMiddleware：摘要生成 + 存储 + 注入
│       ├── pii.py               # PIIMiddleware：敏感信息脱敏
│       └── hitl.py              # HITLMiddleware：park / confirm / list_pending
└── orchestrator/…               # 修改：graph. 前注入 memory_context（跨 thread 召回）到 State
scripts/
├── init_db.py                   # 修改：追加 memories / memory_events / pending_actions 建表+索引
└── seed_memory_setup.py         # 新增：应用启动/迁移期 memory setup 校验（幂等，业务路径不调用）
tests/
└── test_memory.py               # 新增：TC-M1~M12
```

分层依赖（延续单向规则）：

```
API 层 routes/memory.py
   │  只调
   ▼
能力层 app/memory/（service → semantic/episodic/procedural → store）｜ middleware/{summary,pii,hitl}
   │  只调
   ▼
复用层 app/rag/embeddings · app/rag/vectorstore · app/persistence/db · app/profileschemas · orchestrator/state
```

跨层只读 / 显式注入依赖：
- `orchestrator`（chat 流程）→ `app/memory/service`：invoke 前 `recall_for_user` 注入 `memory_context`。
- 阶段 3~6 路由 / 服务 → `app/memory/service`：成功后 best-effort `record_event`（`MEMORY_ENABLED=False` 或异常时静默跳过）。
- `middleware/pii.py` → 记忆写入路径统一过一遍脱敏。

**接线点（改动最小化）**
- `app/__init__.py`:注册 `memory_bp`。
- `app/api/routes/chat.py`:invoke 前调用 `memory_service.recall_for_user()` 并入 state。
- 阶段 3~6 的关键 API route：成功后追加一行 best-effort `record_event(...)`。
- `scripts/init_db.py`:追加三张表 + 索引。
- `docs/api_v1.md`:补 memory 接口。

---

## 4. 模块解耦与分工

### 4.1 各模块职责、输入、输出、不负责什么

| 模块 | 职责 | 主要输入 | 主要输出 | 不负责什么 |
| --- | --- | --- | --- | --- |
| API（`routes/memory.py`） | 收 HTTP、校验、调 Memory 层 | HTTP JSON | 统一 response | 不做记忆/脱敏细节 |
| `service.py` | 总入口：分派 namespace、开关门控、失败兜底 | user_id + source/type + payload | 记忆已写入 / 召回结果 | 不做具体 CRUD 与 embedding |
| `semantic.py` | 事实存取 + 向量召回 | text/payload/user_id | MemoryItem / SearchResult | 不生成（只）夸美文，不做事件日志 |
| `episodic.py` | 事件沉淀 + 回查 | event_type/ref/payload | 落库的 Episode | 给不了最终回答 |
| `procedural.py` | 偏好长期读写 | learning_style/hours/goal | 偏好快照 | 不做学习计划本身 |
| `store.py` | 三表 CRUD + 向量检索 | 结构化对象 | 落库/查询记录 | 不调 LLM |
| `middleware/summary.py` | 长对话摘要 | messages | 摘要文本（含模板兜底） | 不裁剪 Checkpointer 历史 |
| `middleware/pii.py` | 脱敏 | 原始文本 | 脱敏文本 + 命中类型 | 不做业务判断 |
| `middleware/hitl.py` | 守卫操作暂停/确认 | action/payload | PendingAction 决策 | 不执行业务副作用 |

**模块间数据流（单向、无环）**
```
[新会话 invoke]
      │ recall_for_user(config, user_id)  ── semantic(向量/key) + procedural(user_preferences)
      ▼  （inject memory_context → State）
orchestrator/chat ──────────────────────────────────────────────┐
      │                                                        │
[阶段3~6 成功]  record_event(episodic)   [写事实] remember(semantic)  [长对话]
      ▼                                                        ▼
  episodic.record ── store.memory_events          summary.middleware（阈值触发）
                                                       │
  PIIMiddleware：写入记忆前统一过脱敏（email/phone/id → [REDACTED:..]）
                                                       ▼
  HITLMiddleware：守卫操作 park(pending_actions) ── confirm(approve/reject) → 落决策
```

---

## 5. 接口契约（契约先行，冻结后并行开发）

### 5.1 Semantic / Procedural 记忆

**POST `/api/v1/memory/remember`**

```jsonc
{
  "user_id": "U10001",
  "namespace": "semantic",      // semantic | procedural | summary
  "key": "long_term_goal",      // (user_id, namespace, key) 唯一，重复即覆盖
  "text": "用户短期目标：转型 AI 应用开发（RAG/智能体）",
  "payload": { "importance": 0.9 }
}
```

**响应**

```jsonc
{
  "status": "ok",
  "mem_id": "MEM_xxx",
  "pii_redacted": true,     // 写入时是否发生脱敏
  "vectorized": true        // 是否生成语义向量（embedding 可用时）
}
```

**POST `/api/v1/memory/search`**（语义召回）

```jsonc
{ "user_id": "U10001", "namespace": "semantic", "query": "用户目标", "top_k": 5 }
```

响应 `MemorySearchResult[]`：`[{ mem_id, key, text, payload, score }]`。`namespace="episodic"` 时退化为按 key/类型匹配。

**GET `/api/v1/memory?user_id=U10001&namespace=semantic&limit=50`**（列出）；**`DELETE /api/v1/memory/<mem_id>`**。

### 5.2 Episodic 记忆

**POST `/api/v1/memory/events`**

```jsonc
{
  "user_id": "U10001",
  "event_type": "evaluation_done",     // profile_updated | gap_reported | plan_generated | practice_created | evaluation_done | plan_replanned | conversation_summary
  "ref_ids": { "evaluation_id": "EVL_xxx", "plan_id": "PLAN_xxx" },
  "summary": "完成 rag_retriever 代码评估，overall=76",
  "payload": { "overall_score": 76 }
}
```

响应：`{"status":"ok","event_id":"EVT_xxx"}`。

**GET `/api/v1/memory/events?user_id=U10001&event_type=evaluation_done&limit=20`**（回查成长轨迹）。

### 5.3 摘要压缩

**POST `/api/v1/memory/summarize`**（长对话摘要，供 chat 接入）

```jsonc
{ "user_id": "U10001", "thread_id": "T20260826", "messages": [...] }
```

响应：`{"summary":"…","stored":true,"is_llm_enhanced":false}`。写 `namespace="summary"`/`key="thread:{thread_id}"` 并存一条 `conversation_summary` Episode。

### 5.4 PII / HITL

**PII（内联过滤器）**：不单独接口；在 `remember`/`events` 写入路径自动生效，响应透出 `pii_redacted`。

**POST `/api/v1/memory/pending`（HITL 创建）** —— 供守卫型操作暂停

**GET `/api/v1/memory/pending?user_id=U10001&status=pending`** —— 待确认列表

```jsonc
{ "id": "PA_xxx", "action_type": "plan_reset", "payload": {}, "summary": "重置学习计划将丢弃当前进度", "status": "pending", "requested_at": "…" }
```

**POST `/api/v1/memory/pending/<pa_id>/confirm`**

```jsonc
{ "user_id": "U10001", "decision": "approve" }   // approve | reject
```

响应：`{"status":"approved","decided_at":"…"}`。决策落库；已被决/过期返回 422 防重复处理。

### 5.5 错误码（合并）

| 场景 | HTTP | code |
| --- | --- | --- |
| 非 JSON body | 400 | 40001 |
| 参数非法/命名空间非法/决策已决 | 422 | 42200 |
| memory 记录不存在（查询/删除/确认） | 404 | 40470 |
| 记忆写入失败（走兜底，不阻断主流程） | 500 | 50070 |
| DB 未配置 | 503 | 70400（沿用未配置语义） |

---

## 6. 数据模型（幂等建表，`scripts/init_db.py`）

```sql
-- 语义/偏好/摘要（命名空间化）
CREATE TABLE IF NOT EXISTS memories (
  id         VARCHAR(64) PRIMARY KEY,
  user_id    VARCHAR(64) NOT NULL,
  namespace  VARCHAR(24) NOT NULL,          -- semantic | procedural | summary
  key        VARCHAR(96) NOT NULL,
  text       TEXT,
  payload    JSONB,
  embedding  vector(1024),                  -- 对齐阶段2 rag_chunks 维度；embedding 关闭时可为 NULL
  importance REAL DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (user_id, namespace, key)
);
CREATE INDEX IF NOT EXISTS idx_memories_user_namespace ON memories(user_id, namespace);
-- HNSW 仅建在非空向量上（避免空向量索引膨胀）
CREATE INDEX IF NOT EXISTS idx_memories_embedding
  ON memories USING hnsw (embedding vector_cosine_ops)
  WHERE embedding IS NOT NULL;

-- 经历（append-only，成长轨迹）
CREATE TABLE IF NOT EXISTS memory_events (
  id         VARCHAR(64) PRIMARY KEY,
  user_id    VARCHAR(64) NOT NULL,
  event_type VARCHAR(32) NOT NULL,
  ref_ids    JSONB,
  summary    TEXT,
  payload    JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_memory_events_user_type ON memory_events(user_id, event_type);

-- HITL 待确认动作
CREATE TABLE IF NOT EXISTS pending_actions (
  id           VARCHAR(64) PRIMARY KEY,
  user_id      VARCHAR(64) NOT NULL,
  action_type  VARCHAR(32) NOT NULL,
  payload      JSONB,
  status       VARCHAR(16) NOT NULL DEFAULT 'pending',  -- pending|approved|rejected|expired
  summary      TEXT,
  requested_at TIMESTAMPTZ DEFAULT now(),
  decided_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_pending_actions_user_status ON pending_actions(user_id, status);
```

> 说明：程序性记忆复用阶段 3 `user_preferences`（`user_id,key,value` JSONB），不另建重复 KV；`memories.namespace='procedural'` 仅存需要语义检索的偏好事实（可选）。**建表与索引均只在 `init_db.py` 执行**，与 `checkpointer.setup()` 同口径。

---

## 7. 配置（`config.py` + `.env.example`）

| 配置 | 默认 | 说明 |
| --- | --- | --- |
| `MEMORY_ENABLED` | true | 总开关；false 时所有记忆写入/召回短路为空 |
| `MEMORY_EMBED_ENABLED` | true | 事实记忆是否向量化（关闭则只能 key/全文匹配） |
| `MEMORY_TOP_K` | 5 | 召回默认 top-k |
| `MEMORY_SUMMARY_THRESHOLD_MESSAGES` | 20 | 触发摘要压缩的消息轮数阈值 |
| `MEMORY_SUMMARY_LLM_ENABLED` | true | 摘要用 LLM 润色（false/失败走模板） |
| `MEMORY_PII_ENABLED` | true | 写入前脱敏（email/phone/id 正则） |
| `MEMORY_HITL_ENABLED` | true | 守卫操作暂停开关 |
| `MEMORY_HITL_EXPIRES_SECONDS` | 86400 | 待确认动作超时（expired） |

> 一致性：`memories.embedding` 维度 = `EMBEDDING_DIM`（默认 1024）；`MEMORY_EMBED_ENABLED=False` 时 `EmbeddingClient` 不可用也不报错，写 NULL 向量、走 key/文本匹配兜底。

---

## 8. 开发任务拆解（按依赖排序，可并行分支）

| # | 任务 | 产出 | 依赖 |
| --- | --- | --- | --- |
| 1 | `init_db.py` 追加三张表 + 索引 + `seed_memory_setup.py` 幂等校验 | 表结构 | 无 |
| 2 | 冻结契约 `app/memory/schemas.py` | Pydantic 契约 | 1 |
| 3 | `store.py`：memories CRUD+向量检索（对齐 `vectorstore` 写法）+ events + pending | 持久化 | 2 |
| 4 | `semantic.py`：remember/recall/search（复用 `EmbeddingClient`） | 语义记忆 | 2,3 |
| 5 | `procedural.py`：包 `user_preferences` 做偏好读写 | 偏好记忆 | 2 |
| 6 | `episodic.py`：record_event / query_events | 经历记忆 | 2,3 |
| 7 | `middleware/pii.py`：脱敏过滤器 | PII | 2 |
| 8 | `middleware/summary.py`：摘要生成+存储+注入 | 摘要压缩 | 2,3,7 |
| 9 | `middleware/hitl.py`：park / confirm / list_pending | HITL | 2,3 |
| 10 | `service.py`：Memory Manager 总入口（分派 + 门控 + 兜底） | 统一编排 | 4~9 |
| 11 | 接线：`routes/memory.py` + 注册 + chat 注入 `memory_context` + 阶段3~6 `record_event` | 路由/接入 | 10 |
| 12 | 测试 `test_memory.py`（TC-M1~M12） | 测试 | 1~11 |
| 13 | 文档 `docs/api_v1.md` + `.env.example` 补配置 | 文档 | 11 |

> 并行建议：任务 3/5/6（存储与两类记忆）与 7/8/9（三个中间件）可并行；接入与测试随后。

---

## 9. 测试计划

**纯规则用例（无需 DB）**
- TC-M1 PII 脱敏：文本含 email + 手机号 → 均替换为 `[REDACTED:email]` / `[REDACTED:phone]`，原文不落库。
- TC-M2 摘要模板兜底：`MEMORY_SUMMARY_LLM_ENABLED=false` → 仍产出非空摘要。
- TC-M3 HITL 状态机：park→approve、park→reject、重复 confirm 抛 422，超时置 expired。

**集成用例（依赖真实 DB + 种子）**
- TC-M4 语义写入+召回：`remember(semantic)` 后 `search` 能召回该事实（embedding 可用时按相似度）。
- TC-M5 键覆盖幂等：同 `(user_id,namespace,key)` 重复 remember → 覆盖不重复插入。
- TC-M6 跨 thread 召回：新 thread 经 `recall_for_user` 能读到历史语义事实 + 程序性偏好（AC1）。
- TC-M7 经历沉淀：阶段 6 评估成功后自动落 `evaluation_done` Episode，含 `ref_ids`。
- TC-M8 程序性偏好：写 `learning_style` 后新 thread 读取一致（AC3）。
- TC-M9 摘要压缩：写入 summary 且 `recall_for_user` 注入 `memory_context.message_summary`（AC4）。
- TC-M10 HITL 集成：守卫操作 pause 后未确认前不执行；approve 后决策落库（AC5）。
- TC-M11 关闭降级：`MEMORY_ENABLED=false` → 阶段3~6 正常跑，`record_event` 静默跳过（不阻断主流程）。
- TC-M12 路由：非 JSON → 400；非法 namespace / 决策已决 → 422；memory 不存在 → 404。

---

## 10. 验收标准（对照计划书阶段 7）

| AC | 验收项 | 对应用例 |
| --- | --- | --- |
| AC1 | 新会话可读取历史能力画像 | TC-M4/M6 跨 thread 召回画像/偏好 |
| AC2 | 学习经历可形成 Episode | TC-M7 阶段动作落 `memory_events` |
| AC3 | 用户学习偏好可长期保留 | TC-M8 程序性偏好跨 thread 一致 |
| AC4 | 超长上下文可以压缩 | TC-M9 摘要生成 + 注入 |
| AC5 | 关键操作可暂停并人工确认 | TC-M3/M10 HITL pause→confirm |
| AC6 | Memory Namespaces 可用且隔离 | TC-M4/M5 命名空间化 + 键幂等 |
| AC7 | setup 仅在启动/迁移执行 + 兜底可测 | TC-M11/M12 关闭降级 + 路由 |
| AC8 | PII 敏感信息不加长期记忆 | TC-M1 写入路径脱敏 |

---

## 11. 风险与兜底

| 风险 | 影响 | 缓解/兜底 |
| --- | --- | --- |
| embedding 不可用（无 key/接口） | 语义召回退化为关键词 | `MEMORY_EMBED_ENABLED=False` 写 NULL 向量，走 key/文本匹配 |
| 摘要 LLM 失败 | 无摘要 | 模板兜底，仍落 summary |
| 记忆写入拖慢主流程 | 响应延迟/偶发失败 | 全部 best-effort：异常仅告警不阻断；`MEMORY_ENABLED` 总开关 |
| PII 漏判 | 敏感信息入库 | 正则覆盖常见格式；`MEMORY_PII_ENABLED` 可强制开启；支持后续 LLM 识别增强 |
| 误伤性操作（计划重置等） | 用户进度丢失 | HITL pause 默认开启，超时 expired，决策落库可审计 |
| Checkpointer 历史无法裁剪 | 单会话仍膨胀 | 用"摘要沉淀 + 优先注入"缓解；不破坏既有单会话恢复 |
| 程序性记忆与阶段3 preference 重复写 | 数据不一致 | 以 `user_preferences` 为唯一权威，`procedural.py` 只作包装 |

---

## 12. 前置依赖与交付清单

- 前置依赖：阶段 2（`EmbeddingClient`/pgvector）、阶段 1（`persistence/checkpointer`/`chat`）、阶段 3（`user_preferences`）、阶段 5/6（Episode 接线点）。
- 交付清单：
  - `scripts/init_db.py`（三张表 + 索引）+ `seed_memory_setup.py` + `docs/api_v1.md`（memory 接口 + 错误码）
  - `app/memory/`（schemas/store/semantic/episodic/procedural/service + middleware/{summary,pii,hitl}）
  - `routes/memory.py`、`chat.py` 注入 `memory_context`、阶段 3~6 路由 best-effort `record_event`
  - `MEMORY_*` 配置 + `.env.example`
  - `tests/test_memory.py`（TC-M1~M12）