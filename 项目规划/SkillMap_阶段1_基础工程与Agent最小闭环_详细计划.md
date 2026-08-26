# SkillMap 阶段 1 详细实施计划 — 基础工程与 Agent 最小闭环

> 对应：《SkillMap_个人技术栈成长智能体_项目计划书》阶段 1  
> 版本：V1.0  
> 风格：模块解耦 + 分工明确，先定契约、后并行开发

---

## 1. 阶段定位与目标

**一句话目标**：跑通「Flask 收到请求 → LangGraph 编排 → 单 Agent 应答 → Checkpointer 持久化」的最小闭环，让团队拥有统一运行入口和可恢复的会话/任务状态。

**为什么要先做阶段 1**：后续 5 个业务 Agent（Profile/Gap/Planner/Practice/Evaluation）都依赖「统一 API 入口 + 可恢复会话 + 标准 JSON 契约 + 统一错误/日志」。阶段 1 先把这条"管道"打通并锁定契约，后续阶段只需往管道里"插入新 Agent"，不需要再改管道本身。

**本阶段核心目标拆解**

| # | 目标 | 验收可测性 |
| --- | --- | --- |
| G1 | Flask 服务可启动 | `GET /health` 返回 up |
| G2 | Agent 最小闭环可运行 | `POST /api/v1/chat` 返回标准 JSON |
| G3 | 同一 thread_id 上下文可恢复 | 第二次提问能"记得"第一次的内容 |
| G4 | 服务重启后会话仍可恢复 | 重启进程后再问，仍能恢复上下文 |
| G5 | 契约稳定 | 统一 response/error schema 有测试守护 |
| G6 | 链路可观测 | 每条请求有 trace_id，日志含 user/thread/agent |

---

## 2. 范围边界

### 2.1 本阶段做什么（In Scope）

- 工程骨架：Git 仓库、分支规范、虚拟环境、依赖锁定
- 配置管理：环境变量加载、LLM Key / 模型、PostgreSQL 连接
- `GET /health` 健康检查（含 DB、LLM 连通性探测）
- `POST /api/v1/chat` 对话入口（单 Agent 最小闭环）
- LangGraph 图骨架 + AgentState + 意图路由占位
- LangGraph Checkpointer（PostgresSaver）持久化会话
- 统一 response / error schema
- 中间件：trace_id 注入、日志、异常兜底
- 第一版 API 文档 + 第一个集成测试

### 2.2 本阶段明确不做（Out of Scope）

| 不做 | 原因 | 何时做 |
| --- | --- | --- |
| 5 个业务 Agent 的真实逻辑 | 阶段 1 只验证编排链路，业务逻辑阶段 3~6 做 | 阶段 3~6 |
| RAG 入库/检索 | 依赖阶段 1 的 DB 与基础工程 | 阶段 2 |
| 用户技术画像/技能库 | 同上 | 阶段 3 |
| 前端页面 | 后端契约先行 | 阶段 8 / Phase A 页面框架 |
| 认证鉴权完整体系 | 阶段 1 用开发态默认用户，接口预留 Header 字段 | 阶段 8 或独立任务 |
| 多 Agent 并行编排 | 先单 Agent 验证 | 阶段 3+ |
| 流式 SSE 输出 | 阶段 1 先做非流式，SSE 预留事件类型 | 阶段 8 或阶段 2 起按需开启 |

> 边界原则（对齐计划书 1.1）：**MVP 先做单 Agent 能力，再组合为多 Agent 编排**；本阶段绝不为"以后可能用到"提前写业务逻辑。

---

## 3. 技术选型与工程结构

### 3.1 技术栈

| 层 | 选型 | 说明 |
| --- | --- | --- |
| Web 框架 | Flask | 轻量，团队熟悉 |
| 编排 | LangGraph | 图编排、State、Checkpointer |
| 持久化 | PostgreSQL + LangGraph PostgresSaver | 会话 Checkpoint 落库 |
| 数据校验 | Pydantic v2 | 请求/响应/Agent 输出统一 schema |
| LLM 调用 | LangChain 模型接口 | 通过配置切换模型，阶段 1 用最简模型完成闭环 |
| 依赖管理 | poetry 或 pip + requirements 锁定 | 统一环境 |
| 测试 | pytest + Flask test client | 集成测试 |

### 3.2 建议目录结构（模块即边界）

```
SkillMap/
├── .env.example              # 配置模板（不含真实密钥）
├── pyproject.toml            # 依赖与元数据
├── app/                      # 主应用
│   ├── config.py             # 配置管理（Config 类 + 环境变量）
│   ├── api/                  # 【接入层】只做 HTTP 入/出，不碰业务
│   │   ├── errors.py         # 统一异常与错误码映射
│   │   ├── schemas.py        # 请求/响应 Pydantic 契约
│   │   └── routes/
│   │       ├── health.py     # GET /health
│   │       └── chat.py       # POST /api/v1/chat
│   ├── orchestrator/         # 【编排层】LangGraph 图与状态
│   │   ├── state.py          # SkillMapState（TypedDict）
│   │   └── graph.py          # 构建编译图、绑定 checkpointer
│   ├── agents/               # 【Agent 层】单 Agent 最小实现
│   │   ├── base.py           # Agent 基类：固定输入/输出契约
│   │   └── orchestrator_agent.py  # 阶段 1：识别意图 → 回复
│   ├── persistence/          # 【持久化层】
│   │   ├── db.py             # engine/session 工厂
│   │   └── checkpointer.py   # PostgresSaver 初始化（仅启动/迁移执行）
│   ├── middleware/           # 【横切层】
│   │   ├── trace.py          # trace_id 生成与传递
│   │   └── logging_middleware.py
│   └── utils/
├── scripts/
│   └── init_db.py            # 建表/迁移脚本（应用启动前执行一次）
├── tests/
│   ├── conftest.py
│   └── test_chat_integration.py
└── docs/
    └── api_v1.md             # 第一版接口文档
```

---

## 4. 模块解耦与分工（本计划核心）

### 4.1 分层依赖规则（单向依赖）

```
API 层（Flask 路由）
   │  只能调用
   ▼
编排层（LangGraph graph / state）
   │  只能调用
   ▼
Agent 层（单 Agent 最小实现）
   │  只能调用
   ▼
持久化层 / 模型层（DB、Checkpointer）
```

**强制约定**：
- 上层可调用下层；下层**不得**反向 import 上层。
- API 层**不感知** Agent 内部逻辑；Agent 层**不感知** HTTP 细节。
- 所有跨层数据必须走**契约对象**（Pydantic / TypedDict），禁止传递裸 dict 之外的自由结构（Agent 内部 State 除外）。

### 4.2 各模块职责、输入、输出、不负责什么

| 模块 | 职责 | 主要输入 | 主要输出 | 不负责什么 |
| --- | --- | --- | --- | --- |
| API 层（routes） | 接收 HTTP、参数校验、调用编排层、包装统一响应 | HTTP JSON | 统一 response | 不做业务判断、不调 LLM |
| 编排层（graph） | 构建图、管理 State、绑定 Checkpointer、路由意图 | UserRequest + thread_id | WorkflowResult | 不写 HTTP、不做深度业务分析 |
| Agent 层 | 阶段 1 识别意图并给出结构化回复 | 结构化 State + 上下文 | 结构化 JSON（Pydantic 校验） | 不做持久化、不处理 HTTP |
| 持久化层 | 会话 Checkpoint 读写、连接管理 | config | Checkpointer / session | 不参与业务逻辑 |
| 中间件 | trace 注入、日志、异常兜底 | 请求/事件 | 日志记录 + trace_id | 不改业务数据 |

### 4.3 团队分工（阶段 1 涉及 3 个角色）

| 角色 | 负责模块 | 主要交付物 | 依赖模块 | 是否可并行 |
| --- | --- | --- | --- | --- |
| 平台/后端 | config、API 层、errors、persistence、init_db、测试基线 | 工程骨架、统一 schema、DB 迁移、集成测试 | 无（可先做） | 是（与 Agent 并行） |
| Agent/编排 | state、graph、agents、router | 图骨架、AgentState、单 Agent 最小闭环 | 依赖后端先定「编排层入/出契约」 | 契约后并行 |
| 测试 | 集成测试、验收用例 | `test_chat_integration.py`、验收核对清单 | 两端都交付后联调 | 可先写测试框架与契约断言 |

**并行开发的关键**：后端与 Agent 的**第一件事**是共同敲定两份契约——「编排层入/出契约」（见第 5、6 节）与「统一响应 schema」。契约锁定后，双方可各自并行开发，互不阻塞；测试团队基于契约先写断言。

---

## 5. 输入格式要求（接口契约）

### 5.1 HTTP 请求入口

```
POST /api/v1/chat
Content-Type: application/json
X-Trace-ID: 可选（服务端自动生成）
Idempotency-Key: 可选（同一 key 窗口内不重复执行）
```

### 5.2 UserRequest 请求体（顶层契约）

```json
{
  "user_id": "U10001",
  "thread_id": "T20260826",
  "intent_hint": null,
  "message": "我想转向 AI 应用开发",
  "attachments": []
}
```

### 5.3 字段与校验规则（Pydantic 强制）

| 字段 | 类型 | 必填 | 约束 | 说明 |
| --- | --- | --- | --- | --- |
| user_id | string | 是 | `^[A-Za-z0-9_-]{1,64}$` | 用户 ID |
| thread_id | string | 是 | `^[A-Za-z0-9_-]{1,64}$` | 会话 ID；同 thread_id = 同上下文 |
| intent_hint | string? | 否 | 枚举：`profile_update`/`gap_analysis`/`plan_generation`/`practice`/`evaluation`/`question`/`chat`/null | 前端可提示意图；null 则交由编排层识别 |
| message | string | 是 | 1~8000 字符，去首尾空白 | 用户消息 |
| attachments | array | 否 | 每项 `{type: string, file_id?: string, url?: string, mime_type?: string}`，最多 5 个 | 阶段 1 允许为空数组；文件能力后续启用 |

> 校验失败 → HTTP 422 + `{"code":42200,...}`。

### 5.4 编排层入参（API 层 → 编排层）

API 层将 HTTP 请求转换为编排层契约对象，**不做业务处理**：

```
Input:  (user_id, thread_id, message, intent_hint, attachments)  →  OrchestratorInput
```

编排层入参即上述 UserRequest 的规范化对象（字段一致，去掉 HTTP 细节）。

### 5.5 配置输入（启动期）

| 环境变量 | 必填 | 说明 | 示例 |
| --- | --- | --- | --- |
| `DATABASE_URL` | 是 | PostgreSQL 连接串 | `postgresql+psycopg://user:pass@localhost:5432/skillmap` |
| `LLM_API_KEY` | 是 | LLM 密钥 | 通过 `.env` 注入，不入库 |
| `LLM_MODEL` | 否 | 模型名，默认提供 | `gpt-4o-mini` |
| `LOG_LEVEL` | 否 | 日志级别 | `INFO` |
| `ENV` | 否 | 环境标识 | `dev`/`prod` |

---

## 6. 输出格式要求（接口契约）

### 6.1 统一响应格式（所有接口）

**成功**（HTTP 200）

```json
{
  "code": 0,
  "message": "ok",
  "data": { "...": "..." }
}
```

**业务/系统错误**（HTTP 4xx/5xx）

```json
{
  "code": 42200,
  "message": "message 不能为空",
  "data": null,
  "trace_id": "trc_8f3a2b"
}
```

### 6.2 /health 输出

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "status": "up",
    "version": "v1.0.0",
    "db": "ok",
    "llm": "ok"
  }
}
```

> `db`/`llm` 任一不可用时不返回 500，而是 `status:"degraded"` + 对应字段 `"down"`，便于部署探针区分。

### 6.3 /api/v1/chat 输出（Agent 最小闭环）

**成功**（HTTP 200）

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "route": "chat",
    "steps": ["intent_recognize", "reply"],
    "reason": "未能明确归类为用户画像/缺口/规划等业务意图，走通用问答",
    "reply": "收到，我已经记住你的目标：转向 AI 应用开发。可以继续补充你的技术栈，我会帮你梳理。",
    "workflow_status": "done",
    "artifacts": {},
    "evidence": []
  }
}
```

**字段约定**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| route | string | 是 | 本次路由结果（阶段 1 仅 `chat`，预留其余枚举） |
| steps | string[] | 是 | 实际执行的步骤序列 |
| reason | string | 是 | 路由判断理由（可追溯） |
| reply | string | 是 | 给用户的回复文本 |
| workflow_status | string | 是 | `running`/`done`/`error` |
| artifacts | object | 是 | 业务产物引用（如 `{gap_report_id:"GAP_001"}`），阶段 1 为空 |
| evidence | array | 是 | RAG 证据，阶段 1 为空数组，结构见契约 |

### 6.4 Agent 输出格式（编排层内部）

Agent 必须返回**结构化输出**，禁止返回自由文本让上层解析。阶段 1 的 Agent 输出契约：

```json
{
  "intent": "chat",
  "reply": "...",
  "confidence": 0.9,
  "workflow_status": "done",
  "artifacts": {}
}
```

> 实现要求（对齐计划书 11 节）：Agent 内部用 **Pydantic/Structured Output** 定义 `AgentOutput`，LLM 输出经 schema 校验后进入 State；校验失败走兜底（返回通用回复），不抛裸异常到 HTTP 层。

### 6.5 错误码（阶段 1 启用子集）

| code | HTTP | 说明 |
| --- | --- | --- |
| 0 | 200 | 成功 |
| 40000 | 400 | 请求参数缺失或非法 |
| 40001 | 400 | JSON 格式错误 |
| 40400 | 404 | 资源不存在 |
| 42200 | 422 | 业务校验失败 |
| 50000 | 500 | 服务端未知错误 |
| 50001 | 500 | LLM 调用失败 |
| 50005 | 500 | Checkpointer/DB 初始化失败 |

> 完整错误码表后续阶段扩展；阶段 1 只实现上表子集，但**错误响应结构**（含 trace_id）从第一天就固定。

### 6.6 日志格式要求

每条请求输出一条结构化日志（字段固定）：

```
time, level, trace_id, user_id, thread_id, route, agent_name,
start/end, latency_ms, status, tool_calls[]
```

- 不记录明文密钥、完整 Token、敏感个人信息。
- 异常日志必须带 trace_id 与堆栈，便于按 trace 串联全链路。

---

## 7. 数据契约与存储（阶段 1 最小集）

### 7.1 SkillMapState（编排层运行时状态）

```python
class SkillMapState(TypedDict, total=False):
    messages: list        # 对话上下文（LangGraph 消息）
    user_id: str
    thread_id: str
    intent: str
    target_role: str | None
    skill_profile: dict   # 阶段 1 空占位
    skill_gap: dict       # 阶段 1 空占位
    learning_plan: dict   # 阶段 1 空占位
    practice_plan: dict   # 阶段 1 空占位
    evaluation_report: dict  # 阶段 1 空占位
    retrieved_evidence: list
    memory_context: dict
    current_agent: str
    workflow_status: str
    error: dict | None
```

> 状态字段**一次性定义完整**（对齐计划书第 6 节），阶段 1 只使用其中子集，避免后续反复改 State 结构。

### 7.2 持久化范围

| 数据 | 存储方式 | 生命周期 |
| --- | --- | --- |
| 会话 Checkpoint | LangGraph PostgresSaver（自动建表） | 长期，随 thread 删除 |
| 用户基础信息 | `users` 表（最小字段） | 长期 |
| 会话元信息 | `threads` 表（thread_id、user_id、title、created_at、last_message_at） | 长期 |

**users / threads 最小表结构（V1）**

```sql
CREATE TABLE users (
  id          VARCHAR(64) PRIMARY KEY,
  name        VARCHAR(128),
  target_role VARCHAR(64),
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE threads (
  thread_id       VARCHAR(64) PRIMARY KEY,
  user_id         VARCHAR(64) NOT NULL,
  title           VARCHAR(255),
  created_at      TIMESTAMPTZ DEFAULT now(),
  last_message_at TIMESTAMPTZ DEFAULT now()
);
```

### 7.3 初始化时机（关键约定）

- `init_db.py`（建表）与 Checkpointer 初始化只在**应用启动/迁移阶段**执行一次。
- **禁止**在每次业务写入路径中重复建表或执行 setup（对齐计划书 11 节）。

---

## 8. 功能清单（本阶段能实现什么）

| # | 功能 | 说明 | 关联目标 |
| --- | --- | --- | --- |
| F1 | 服务启动与健康检查 | `/health` 探测 DB / LLM 连通性 | G1 |
| F2 | 对话最小闭环 | `/api/v1/chat` 走完整编排链路并返回标准 JSON | G2 |
| F3 | 意图识别占位 | 编排层识别 `intent_hint` 或兜底为 `chat`；业务意图后续阶段启用 | G2 |
| F4 | 会话上下文恢复 | 同一 `thread_id` 第二次提问可引用前文 | G3 |
| F5 | 跨重启持久化 | Checkpointer 落 PostgreSQL，重启后上下文可恢复 | G4 |
| F6 | 统一响应/错误 | 所有接口统一 `code/message/data` 结构 | G5 |
| F7 | 链路可观测 | trace_id 全链路、结构化日志 | G6 |
| F8 | 配置管理 | 环境变量加载、`.env.example`、密钥不入库 | G5 |
| F9 | 集成测试 | `test_chat_integration.py` 覆盖 F2~F6 | G5 |
| F10 | 第一版 API 文档 | `docs/api_v1.md`（可同步到 OpenAPI） | G5 |

---

## 9. 验收标准（做到什么程度）

### 9.1 验收条件（全部满足即完成本阶段）

| 编号 | 验收项 | 验证方式 |
| --- | --- | --- |
| AC1 | Flask 能启动并提供 `/api/chat` | 启动后 `GET /health` 返回 `status:"up"`；`POST /api/v1/chat` 返回 200 |
| AC2 | 同一 thread_id 可恢复上下文 | 会话 A 中第 2 次提问能引用第 1 次内容（测试断言回复包含关联信息） |
| AC3 | 服务重启后会话仍可恢复 | 重启进程后，对同一 thread_id 提问，上下文仍可恢复 |
| AC4 | Agent 返回标准 JSON | 响应符合 `code/message/data` 结构；`data` 含 `route/steps/reply/workflow_status` |
| AC5 | 错误处理统一 | 非法入参返回 422 且带 `trace_id`；LLM 失败返回 50001 且不泄露内部细节 |
| AC6 | 契约有测试守护 | 集成测试覆盖成功、恢复、错误三路径，`pytest` 全绿 |
| AC7 | 日志可串联 | 通过 trace_id 能在日志中串起一次请求全链路 |

### 9.2 集成测试用例清单（首个测试集）

| 用例 | 输入 | 预期 |
| --- | --- | --- |
| TC1 健康检查 | `GET /health` | 200，`data.status=="up"` |
| TC2 正常对话 | 合法 UserRequest | 200，`data.workflow_status=="done"`，含 `reply` |
| TC3 上下文恢复 | 同一 thread_id 连续 2 次提问 | 第 2 次回复可关联第 1 次内容 |
| TC4 跨重启恢复 | 重启后对同一 thread_id 提问 | 仍可恢复上下文 |
| TC5 非法入参 | `message` 缺失/超长/`user_id` 非法 | 422 + `code==42200` + `trace_id` |
| TC6 坏 JSON | 非 JSON body | 400 + `code==40001` |
| TC7 不同 thread 隔离 | 两个 thread 互不影响 | 各自上下文独立 |
| TC8 LLM 异常兜底 | mock LLM 抛错 | 500 + `code==50001`，无敏感信息泄漏 |

---

## 10. 任务拆解与并行分工

### 10.1 前置（契约对齐，双方共同完成）

- [ ] 敲定「编排层入/出契约」（第 5、6 节 schema）
- [ ] 敲定「统一响应/错误 schema」与错误码子集
- [ ] 敲定 `SkillMapState` 字段（一次性定义完整）
- [ ] 敲定日志字段规范

> 该步骤是唯一强阻塞项，完成后后端与 Agent 即可并行。

### 10.2 后端/平台任务（与 Agent 并行）

1. 初始化 Git 仓库 + 分支规范（`main`/`dev`/`feature/*`）
2. 建立虚拟环境 + 依赖锁定 + `pyproject.toml`
3. 配置管理：`.env.example`、Config 类、环境变量校验
4. `scripts/init_db.py`：建表/迁移脚本
5. API 层：`GET /health`、`POST /api/v1/chat` 路由骨架
6. `errors.py`：统一异常 → 错误码映射、trace_id 注入
7. `persistence/`：DB engine、PostgresSaver 初始化（启动期）
8. 中间件：日志、trace
9. 第一版接口文档 `docs/api_v1.md`
10. 测试基线：`conftest.py`、契约断言工具

### 10.3 Agent/编排任务（契约后并行）

1. `state.py`：定义 `SkillMapState`
2. `agents/base.py`：Agent 基类（固定输入/输出契约）
3. `orchestrator_agent.py`：意图识别占位 + 结构化回复（Pydantic 校验 + 兜底）
4. `graph.py`：构建编译图，绑定 Checkpointer，暴露 `invoke(input, config={thread_id,...})`
5. 与后端联调：确认编排层入/出契约一致

### 10.4 测试任务

1. 基于契约写断言（不依赖具体实现）
2. 实现 TC1~TC8
3. 输出验收核对清单（对应 AC1~AC7）

### 10.5 里程碑（阶段 1 内）

| 里程碑 | 内容 | 完成标志 |
| --- | --- | --- |
| M1 | 契约冻结 | 第 10.1 全部项签署 |
| M2 | 骨架可跑 | `/health` 通、目录/配置/DB 就绪 |
| M3 | 最小闭环 | `/api/v1/chat` 返回标准 JSON |
| M4 | 持久化验证 | AC2~AC3 通过（重启恢复） |
| M5 | 测试与文档 | TC1~TC8 全绿 + API 文档发布 |

---

## 11. 风险与注意事项

| 风险 | 表现 | 应对 |
| --- | --- | --- |
| LLM 输出不稳定 | 回复非结构化 | Agent 输出强制 Pydantic 校验 + 兜底回复，不向 HTTP 抛裸错 |
| Checkpointer 初始化误用 | 每次写入重复 setup | 初始化仅在启动/迁移阶段；代码评审强制约束 |
| 密钥泄露 | 配置入库/入日志 | `.env` 注入、日志脱敏、`.gitignore` 排除 `.env` |
| 契约随意改动 | 前后端/测试返工 | 阶段内契约改动需评审并同步更新测试断言 |
| 会话无限膨胀 | 上下文超限 | 阶段 1 记录消息条数上限（如 50 条），超限策略后续阶段（Summarization）引入 |
| 依赖版本漂移 | 环境不一致 | 锁定依赖版本；团队统一 Python 版本 |

---

## 12. 交付物清单（阶段 1）

- [ ] 可运行 Flask 服务（`/health`、`/api/v1/chat`）
- [ ] LangGraph 图骨架 + `SkillMapState` + 单 Agent 最小闭环
- [ ] PostgresSaver 会话持久化（跨重启可恢复）
- [ ] 统一 response/error schema + 错误码子集
- [ ] trace_id 日志链路 + 脱敏
- [ ] `scripts/init_db.py`（启动期一次性执行）
- [ ] `docs/api_v1.md` 第一版接口文档
- [ ] `tests/test_chat_integration.py`（TC1~TC8）全绿
- [ ] 验收核对清单（AC1~AC7）
