# SkillMap 阶段 8 详细实施计划 — 前端整合与比赛 Demo

> 对应：《SkillMap_个人技术栈成长智能体_项目计划书》阶段 8"前端整合与比赛 Demo"
> 版本：V1.0
> 风格：复用阶段 4/5/6/7 的"模块解耦 + 契约先行 + 并行开发"行文规范

---

## 1. 阶段定位与目标

**一句话目标**：把阶段 1~7 已跑通的后端能力（画像→缺口→计划→实践→评估→再规划→长期记忆）**整合为一个可操作的产品 Demo**，形成 **3~5 分钟可重复演示链路**：一个示例用户在 5 个前端页面上走完"填画像 → 看技能图谱 → 出缺口报告 → 生成学习计划 → 做实践任务 → 代码评估 → 成长报告"的完整闭环。

**本阶段不是新业务逻辑，而是"整合 + 产品化 + 演示化"**：后端业务在阶段 3~7 已完成并被全量测试覆盖；阶段 8 负责——
1. 补 3 个**只读/聚合/流式**后端编排点（Dashboard 聚合、Skill Graph 全量读取、Chat 流式输出）；
2. 在现有 Vue 前端上新增 **5 个核心页面**并接入真实接口；
3. 沉淀 **Demo 数据集**与 **一键初始化脚本**，做到"不依赖人工后台操作"；
4. 跑 **端到端演示链路** + 整理 **答辩材料**。

**演示验收硬标准**（计划书阶段 8 原文）：
- Demo 不依赖人工后台操作；
- 关键链路可在 3~5 分钟内跑通；
- 异常时有降级方案；
- 所有核心结论可解释/可追溯（每页结论都带 evidence / 推理 / 来源）。

**一个重要边界（务必提前讲清）**：阶段 1 的 `orchestrator_agent` 目前是"意图识别 + 通用回复"，阶段 3~7 的画像/缺口/计划/实践/评估实际由 **HTTP 业务路由** 分别在各自页面被调用，并未做成单一 LangGraph 主脑里的多个 node 节点。阶段 8 **不做**"把所有 Agent 塞进一个编排图"的重构（风险高、非演示必需），而是采用**"Chat 识别意图 → 引导用户到对应页面 → 页面直连业务接口"**的产品化形态；"图内多节点编排收口"如需继续，留待阶段 8 之后的后续迭代。

**本阶段核心目标拆解**

| # | 目标 | 交付物 | 可测性 |
| --- | --- | --- | --- |
| G1 | 5 个核心页面 | Dashboard / Skill Graph / Gap Report / Learning Plan / Practice·Evaluation | 路由可达 + 数据渲染 |
| G2 | Agent Trace | Chat 里展示每条回复的 route / reason / steps | 有实际 trace 数据 |
| G3 | 流式 Agent 输出 | `/api/v1/chat/stream`（SSE）+ 前端增量渲染 | SSE 事件序列正确 |
| G4 | Dashboard 聚合 | `/api/v1/dashboard/<user>`（画像+进度+评估+成长） | DTO 字段齐全 |
| G5 | Skill Graph 读取 | `/api/v1/graph`（nodes+edges） | 图谱渲染 |
| G6 | Demo 数据集 + 一键初始化 | `scripts/demo_init.py` + 示例用户/代码 | 可重复执行（幂等） |
| G7 | 端到端演示链路 | `scripts/run_demo.py` + e2e 断言 | 3~5 分钟走通 |
| G8 | 回答答辩材料 | 演示分镜 + 追问预案 | 文档化 |

---

## 2. 范围边界

### 2.1 本阶段做什么（In Scope）

**后端（仅新增 3 处只读/聚合/流式点，不新增业务规则）**：
- `GET /api/v1/graph`：读取 skill_nodes / skill_edges 全量（复用 `gap/graph_store`）。
- `GET /api/v1/dashboard/<user_id>`：聚合画像 + 最新计划 + 最新评估 + 最近成长事件。
- `POST /api/v1/chat/stream`：SSE 流式回复（LLM 流式优先，规则兜底；降级到非流式）。
- `GET /api/v1/plan/list?user_id=`：列出用户计划摘要（供 Learning Plan 页选计划）。
- 阶段 8 新增编排模块 `app/dashboard/`（聚合）与 `app/agents/streamer.py`（流式）。

**前端（新增 5 个页面 + 侧边栏路由，接入真实接口）**：
- DashboardView（概览 + 成长报告 Growth Report）
- SkillGraphView（技能图谱可视化）
- GapReportView（缺口报告 + 优先级 + 推荐学习序）
- LearningPlanView（计划 + 任务状态流转）
- PracticeEvalView（实践任务 + 代码上传 + 能力评估 + 再规划触发）
- ChatView 增强：Agent Trace 展示 + 流式开关（复用现有页面）
- HealthView 保留为开发诊断页（不计入 5 页）

**其他**：Demo 数据集、`scripts/demo_init.py`、`scripts/run_demo.py`、e2e 测试（TC-Demo）、文档（演示分镜/接口补充）。

### 2.2 本阶段明确不做（Out of Scope）

| 不做 | 原因 |
| --- | --- |
| 把 6 个 Agent 重构成单一 LangGraph 多节点主脑 | 非演示必需、回归风险大，留作阶段 8 之后迭代 |
| 前端登录鉴权 / 多租户 | Demo 用 `demo_user` 单用户 |
| 生产级部署（Docker/K8s/HTTPS） | 本地一键起服务即可满足比赛 |
| 大数据量图表性能优化 | 演示数据量小 |
| 移动端适配 / 主题换肤 | 桌面演示优先 |

> 边界原则：**后端零业务新增**——所有演示数据都来自阶段 3~7 的已实现接口；阶段 8 只做"读 + 聚合 + 流式传输 + 前端组装"，异常时前端统一降级提示，保证不白屏。

---

## 3. 技术选型与工程结构

### 3.1 技术栈（阶段 1~7 已有，无新增依赖）

| 项 | 选型 |
| --- | --- |
| 后端 | Flask + `app.persistence.db`（psycopg），复用阶段 3~7 service/store |
| 图谱可视化 | 前端自绘 SVG（无新增依赖，避免比赛环境装库失败），读 `/api/v1/graph` 布局渲染 |
| 流式 | Flask `Response(..., content_type='text/event-stream')` + LangGraph `stream` / LLM `.stream` |
| 前端 | Vue3 + Pinia + Vue Router + Vite（已有），`chatService` 扩展为 SSE（`fetch` + `ReadableStream`） |
| 一键初始化 | Python `scripts/demo_init.py`（幂等，复用 `init_db`/`seed_skills`/`seed_skill_graph`/`ingest` + 造演示用户/代码） |

### 3.2 工程结构（新增/修改点）

```
app/
├── dashboard/                 # 【新增】演示聚合层
│   ├── __init__.py
│   ├── schemas.py             # DashboardDTO 契约
│   └── service.py             # 聚合：画像 + 最新计划 + 最新评估 + 成长事件（只读）
├── agents/
│   └── streamer.py            # 【新增】SSE 流式回复（LLM/.stream，规则兜底）
├── api/routes/
│   ├── dashboard.py           # 【新增】GET /api/v1/dashboard/<user_id>
│   ├── graph.py               # 【新增】GET /api/v1/graph
│   ├── plan.py                # 【修改】追加 GET /api/v1/plan/list?user_id=
│   └── chat.py                # 【修改】追加 POST /api/v1/chat/stream（SSE）
├── __init__.py                # 修改：注册 dashboard_bp / graph_bp
scripts/
├── demo_init.py               # 【新增】一键初始化（幂等）
├── demo_code_sample/          # 【新增】示例代码 + 测试（评估演示用）
│   ├── calc.py
│   └── test_calc.py
└── run_demo.py                # 【新增】三分钟演示链路脚本（打印步骤+HTTP 调用）
frontend/src/
├── api/
│   ├── dashboard.js           # 【新增】/dashboard / /graph
│   ├── plan.js                # 【新增】/plan /list /transition
│   ├── practice.js            # 【新增】/practice /evaluation
│   └── chat.js                # 【修改】新增 SSE streamChat()
├── stores/
│   ├── dashboard.js           # 【新增】
│   ├── graph.js               # 【新增】
│   ├── plan.js                # 【新增】
│   └── practiceEval.js        # 【新增】
├── views/                     # 【新增】DashboardView / SkillGraphView / GapReportView / LearningPlanView / PracticeEvalView
├── components/                # 【新增】SkillGraph.vue、GapReportTable.vue、PlanTimeline.vue、EvalReportCard.vue、GrowthTimeline.vue、TracePanel.vue 等
└── router/index.js            # 修改：注册 5 页面 + 侧边导航
tests/
└── test_demo_e2e.py           # 【新增】TC-Demo：/graph /dashboard /plan/list 形状 + Demo 链路接口断言
```

层依赖（延续单向规则）：`dashboard/service` → 复读阶段 3~7 的各 `store`/`service`（只读）；`streamer` → `agents/orchestrator_agent`（复用意图分类）+ LLM 流式；`routes/dashboard|graph` 只调 `dashboard/service` 与 `gap/graph_store`。

**接线点（改动最小化）**：`app/__init__.py` 注册 2 个新 blueprint；`plan.py` 加 1 个只读路由。**不触碰**阶段 3~7 任何业务实现。

---

## 4. 模块解耦与分工

| 模块 | 职责 | 输入 | 输出 | 不负责什么 |
| --- | --- | --- | --- | --- |
| `dashboard/service.py` | 聚合只读 DTO | user_id | `DashboardDTO` | 不改任何业务表 |
| `agents/streamer.py` | 生成流式回复事件 | message/thread | `yield` SSE 事件 | 业务意图的判定（复用 orchestrator） |
| `routes/dashboard.py` | HTTP 收口 | user_id | JSON | 聚合逻辑 |
| `routes/graph.py` | 图谱读取 | 无 | {nodes, edges} | 布局/渲染（前端做） |
| `routes/plan.py`(改) | 计划列表 | user_id | plan 摘要列表 | 只读，复用 todo_store |
| 前端 5 个视图 | 调接口 + 渲染 | 用户操作 | 页面 | 业务逻辑 |
| `demo_init.py` | 一键数据准备 | 无 | 幂等落库 | 起服务（另起） |

数据流（演示链路）：
```
demo_init(建 demo_user+画像+样本代码) 
   → Dashboard(读画像/计划/评估/成长) 
   → SkillGraph(/api/v1/graph) 
   → GapReport(POST /gap/request) 
   → LearningPlan(POST /plan/generate, 状态流转） 
   → PracticeEval(POST /practice/generate → /evaluation/artifact → /evaluation/evaluate → 触发 replan → 回写记忆)
   → Chat(SSE 流式答疑 / Agent Trace)
```

---

## 5. 接口契约（契约先行，后端先行冻结）

### 5.1 现有接口（页面直接复用，仅列本阶段用到的）

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/v1/profile/<user_id>` | 画像页/概览首页 |
| POST | `/api/v1/gap/request` | Gap Report 页 |
| POST | `/api/v1/plan/generate` | 生成计划 |
| GET | `/api/v1/plan/<plan_id>` | 计划详情 |
| POST | `/api/v1/plan/<id>/tasks/<task>/transition` | 任务流转 |
| POST | `/api/v1/practice/generate` | 生成实践 |
| GET | `/api/v1/practice/<practice_id>` | 实践详情 |
| POST | `/api/v1/evaluation/artifact` | 上传代码 |
| POST | `/api/v1/evaluation/evaluate` | 触发评估 |
| GET | `/api/v1/memory/events?user_id=` | 成长轨迹 |
| GET | `/api/v1/memory?user_id=` | 长期事实 |

### 5.2 新增接口

**`GET /api/v1/graph`** → `{ "nodes": [{ id, name, category }], "edges": [{ source, target }] }`
（节点=skill_nodes，边=skill_edges，供前端 SVG 布局；数据量小直接全量返回。）

**`GET /api/v1/dashboard/<user_id>`** → `DashboardDTO`

```jsonc
{
  "user_id": "demo_user",
  "profile": { "skills": [{ "skill_id", "name", "theory_score", "practice_score" }], "skill_count": 3 },
  "latest_plan": { "plan_id", "goal", "status", "total_tasks", "done_tasks", "progress": 0.4 } | null,
  "latest_evaluation": { "evaluation_id", "skill_id", "overall_score", "replanned", "created_at" } | null,
  "growth": [{ "id", "event_type", "summary", "created_at" }],      // 最近 memory_events（成长报告）
  "facts": [{ "key", "text", "namespace" }]                          // 长期记忆（跨会话事实）
}
```

**`GET /api/v1/plan/list?user_id=demo_user`** → `[{ "plan_id", "goal", "status", "progress", "created_at" }]`

**`POST /api/v1/chat/stream`**（SSE，`text/event-stream`）

```jsonc
// 请求体（与 POST /api/v1/chat 一致）
{ "user_id": "demo_user", "thread_id": "T1", "message": "帮我看看学习计划怎么做", "intent_hint": null }
// 响应为一行一个 SSE 事件：
// data: {"type":"meta","intent":"plan_generation","route":"plan","thread_id":"T1"}
// data: {"type":"delta","text":"…"}
// data: {"type":"done","thread_id":"T1"}
// (异常) event:error data: <msg>
```

### 5.3 错误码

| 场景 | HTTP | code |
| --- | --- | --- |
| user_id 非法/缺失参数 | 422 | 42200 |
| 聚合/图谱资源不可用（表未就绪） | 500 | 50080 |
| SSE 流式异常（降级为一次性事件） | 500 | 50081 |

---

## 6. 数据模型（复用既有，不新建业务表）

- 本阶段**不新增任何业务表**。Dashboard / Graph / Plan list 全部由以下已有数据提供：
  - `user_skills`/`skills`（画像，阶段 3）
  - `skill_nodes`/`skill_edges`（图谱，阶段 4）
  - `learning_plans`/`learning_tasks`（计划，阶段 5）
  - `practices`/`evaluations`/`code_snippets`（实践/评估，阶段 6）
  - `memory_events`/`memories`（成长/事实，阶段 7）
- Dashboard DTO 为**运行时聚合**，不落库。

---

## 7. 配置

| 配置 | 默认 | 说明 |
| --- | --- | --- |
| `DEMO_USER_ID` | `demo_user` | 演示专用用户 id |
| `STREAM_ENABLED` | true | SSE 流式开关；false 时前端直接走非流式 `/chat` |

`.env.example` 追加两行注释；不改动既有配置。

---

## 8. 开发任务拆解（按依赖排序，可并行）

| # | 任务 | 产出 | 依赖 |
| --- | --- | --- | --- |
| 1 | 契约冻结：`dashboard/schemas.py` + `graph` DTO | 后端契约 | 无 |
| 2 | `routes/graph.py` + 注册 | `GET /api/v1/graph` | 1 |
| 3 | `dashboard/service.py` 聚合 + `routes/dashboard.py` | `GET /api/v1/dashboard/<user>` | 1,2 |
| 4 | `plan.py` 追加 `GET /api/v1/plan/list` | 计划列表 | 1 |
| 5 | `agents/streamer.py` + `routes/chat.py` 追加 SSE | `POST /api/v1/chat/stream` | 1 |
| 6 | 前端 API/Stores（dashboard/graph/plan/practiceEval + chat SSE） | 数据层 | 2~5 |
| 7 | 前端 5 个视图 + 复用组件 + 路由/侧边栏 | 页面 | 6 |
| 8 | ChatView 增强：Agent Trace + 流式开关 | Trace/流式 | 6 |
| 9 | `scripts/demo_init.py` + `demo_code_sample` | 一键数据 | 2~5 |
| 10 | `scripts/run_demo.py` + `tests/test_demo_e2e.py`（TC-Demo） | 演示链路+断言 | 9 |
| 11 | 文档：演示分镜/追问预案，`docs/api_v1.md` 补 8.x | 答辩材料 | 10 |

> 并行建议：2/3/4/5（后端四路）可并行；6 依赖 2~5；7/8 依赖 6；9/10 收口。

---

## 9. 测试计划

**单元/形状用例**
- TC-D1 `/api/v1/graph`：返回 nodes+edges，均为非空列表且字段完整。
- TC-D2 `/api/v1/dashboard/<user>`：字段齐全（profile/latest_plan/latest_evaluation/growth/facts），无数据时给空值而非 500。
- TC-D3 `/api/v1/plan/list?user_id=`：返回计划摘要，未知用户返回空列表。
- TC-D4 SSE `chat/stream`：能消费到 meta→delta→done 事件；`STREAM_ENABLED=false` 时走非流式兜底。
- TC-D5 `demo_init` 幂等：连跑两次不报错、不重复插入。

**端到端演示链路（TC-Demo）**
- TC-D6 演示五步走通：建数据 → gap → plan → practice → eval，逐接口 2xx 且核心字段非空。
- TC-D7 评估后触发 replan 且回写 memory（成长事件递增）。
- TC-D8 前端路由可达：5 个视图懒加载组件均能解析（用 `new URL` 评估导入存在性）。

---

## 10. 验收标准（对照计划书阶段 8）

| AC | 验收项 | 落实 |
| --- | --- | --- |
| AC1 | Demo 不依赖人工后台操作 | `demo_init.py` 一键造数；页面全量调用 HTTP |
| AC2 | 关键链路 3~5 分钟跑通 | `run_demo.py` 分镜脚本 + TC-D6 |
| AC3 | 异常时有降级方案 | SSE 降级非流式、前端空态/错误兜底不白屏、无 DB 数据给空值 |
| AC4 | 所有核心结论可解释/可追溯 | 每页展示 reason/evidence/来源；Agent Trace 展示推理 |
| AC5 | 5 个核心页面落地 | Dashboard/Graph/Gap/Plan/Practice 路由可达且渲染数据 |
| AC6 | 流式 Agent 输出 | `/chat/stream` SSE + 前端增量渲染 |
| AC7 | 答辩材料就绪 | 演示分镜 + 追问预案 |

---

## 11. 风险与兜底

| 风险 | 影响 | 缓解/兜底 |
| --- | --- | --- |
| `demo_init` 依赖外网（RAG 分片/LLM） | 初始化失败 | 知识库已本地 `ingest`；向量/hash embedding 本地可用；LLM 失败走规则 |
| SSE 在部分网络/CDN 下不可用 | 流式失效 | `STREAM_ENABLED=false` 一键切回非流式；前端检测 SSE 失败自动降级 |
| skill 图谱布局复杂 | 图乱 | 前端 SVG 分层（按 category）+ 力导向简易布局，数据量小够用 |
| 某页无数据（空 DB） | 白屏 | Dashboard/Plan 页空态占位 + 引导"运行 demo_init" |
| 评估 LLM 润色失败 | 报告缺建议 | 走既有模板兜底（阶段 6 已实现） |
| Dashboard 聚合连表过多变慢 | 首屏慢 | 只读+每项独立小查询，演示数据量小；可接受 |

---

## 12. 前置依赖与交付清单

- 前置依赖：阶段 1~7 全部完成且全量测试通过（当前已满足）。
- 交付清单：
  - 后端：`app/dashboard/`（schemas+service）、`app/agents/streamer.py`、`routes/dashboard.py`、`routes/graph.py`、`routes/plan.py`（+list）、`routes/chat.py`（+stream）、`app/__init__.py` 注册。
  - 前端：5 个视图 + 复用组件 + 路由侧栏；ChatView 增强（Trace + 流式）；新增 api/stores。
  - 脚本：`scripts/demo_init.py`、`scripts/demo_code_sample/`、`scripts/run_demo.py`。
  - 测试：`tests/test_demo_e2e.py`（TC-D1~D8）。
  - 文档：演示分镜 + `docs/api_v1.md` 补 8.x + `.env.example` 配置。