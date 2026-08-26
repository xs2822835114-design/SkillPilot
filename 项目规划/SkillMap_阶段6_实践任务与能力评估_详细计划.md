# SkillMap 阶段 6 详细实施计划 — 实践任务与能力评估

> 对应：《SkillMap_个人技术栈成长智能体_项目计划书》阶段 6"实践任务与能力评估"
> 版本：V1.0
> 风格：模块解耦 + 契约先行 + 并行开发（与阶段 4/5 详细计划保持一致的行文规范）

---

## 1. 阶段定位与目标

**一句话目标**：建立"学了以后必须做"的闭环——把阶段 5 的 `LearningTask` 转化为可交付、带验收标准的实践任务（`PracticePlan`），再通过代码/项目/测试证据做**结构化能力评估**（`EvaluationReport`，区分理论掌握与实践掌握），并自动回写画像、触发缺口再计算与学习路线重规划。

**为什么必须先做阶段 6**：阶段 5 生成了"待做"的学习任务，但没有回答"做到什么程度、如何证明真会了"。如果只靠 `Evaluation` 前一步的规则把任务标为 `done`，就是"自评完成"而非"证据完成"。阶段 6 用两件事补齐闭环：Practice Agent 负责"把任务转成可交付物与验收标准"；Evaluation Agent 负责"用证据（代码结构、可运行性、测试）判分并回写画像"——从而让 `Gap → Plan → Practice → Evaluation → Re-plan` 真正自治：评估产出新缺口、评估触发再规划。

**本阶段核心目标拆解**

| # | 目标 | 验收可测性 |
| --- | --- | --- |
| G1 | 任务→实践计划 | 每个 `LearningTask` 可生成含 `deliverables + rubric` 的 `PracticePlan` |
| G2 | 结构化评估 | 代码/项目产出 `EvaluationReport`：`overall_score + skill_scores + evidence`，对象化（非散文） |
| G3 | 区分理论/实践 | `skill_scores` 分离 `theory` 与 `practice`，且均绑定 `evidence` |
| G4 | 评估→画像更新 | `report` 生成后自动更新 `user_skills`（practice_score/confidence/evidence） |
| G5 | 评估→再规划 | 画像更新后触发 gap 再计算→ `replan`（可开关） |
| G6 | MVP 静态分析 | 至少支持 Python 基础静态分析（语法/结构/可运行性/测试） |
| G7 | 契约稳定 + 兜底 | 有测试；主体规则实现，LLM 仅润色文案，失败走模板兜底 |

---

## 2. 范围边界

### 2.1 本阶段做什么（In Scope）

- 建表：`practices` / `evaluations` / `code_snippets`（幂等，`projects` 阶段 3 已有）
- `Practice Agent`：`LearningTask`（skill_id/acceptance_criteria/level）→ `PracticePlan`（deliverables + rubric）
- `Evaluation Agent`：代码/仓库/片段 → 静态分析 → 结构化评分 + 证据
- 规则评分：`theory_score / practice_score / overall_score`（纯规则，可重复）
- 证据收集：`[{type, message}]` 与 `skill_scores` 绑定
- 评估后回写：复用阶段 3 `skill_service.apply_patch` 更新 `practice_score/confidence/evidence`
- 评估后再规划：触发 gap 再计算 → 阶段 5 `replan`（`evaluate_trigger_replan` 开关）
- 代码片段上传（无仓库时的兜底 artifact）与 GitHub 仓库接入/URL 拉取
- `POST /api/v1/practice/*`、`POST /api/v1/evaluation/*` 接口
- 契约文档 + 集成测试（TC-E1~E10）
- 补 `evaluation`/`practice` 相关 `AgentRoute` 列表项（阶段 1 orchestrator 意图白名单）

### 2.2 本阶段明确不做（Out of Scope）

| 不做 | 原因 | 何时做 |
| --- | --- | --- |
| 多语言静态分析 | MVP 只保证一种语言（Python） | 后续迭代 |
| 自动运行测试并断言 | MVP 检测"是否有测试/测试文件"，不真跑 CI | 后续迭代 |
| AI 代码生成/注释大模型评审 | 评估主体用规则，LLM 仅润色建议文案 | 与阶段 4/5 原则一致 |
| 完整长期记忆（评估结果记忆化沉淀） | 结果落库即可，不做记忆层 | 阶段 7 |
| 前端实践/评估交互页 | 后端契约先行 | 阶段 8 |
| Agent 类化（`PracticeAgent`/`EvaluationAgent` 类） | 以模块+接口交付，与阶段 3~5 一致 | 阶段 8 编排收口 |

> 边界原则（对齐计划书）：评估给分、理论/实践区分、证据采集一律**规则驱动、可重复**；LLM 只负责润色建议文案，**不决定评分与证据**。

---

## 3. 技术选型与工程结构

### 3.1 技术栈（阶段 1~5 基础上，无新增依赖）

| 项 | 选型 | 说明 |
| --- | --- | --- |
| 存储 | PostgreSQL（复用 `psycopg` 直连 `persistence/db.py`） | 沿用既有风格 |
| 静态分析 | Python 标准库 `compile` + `ast` +（可选)`pyflakes`，缺依赖时降级 | 保证语法/结构/可运行性基础检查 |
| 仓库拉取 | 纯 HTTP（`urllib`）读 `/raw/**` / 上传片段两种 artifact 输入 | 不引入 git 子进程 |
| 评分 | 纯 Python 规则（复用阶段 3 `rule_engine.level_from_scores`） | G7 可重复 |
| 回写/再规划 | 复用阶段 3 `skill_service.apply_patch` + 阶段 5 `planner.replan` | 不回造轮子 |
| LLM | 仅建议文案润色，复用阶段 1 `LLMClient` | 失败走模板兜底 |

> 关键复用：
> - **阶段 3**：`apply_patch`（评分回写画像）、`level_from_scores`、`user_skills`/`projects`.
> - **阶段 4**：`gap_agent.analyze`（评估后 gap 再计算）。
> - **阶段 5**：`planner.replan`（画像更新后学习路线再规划）。

### 3.2 工程结构（新增/修改点）

```
app/
├── config.py                    # 修改：新增 PRACTICE_*/EVAL_* 配置（可选）
├── api/routes/
│   ├── practice.py              # 新增：POST /api/v1/practice/generate · GET /practice/<id>
│   ├── evaluation.py            # 新增：POST /api/v1/evaluation/artifact · POST /evaluation/evaluate
│   └── __init__.py              # 修改：注册 practice_bp / evaluation_bp
├── practice/                    # 新增：【Practice Agent 能力】不感知 HTTP
│   ├── __init__.py
│   ├── schemas.py               # 契约：PracticeCreateRequest / PracticePlan / PracticeDeliverable / RubricCriterion
│   ├── planner.py               # 编排：LearningTask → PracticePlan（deliverables + rubric，规则为主）
│   └── explain.py               # deliverables/提示文案模板 + LLM 润色兜底
├── evaluation/                  # 新增：【Evaluation Agent 能力】不感知 HTTP
│   ├── __init__.py
│   ├── schemas.py               # 契约：EvaluationRequest / ArtifactUpload / SkillScore / EvidenceItem / EvaluationReport
│   ├── analyzers.py             # Python 静态分析（compile/ast/pyflakes降级）→ 结构化 CheckResult[]
│   ├── scorer.py                # 规则评分：theory/practice/overall + next_recommendations
│   ├── update.py                # 评估→回写画像（apply_patch）+ gap 再计算→replan（开关）
│   └── store.py                 # code_snippets / evaluations 持久化
└── persistence/…                # 复用 db.connect
scripts/
├── init_db.py                   # 修改：追加 practices / evaluations / code_snippets 建表
├── seed_skill_graph.py          # 复用（评估示例依赖场景）
tests/
└── test_practice.py  test_evaluation.py  # 新增：TC-E1~E10（可拆成实践/评估两组）
```

分层依赖（延续单向规则）：

```
API 层 routes/practice.py · routes/evaluation.py
   │  只调
   ▼
能力层 app/practice/（planner ← explain）｜ app/evaluation/（analyzers → scorer → update → store）
   │  只调
   ▼
复用层 app/profile/* · app/gap/* · app/todo/* ｜ 持久化 app/persistence/db.py
```

跨层只读依赖：
- `app/practice/planner.py → app/todo/LearningTask`（读取任务，不改动）。
- `app/evaluation/update.py → app/profile/skill_service`（回写）＋ `app/gap/gap_agent`（再计算）＋ `app/todo/planner.replan`（再规划）。

**接线点（改动最小化）**
- `app/__init__.py`:注册 `practice_bp`、`evaluation_bp`。
- `app/orchestrator/intents.py`（或等价路由白名单）：补 `practice_generation`、`evaluation` 意图。
- `scripts/init_db.py`:追加三张表。
- `docs/api_v1.md`:补 practice/evaluation 接口。

---

## 4. 模块解耦与分工

### 4.1 各模块职责、输入、输出、不负责什么

#### Practice Agent 侧

| 模块 | 职责 | 主要输入 | 主要输出 | 不负责什么 |
| --- | --- | --- | --- | --- |
| API（`routes/practice.py`） | 收 HTTP、校验、调 Practice 层 | HTTP JSON | 统一 response | 不做交付物生成细节 |
| `planner.py` | LearningTask→PracticePlan | LearningTask | PracticePlan（deliverables+rubric） | 不判代码质量 |
| `explain.py` | 交付物/提示文案模板 + LLP 润色兜底 | skill/level/acceptance | 文案字符串 | 不生成可运行代码 |

#### Evaluation Agent 侧

| 模块 | 职责 | 主要输入 | 主要输出 | 不负责什么 |
| --- | --- | --- | --- | --- |
| API（`routes/evaluation.py`） | artifact 入库 + 触发评估 | HTTP + artifact | 统一 response | 不做静态分析细节 |
| `analyzers.py` | Python 静态分析 | 代码文本/仓库文件 | `CheckResult[]`（结构化） | 不给最终分数 |
| `scorer.py` | 规则评分 + 建议 | CheckResult[] | theory/practice/overall + recommendations | 不写画像 |
| `update.py` | 回写画像 + 再规划编排 | EvaluationReport | 新画像快照 + 最新 planning | 不做评分细节 |
| `store.py` | snippets/evaluations 持久化 | 对象 | 落库记录 | 不调 LLM |

**模块间数据流**（单向、无环）
```
LearningTask ─→ practice/planner ─→ PracticePlan（含 deliverable + rubric，即验收标准）
                                          │（提交物）
                                          ▼
                          UploadArtifact / 仓库 URL ─→ evaluation/analyzers ─→ CheckResult[]
                                                                   │
                                           update ◀── scorer（theory/practice/overall + evidence）
                                              │
                        ┌─────────────────────┼──────────────────────┐
                        ▼                     ▼                       ▼
              profile.apply_patch        gap_agent.analyze      (可选) todo.planner.replan
           （回写 practice_score↑）      （再计算缺口）
```

---

## 5. 接口契约（契约先行，冻结后并行开发）

### 5.1 Practice Agent

**POST `/api/v1/practice/generate`**

```jsonc
{
  "user_id": "U10001",
  "task_id": "PLAN_xxx-T03",   // 阶段 5 LearningTask
  "skill_id": "rag_retriever",
  "level_target": 3,           // 目标等级（来自缺口）
  "format": "project"          // 现阶段固定 project
}
```

**响应 `PracticePlan`**

```jsonc
{
  "practice_id": "PRA_xxx",
  "user_id": "U10001",
  "task_id": "PLAN_xxx-T03",
  "skill_id": "rag_retriever",
  "level_target": 3,
  "created_at": "…",
  "is_llm_enhanced": false,
  "deliverables": [
    { "key": "code_repo", "desc": "可运行的 RAG 检索 demo 代码库" },
    { "key": "readme",    "desc": "README：说明检索流程、依赖、运行方式" },
    { "key": "tests",     "desc": "含 1+ 个可运行的检索正确性测试" }
  ],
  "rubric": [
    { "criterion": "功能实现", "weight": 0.4 },
    { "criterion": "代码结构与可读性", "weight": 0.2 },
    { "criterion": "测试覆盖", "weight": 0.25 },
    { "criterion": "文档可运行性", "weight": 0.15 }
  ],
  "guide": "…"  // 可选：LLM 润色后的实践指引，失败走模板
}
```

> 约束：`load(task_id)` 校验 `skill_id` 一致；`format` 现阶段仅 `project`，否则 422。
> rubric 的 criterion/weight 由 `level_target` 规则生成（无需 LLM）。

### 5.2 Evaluation Agent

**POST `/api/v1/evaluation/artifact`**（上传代码片段，无仓库兜底）

```jsonc
{
  "user_id": "U10001",
  "practice_id": "PRA_xxx",
  "language": "python",
  "filename": "retriever.py",
  "content": "def search(...): ...",
  "test_content": "def test_search(): ..."   // 可选：测试代码
}
```

**POST `/api/v1/evaluation/evaluate`**

```jsonc
{
  "user_id": "U10001",
  "practice_id": "PRA_xxx",
  "artifact_type": "github",     // github | snippet
  "artifact_ref": "https://github.com/u/repo",
  "repo_files": { "app/main.py": "…", "tests/test_main.py": "…" }, // snippet 时用；github 时可选
  "trigger_replan": true         // 评估后是否自动重算缺口+重规划（默认 true）
}
```

**响应 `EvaluationReport`**

```jsonc
{
  "evaluation_id": "EVL_xxx",
  "practice_id": "PRA_xxx",
  "skill_id": "rag_retriever",
  "overall_score": 76,
  "skill_scores": [
    { "skill_id": "rag_retriever", "theory": 80, "practice": 70 }
  ],
  "evidence": [
    { "type": "syntax",     "passed": true,  "message": "源码可编译" },
    { "type": "structure",  "passed": true,  "message": "存在 3 个函数、1 个类" },
    { "type": "runnable",   "passed": true,  "message": "存在可执行的 __main__/入口" },
    { "type": "tests",      "passed": true,  "message": "发现测试文件 test_main.py（2 个用例）" },
    { "type": "lint",       "passed": false, "message": "存在未使用导入 os / TODO 注释" }
  ],
  "next_recommendations": [
    "测试覆盖不足：建议为 search 补充 2 个边界用例后再评估",
    "存在未使用导入，建议清理后提交"
  ],
  "profile_updated": true,     // 是否已回写画像
  "replanned": true            // 是否已触发学习路线重规划
}
```

> 语义：
> - `skill_scores` 必须含 `theory` 与 `practice` 两个维度，且各自能追溯到 `evidence`。
> - `trigger_replan=false` 时仅回写画像、不重规划（`replanned=false`）。

**错误码（合并）：**

| 场景 | HTTP | code |
| --- | --- | --- |
| 非 JSON body | 400 | 40001 |
| 参数非法/实践或任务不存在/格式不支持 | 422 | 42200 |
| practice 不存在（查询） | 404 | 40420 |
| 评估/静态分析失败（走兜底） | 500 | 50060 |
| 实践生成失败（走兜底） | 500 | 50050 |

---

## 6. 数据模型（幂等建表，`scripts/init_db.py`）

```sql
CREATE TABLE IF NOT EXISTS practices (
  id           VARCHAR(64) PRIMARY KEY,
  plan_id      VARCHAR(64),
  task_id      VARCHAR(64),
  user_id      VARCHAR(64) NOT NULL,
  skill_id     VARCHAR(64),
  format       VARCHAR(24) NOT NULL DEFAULT 'project',
  level_target SMALLINT NOT NULL DEFAULT 1,
  deliverables_json JSONB,
  rubric_json       JSONB,
  status       VARCHAR(24) NOT NULL DEFAULT 'pending',
  is_llm_enhanced  BOOLEAN NOT NULL DEFAULT false,
  created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_practices_user ON practices(user_id);

CREATE TABLE IF NOT EXISTS evaluations (
  id           VARCHAR(64) PRIMARY KEY,
  practice_id  VARCHAR(64),
  user_id      VARCHAR(64) NOT NULL,
  artifact_type VARCHAR(24) NOT NULL DEFAULT 'snippet',  -- github | snippet
  artifact_ref TEXT,
  skill_id     VARCHAR(64),
  overall_score SMALLINT,
  report_json  JSONB,
  profile_updated BOOLEAN NOT NULL DEFAULT false,
  replanned       BOOLEAN NOT NULL DEFAULT false,
  created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_evaluations_user ON evaluations(user_id);

CREATE TABLE IF NOT EXISTS code_snippets (
  id           VARCHAR(64) PRIMARY KEY,
  user_id      VARCHAR(64) NOT NULL,
  practice_id  VARCHAR(64),
  language     VARCHAR(24) NOT NULL DEFAULT 'python',
  filename     VARCHAR(255),
  content      TEXT,
  created_at   TIMESTAMPTZ DEFAULT now()
);
```

> 说明：`projects` 阶段 3 已存在，本阶段复用；`evaluations.report_json` 存完整 `EvaluationReport`（含 evidence/recommendations）。

---

## 7. 配置（`config.py` + `.env.example`）

| 配置 | 默认 | 说明 |
| --- | --- | --- |
| `EVAL_STATIC_STRICT` | true | 静态分析是否启用警告级检查 |
| `EVAL_THEORY_WEIGHT` | 0.4 | theory 在 overall 中的权重（practice=1-w） |
| `EVAL_TRIGGER_REPLAN_DEFAULT` | true | evaluate 默认是否触发再规划 |
| `EVAL_MIN_CONFIDENCE_DELTA` | 0.0 | 评分回写的一致性校验（可选） |
| `PRACTICE_DEFAULT_LEVEL_TARGET` | 3 | 未显式传 level_target 时的默认目标等级 |
| `PRACTICE_LLM_ENABLED` / `EVAL_LLM_ENABLED` | true | 是否润色文案（false=模板） |

> 回写 confidence 复用阶段 3 合并公式（`merge_confidence`）；`practice_score` 直接覆盖式回写（评估即以证据为准）。

---

## 8. 开发任务拆解（按依赖排序，可并行分支）

| 任务 | 产出 | 依赖 |
| --- | --- | --- |
| 1. `init_db.py` 追加三张表 + 幂等验证 | 表结构 | 无 |
| 2. 冻结契约 `app/practice/schemas.py`、`app/evaluation/schemas.py` | Pydantic 契约 | 1 |
| 3. 静态分析 `evaluation/analyzers.py`（compile+ast，pyflakes 降级）→ CheckResult[] | 结构化检查器 | 2 |
| 4. 规则评分 `evaluation/scorer.py`（theory/practice/overall + recommendations） | 评分器 | 2,3 |
| 5. 回写与再规划 `evaluation/update.py`（apply_patch→gap→replan） | 回写编排 | 2,4 |
| 6. 持久化 `evaluation/store.py`（snippets/evaluations） | 存储 | 2 |
| 7. Practice 生成 `practice/planner.py`（deliverables+rubric，规则）+ `explain.py` 润色 | PracticePlan | 2 |
| 8. 接口 `routes/practice.py`、`routes/evaluation.py` + 注册 + 意图白名单 | 路由 | 1~7 |
| 9. 测试 `test_practice.py`/`test_evaluation.py`（TC-E1~E10） | 测试 | 1~8 |
| 10. 文档 `docs/api_v1.md` + `.env.example` 补配置 | 文档 | 8 |

> 并行建议：任务 3/4/5（评估核心）与 7（实践生成）可并行；测试用例与主开发并行准备。

---

## 9. 测试计划

**纯规则用例（无需 DB）**
- TC-E1 静态分析结构：合法 Python → syntax/structure/runnable/tests 检查通过。
- TC-E2 评分含证据：`overall/theory/practice` 有值且 `evidence` 非空。
- TC-E3 区分理论/实践：缺失测试/不可运行 → `practice < theory` 且对应 evidence。
- TC-E4 建议生成：缺测试 → recommendations 提示补测试；有未使用导入 → 提示清理。

**集成用例（依赖真实 DB + 种子）**
- TC-E5 评估→画像更新：evaluate 后 `user_skills.practice_score` 上升、evidence 含 `EVL_xxx`。
- TC-E6 评估→再规划：`trigger_replan` 后返回 `replanned=true`，且 `todo.replan` 保留 done 任务。
- TC-E7 评估→关闭再规划：`trigger_replan=false` → `replanned=false`，仅回写画像。
- TC-E8 幂等/可重复：同 artifact 重复 evaluate → 评分不变（或仅在 evidence 追加，不重复改分）。
- TC-E9 LLM 兜底：`EVAL_LLM_ENABLED/PRACTICE_LLM_ENABLED=false` → `is_llm_enhanced=false`、报告完整。
- TC-E10 snippet 兜底：无仓库、仅上传片段 → 仍产出完整 `EvaluationReport`。
- TC-E11（路由）：非 JSON → 400；缺字段/非法 format → 422；practice 不存在 → 404。

---

## 10. 验收标准（对照计划书阶段 6）

| AC | 验收项 | 对应用例 |
| --- | --- | --- |
| AC1 | 代码评估输出必须结构化 | TC-E1/E2 `evidence` 为 `[{type,message}]` |
| AC2 | 评分含 evidence | TC-E2 每 score 可追溯证据 |
| AC3 | 能区分理论掌握与实践掌握 | TC-E3 `theory`/`practice` 分离 |
| AC4 | 评估完成后自动触发画像更新 | TC-E5 `user_skills` 更新 |
| AC5 | 评估后自动再计算缺口/再规划 | TC-E6 `replanned=true` 且保留 done |
| AC6 | 至少支持一种代码语言的基础静态分析 | TC-E1 Python compile/ast 检查 |
| AC7 | 契约稳定 + 兜底可测 | TC-E9~E11 |

---

## 11. 风险与兜底

| 风险 | 影响 | 缓解/兜底 |
| --- | --- | --- |
| 仓库无法拉取（网络/私有） | 评估无输入 | 支持上传片段（snippet）兜底；`repo_files` 直传也可 |
| 静态分析依赖缺失 | 检查降级 | `compile`+`ast` 为标准库，`pyflakes` 缺失即跳过 lint 类，不报错 |
| 自动回写误伤画像 | 等级漂移 | 回写用 `apply_patch`（覆盖 practice_score、追加 evidence）；保留 `trigger_replan` 开关 |
| LLM 失败 | 文案缺失 | 仅润色 guide/recommendations，失败走模板；评分与证据永不依赖 LLM |
| "自评 done"错觉 | 数据失真 | 画像更新以评估证据为准，阶段 5 任务状态不因评估自动 done（由用户/评估建议推进） |

---

## 12. 前置依赖与交付清单

- 前置依赖：阶段 5（`LearningTask`、`replan`）；阶段 3（`apply_patch`）；阶段 4（`gap_agent`）。
- 交付清单：
  - `scripts/init_db.py`（三张表）+ `docs/api_v1.md`（practice/evaluation 接口 + 错误码）
  - `app/practice/`（schemas/planner/explain）+ `app/evaluation/`（schemas/analyzers/scorer/update/store）
  - `routes/practice.py`、`routes/evaluation.py`、`orchestrator` 意图白名单补充
  - `PRACTICE_*`/`EVAL_*` 配置 + `.env.example`
  - `tests/test_practice.py`、`tests/test_evaluation.py`（TC-E1~E11）