# 从零手敲 SkillMap：一个 LLM 智能体的完整工程化教程

> 目标读者：**有 Python 与 Vue 基础，但没做过 LLM 应用工程**的初学者。
> 学习方式：跟着本教程，**从一个空目录开始，一个阶段一个阶段手敲**，最终得到本仓库的完整项目。
> 本教程与代码同步；建议每学完一章就对照源码 `app/`、`frontend/src/`、`scripts/`、`tests/` 复核。

---

## 第 0 章 开工前的全局认知

### 0.1 我们要手敲出什么

一个「**个人技术栈成长智能体**」，完整闭环是：

```
用户说出现状与目标
   → 画像（Profile）：把能力结构化
   → 差距（Gap）：对照目标岗位算出缺口
   → 规划（Plan）：把缺口排成可执行的学习任务
   → 实践（Practice）：把任务变成可交付的练习
   → 评估（Evaluation）：评代码、回写画像、触发再规划
   → 记忆（Memory）：长期记住用户，服务下次对话
```

整个项目分 **8 个阶段** 逐步实现，每一阶段都在上一阶段基础上加一块能力，且**每阶段都能独立运行、独立验证**。这就是"增量演进"。

### 0.2 五条贯穿全程的工程心法（先背下来）

1. **分层 + 单向依赖**：`接入层 → 编排层 → Agent 层 → 业务层 → 持久化层`，上层只能调下层，下层永远不能 import 上层。
2. **契约先行**：写代码前先定义 Pydantic Schema 和 HTTP 契约，前后端照契约并行开发。
3. **规则兜底，LLM 只做增强**：打分、排序、状态流转这些"要可重复"的用纯规则；LLM 只负责"抽技能/润色文案"，失败走模板兜底。这样**没有 API Key 也能跑通闭环**。
4. **统一响应信封 + 统一错误码**：所有接口返回 `{code, message, data, trace_id}`，前端按 `code` 兜底，绝不白屏。
5. **幂等**：建表、种子、入库、Demo 造数，重复跑不出问题。

### 0.3 环境准备

```bash
# Python 3.10+，创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate
pip install flask langgraph langgraph-checkpoint-postgres langchain-core \
            langchain-openai psycopg[binary] pydantic python-dotenv \
            langchain-text-splitters pgvector requests trafilatura \
            pytest pytest-cov

# PostgreSQL 16（macOS: brew install postgresql@16；或 Docker）
# 需要 vector 扩展（pgvector），以超管在某库执行一次：
#   CREATE EXTENSION IF NOT EXISTS vector;

# Node.js 18+（前端用）
```

> 真实项目把依赖写在 `pyproject.toml`（见仓库根目录），用 `pip install -e ".[dev]"` 一键装完。

### 0.4 全局约定（所有阶段通用）

**统一响应信封**（在 `app/api/errors.py` 实现）：

```json
{ "code": 0, "message": "ok", "data": {...}, "trace_id": "..." }
```

**核心错误码**：

| code | 含义 |
| --- | --- |
| 0 | 成功 |
| 40001 | JSON 格式错误（400） |
| 42200 | 业务校验失败（422） |
| 404xx | 资源不存在（404） |
| 50000 | 服务端未知错误（500） |
| 500xx | 各业务模块失败（走兜底，不白屏） |

---

## 第 1 章 阶段 1：基础工程与 Agent 最小闭环

> 目标：跑通「浏览器一句话 → Flask → LangGraph 编排 → 一个 Agent 处理 → 标准 JSON」，且**重启服务不丢会话**。

### 1.1 先理解三个概念

- **Flask 应用工厂**：一个 `create_app()` 函数，把所有路由、中间件、配置组装成 app。好处：测试时能造多个隔离的 app。
- **LangGraph**：把"智能体的执行"建模成**状态机 + 图**。节点（node）是函数，边（edge）是节点间的连接，状态（state）是共享数据。
- **Checkpointer（检查点）**：每跑完一个节点就把状态存下来，这样**同一 thread_id 的对话能接着上次继续**（上下文恢复）。

### 1.2 手敲步骤（按这个顺序建文件）

```
SkillPilot/
├── pyproject.toml            # 依赖与 pytest 配置
├── .env.example              # 环境变量模板
├── app/
│   ├── config.py             # .env → Config 对象
│   ├── contracts.py          # 跨层常量（合法意图枚举等）
│   ├── __init__.py           # create_app 应用工厂
│   ├── __main__.py           # python -m app 启动
│   ├── api/
│   │   ├── errors.py         # 统一错误处理
│   │   ├── schemas.py        # 请求体校验（Pydantic）
│   │   └── routes/
│   │       ├── health.py     # GET /health
│   │       └── chat.py       # POST /api/v1/chat
│   ├── orchestrator/
│   │   ├── state.py          # SkillMapState
│   │   └── graph.py          # 把节点连成图并编译
│   ├── agents/
│   │   ├── base.py           # Agent 基类（契约）
│   │   └── orchestrator_agent.py  # 意图识别 + 回复
│   ├── persistence/
│   │   ├── db.py             # 数据库连接
│   │   ├── checkpointer.py   # 会话保存器（Postgres/内存）
│   │   └── thread_store.py   # threads 表读写
│   └── middleware/           # trace_id / 请求日志
├── scripts/init_db.py        # 建库建表
└── tests/test_chat_integration.py
```

### 1.3 关键代码（手敲时对照）

**① 配置：`app/config.py`**

```python
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()  # 加载根目录 .env

@dataclass
class Config:
    env: str = "dev"
    version: str = "v1.0.0"
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)
```

**② 状态：`app/orchestrator/state.py`** —— 一次会话的"总状态"

```python
from typing import Any, Optional
from dataclasses import dataclass, field

@dataclass
class SkillMapState:
    user_id: str = ""
    thread_id: str = ""
    intent: str = "chat"
    message: str = ""
    steps: list[str] = field(default_factory=list)   # 记录走了哪些节点（可解释）
    artifacts: dict[str, Any] = field(default_factory=dict)
    reply: str = ""
    workflow_status: str = "pending"
```

**③ Agent：`app/agents/orchestrator_agent.py`**

```python
def run(state: SkillMapState) -> SkillMapState:
    state.steps.append("intent_recognize")
    state.intent = _recognize(state.message)   # 简单关键词识别，或用 LLM
    state.steps.append("reply")
    state.reply = _compose_reply(state)        # LLM 失败走规则模板
    state.workflow_status = "done"
    return state
```

**④ 图：`app/orchestrator/graph.py`** —— 核心！把节点连起来

```python
from langgraph.graph import StateGraph
from app.agents.orchestrator_agent import run as agent_node

def build_graph(checkpointer):
    g = StateGraph(SkillMapState)
    g.add_node("orchestrator_agent", agent_node)
    g.set_entry_point("orchestrator_agent")
    g.add_edge("orchestrator_agent", "__end__")
    return g.compile(checkpointer=checkpointer)  # 关键：挂 Checkpointer 才能续会话
```

**⑤ 接入层：`app/api/routes/chat.py`**（只做 HTTP 入出，不做业务）

```python
@chat_bp.post("/api/v1/chat")
def chat():
    body = ChatRequest(**request.get_json())      # Pydantic 校验
    graph = current_app.extensions["skillmap"]["graph"]
    final = graph.invoke(
        SkillMapState(user_id=body.user_id, thread_id=body.thread_id, message=body.message),
        config={"configurable": {"thread_id": body.thread_id}},  # 靠它恢复上下文
    )
    return ok({"route": "chat", "steps": final.steps, "reply": final.reply, ...})
```

**⑥ 建表：`scripts/init_db.py`**

```python
conn.execute("CREATE TABLE IF NOT EXISTS threads (thread_id VARCHAR(64) PRIMARY KEY, user_id VARCHAR(64) NOT NULL, ...)")
```

### 1.4 验证

```bash
python -m scripts.init_db && python -m app
curl http://localhost:5000/health          # {"status":"up",...}
curl -X POST http://localhost:5000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"U1","thread_id":"T1","message":"我想转向 AI 应用开发"}'
# 第二次带相同 thread_id 再发一句，能看到上下文延续（如"你刚才说想转 AI"）
```

### 1.5 常见坑

- **Checkpointer 不生效**：调用 `graph.invoke` 时必须传 `config={"configurable": {"thread_id": ...}}`，否则每次都是新会话。
- **分层被破坏**：业务层 import 了接入层 → 改成在 `create_app` 里把依赖注入 `app.extensions`。
- **macOS 端口 5000 被 AirPlay 占用**：用 `PORT=8081 python -m app`。

---

## 第 2 章 阶段 2：技术知识库与 RAG

> 目标：把技术资料入库、支持向量检索、并做"基于资料的问答"（带证据）。为后面阶段提供"技能 → 学习资料"。

### 2.1 先理解概念

- **分片（Splitter）**：长文档切成小块，每块 800 字符、重叠 100。
- **Embedding**：文本 → 向量。有 Key 用真实模型，没 Key 用**确定性哈希向量兜底**（保证链路不断）。
- **pgvector**：PostgreSQL 的向量扩展，支持 HNSW 索引做相似度检索。
- **RAG 问答**：检索 → 把命中的块塞给 LLM → 生成答案 + 证据列表。

### 2.2 手敲步骤

```
app/rag/
├── splitter.py      # 文本分片
├── embeddings.py    # 嵌入服务（含哈希兜底）
├── vectorstore.py   # 向量入库（upsert）
├── retriever.py     # 相似度检索（带 category/skill_tags 过滤）
├── qa_chain.py      # 检索 + LLM 生成答案
├── crawler.py       # trafilatura 抓网页正文
└── service.py       # 编排以上
app/api/routes/rag.py    # POST /rag/ingest | /rag/search | /rag/query
scripts/ingest_materials.py   # 读 materials/manifest.json 批量入库
```

### 2.3 关键代码

**向量化（带兜底）：`app/rag/embeddings.py`**

```python
def embed(text: str) -> list[float]:
    if config.embedding_enabled:
        try:
            resp = requests.post(f"{base}/embeddings", json={"model": model, "input": text}, timeout=10)
            return resp.json()["data"][0]["embedding"]
        except Exception:
            pass
    return _hash_embedding(text)      # 确定性兜底，链路不断

def _hash_embedding(text: str) -> list[float]:
    vec = [0.0] * 1024
    for token in re.findall(r"\w+", text.lower()):
        vec[hash(token) % 1024] += 1.0
    return vec
```

**检索：`app/rag/vectorstore.py`**（psycopg + pgvector 余弦距离）

```sql
SELECT chunk_id, doc_id, content, 1 - (embedding <=> %s::vector) AS score
FROM rag_chunks
WHERE (%s::text IS NULL OR category = %s)
  AND embedding IS NOT NULL
ORDER BY embedding <=> %s::vector
LIMIT %s;
```

### 2.4 验证

```bash
python -m scripts.init_db                      # 建 rag_documents / rag_chunks
python -m scripts.ingest_materials             # 入库（幂等）
# POST /api/v1/rag/ingest   → {doc_id, num_chunks}
# POST /api/v1/rag/search   → results[]（带 score）
# POST /api/v1/rag/query    → {answer, evidence[]}
```

### 2.5 常见坑

- **vector 扩展装错库**：`CREATE EXTENSION vector` 要在**目标业务库**（skillmap）执行，不是 postgres 库。
- **维度不一致**：建表时 `embedding vector(1024)` 要和嵌入模型输出维度一致。
- **检索为空**：检查 chunk 是否真的写入了 `embedding`（哈希兜底也会写，不会空）。

---

## 第 3 章 阶段 3：用户技术画像

> 目标：把自然语言/项目简介变成**结构化技能画像**，可版本化、带置信度、带证据。

### 3.1 先理解设计决策

- **LLM 只负责"抽出什么技能"**；等级换算、置信度合并、增量合并全部走**规则**（可重复）。
- **`skill_id` 必须命中技能字典**（`skills` 表），没命中的片段进 `unmatched_tokens`，不静默丢弃。
- **增量更新不覆盖**：只更新 patch 里出现的技能；分数为 null 不更新；每次影响 `version += 1`。

### 3.2 手敲步骤

```
app/profile/
├── schemas.py        # SkillProfilePatch / SkillProfile / SkillEvidence / UserPreference
├── rule_engine.py    # 等级换算、置信度合并
├── skill_service.py  # 技能字典检索
├── extractor.py      # LLM 抽取（结构化输出 + 规则兜底）
└── store.py          # user_skills/projects/user_preferences 读写
app/api/routes/profile.py   # extract | upsert | projects | GET <user_id>
scripts/seed_skills.py      # 由 JSON 生成技能字典种子（幂等）
```

### 3.3 关键代码

**规则引擎（非 LLM）：`app/profile/rule_engine.py`**

```python
def compute_level(theory: int, practice: int, w: float = 0.6) -> int:
    return min(5, int((theory * (1 - w) + practice * w) / 20))  # 上限 5

def merge_confidence(prev, new):
    return new if prev is None else 0.4 * prev + 0.6 * new    # 新证据更可信
```

**增量合并：`app/profile/store.py`**

```python
# 只处理 patch 中出现的 skill_id；分数为 null 跳过；每次影响 version += 1
for sk in patch.skills:
    row = fetch_user_skill(user_id, sk.skill_id)
    if sk.theory_score is not None:  theory = sk.theory_score
    if sk.practice_score is not None: practice = sk.practice_score
    # ... 更新 user_skills，回写 skill_evidence
```

### 3.4 验证

```bash
python -m scripts.init_db && python -m scripts.seed_skills
# POST /api/v1/profile/extract {"content":"我会 Java、Spring Boot、MySQL，做过订单系统"}
#   → {patch.skills:[...], unmatched_tokens:[...]}
# POST /api/v1/profile/upsert   → 合并后的完整 SkillProfile
# GET  /api/v1/profile/<user_id>
```

### 3.5 常见坑

- **LLM 返回的技能不在字典**：先 normalize（小写/去空格）再查字典，查不到进 `unmatched_tokens`。
- **confidence 为 0 被过滤**：演示数据要显式给 `confidence >= 0.4`（`PROFILE_MIN_CONFIDENCE`），否则技能进不了画像。

---

## 第 4 章 阶段 4：技能图谱与 Gap 分析

> 目标：输入「画像 + 目标岗位」，输出**结构化、带优先级、可解释、可重复**的 `SkillGapReport`。

### 4.1 先理解概念

- **技能图谱**：`skill_nodes`（节点）+ `skill_edges`（`requires` 前置关系）+ `role_skills`（岗位要求：level/weight）。
- **缺口判定**：岗位要求 level > 当前 level ⇒ 缺口；缺口还包括**缺失前置**的传递展开。
- **优先级**：`score`（weight + 等级差 + 前置降权）映射到 P1/P2/P3。
- **推荐顺序**：按前置关系做**拓扑排序**（`recommended_sequence`）。

### 4.2 手敲步骤

```
app/gap/
├── graph_store.py   # 从 skill_nodes/edges/role_skills 读图
├── gap_score.py     # 缺口评分（纯规则）
├── closure.py       # 前置依赖传递展开
├── explain.py       # 生成可读 reason
├── schemas.py       # SkillGapReport / GapItem
└── gap_agent.py     # 编排：画像 + 岗位 → report
app/api/routes/gap.py        # POST /gap/request
scripts/seed_skill_graph.py  # 由 JSON 灌入节点/边/岗位要求
```

### 4.3 关键代码

**缺口判定 + 评分：`app/gap/gap_score.py`**

```python
def gap_score(required_level, current_level, weight, is_prereq=False, decay=0.5):
    diff = max(0, required_level - current_level)
    score = weight * min(1.0, diff / required_level)
    if is_prereq:
        score *= decay          # 缺失前置降权
    return round(score, 3)

def to_priority(score: float) -> str:
    if score >= 0.6: return "P1"
    if score >= 0.3: return "P2"
    return "P3"
```

**前置传递展开：`app/gap/closure.py`** —— 找齐"学这个技能前必须先学的"。

```python
def expand_prerequisites(skill_id, graph, visited=None):
    visited = visited or set()
    if skill_id in visited: return []
    visited.add(skill_id)
    out = []
    for pre in graph.get_requires(skill_id):
        out.append(pre)
        out.extend(expand_prerequisites(pre, graph, visited))
    return out
```

### 4.4 验证

```bash
python -m scripts.seed_skill_graph
# POST /api/v1/gap/request {"user_id":"U1","target_roles":["RC013"]}
#   → reports[0].gaps[]（score/priority/reason/prerequisites/recommended_sequence）
```

### 4.5 常见坑

- **岗位 ID 不存在** → 422：先 `SELECT role_id FROM role_skills` 确认。
- **拓扑排序成环**：`recommended_sequence` 用 Kahn 算法，遇到环要有兜底（丢弃成环节点或按原始顺序）。

---

## 第 5 章 阶段 5：学习规划与 Todo

> 目标：把 `SkillGapReport` 变成**有依赖、可执行、可验收、可恢复、可局部重规划**的学习路线。

### 5.1 先理解设计

- **分桶**：同一技能可并行学习的任务放同一 phase，phase 间严格按前置顺序。
- **状态机**：任务 `pending → doing → done`，非法流转（跳过 doing）返回 422，重复 complete 幂等。
- **重规划**：只重建 `pending/doing` 任务，**`done` 任务保留不回退不重算**——这是用户体验关键。

### 5.2 手敲步骤

```
app/todo/
├── schemas.py       # LearningPlan / LearningTask / PlanMetrics
├── planner.py       # gap report → phases/tasks（纯规则）
├── scheduler.py     # 依赖排序 + 周预算摊派
├── todo_store.py    # 计划/任务读写 + 状态流转
└── explain.py       # 任务文案/目标（LLM 润色，模板兜底）
app/api/routes/plan.py   # generate | GET <id> | list | transition | replan
```

### 5.3 关键代码

**状态流转（带非法校验）：`app/todo/todo_store.py`**

```python
ALLOWED = {"pending": {"doing"}, "doing": {"done"}, "done": set()}

def transition(task, action):
    if action == "start":   target = "doing"
    elif action == "complete": target = "done"
    else: raise ValidationError("非法动作")
    if target not in ALLOWED[task.status]:
        raise ValidationError(f"非法流转 {task.status} → {target}")
    task.status = target   # 幂等：重复 complete 仍返回 done
```

**重规划保留 done：`app/todo/planner.py`**

```python
def replan(old_tasks, new_gap):
    kept = [t for t in old_tasks if t.status == "done"]   # 已完成保留
    rebuilt = build_from_gap(new_gap)                     # 重建 pending/doing
    return merge(kept, rebuilt)
```

### 5.4 验证

```bash
# POST /api/v1/plan/generate {"user_id":"U1","target_roles":["RC013"]}
#   → plan_id, phases[].tasks[]（每个任务有 estimated_hours/acceptance_criteria）
# POST /api/v1/plan/{id}/tasks/{tid}/transition {"action":"start"}  → doing
# POST /api/v1/plan/{id}/replan {}  → 只重建未完成任务
# GET  /api/v1/plan/list?user_id=U1
```

### 5.5 常见坑

- **重规划把 done 任务弄没了**：合并时**先取旧任务里 status==done 的**，再拼接新生成的。
- **单任务小时越界**：用 `PLAN_MIN_TASK_HOURS`/`PLAN_MAX_TASK_HOURS` 夹住（2~12h）。

---

## 第 6 章 阶段 6：实践任务与能力评估

> 目标：把任务变实践练习，对提交的代码做**结构化评估**，自动回写画像并触发再规划，**补全整个闭环**。

### 6.1 先理解设计

- **评估区分理论/实践**：`theory`（语法/结构/代码质量）与 `practice`（可运行性/测试），再按权重合成 `overall_score`。
- **证据驱动**：`evidence[]` 记录每项检查的 pass/fail 与说明，可解释。
- **评估后自动动作**：回写 `user_skills`（practice_score/confidence/evidence）→ 触发缺口重算 → 学习路线重规划。

### 6.2 手敲步骤

```
app/practice/
├── schemas.py       # PracticePlan / Deliverable / Rubric
├── planner.py       # task → 实践计划（交付物+评分标准）
└── explain.py       # 实践指引文案
app/evaluation/
├── schemas.py       # EvaluationReport / SkillScore / Evidence
├── analyzers.py     # 静态分析：语法/结构/可运行/测试/风格
├── scorer.py        # 证据 → 理论/实践/总分
├── service.py       # 编排评估
├── store.py         # practices/evaluations/code_snippets 读写
└── update.py        # 回写画像 + 触发再规划（闭环关键）
app/api/routes/evaluation.py   # practice_bp + eval_bp
```

### 6.3 关键代码

**静态分析核心：`app/evaluation/analyzers.py`** —— 用 AST 检查 Python 代码

```python
import ast

def analyze_syntax(content: str) -> Evidence:
    try:
        ast.parse(content)
        return Evidence("syntax", True, "代码可编译")
    except SyntaxError as e:
        return Evidence("syntax", False, f"语法错误: {e.msg}")

def analyze_tests(files: dict) -> Evidence:
    n = sum(1 for f in files if f.startswith("test") or "test" in f.lower())
    return Evidence("tests", n > 0, f"发现测试用例 {n} 个")
```

**评分合成：`app/evaluation/scorer.py`**

```python
def overall(theory, practice, theory_w=0.4):
    return round(theory * theory_w + practice * (1 - theory_w))
```

**闭环回写（最重要）：`app/evaluation/update.py`**

```python
def apply_evaluation(user_id, skill_id, report):
    upsert_user_skill(user_id, skill_id, practice=report.practice, confidence=0.8, evidence=[report.evaluation_id])
    if trigger_replan:
        gap = recompute_gap(user_id, target_role)
        replan_learning_plan(user_id, gap_report=gap)   # 保留 done 任务
    record_memory_event("evaluation_done", ...)          # 沉淀成长经历
```

### 6.4 验证

```bash
# POST /api/v1/practice/generate {"task_id":"...","skill_id":"python"} → practice_id
# POST /api/v1/evaluation/artifact {practice_id, language, filename, content, test_content}
# POST /api/v1/evaluation/evaluate {practice_id, trigger_replan:true}
#   → overall_score, evidence[], profile_updated:true, replanned:true
```

### 6.5 常见坑

- **评估失败不能把画像搞坏**：`update.py` 里回写失败要单独 try/except，不回滚已成功的评估。
- **测试文件识别**：文件名含 `test` 或路径含 `tests/` 才算测试文件，别把 `test_content` 忘存。

---

## 第 7 章 阶段 7：长期记忆与 Middleware

> 目标：让系统**长期记住**用户，并在写入/对话链路上加三类横切能力：PII 脱敏、摘要压缩、HITL 人工确认。

### 7.1 先理解概念

- **三种记忆命名空间**：`semantic`（事实）、`procedural`（偏好，复用 user_preferences）、`summary`（对话摘要）。
- **Episodic（经历）**：`memory_events` 表沉淀成长事件（画像更新、评估完成……），阶段 3~6 接口成功后 best-effort 自动写入。
- **三个 Middleware**：
  - **PII 脱敏**：写记忆前把邮箱/手机/身份证替换成 `[REDACTED:email]`。
  - **摘要压缩**：消息轮数 ≥ 阈值（默认 20）自动生成/存储对话摘要。
  - **HITL**：高风险操作（如重置计划）先写入 `pending_actions` 暂停，等人工 approve/reject 再执行。

### 7.2 手敲步骤

```
app/memory/
├── store.py           # memories/memory_events/pending_actions 读写（HNSW 向量索引）
├── semantic.py        # 事实记忆（向量化 + 语义召回）
├── episodic.py        # 经历记忆
├── procedural.py      # 偏好记忆
├── service.py         # 记忆读写编排
├── schemas.py
└── middleware/
    ├── pii.py         # 脱敏
    ├── summary.py     # 摘要
    └── hitl.py        # 人工确认
app/api/routes/memory.py   # remember/search/summarize/events/pending/confirm
```

### 7.3 关键代码

**PII 脱敏：`app/memory/middleware/pii.py`**

```python
PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "email"),
    (re.compile(r"1[3-9]\d{9}"), "phone"),
]

def redact(text: str) -> tuple[str, bool]:
    hit = False
    for pat, kind in PATTERNS:
        if pat.search(text):
            text = pat.sub(f"[REDACTED:{kind}]", text)
            hit = True
    return text, hit
```

**语义检索（向量 + 关键词兜底）：`app/memory/semantic.py`**

```python
def search(user_id, query, top_k):
    if memory_embed_enabled:
        vec = embed(query)
        rows = sql("SELECT ... FROM memories WHERE user_id=%s AND embedding IS NOT NULL ORDER BY embedding <=> %s LIMIT %s", ...)
        if rows: return rows
    return sql("SELECT ... WHERE user_id=%s AND text ILIKE %s LIMIT %s", ...)   # 退化
```

### 7.4 验证

```bash
# POST /api/v1/memory/remember {namespace:"semantic", key:"goal", text:"...含邮箱..."}
#   → pii_redacted:true
# POST /api/v1/memory/search {namespace:"semantic", query:"目标"}
# POST /api/v1/memory/events {event_type:"evaluation_done", summary:"..."}
# POST /api/v1/memory/pending {action_type:"plan_reset", summary:"..."}
# POST /api/v1/memory/pending/<pa_id>/confirm {decision:"approve"}
```

### 7.5 常见坑

- **HNSW 索引 + 部分索引**：`WHERE embedding IS NOT NULL` 的部分索引在 INSERT 时要注意，NULL 向量不索引。
- **记忆读写短路**：`MEMORY_ENABLED=false` 时接口仍返回标准结构（空结果），不 500。

---

## 第 8 章 阶段 8：前端整合与比赛 Demo

> 目标：把 1~7 的后端能力整合成**可操作产品页 + 3~5 分钟演示链路**。

### 8.1 新增的最小后端点（业务全部复用）

- `GET /api/v1/graph` —— 全量图谱（只读，供前端 SVG 渲染）
- `GET /api/v1/dashboard/<user_id>` —— 聚合画像/计划/评估/成长/记忆（只读快照，不落库）
- `GET /api/v1/plan/list` —— 计划列表（只读）
- `POST /api/v1/chat/stream` —— **SSE 流式**回复

**SSE 实现要点（`app/agents/streamer.py`）**：

```python
def stream(events: list[dict]):
    def gen():
        yield "data: " + json.dumps({"type": "meta", "intent": "...", "route": "..."}) + "\n\n"
        for delta in chunks:  # 增量文本
            yield "data: " + json.dumps({"type": "delta", "text": delta}) + "\n\n"
        yield "data: " + json.dumps({"type": "done", "thread_id": tid}) + "\n\n"
    return Response(gen(), mimetype="text/event-stream")
```

前端用 `fetch` + `ReadableStream` 逐块解析 `type: meta/delta/done`；异常收到 `type: error` 就回退非流式 `/chat`。

### 8.2 手敲步骤（前端）

```
frontend/src/
├── main.js                    # 挂载 Vue + Pinia + Router
├── router/index.js            # 6 条路由（工作台/对话/图谱/缺口/计划/实践评估/健康）
├── api/http.js                # axios 实例 + 统一信封解包 + ApiError
├── api/{dashboard,graph,plan,practice,chat}.js
├── services/{chatService,healthService}.js
├── stores/{chat,dashboard,graph,plan,practiceEval,health}.js
├── views/{DashboardView,ChatView,SkillGraphView,GapReportView,LearningPlanView,PracticeEvalView,HealthView}.vue
└── components/{SkillGraph,PlanTimeline,GapReportTable,EvalReportCard,...}.vue
```

**Pinia store 示例（`stores/plan.js`）**：视图只调 store，store 调 api，视图不碰 axios。

```js
export const usePlanStore = defineStore('plan', {
  state: () => ({ plan: null, loading: false, error: null }),
  actions: {
    async generate(payload) {
      this.loading = true
      try { this.plan = await planApi.generate(payload) }
      catch (e) { this.error = e.message }
      finally { this.loading = false }
    },
  },
})
```

**SVG 技能图谱（`components/SkillGraph.vue`）**：节点坐标用手写**力导向**迭代收敛，颜色按 `category` 映射（用 computed，避免异步数据加载时全灰）。

### 8.3 演示脚本

```
scripts/demo_init.py   # 幂等造数：建表+种子+知识库+demo_user 画像+示例代码
scripts/run_demo.py    # 服务起来后自动核对 7 段链路（Dashboard→图谱→Gap→计划→实践→评估→成长）
tests/test_demo_e2e.py # 端到端测试守护
```

```bash
python -m scripts.init_db
python -m scripts.seed_skills
python -m scripts.seed_skill_graph
python -m scripts.demo_init
python -m app                     # 或 PORT=8081 python -m app
# 另开终端：
python -m scripts.run_demo        # 7 段全 ✓
cd frontend && npm run dev        # 打开 http://localhost:5173 演示页面
```

### 8.4 常见坑

- **前端代理**：Vite 要把 `/api` 代理到后端（默认 8081），否则跨域/404。
- **SSE 事件没 type**：`streamer` 里必须把事件名写进 `data.type`，前端才好分发。
- **图表异步全灰**：颜色映射要用 computed 基于 props 计算，别在 setup 里一次性初始化。
- **演示链路中断**：LLM 增强接口慢（可到 90s），想更快可 `PLAN_LLM_ENABLED=false` 等开关走纯规则。

---

## 第 9 章 总复习：一张表看完整项目

| 阶段 | 你学会了什么 | 关键文件 |
| --- | --- | --- |
| 1 | Flask 工厂 / LangGraph / Checkpointer / 分层 | `orchestrator/graph.py` |
| 2 | 向量库 / 分片 / RAG 问答 / 哈希兜底 | `rag/vectorstore.py` |
| 3 | Pydantic / 规则引擎 / 增量合并 / 证据 | `profile/rule_engine.py` |
| 4 | 图模型 / 前置传递 / 拓扑排序 / 优先级 | `gap/gap_score.py` |
| 5 | 任务分桶 / 状态机 / 局部重规划 | `todo/todo_store.py` |
| 6 | 静态分析 / 理论实践分 / 闭环回写 | `evaluation/update.py` |
| 7 | 三类记忆 / PII / 摘要 / HITL | `memory/middleware/pii.py` |
| 8 | Vue3 整合 / SSE / 力导向图 / 演示脚本 | `agents/streamer.py` |

**答辩/面试三句话总结这个项目**：

1. 它把「画像→缺口→规划→实践→评估→再规划」做成**规则可重复、LLM 只增强**的闭环，没有 Key 也能跑。
2. 工程上坚持**分层单向依赖 + 契约先行 + 统一错误码 + 幂等**，8 个阶段每个都能独立验证、增量演进。
3. 阶段 8 把它做成了可演示产品：6 个页面 + SSE 流式 + 技能图谱可视化 + 一键 Demo 数据。

### 推荐的后续练习

- 给阶段 3 加一个"语音输入画像"的接口。
- 给阶段 4 的图加一个可视化编辑后台。
- 把 Checkpointer 换成 Redis/云存储，验证会话在**多实例**间恢复。
- 给评估器加一个 `language=javascript` 的 ESLint 静态检查。

---

> 学完还不满足？去看 `项目规划/` 下每个阶段的《详细计划》，那里有**先于代码的契约与验收标准**，是本项目"契约先行"的第一手教材。
