# SkillMap 阶段 5 详细实施计划 — 学习规划与 Todo

> 对应：《SkillMap_个人技术栈成长智能体_项目计划书》阶段 5"学习规划与 Todo"
> 版本：V1.0
> 风格：模块解耦 + 契约先行 + 并行开发（与阶段 4 详细计划保持一致的行文规范）

---

## 1. 阶段定位与目标

**一句话目标**：把阶段 4 的 `SkillGapReport`（有序缺口）转换为**有依赖关系、可执行、可验收、可恢复进度、可局部重规划**的学习路线（`LearningPlan`），并提供 Todo 任务持有与状态流转（`pending → doing → done`）。

**为什么必须先做阶段 5**：阶段 4 回答了"缺什么、先补什么"，但用户需要的是"按什么顺序、每周花多少小时、每条任务做到什么程度算完成"。学习路线不是把缺口列表平铺——同一缺口"RAG"，拆成"先学 Embedding 再学 Retriever"才有可执行性；每条任务要有目标、资源、预计时间与验收标准，才能被评估闭环（阶段 6）判定是否真正掌握并触发再规划。只有把"有序缺口 + 用户时间预算 + 学习偏好 + RAG 资料"组合成可持久化、可流转的任务，才能形成 `Gap → Plan → Practice → Evaluation → Re-plan` 的执行闭环。

**本阶段核心目标拆解**

| # | 目标 | 验收可测性 |
| --- | --- | --- |
| G1 | 计划符合依赖 | `LearningPlan` 的 phase/task 顺序满足技能前置关系（消费 `recommended_sequence` 拓扑序） |
| G2 | 任务可执行 | 每项 `LearningTask` 有目标/资源链接/预计时间/验收标准 |
| G3 | 进度可恢复 | 计划与任务落库；服务重启后按 `plan_id` 可恢复状态 |
| G4 | 状态可流转 | `pending → doing → done` 合法流转，含非法流转拒绝 |
| G5 | 计划可调整 | 用户反馈后支持局部重规划，不覆盖已 done 任务 |
| G6 | 契约稳定 + 兜底 | 有测试；规划主体规则实现，LLM 仅润色任务描述/资源，失败走模板兜底 |

---

## 2. 范围边界

### 2.1 本阶段做什么（In Scope）

- 建表：`learning_plans` / `learning_tasks`（含状态、时间、验收标准、资源）
- `Planner Agent`：`SkillGapReport` + 时间预算 + 偏好 → 有序 `LearningPhase`/`LearningTask`
- 时间/顺序调度规则（纯规则、可重复）：拓扑序 + 周时制分桶 → phase
- TodoListMiddleware：任务持有、状态流转、进度保存/恢复
- RAG 资源推荐：为任务生成资料链接（title/url/chunk_id）
- `LearningPlan` 局部重规划接口
- `POST /api/v1/plan/*` 接口（生成 / 查询 / 状态流转 / 重规划）
- 契约文档 + 集成测试（TC-P1~P10）

### 2.2 本阶段明确不做（Out of Scope）

| 不做 | 原因 | 何时做 |
| --- | --- | --- |
| 实践任务生成 | 把学习任务转化为代码/项目交付物 | 阶段 6 |
| 能力评估 / 画像更新 | 由证据闭环触发"评估→再规划" | 阶段 6 |
| 完整长期记忆（学习偏好/行为记忆化） | 偏好用参数传入即可，不做记忆化 | 阶段 7 |
| 前端 Plan 交互页 | 后端契约先行 | 阶段 8 |
| 精确 LLM 生成学习路线骨架 | 骨架由规则生成，LLM 仅润色文案/资源 | 与阶段 4 一致，后置 |

> 边界原则（对齐计划书）：学习计划主体（顺序、分桶、状态机、可恢复）一律**规则驱动、可重复**；LLM 只负责润色任务描述、推荐资源文案，**不决定顺序与验收**。

---

## 3. 技术选型与工程结构

### 3.1 技术栈（阶段 1~4 基础上，无新增依赖）

| 项 | 选型 | 说明 |
| --- | --- | --- |
| 存储 | PostgreSQL（复用 `psycopg` 直连，`persistence/db.py`） | 沿用既有风格 |
| Todo 持有 | 关系表 `learning_plans`/`learning_tasks` + 应用层状态机 | 不引入任务框架 |
| 调度/排序 | 纯 Python（复用 `gap/closure.topo_sort` 排序 + 周时制分桶） | G5 可重复 |
| LLM | 仅任务描述/推荐资源润色，复用阶段 1 `LLMClient` | 失败走模板兜底 |

> 关键复用：**阶段 4 的 `closure.topo_sort` 与 `graph_store`**。任务顺序直接消费 `SkillGapReport.recommended_sequence`，避免重复实现依赖排序。

### 3.2 工程结构（新增/修改点）

```
app/
├── config.py                 # 修改：新增 PLAN_* 配置（可选）
├── api/routes/
│   ├── plan.py               # 新增：POST /api/v1/plan/generate · /plan/<id> · 状态流转 · 重规划
│   └── __init__.py           # 修改：注册 plan_bp
├── todo/                     # 新增：【Todo 层】不感知 HTTP
│   ├── __init__.py
│   ├── schemas.py            # 契约：PlanRequest / LearningPlan / LearningPhase / LearningTask / TaskTransition
│   ├── scheduler.py          # 拓扑序 + 周时预算分桶 → phases（纯规则，可重复）
│   ├── todo_store.py         # learning_plans/learning_tasks 持久化 + 状态流转
│   ├── planner.py            # 编排：SkillGapReport + 时间 + 偏好 → LearningPlan（含可选 LLM 润色）
│   └── explain.py            # 任务描述/推荐资源模板（默认不依赖 LLM）+ LLM 润色兜底
└── persistence/
    └── ...                   # 复用 db.connect
scripts/
├── init_db.py                # 修改：追加 learning_plans / learning_tasks 建表
└── seed_demo_plan.py         # 新增（可选）：一键初始化示例用户计划，便于 Demo 与联调
tests/
└── test_todo.py              # 新增：TC-P1~P10
```

分层依赖（延续单向规则）：

```
API 层 api/routes/plan.py
   │  只调
   ▼
Todo 层 app/todo/（todo_store ← scheduler → planner｜explain）
   │  只调
   ▼
持久化 app/persistence/db.py
```

跨层只读依赖：`app/todo/planner.py → app/gap/*`（读取 `SkillGapReport` 及拓扑序），不改动阶段 4 的缺口计算。

**接线点（改动最小化）**
- `app/__init__.py`：注册 `plan_bp`。
- `scripts/init_db.py`：追加 `learning_plans`/`learning_tasks` 两张表。
- `docs/api_v1.md`：补 plan 接口。

---

## 4. 模块解耦与分工

### 4.1 各模块职责、输入、输出、不负责什么

| 模块 | 职责 | 主要输入 | 主要输出 | 不负责什么 |
| --- | --- | --- | --- | --- |
| API 层（`routes/plan.py`） | 收 HTTP、校验、调 Todo 层、统一响应 | HTTP JSON | 统一 response | 不做调度/状态细节 |
| 持久化（`todo_store.py`） | plans/tasks 建查询、状态流转、重规划落库 | plan_id / task_id / status | 计划/任务快照 | 不算时间、不调 LLM |
| 调度（`scheduler.py`） | 消费拓扑序，按周时预算分桶为 phases | recommended_sequence + 时间预算 | `LearningPhase[]` | 不写库 |
| 编排（`planner.py`） | 报告+时间+偏好 → LearningPlan | PlanRequest | LearningPlan | 不写 HTTP |
| 解释（`explain.py`） | 任务描述/资源模板 + LLM 润色 | 任务规则结果 | 可读 task 描述/资源 | 不决策顺序 |

### 4.2 团队分工（阶段 5 建议 2~3 角色）

| 角色 | 负责模块 | 主要交付物 | 依赖 | 是否可并行 |
| --- | --- | --- | --- | --- |
| 平台/后端 | config、`routes/plan.py`、`todo_store.py`、`init_db`、（可选 seed_demo_plan） | 两张表+接口骨架 | 无（契约先行） | 是 |
| 计划算法 | `scheduler.py`、`explain.py`、`planner.py` | 顺序/分桶/编排走通 | 契约 + 阶段 4 `SkillGapReport` 样例 | 契约后并行 |
| 资料/测试 | `test_todo.py`、示例场景 | TC-P1~P10 | 两端交付后联调 | 可先写状态机断言 |

> 并行关键是**先冻结第 5 节 schema**（尤其 `LearningPlan` 的分层结构与任务状态机语义）。

---

## 5. 输入 / 输出接口契约（Todo）★ 重点

> 复用统一规范：成功 `{"code":0,"data":...}`；错误带 `trace_id`；snake_case。新增错误码 `50040`（计划生成失败，走兜底）、`40410`（计划/任务不存在）。

### 5.1 输入结构：`PlanRequest`

```jsonc
// POST /api/v1/plan/generate
{
  "user_id": "U10001",
  // 二选一制定计划来源：
  "gap_report": null,       // A) 直接传入阶段 4 的 SkillGapReport（推荐：前端把拿到的报告回传，避免重复计算）
  //   B) 不传 gap_report 时，复用阶段 4 的 gap 输入，后端自动重算缺口：
  "target_roles": ["RC002"],  // B
  "target_skills": null,      // B（可选）
  // 规划参数：
  "available_hours_per_week": 8,   // 每周可投入小时
  "deadline": "2026-11-30",        // 目标时间（ISO 日期），用于约束总跨度
  "learning_style": "project_driven", // 学习偏好（可选；对齐计划书：项目驱动/系统性；进占位偏好，供 LLM 润色）
  "phases_cap": 5                    // 可选：最多生成阶段数，默认由调度规则算
}
```
> 约束：
> - `gap_report` 与 `target_roles/target_skills` **至少提供一种**；都提供时以 `gap_report` 为准（避免重算歧义）。
> - 若走 B 路，后端调用阶段 4 `gap_agent.analyze` 计算报告的 `recommended_sequence` 与 `gaps[].recommended_sequence`，再进入规划；`top_gaps` 沿用默认。
> - `available_hours_per_week` 默认 5；`deadline` 缺省则表示按小时总量自然分桶不限跨度。

### 5.2 输出结构：`LearningPlan` ★（阶段 5 核心产物，也是阶段 6 输入）

```jsonc
{
  "plan_id": "PLAN_001",
  "user_id": "U10001",
  "goal": "AI Agent 工程师 3 个月能力达成",
  "source_role": "RC002",                 // 空串表示自定义目标能力
  "created_at": "2026-08-27T12:00:00Z",
  "status": "in_progress",                 // in_progress | finished
  "is_llm_enhanced": true,                 // 任务描述/资源是否由 LLM 润色

  "metrics": {
    "total_hours": 76,                     // 全部任务预计小时之和
    "total_tasks": 12,
    "done_tasks": 0,
    "weeks_est": 10                        // 按 weekly_hours 估算周数
  },

  "phases": [
    {
      "phase_id": "P1",
      "title": "基础前置（Python / LLM API）",
      "order": 1,
      "skill_ids": ["python", "llm_api"],
      "tasks": [
        {
          "task_id": "T1",
          "skill_id": "python",
          "title": "补齐 Python 与应用基础",
          "estimated_hours": 6,
          "status": "pending",              // pending | doing | done
          "acceptance_criteria": "能完成 Top-K 检索接口所需的 Python 切面；运行 3 个示例通过",
          "resources": [
            {"title": "Python 官方教程", "url": "https://docs.python.org/3/tutorial/", "source": "official", "chunk_id": "C001"}
          ]
        }
      ]
    }
  ]
}
```

> **字段语义要点**
> - `phases` 内按周时预算分桶，phase 间保持 `skill_ids` 前置先后；phase 内任务可并行（无相互前置）。
> - 每个 `LearningTask` 的 `acceptance_criteria` 有规则模板生成（默认不依赖 LLM），可在 LLM 开启时润色措辞。
> - `status` 状态机：`pending → doing → done`（见 5.3）。`plan.status` 由 `phases[*].tasks[].status` 汇总（全部 done ⇒ `finished`）。
> - 顺序、分桶、状态、验收默认全部**规则计算**；仅 `title`/`acceptance_criteria` 措辞与 `resources` 文案可由 LLM 润色。

### 5.3 任务状态机（todo_store，纯规则）

```
pending --（POST transition:start）--> doing --（POST transition:complete）--> done
   │                                        │
   └--------------------（可选）----------> blocked/back_to_pending  // V1 仅实现前向闭环，blocked 预留
```
- 合法流转：`pending→doing`、`doing→done`；**其余一律拒绝**（如 `pending→done` 直接跳过 doing → 422）。
- 重复流转幂等：对已 done 任务再次 `complete` 返回当前状态成功（不改写 `updated_at` 语义上一次完成时间）。
- `transition` 动作名：`start` / `complete`。响应返回更新后的 `LearningTask`。

### 5.4 Planner 调度规则（scheduler，纯规则）

```
输入：recommended_sequence 拓扑序 S、available_hours_per_week = W、deadline = D（可空）、N = 每阶段任务上限
1) 依据 S 拓扑序建立"技能→任务"映射（每个缺口技能生成 1 个主任务；其缺失前置技能各生成 1 个前置任务，标 required=true）
2) 按拓扑序把任务排入 phases：
     - 逻辑上：所有 required 前置任务必须先于依赖它的主任务所在 phase
     - 物理分桶：若 N 个任务全部满足前置则归入当前 phase；否则开启新 phase
   （近似策略：以拓扑深度 depth 分组即为天然 phase 边界；depth 相同且无相互前置者同 phase）
3) 时间估算：每任务默认 estimated_hours = clamp(缺口 delta * 基准小时, MIN, MAX)（如 delta≥3 → 10h；delta=1 → 4h）
4) 若给定 D：按 W 与总小时估算 weeks_est，超出 D 时不硬缩 task 小时，而是在报告里给出峰值建议
5) accepted 仅辅助润色；不改变排序
```

> 规则集中、参数可配（`PLAN_*`），同一输入结构、结果严格一致（TC-P6 守护）；LLM 不参与顺序/分桶/状态。

### 5.5 局部重规划（replan）

```jsonc
// POST /api/v1/plan/{plan_id}/replan
{
  "gap_report": { ... },          // 可选：更新后的 SkillGapReport（阶段 6 评估触发再规划时用它）
  "feedback": "时间太紧，压缩一下任务",  // 可选：用户反馈，用于 LLM 润色 + 小时系数调整
  "weekly_hours": 6                // 可选：新的周时预算
}
```
- **行为**：只重建 `pending/doing` 的 phase/task（`done` 任务保留、不回退、不重算）；依据新报告/新预算重排剩余任务。
- **V1 规则兜底**：即使 LLM 关闭，仍可按新 `recommended_sequence` 作规则重排（TC-P8 覆盖）。

### 5.6 查询

```jsonc
// GET /api/v1/plan/{plan_id}
// → {"code":0,"data":{ ...LearningPlan }}；不存在 → 40410
```

### 5.7 配置输入（`config.py` 可选新增）

| 环境变量 | 必填 | 说明 | 示例 |
| --- | --- | --- | --- |
| `PLAN_DEFAULT_WEEKLY_HOURS` | 否 | 默认每周投入小时 | `5` |
| `PLAN_PHASES_CAP` | 否 | 默认最大阶段数 | `8` |
| `PLAN_MIN_TASK_HOURS` / `PLAN_MAX_TASK_HOURS` | 否 | 单任务小时上下限 | `2` / `12` |
| `PLAN_LLM_ENABLED` | 否 | 是否 LLM 润色任务/资源 | `true` |

---

## 6. 数据契约与存储

### 6.1 两张表（纳入 `scripts/init_db.py`，幂等）

```sql
CREATE TABLE IF NOT EXISTS learning_plans (
  id         VARCHAR(64) PRIMARY KEY,
  user_id    VARCHAR(64) NOT NULL,
  goal       VARCHAR(255),
  source_role VARCHAR(64),
  status     VARCHAR(24) NOT NULL DEFAULT 'in_progress', -- in_progress | finished
  skill_ids  JSONB,          -- 规划依据的 ordered skill 列表（快照，便于审计/重放）
  report_json JSONB,         -- 生成该计划所依据的 SkillGapReport 快照
  metrics_json JSONB,        -- total_hours/total_tasks/weeks_est 快照
  is_llm_enhanced BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_learning_plans_user ON learning_plans(user_id);

CREATE TABLE IF NOT EXISTS learning_tasks (
  id                 VARCHAR(64) PRIMARY KEY,
  plan_id            VARCHAR(64) NOT NULL REFERENCES learning_plans(id) ON DELETE CASCADE,
  phase_id           VARCHAR(64) NOT NULL,
  phase_order        SMALLINT NOT NULL,
  task_order         SMALLINT NOT NULL,
  skill_id           VARCHAR(64),
  title              VARCHAR(255),
  estimated_hours    REAL NOT NULL DEFAULT 4,
  status             VARCHAR(24) NOT NULL DEFAULT 'pending', -- pending | doing | done
  acceptance_criteria TEXT,
  resources_json     JSONB,        -- [{title,url,source,chunk_id}]
  required           BOOLEAN NOT NULL DEFAULT false, -- 前置补齐任务
  started_at         TIMESTAMPTZ,
  finished_at        TIMESTAMPTZ,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_learning_tasks_plan ON learning_tasks(plan_id, phase_order, task_order);
```

### 6.2 初始化时机（延续约定）

- 建表仅在迁移期执行；**禁止**在规划/流转路径内重复 `CREATE`。
- `seed_demo_plan.py`（可选）：为 Demo 用户一键生成样例计划，幂等（按 plan_id 幂等 upsert）。

---

## 7. 功能清单

| # | 功能 | 关联目标 |
| --- | --- | --- |
| F1 | learning_plans / learning_tasks 建表（init_db 幂等） | G3 |
| F2 | PlanRequest 生成计划（A 传报告 / B 自算缺口两路） | G1/G2/G5 |
| F3 | 拓扑序 + 周预算分桶 → phases（scheduler 纯规则） | G1 |
| F4 | 任务验收标准模板生成（explain 默认不依赖 LLM） | G2 |
| F5 | RAG 资料链接推荐（resources 含 title/url/chunk_id） | G2 |
| F6 | 任务状态流转 pending→doing→done + 非法流转拒绝 | G4 |
| F7 | 计划/任务持久化与按 plan_id 恢复（可保存并恢复进度） | G3 |
| F8 | 局部重规划（不覆盖 done 任务；LLM 关也规则可重排） | G5 |
| F9 | `docs/api_v1.md` 补 plan 接口 | G6 |
| F10 | `test_todo.py`（TC-P1~P10） | G6 |

---

## 8. 验收标准与测试用例

### 8.1 验收条件（全部满足即完成）

| 编号 | 验收项 | 验证方式 |
| --- | --- | --- |
| AC1 | 建表就绪 | `init_db` 可重复；`\dt learning_plans|learning_tasks` 存在 |
| AC2 | 计划符合依赖 | 用 RC002 报告生成，任一任务所需前置先于它所在 phase |
| AC3 | 任务可执行 | 每任务含 title/estimated_hours/acceptance_criteria/resources |
| AC4 | 进度可恢复 | 生成→重启→按 plan_id 查询，名词状态一致 |
| AC5 | 状态流转 | transition start/complete 通过；非法流转返回 422 |
| AC6 | 可局部重规划 | 改 weekly_hours 重规划后 done 任务保留、pending 任务被重排 |
| AC7 | 契约有测试 | TC-P1~P10 全绿 |

### 8.2 集成测试用例（`tests/test_todo.py`）

| 用例 | 输入 | 预期 |
| --- | --- | --- |
| TC-P1 依赖有序 | RC002 的 report 生成计划 | phases 内 task 满足前置；依赖技能所在 phase > 前置 phase |
| TC-P2 字段齐全 | 任一 plan | 每 task 有 title/hours/acceptance/resources 且非空 |
| TC-P3 走 B 路自算 | 传 target_roles=RC002 不传 gap_report | 内部复用 gap_agent 算出序号并生成 plan |
| TC-P4 持久化恢复 | 生成后按 plan_id 查 | 结构与 metrics 一致 |
| TC-P5 状态流转 | start→complete | pending→doing→done；重复 complete 幂等成功 |
| TC-P6 非法流转 | 直接 pending→done 或回退 | 422 + code 42200 + trace_id |
| TC-P7 可重复 | 同一 PlanRequest 两次 | phases/tasks 结构与顺序逐字段一致 |
| TC-P8 重规划保 done | weekly_hours 改变重规划 | done 任务保留、pending 被重排 |
| TC-P9 LLM 兜底 | PLAN_LLM_ENABLED=off | 仍返回完整 plan，is_llm_enhanced=false |
| TC-P10 非法入参 | 无 gap_report 且无 target_roles | 422；plan 缺失 GET → 40410 |

---

## 9. 任务拆解与并行分工

### 9.1 前置（契约对齐，先做）

- [ ] 冻结第 5 节 schema：`PlanRequest` / `LearningPlan` / `LearningPhase` / `LearningTask` / `TaskTransition` 与状态机语义
- [ ] 确认阶段 4 `SkillGapReport` 输出字段对其消费点（material：`recommended_sequence`、`gaps[].recommended_sequence`、`gaps[].score/priority/required_level/current_level`）
- [ ] 确认 RAG `SearchRequest/EvidenceList` 返回可用作 `resources`（title/url/source/chunk_id）

### 9.2 平台/后端（与计划算法并行）

1. `init_db.py` 追加两张表
2. `config.py` 加 `PLAN_*`
3. `todo_store.py`：建计划 / 查 / 状态流转 / 重规划落库
4. `routes/plan.py` 接口骨架 + 注册 `plan_bp`
5. 测试基线：状态机断言工具

### 9.3 计划算法（契约后并行）

1. `scheduler.py`：拓扑序分桶 + 周预算 + 小时估算
2. `explain.py`：任务描述/验收/资源模板（默认不依赖 LLM）
3. `planner.py`：A/B 两路编排 + `is_llm_enhanced` 兜底
4. 与后端联调 plan 接口

### 9.4 资料/测试

1. RC001/RC002/RC010/RC025/RC008 生成样例计划（期望依赖校验数据）
2. 实现 TC-P1~P10
3. 输出验收核对清单（AC1~AC7）

### 9.5 里程碑

| 里程碑 | 内容 | 完成标志 |
| --- | --- | --- |
| M1 | 契约冻结 + 建表 | schema 签署、两张表就绪 |
| M2 | 计划算通 | plan/generate 返回 LearningPlan |
| M3 | 状态流转 | transition start/complete 生效、非法拒绝 |
| M4 | 恢复 + 重规划 | 按 plan_id 恢复、重规划保 done |
| M5 | 依赖校验 | TC-P1/P7 通过 |
| M6 | 测试与文档 | TC-P1~P10 全绿 + api_v1.md 更新 |

---

## 10. 风险与注意事项

| 风险 | 表现 | 应对 |
| --- | --- | --- |
| 报告快照漂移 | 重规划时用了旧缺口 | `report_json`/`skill_ids` 落库快照；带新版报告则重算 |
| 拓扑序缺失/环 | phases 排序异常 | 直接复用阶段 4 `closure.topo_sort`；缺失则退化为输入顺序 |
| 状态机回退 | 误改已 done 任务 | 强制 `pending→doing→done`，其余 422；done 不重算 |
| 任务墙过密 | weekly_hours 太小导致 weeks_est 超 deadline | 不硬缩任务小时，仅报告峰值建议；规则上限 `PLAN_*` |
| 依赖 LLM | 顺序/验收抖动 | 顺序/分桶/状态全走规则；LLM 仅润色文案/资源，失败模板兜底 |
| 资源失效 | RAG 无匹配资料 | tasks.resources 允许空并由 explain 给占位提示，不作为阻塞 |

---

## 11. 交付物清单（阶段 5）

- [ ] `learning_plans` / `learning_tasks` 表（init_db 幂等）
- [ ] `app/todo/`：scheduler / todo_store / planner / explain
- [ ] `POST /api/v1/plan/generate`（A 传报告 / B 自算缺口两路）+ `GET /api/v1/plan/{plan_id}` + `POST /api/v1/plan/{plan_id}/replan` + 任务状态流转
- [ ] `LearningPlan` 分层结构 + 调度规则 + 状态机 + 验收/资源模板
- [ ] `config.py` `PLAN_*` 配置 + `50040`/`40410` 错误码
- [ ] `docs/api_v1.md` 增补 plan 契约
- [ ] `tests/test_todo.py`（TC-P1~P10）全绿
- [ ] 验收核对清单（AC1~AC7）

> **对接下一阶段**：阶段 6 的 `PracticePlan` 直接消费 `LearningTask`（skill_id / acceptance_criteria / resources）生成实践任务；评估完成后用新 `SkillGapReport` 调 `replan`，实现"评估 → 画像更新 → Gap 再计算 → 计划调整"闭环。