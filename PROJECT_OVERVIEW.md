# SkillMap 项目现状速查（供改进咨询）

## 一、一句话定位

SkillMap 是一个**面向个人技术栈成长的对话式学习助手**：用户用自然语言描述目标岗位或想学的技能，系统识别意图、生成结构化学习计划，并以技能图谱可视化岗位能力要求。目前已完成一次**功能精简**——砍掉了实践评估、能力评估、RAG 问答、缺口分析等繁重功能，只保留「对话 + 学习计划 + 技能图谱 + 服务健康」四条主线。

## 二、技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12 · Flask · LangGraph · LangChain |
| 数据库 | PostgreSQL 16 + pgvector（可选） |
| 前端 | Vue 3 + Vite + Pinia + vue-router |
| LLM | DeepSeek（OpenAI 兼容端点），无 key 时走规则兜底 |
| Embedding | 可选（Qwen-DashScope），默认关闭走本地 hash 兜底 |

## 三、目录结构

```
SkillPilot/
├── app/
│   ├── __init__.py           # Flask app 工厂，注册 4 个 blueprint
│   ├── __main__.py           # python -m app 启动
│   ├── config.py             # 环境变量 → Config 对象（含大量已下线阶段配置）
│   ├── contracts.py          # 全局契约：VALID_INTENTS = {chat, plan_generation}
│   ├── api/
│   │   ├── routes/           # chat.py / plan.py / graph.py / health.py（仅存的 4 个接口）
│   │   ├── schemas.py        # UserRequest 等入参校验
│   │   └── errors.py         # 统一错误码/响应封装
│   ├── agents/               # 对话核心：orchestrator/routing/reply/streamer/intent_parser/websearch
│   ├── orchestrator/         # LangGraph 编排：graph.py（建图）、state.py（SkillMapState）
│   ├── persistence/          # db.py（连接）、checkpointer.py、thread_store.py
│   ├── todo/                 # 学习计划业务（planner、todo_store）
│   ├── gap/                  # 仅 graph_store.py 在用（技能图谱读取）；其余缺口分析已下线
│   ├── profile/              # 仅 store.py 在用（技能词典读取）；画像抽取已下线
│   ├── memory/               # 长期记忆（chat 路由仍在用：memory_context + 摘要压缩）
│   └── rag/                  # 功能已移除；仅 embeddings.py 被 memory 语义检索复用
├── frontend/src/
│   ├── views/                # ChatView / LearningPlanView / SkillGraphView / HealthView
│   ├── components/           # AppLayout（单侧栏）、SkillGraph、PlanTimeline 等
│   ├── stores/               # Pinia：chat / plan / graph / health
│   └── api/ + services/      # 双层的 API 封装
├── scripts/                  # init_db / seed_skill_graph / seed_skills / demo_init 等
├── tests/                    # pytest 单元/集成测试
└── SkillPilot_*.json          # 技能图谱 / 岗位能力 / 知识源种子数据（3 份）
```

## 四、核心架构与数据流

后端采用**单向依赖**：API 层 → 编排/知识层 → 持久化层。核心是 LangGraph 条件路由图（`app/orchestrator/graph.py`）：

```
START → orchestrator_agent（意图识别 + 入参解析）
           └─ 条件路由：
                chat            → reply_node
                plan_generation → plan_node → reply_node
           reply_node（拼最终回复 + 透传 artifacts）→ END
```

关键机制（各文件职责）：

- `app/agents/orchestrator_agent.py`：意图识别 + chat 直接回复。LLM 可用走 DeepSeek 结构化输出，失败回退规则；chat 回复会先尝试**联网检索增强**。
- `app/agents/intent_parser.py`：意图 → 结构化入参（**纯规则**，LLM 增强默认关闭）。岗位/技能名最长匹配，缺入参置 `unanswered` 触发追问。
- `app/agents/routing.py`：业务节点纯函数，只保留 `plan_node`；异常不外抛，统一降级为 `need_input` / `degraded`。
- `app/agents/reply.py`：汇合点，追加消息、归一终态、组装 steps/artifacts。
- `app/agents/websearch.py`：chat 的联网检索增强，DuckDuckGo Lite 为主、Bing 兜底，带去重/评分/正文并行抓取，输出编号引用。
- `app/orchestrator/state.py`：`SkillMapState` 运行时状态，含 messages（Checkpointer 持久化）、intent、summary、artifacts 等。
- Checkpointer：有 `DATABASE_URL` 用 PostgresSaver，否则 InMemorySaver（`app/persistence/checkpointer.py`）。

## 五、API 接口清单

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查（DB/LLM 连通性） |
| POST | `/api/v1/chat` | 非流式对话 |
| POST/GET | `/api/v1/chat/stream` | SSE 流式对话 |
| POST | `/api/v1/plan/generate` | 生成学习计划 |
| GET | `/api/v1/plan/list` | 列出某用户计划 |
| GET | `/api/v1/plan/<id>` | 查询计划 |
| POST | `/api/v1/plan/<id>/replan` | 局部重规划 |
| POST | `/api/v1/plan/<id>/tasks/<tid>/transition` | 任务状态流转 |
| POST | `/api/v1/plan/<id>/tasks/<tid>/status` | 手动设置任务状态 |
| DELETE | `/api/v1/plan/clear` | 清空某用户计划 |
| GET | `/api/v1/graph` | 返回全量技能图谱 `{nodes, edges}` |

## 六、数据模型（PostgreSQL）

核心表集中在 `scripts/init_db.py`，但注意**该文件仍创建了所有历史阶段的表**，实际在线使用的只有一部分：

- **在用**：`users`、`threads`、`skills`（技能词典）、`skill_nodes`、`skill_edges`、`role_skills`（图谱/岗位要求）、`learning_plans`、`learning_tasks`（学习计划）、`memories`/`memory_events`/`pending_actions`（长期记忆）。
- **已下线但仍建表**：`rag_documents`/`rag_chunks`、`user_skills`/`projects`/`user_preferences`/`skill_evidence`、`practices`/`evaluations`/`code_snippets`、`interview_sessions`/`interview_answers`。

**数据层关键设计**：`scripts/seed_skill_graph.py` 从 3 份 JSON 生成图谱，并做了两件事：① 把 `skills` 词典与 `skill_nodes` 两套技能 ID **同步统一**；② 为隐式节点补领域（父节点继承 + 关键字推断）。领域 → 前端分类的权威映射在 `app/gap/graph_store.py` 的 `DOMAIN_TO_CATEGORY`。

## 七、前端结构

单侧栏布局（`frontend/src/components/AppLayout.vue`），路由见 `frontend/src/router/index.js`：

- `/chat` 对话（含会话列表、SSE 流式渲染）
- `/plan` 学习计划
- `/graph` 技能图谱（侧栏标签为「学习计划图谱」，与路由 meta 标题「技能图谱」**命名不一致**）
- `/health` 服务健康

前端做了 API 层（`api/*.js`）与服务层（`services/*.js`）双层封装，Pinia 管状态。

## 八、配置与环境

通过 `.env` 注入（模板见根目录 `.env.example`）。最重要的项：`DATABASE_URL`（PostgreSQL，可选）、`LLM_API_KEY`（DeepSeek，不配则规则兜底）、`CHECKPOINTER_BACKEND`。注意 `config.py` 里仍保留大量**已下线阶段**的配置项（阶段 2~6、10 的 eval/practice/interview 等），属冗余。

## 九、测试

`tests/` 下 7 个文件（agent_routing / chat_integration / checkpointer / gap / memory / profile / todo）。跑法：`pytest`。历史上有回归失败源于**远程数据库连接超时**（测试依赖真实 DB），而非逻辑错误。

## 十、当前状态总结（精简后）

✅ **保留并在线**：对话（含 LLM 自然对话 + 联网检索 + SSE 流式）、学习计划（生成/流转/清空）、技能图谱（只读）、服务健康、长期记忆注入。

❌ **已下线但代码/表仍残留**：RAG 问答、用户画像抽取、缺口分析、实践任务、能力评估、AI 访谈评估——相关目录/建表语句/配置项未彻底清理，是当前代码库最大的"技术债"。

## 十一、待改进点（重点）

这部分是按"改进潜力"排序的问题清单：

1. **死代码/冗余清理**（性价比最高）
   - `app/rag` 目录：仅 `embeddings.py` 被 memory 复用，其余 `crawler/loader/retriever/service/splitter/vectorstore` 已无引用。
   - `app/gap` 目录：仅 `graph_store.py` 在用，`gap_agent/gap_score/closure/explain` 已下线。
   - `app/profile` 目录：仅 `store.py` 的 `load_skill_names` 在用，画像抽取逻辑已下线。
   - `init_db.py` 仍建 6 组已下线功能的表；`config.py`/`.env.example` 仍有大量已下线阶段配置。建议统一梳理 import 引用后裁剪。

2. **技能图谱质量与可视化**
   - 整体图**布局算法与孤立节点清理尚未做**，当前可视化较基础。
   - 存在**约 60 个孤立技能节点未映射到任何岗位**（岗位映射缺口，需复核当前数据）。
   - 部分节点 `domain` 仍可能为空，分类靠 id 关键字推断兜底，准确性有限。

3. **意图识别与入参解析过于"规则化"**
   - `intent_parser.py` 纯规则匹配，LLM 增强默认关闭，岗位/技能名容错弱（依赖别名表和最长匹配）。

4. **无 LLM key 时体验差**
   - 规则兜底回复较机械（"我还没接上大模型…"）。

5. **联网检索脆弱**
   - `websearch.py` 依赖第三方页面 HTML 解析，易被反爬/结构变更击穿。

6. **缺认证与多租户隔离**
   - `thread_id` 即会话标识，无用户鉴权；`user_id` 由前端自定。

7. **命名/残留细节**
   - 侧栏「学习计划图谱」vs 路由标题「技能图谱」不一致；`frontend/src/utils/demo.js`、`ChatGPT.html` 等 demo 残留。

8. **测试耦合真实 DB**
   - 测试依赖远程数据库，导致历史回归失败；建议引入测试库隔离或 mock。

## 十二、如何快速跑起来

```bash
# 后端
.venv/bin/python -m scripts.init_db          # 初始化数据库（可选，需 DATABASE_URL）
.venv/bin/python -m scripts.seed_skill_graph # 灌入技能图谱种子数据
.venv/bin/python -m app                       # 启动（默认 5000 端口）

# 前端
cd frontend && npm install && npm run dev     # Vite dev server
```