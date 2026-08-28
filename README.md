# SkillMap · 个人技术栈成长智能体

> 一个从「能力画像 → 缺口分析 → 学习规划 → 实践 → 评估 → 再规划」**全闭环**的个人技术栈成长智能体（Agent），
> 通过 8 个阶段增量演进，把一个"单 Agent 最小闭环"逐步打磨成带 RAG、长期记忆、前端产品页的**可演示产品**。

- **技术栈**：Python + Flask + LangGraph + PostgreSQL(pgvector) + Vue3 + Pinia
- **当前进度**：阶段 1~8 全部落地，后端 100+ 测试通过，前端 6 个页面 + 3~5 分钟比赛演示链路
- **比赛演示**：`demo_init.py` 一键造数 → 启动服务 → `run_demo.py` 自动核对 7 段链路

---

## 一、它解决什么问题

用户告诉 SkillMap「我的技术现状 + 想转的目标岗位」，系统帮你：

1. **画像**：从自然语言/项目简介提取结构化技能（带分数、置信度、证据）
2. **差距**：对照目标岗位技能要求，算出缺口与优先级（P1/P2/P3）和推荐学习顺序
3. **规划**：把缺口转成有依赖关系、可验收、可流转（pending→doing→done）的学习计划
4. **实践**：把每个任务转成带交付物与评分标准的实践练习
5. **评估**：对提交的代码做结构化评估（区分理论/实践分），自动回写画像并触发**再规划**
6. **记忆**：长期记住用户事实、偏好、成长经历，写入前自动 PII 脱敏、超长对话自动摘要、关键操作人工确认

> 一句话：**它是"带工程素养的 LLM 应用"的学习范本** —— 分层、契约先行、规则兜底、可重复、可测试。

---

## 二、核心特性（按阶段）

| 阶段 | 主题 | 交付亮点 |
| --- | --- | --- |
| 1 | 基础工程与 Agent 最小闭环 | Flask 应用工厂 + LangGraph 编排 + Checkpointer 会话持久化 + 统一响应/错误码 + 前端对话页 |
| 2 | 技术知识库与 RAG | pgvector 向量库、分片/嵌入/检索/问答、网页正文抽取（trafilatura）、幂等入库 |
| 3 | 用户技术画像 | 技能字典、规则等级换算、LLM 抽取 + 规则兜底、增量合并、证据可追溯 |
| 4 | 技能图谱与 Gap 分析 | 技能图种子、前置依赖传递、拓扑排序、缺口评分与优先级、可解释 report |
| 5 | 学习规划与 Todo | 任务分桶/依赖排序/状态机、局部重规划且保留 done 任务 |
| 6 | 实践任务与能力评估 | 实践计划生成、代码静态分析、理论/实践分、自动回写画像 + 触发再规划（闭环补全） |
| 7 | 长期记忆与 Middleware | semantic/episodic/procedural 记忆、HNSW 向量索引、PII 脱敏、摘要压缩、HITL 人工确认 |
| 8 | 前端整合与比赛 Demo | 6 页面（工作台/对话/图谱/缺口/计划/实践评估）、SSE 流式回复、SVG 技能图谱、一键 Demo |

---

## 三、技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | Vue 3 · Vite · Pinia · Vue Router · axios · 原生 SVG（技能图谱） |
| 后端 | Python 3.10+ · Flask · LangGraph · Pydantic v2 · psycopg 3 |
| 存储 | PostgreSQL 16 + pgvector 扩展（RAG 向量检索 / 记忆向量检索） |
| LLM | OpenAI 兼容端点（默认 DeepSeek），Embedding 可选 OpenAI 兼容服务；**无 Key 也能跑**（规则/哈希嵌入兜底） |
| 其他 | trafilatura（网页正文抽取）、pytest + pytest-cov（测试） |

---

## 四、快速开始

### 4.1 环境要求

- Python 3.10+
- PostgreSQL 16（含 `vector` 扩展，`CREATE EXTENSION vector`）
- Node.js 18+

### 4.2 后端启动

```bash
# 1. 进入项目根目录，创建虚拟环境并安装依赖
cd SkillPilot
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# 2. 配置环境变量
cp .env.example .env
#    编辑 .env，至少填：DATABASE_URL（PostgreSQL 连接串）
#    可选：LLM_API_KEY / LLM_MODEL / LLM_BASE_URL（不填则走规则兜底）

# 3. 初始化数据库（建库 + 建全部阶段表，幂等）
python -m scripts.init_db

# 4. 灌入技能字典 / 技能图与岗位种子（幂等）
python -m scripts.seed_skills
python -m scripts.seed_skill_graph

# 5. （比赛演示，可选）一键造演示数据：demo_user 画像 + 示例代码
python -m scripts.demo_init

# 6. 启动服务（默认 5000；macOS 若被 AirPlay 占用，用 8081）
python -m app
# 或指定端口：PORT=8081 python -m app
```

> 验证：`curl http://localhost:5000/health` 返回 `{"status":"up",...}`。

### 4.3 前端启动

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173（自动代理 /api 到 http://localhost:8081）
```

> 前端代理目标可在 `frontend/vite.config.js` 中通过 `VITE_DEV_PROXY_TARGET` 覆盖，默认 `http://localhost:8081`。

### 4.4 运行测试

```bash
python -m pytest                    # 全量后端测试（100+）
python -m pytest tests/test_demo_e2e.py -v   # 仅 Demo 端到端链路
```

### 4.5 比赛演示（3~5 分钟链路）

```bash
# 前置：已完成 4.2 的 init_db / seed_skills / seed_skill_graph / demo_init，且服务已启动
python -m scripts.run_demo
```

脚本按演示分镜依次核对 7 段链路：`Dashboard → 技能图谱 → Gap 缺口 → 学习计划 → 实践任务 → 代码评估(含再规划) → 成长轨迹`，全部 `✓` 即链路可用。

---

## 五、项目结构

```
SkillPilot/
├── app/                 # 后端主应用（Python 包，分层）
│   ├── api/routes/      #   接入层：HTTP 路由（chat/rag/profile/gap/plan/evaluation/memory/graph/dashboard）
│   ├── orchestrator/    #   编排层：LangGraph 状态图与运行状态
│   ├── agents/          #   Agent 层：意图识别 / SSE 流式
│   ├── profile/         #   阶段3 用户画像（schemas/rule_engine/extractor/store/skill_service）
│   ├── gap/             #   阶段4 缺口分析（gap_score/closure/explain/graph_store）
│   ├── todo/            #   阶段5 学习规划（planner/scheduler/todo_store）
│   ├── practice/        #   阶段6 实践计划（planner/explain）
│   ├── evaluation/      #   阶段6 能力评估（analyzers/scorer/service/store/update）
│   ├── memory/          #   阶段7 长期记忆（semantic/episodic/procedural + middleware: pii/summary/hitl）
│   ├── rag/             #   阶段2 RAG（splitter/embeddings/vectorstore/retriever/qa_chain/crawler）
│   ├── dashboard/       #   阶段8 工作台聚合（只读快照）
│   ├── persistence/     #   持久化（db/checkpointer/thread_store）
│   ├── middleware/      #   横切（trace / 请求日志）
│   ├── config.py        #   配置（.env → Config 对象）
│   └── __init__.py      #   create_app 应用工厂
├── frontend/            # 前端（Vue3 SPA）
│   └── src/
│       ├── views/       #   6 个页面（Dashboard/Chat/SkillGraph/GapReport/LearningPlan/PracticeEval/Health）
│       ├── components/  #   可复用组件（SkillGraph/PlanTimeline/GapReportTable/EvalReportCard/chat/...）
│       ├── stores/      #   Pinia 状态（chat/dashboard/graph/plan/practiceEval/health）
│       ├── api/         #   纯 HTTP（http.js 统一信封 + 各模块）
│       ├── services/    #   业务归一化
│       └── router/      #   路由
├── scripts/             # 运维/种子/演示脚本（init_db/seed_skills/seed_skill_graph/ingest_materials/demo_init/run_demo）
├── materials/           # RAG 知识库语料（manifest.json + notes/）
├── tests/               # 后端测试（test_chat/checkpointer/rag/profile/gap/todo/evaluation/memory/demo_e2e）
├── docs/                # 文档（api_v1.md / 初学者学习指南.md / 手敲学习资料.md）
└── 项目规划/             # 项目计划书 + 阶段1~8 详细计划 + 接口文档
```

### 分层依赖（核心设计）

```
接入层 api → 编排层 orchestrator → Agent 层 agents → 业务层(profile/gap/todo/...) → 持久化 persistence
```

上层只能调下层，**下层不能反向 import 上层**。这样加新业务时，接入层和管道不用改，只要往编排图里塞新节点。

---

## 六、API 一览

统一响应信封：成功 `{"code":0,"message":"ok","data":...}`；错误带 `code / trace_id`。

| 模块 | 接口 |
| --- | --- |
| 健康 | `GET /health` |
| 对话 | `POST /api/v1/chat`、`POST /api/v1/chat/stream`（SSE 流式） |
| RAG | `POST /api/v1/rag/ingest`、`/search`、`/query` |
| 画像 | `POST /api/v1/profile/extract`、`/upsert`、`/projects`、`GET /profile/<user_id>` |
| 缺口 | `POST /api/v1/gap/request` |
| 计划 | `POST /api/v1/plan/generate`、`GET /plan/<id>`、`GET /plan/list`、`POST /plan/<id>/tasks/<task_id>/transition`、`POST /plan/<id>/replan` |
| 实践 | `POST /api/v1/practice/generate`、`GET /practice/<id>` |
| 评估 | `POST /api/v1/evaluation/artifact`、`/evaluate` |
| 记忆 | `POST /api/v1/memory/remember`、`/search`、`/summarize`、`/pending`、`GET /memory`、`/memory/events`、`/memory/pending`、`POST /memory/pending/<pa_id>/confirm`、`DELETE /memory/<mem_id>` |
| 图谱 | `GET /api/v1/graph` |
| 工作台 | `GET /api/v1/dashboard/<user_id>` |

完整契约与错误码见 [docs/api_v1.md](docs/api_v1.md)。

---

## 七、文档导航

| 文档 | 说明 |
| --- | --- |
| [docs/api_v1.md](docs/api_v1.md) | 全量 API 契约（请求/响应/错误码） |
| [docs/初学者学习指南.md](docs/初学者学习指南.md) | 面向初学者的代码阅读指南（阶段 1 视角） |
| [docs/手敲SkillMap学习资料.md](docs/手敲SkillMap学习资料.md) | **从零手敲**本项目的分阶段教程（推荐新同学从这篇开始） |
| [项目规划/SkillMap_个人技术栈成长智能体_项目计划书.docx](项目规划/SkillMap_个人技术栈成长智能体_项目计划书.docx) | 项目计划书 |
| [项目规划/SkillMap_API接口文档.md](项目规划/SkillMap_API接口文档.md) | 全量接口设计文档 |
| [项目规划/SkillMap_阶段N_..._详细计划.md](项目规划/) | 阶段 1~8 详细实施计划（契约先行） |
| [materials/README.md](materials/README.md) | RAG 知识库语料与入库说明 |

---

## 八、设计要点（为什么这么写）

1. **分层 + 单向依赖**：接入/编排/Agent/业务/持久化各司其职，加功能不动管道。
2. **契约先行**：每阶段先定 Pydantic Schema 与 API 契约（见各阶段计划与 api_v1.md），前后端并行。
3. **规则兜底，LLM 只做增强**：打分、排序、状态流转等**纯规则可重复**；LLM 只负责"抽技能/润色文案"，失败走模板兜底，保证无 Key 也能跑通闭环。
4. **幂等优先**：建表、种子、入库、Demo 造数全部可安全重跑。
5. **统一错误码**：业务校验 42200、资源不存在 404xx、服务失败 500xx，前端按 code 兜底，不白屏。
6. **工程可测试**：每阶段配 TC 测试；阶段 8 有端到端测试守护演示链路。

---

## 九、Roadmap（已完成 1~8）

- [x] 阶段 1：基础工程与 Agent 最小闭环
- [x] 阶段 2：技术知识库与 RAG
- [x] 阶段 3：用户技术画像
- [x] 阶段 4：技能图谱与 Gap 分析
- [x] 阶段 5：学习规划与 Todo
- [x] 阶段 6：实践任务与能力评估
- [x] 阶段 7：长期记忆与 Middleware
- [x] 阶段 8：前端整合与比赛 Demo

---

## 十、License

内部学习 / 比赛项目，详见项目规划文档。
