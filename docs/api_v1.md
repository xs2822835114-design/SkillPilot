# SkillMap API 文档（阶段 1 第一版）

> 版本：v1.0.0 ｜ 对应计划书阶段 1：基础工程与 Agent 最小闭环
> 完整接口文档见：`项目规划/SkillMap_API接口文档.md`

## 通用约定

- 成功：`{"code":0,"message":"ok","data":...}`
- 错误：`{"code":非0,"message":"...","data":null,"trace_id":"..."}`
- JSON 字段 snake_case；ID 为 string；时间为 ISO 8601

## 1. 健康检查

```
GET /health
```

```json
{
  "code": 0,
  "message": "ok",
  "data": { "status": "up", "version": "v1.0.0", "db": "ok", "llm": "disabled" }
}
```

- `status`：`up`（db 正常或未配置）／`degraded`（db 配置了但不可用）
- `db`：`ok` / `down` / `disabled`；`llm`：`ok` / `disabled`

## 2. 对话 / Agent 编排入口

```
POST /api/v1/chat
```

**请求体**

```json
{
  "user_id": "U10001",
  "thread_id": "T20260826",
  "intent_hint": null,
  "message": "我想转向 AI 应用开发",
  "attachments": []
}
```

**响应 200**

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "route": "chat",
    "steps": ["intent_recognize", "reply"],
    "reason": "已识别意图「gap_analysis」；阶段 1 为单 Agent 最小闭环，业务 Agent（阶段 3~6）尚未接入",
    "reply": "…",
    "workflow_status": "done",
    "artifacts": {},
    "evidence": []
  }
}
```

**错误**

| 场景 | HTTP | code |
| --- | --- | --- |
| 非 JSON body | 400 | 40001 |
| 参数校验失败（缺 message / 超长 / ID 非法 / 全空白） | 422 | 42200 |
| 服务端未预期异常 | 500 | 50000 |

## 3. RAG 知识库（阶段 2）

> 用于把技术资料入库、向量检索与带证据问答。`category / skill_tags / role_target / doc_id / source_type` 均参与过滤。

### 3.1 入库

```
POST /api/v1/rag/ingest
```

**请求体**（`source_type` 为 `url` 或 `file` 时，`content` 可空，由服务端抓取/读取）

```json
{
  "source": "notes/rag-notes.md",
  "source_type": "text",
  "content": "RAG 是检索增强生成……",
  "category": "ai",
  "title": "RAG 学习笔记",
  "lang": "zh",
  "skill_tags": ["rag", "retrieval"],
  "role_target": "ai_application_engineer"
}
```

**响应 200**

```json
{
  "code": 0,
  "message": "ok",
  "data": { "doc_id": "DOC_8f3a2b", "num_chunks": 24, "status": "ok" }
}
```

- 幂等：相同 `source` 重复入库为替换式，不产生重复 chunk。
- `url` 时 `source` 必须为 `http(s)://`；纯文本内容上限 100000 字符。

### 3.2 检索

```
POST /api/v1/rag/search
```

**请求体**

```json
{
  "query": "什么是 RAG？",
  "top_k": 5,
  "filter": { "category": "ai", "skill_tags": ["rag"], "doc_id": null }
}
```

**响应 200**

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "results": [
      {
        "chunk_id": "CHK_xx",
        "doc_id": "DOC_8f3a2b",
        "title": "RAG 学习笔记",
        "source": "notes/rag-notes.md",
        "url": null,
        "source_type": "text",
        "category": "ai",
        "role_target": null,
        "content": "RAG 是检索增强生成……",
        "score": 0.914
      }
    ]
  }
}
```

- `top_k`：1~20，默认 5；`url` 字段仅当 `source_type=url` 时等于 `source`。

### 3.3 问答（RAG + LLM）

```
POST /api/v1/rag/query
```

**请求体**（复用检索入参，可另传 `model`）

```json
{ "query": "帮我解释 RAG，并给出官方来源", "top_k": 4, "filter": { "category": "ai" } }
```

**响应 200**

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "answer": "RAG 是指…（基于以下资料）",
    "evidence": [
      {
        "chunk_id": "CHK_xx",
        "doc_id": "DOC_8f3a2b",
        "title": "RAG 学习笔记",
        "source": "notes/rag-notes.md",
        "content": "RAG 是检索增强生成……",
        "score": 0.914
      }
    ],
    "qa_model": "deepseek-v4-flash",
    "top_k_used": 4
  }
}
```

- 无命中时 `answer` 提示"未检索到资料"，`top_k_used=0`；LLM 不可用/失败时用规则回复，结构不变。

### 3.4 错误

| 场景 | HTTP | code |
| --- | --- | --- |
| 非 JSON body / 字段校验失败 | 400 / 422 | 40001 / 42200 |
| Embedding 服务失败（不可用/返回非 200） | 500 | 50010 |
| 检索失败 | 500 | 50011 |

## 4. 用户技术画像（阶段 3）

> 目标：从自然语言/项目简介提取技能，形成可合并、带置信度与证据的 `SkillProfile`。
> 打分/合并全部走规则（`rule_engine`，可重复），LLM 只负责"抽出什么技能"。

### 4.1 抽取（待确认，不落库）

`POST /api/v1/profile/extract`

```jsonc
// 请求
{ "user_id": "U10001", "source_type": "conversation",   // conversation|self_report|project
  "source_ref": "THREAD_T1", "content": "我会 Java、Spring Boot、MySQL，做过订单系统",
  "project_id": null }

// 响应 200 data —— 返回"待确认"patch，前端确认后再 upsert 落库
{ "status": "extracted",
  "patch": { "user_id": "U10001",
    "skills": [{ "skill_id": "java", "theory_score": 78, "practice_score": 80,
                 "confidence": 0.9, "evidence": ["MSG_001"] }],
    "preferences": {} },
  "unmatched_tokens": ["做过订单系统"] }        // 未命中技能字典的片段，可追溯
```

> `skill_id` 必须命中 `skills` 字典；未命中片段进 `unmatched_tokens` 而非静默丢弃。

### 4.2 合并更新（确认/手动登记）

`POST /api/v1/profile/upsert` —— 请求体 = `SkillProfilePatch`：

```jsonc
{ "user_id": "U10001",
  "skills": [{ "skill_id": "python", "theory_score": 78, "practice_score": 70,
               "confidence": 0.9, "evidence": ["E1"] }],   // 可只带部分字段（null 不更新）
  "preferences": {}, "force_replace_evidence": false }
```

响应 200 data = 合并后的完整 `SkillProfile`：`{ user_id, version, updated_at, skills[], projects[], preferences{} }`。
写入后还会回写一条 `profile_updated` 成长事件（best-effort）。

### 4.3 查询画像

`GET /api/v1/profile/<user_id>` → `SkillProfile`；用户无画像时 `skills=[]`、`version=0`。

### 4.4 登记项目

`POST /api/v1/profile/projects`

```jsonc
{ "user_id": "U10001", "project_id": "PROJ_003", "name": "订单系统",
  "description": "基于 Spring Boot + MySQL + Redis 的订单系统",
  "repo_url": null, "skills": ["spring_boot", "mysql"] }   // skills 可选；缺省从 description 抽取
```

响应 200 data = 更新后的 `SkillProfile`（新项目入列，其技能合并进画像）。

### 4.5 等级换算与合并规则（rule_engine，非 LLM）

```
level = floor((0.4 * theory_score + 0.6 * practice_score) / 20)，上限 5
confidence 合并：merged = inp if pre is None else 0.4*pre + 0.6*inp   // 新证据更可信
增量更新：只处理 patch 中出现的 skill_id；分数为 null 不更新；每次影响后 version += 1
```

### 4.6 错误码

| 场景 | HTTP | code |
| --- | --- | --- |
| 请求体非法 JSON | 400 | 40001 |
| 参数校验失败（如 user_id 非法） | 422 | 42200 |
| 画像服务不可用（未配置 DATABASE_URL） | 503 | 50020 |

## 5. Skill Graph / Gap 缺口分析（阶段 4）

> 目标：输入"用户画像 + 目标岗位/能力"，输出结构化、带优先级、可解释、可重复的 `SkillGapReport`。
> score / priority / reason / prerequisites 均由规则计算（可重复）；仅 `suggestions` 可由 LLM 润色（失败走模板兜底）。

```
POST /api/v1/gap/request
```

**请求体**

```jsonc
{
  "user_id": "U10001",
  "target_roles": ["RC002"],            // 目标岗位 ID（可多个，各产出一份 report）
  "target_skills": null,                // 二选一：或直接用目标能力集合 [{"skill":"LangGraph","level":4,"weight":1.0}]
  "profile_version": 12,                // 可选：指定使用的画像版本
  "top_gaps": 50                        // 可选：最多返回缺口数，默认 50
}
```

- 约束：`target_roles` 与 `target_skills` **至少提供一个**；同时提供时以 `target_roles` 为主，`target_skills` 视为额外追加要求。

**响应 200**

```jsonc
{
  "code": 0,
  "message": "ok",
  "data": {
    "reports": [
      {
        "user_id": "U10001",
        "target_role_id": "RC002",
        "target_role": "AI Agent 工程师",
        "role_category": "AI/Application",
        "profile_version_used": 12,
        "generated_at": "2026-08-27T12:00:00Z",
        "is_llm_enhanced": true,
        "coverage": {
          "required_total": 8,
          "covered_skills": ["python"],
          "gap_skills": ["langgraph", "llm_api"],
          "gap_total": 5,
          "coverage_rate": 0.375
        },
        "gaps": [
          {
            "skill_id": "langgraph",
            "name": "LangGraph",
            "required_level": 4,
            "current_level": 0,
            "required_weight": 1.0,
            "score": 0.8,
            "priority": "P1",
            "reason": "…岗位核心技能缺失，等级差 4 级（weight 1.0）…",
            "prerequisites": [ {"skill_id":"python","name":"Python","status":"gap","own_gap_id":null} ],
            "recommended_sequence": ["python", "llm_api", "langchain", "langgraph"]
          }
        ],
        "recommended_sequence": ["python", "llm_api", "langchain", "langgraph", "rag", "vector_db"],
        "suggestions": "先从 Python/LLM API 补齐基础，按 langgraph 的前置链逐层推进……"
      }
    ]
  }
}
```

**字段要点**

- `gaps` 只含真实缺口（当前等级未达要求的岗位技能 + 其缺失前置）；score∈[0,1]、priority∈{P1,P2,P3}、reason 非空。
- 每个 `gap` 的 `prerequisites` 为其 `requires` 传递展开；`own_gap_id` 指向主 `gaps` 中的自身条目（非缺口为 null）。
- `recommended_sequence`（报告级与 gap 级）按前置关系拓扑排序。

**错误**

| 场景 | HTTP | code |
| --- | --- | --- |
| 非 JSON body | 400 | 40001 |
| 无 target_roles 且无 target_skills / 非法字段 | 422 | 42200 |
| 目标岗位不存在 | 422 | 42200 |
| 缺口计算失败（走兜底） | 500 | 50030 |

## 6. 学习规划 / Todo（阶段 5）

> 目标：把阶段 4 的 `SkillGapReport` 转为**有依赖、可执行、可验收、可恢复、可局部重规划**的学习路线。
> 顺序/分桶/状态/验收由规则计算（可重复）；仅 `goal`、任务文案可由 LLM 润色（失败走模板兜底）。

### 6.1 生成学习计划

```
POST /api/v1/plan/generate
```

**请求体**（计划来源二选一：A 直传 `SkillGapReport`，或 B 复用缺口入参后端自算）

```jsonc
{
  "user_id": "U10001",
  "gap_report": null,                 // A：直接传阶段 4 返回的 SkillGapReport
  // B（二选一，不传 gap_report 时）：后端自动重算缺口
  "target_roles": ["RC002"],
  "target_skills": [],
  // 规划参数
  "available_hours_per_week": 8,       // 每周可投入小时（默认 5）
  "deadline": "2026-11-30",            // 可选：目标时间
  "learning_style": "project_driven",  // 可选：学习偏好（仅辅助润色）
  "phases_cap": 5                      // 可选：最多阶段数
}
```

- 约束：`gap_report` 与 `target_roles/target_skills` 至少提供一种；都提供时以 `gap_report` 为准。
- 响应返回完整 `LearningPlan`（`plan_id` 用于后续查询/流转/重规划）。

### 6.2 查询 / 恢复计划

```
GET /api/v1/plan/{plan_id}
```

**响应 200**

```jsonc
{
  "code": 0,
  "message": "ok",
  "data": {
    "plan_id": "PLAN_xxx",
    "user_id": "U10001",
    "goal": "AI Agent 工程师 能力达成计划",
    "source_role": "RC002",
    "created_at": "2026-08-27T12:00:00Z",
    "status": "in_progress",
    "is_llm_enhanced": true,
    "metrics": { "total_hours": 76, "total_tasks": 18, "done_tasks": 0, "weeks_est": 10 },
    "phases": [
      {
        "phase_id": "P1",
        "title": "阶段基础：…",
        "order": 1,
        "skill_ids": ["sql_基础", "vue_react_基础"],
        "tasks": [
          {
            "task_id": "PLAN_xxx-T01",
            "skill_id": "sql_基础",
            "title": "补齐 … 基础（等级差 3 级）",
            "estimated_hours": 9,
            "status": "pending",            // pending | doing | done
            "acceptance_criteria": "…",
            "resources": [ { "title": "…", "url": "…", "source": "…", "chunk_id": "C001" } ],
            "required": false,
            "order": 1
          }
        ]
      }
    ]
  }
}
```

- `phases` 内按技能前置关系分桶（同 phase 可并行，phase 间严格前置）。
- `metrics.done_tasks` 会随状态流转动态更新；全部任务 done ⇒ `status=finished`。

### 6.3 任务状态流转

```
POST /api/v1/plan/{plan_id}/tasks/{task_id}/transition
```

```jsonc
{ "action": "start" }   // pending → doing
{ "action": "complete" } // doing → done
```

- 合法流转 `pending→doing→done`；跳过 doing 直接 complete 等非法流转 → `422 42200`。
- 重复 complete 幂等。

### 6.4 局部重规划

```
POST /api/v1/plan/{plan_id}/replan
```

```jsonc
{
  "gap_report": null,      // 可选：更新后的 SkillGapReport（评估触发再规划时使用）
  "feedback": "时间太紧，压缩一下任务",  // 可选：用户反馈
  "weekly_hours": 6        // 可选：新的周预算
}
```

- 只重建 `pending/doing` 任务；`done` 任务保留、不回退、不重算。
- 未传 `gap_report` 时沿用计划生成时的缺口快照。

**本节错误**

| 场景 | HTTP | code |
| --- | --- | --- |
| 非 JSON body | 400 | 40001 |
| 生成入参非法（无来源）/ 非法流转 / 计划不存在 | 422 | 42200 |
| 计划不存在（GET/重规划） | 404 | 40410 |
| 计划生成/重规划/流转失败 | 500 | 50040 |

## 7. 实践任务与能力评估（阶段 6）

> 目标：把 `LearningTask` 转成可交付、带验收的实践计划（`PracticePlan`），再用代码/测试证据做**结构化评估**（`EvaluationReport`，区分理论/实践），并自动回写画像、触发缺口再计算与学习路线重规划，补全 `Gap → Plan → Practice → Evaluation → Re-plan` 闭环。
> 评分、证据、理论/实践区分纯规则可重复；仅建议/指引文案可由 LLM 润色（失败模板兜底）。

### 7.1 生成实践计划

```
POST /api/v1/practice/generate
```

```jsonc
{
  "user_id": "U10001",
  "task_id": "PLAN_xxx-T03",   // 阶段 5 LearningTask
  "skill_id": "rag_retriever",
  "level_target": 3,            // 可选，默认 3
  "format": "project"          // 现阶段仅 project
}
```

**响应 `PracticePlan`**（含 `deliverables`、`rubric`、`guide`）

```jsonc
{
  "practice_id": "PRA_xxx",
  "task_id": "PLAN_xxx-T03",
  "skill_id": "rag_retriever",
  "level_target": 3,
  "deliverables": [
    { "key": "code_repo", "desc": "可运行的 demo 代码库" },
    { "key": "readme", "desc": "README：说明流程、依赖与运行方式" },
    { "key": "tests",  "desc": "含 1+ 个可运行的测试" }
  ],
  "rubric": [ { "criterion": "功能实现", "weight": 0.4 }, … ],
  "guide": "针对「…」实践：…"
}
```

- `level_target >= 4` 时额外追加 `notes` 交付物并提高测试权重。

### 7.2 上传代码片段（无仓库兜底）

```
POST /api/v1/evaluation/artifact
```

```jsonc
{
  "user_id": "U10001",
  "practice_id": "PRA_xxx",
  "language": "python",
  "filename": "retriever.py",
  "content": "def search(...): ...",
  "test_content": "def test_search(): ..."   // 可选
}
```

### 7.3 能力评估

```
POST /api/v1/evaluation/evaluate
```

```jsonc
{
  "user_id": "U10001",
  "practice_id": "PRA_xxx",
  "artifact_type": "snippet",     // snippet | github
  "artifact_ref": null,           // github 仓库 URL（可选）
  "repo_files": {                 // snippet 时内联代码；github 时可选
    "app/main.py": "…",
    "tests/test_main.py": "…"
  },
  "trigger_replan": true          // 评估后是否回写画像+触发再规划
}
```

**响应 `EvaluationReport`**

```jsonc
{
  "evaluation_id": "EVL_xxx",
  "practice_id": "PRA_xxx",
  "skill_id": "rag_retriever",
  "overall_score": 76,
  "skill_scores": [ { "skill_id": "rag_retriever", "theory": 90, "practice": 70 } ],
  "evidence": [
    { "type": "syntax",    "passed": true,  "message": "「main.py」可编译" },
    { "type": "structure", "passed": true,  "message": "存在 1 个函数、0 个类" },
    { "type": "runnable",  "passed": true,  "message": "存在 __main__ 入口" },
    { "type": "tests",     "passed": true,  "message": "发现测试用例 2 个" },
    { "type": "lint",      "passed": true,  "message": "未发现明显代码质量问题" }
  ],
  "next_recommendations": [ "测试覆盖不足：建议补充边界用例" ],
  "profile_updated": true,   // 已回写 user_skills（practice_score/confidence/evidence）
  "replanned": true          // 已触发学习路线重规划（保留 done 任务）
}
```

- `skill_scores` 区分 `theory`（语法/结构/代码质量）与 `practice`（可运行性/测试）。
- `trigger_replan=false` 时仅回写画像、不重规划。
- `practice_id` 不存在 → 422；`GET /api/v1/practice/{id}` 拉取 → 404 `40420`。

**本节错误**

| 场景 | HTTP | code |
| --- | --- | --- |
| 非 JSON body | 400 | 40001 |
| 参数非法 / 实践不存在 / 任务不存在 | 422 | 42200 |
| 实践任务不存在（查询） | 404 | 40420 |
| 实践生成失败（走兜底） | 500 | 50050 |
| 能力评估失败（走兜底，仅回写失败不回退画像） | 500 | 50060 |

## 8. 长期记忆与 Middleware（阶段 7）

长期记忆分三种命名空间：`semantic`（事实）、`procedural`（学习偏好，复用 `user_preferences`）、`summary`（对话摘要）；另用 `memory_events` 沉淀成长经历（Episodic）、`pending_actions` 支撑 HITL 人工确认。

### 8.1 写入记忆

```
POST /api/v1/memory/remember
```

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
{ "status": "ok", "mem_id": "MEM_xxx", "pii_redacted": true, "vectorized": true }
```

- 写入路径自动过 PII 脱敏（`[REDACTED:email]` 等），`pii_redacted` 透出是否命中。
- `MEMORY_EMBED_ENABLED=false` 或向量化失败时 `vectorized=false`，召回退化为关键词匹配。

### 8.2 语义检索

```
POST /api/v1/memory/search
```

```jsonc
{ "user_id": "U10001", "namespace": "semantic", "query": "用户目标", "top_k": 5 }
```

响应 `MemorySearchResult[]`：`[{ "mem_id", "key", "text", "namespace", "payload", "score" }]`。

列出 / 删除：

```
GET    /api/v1/memory?user_id=U10001&namespace=semantic&limit=50
DELETE /api/v1/memory/<mem_id>
```

### 8.3 经历记忆（Episodic）

```
POST /api/v1/memory/events
```

```jsonc
{
  "user_id": "U10001",
  "event_type": "evaluation_done",
  "ref_ids": { "evaluation_id": "EVL_xxx", "plan_id": "PLAN_xxx" },
  "summary": "完成 rag_retriever 代码评估，overall=76",
  "payload": { "overall_score": 76 }
}
```

`event_type` ∈ `profile_updated | gap_reported | plan_generated | plan_replanned | practice_created | evaluation_done | conversation_summary`。

```
GET /api/v1/memory/events?user_id=U10001&event_type=evaluation_done&limit=20
```

（阶段 3~6 接口成功后会 best-effort 自动沉淀 Episode，重复调用不阻断主流程。）

### 8.4 摘要压缩

```
POST /api/v1/memory/summarize
```

```jsonc
{ "user_id": "U10001", "thread_id": "T20260826", "messages": [ { "role": "user", "content": "…" } ] }
```

响应：`{ "summary": "…", "stored": true, "is_llm_enhanced": false }`。消息轮数 ≥ `MEMORY_SUMMARY_THRESHOLD_MESSAGES` 时才落库；chat 入口超阈值自动触发。

### 8.5 HITL 人工确认

```
POST /api/v1/memory/pending                      // 暂停守卫操作
GET  /api/v1/memory/pending?user_id=U10001&status=pending   // 待确认列表
POST /api/v1/memory/pending/<pa_id>/confirm
```

```jsonc
// POST /pending
{ "user_id": "U10001", "action_type": "plan_reset", "summary": "重置学习计划将丢弃当前进度" }
// POST /pending/<pa_id>/confirm
{ "user_id": "U10001", "decision": "approve" }   // approve | reject
```

未确认/已过期/已决不可重复处理 → 422。

### 8.6 错误

| 场景 | HTTP | code |
| --- | --- | --- |
| 非 JSON body | 400 | 40001 |
| 参数非法 / 非法命名空间 / 决策已决 | 422 | 42200 |
| 记忆记录不存在（查询/删除/确认） | 404 | 40470 |
| 记忆写入/召回失败（走兜底，不阻断主流程） | 500 | 50070 |

## 9. 前端整合与比赛 Demo（阶段 8）

> 阶段 8 为「整合 + 产品化」：仅新增 3 处只读/聚合/流式编排点，业务逻辑全部复用阶段 3~7。
> 演示数据可用 `python -m scripts.demo_init` 一键初始化（幂等）；`python -m scripts.run_demo` 跑链路核对。

### 9.1 技能图谱（只读）

`GET /api/v1/graph` → 全量图谱（节点 + 边，供前端 SVG 布局）。

```jsonc
{
  "nodes": [{ "id": "python", "name": "Python", "category": "Language" }],
  "edges": [{ "source": "python", "target": "llm_api" }]
}
```

### 9.2 工作台聚合（只读）

`GET /api/v1/dashboard/<user_id>` → `DashboardDTO`（画像 + 最新计划 + 最新评估 + 成长事件 + 长期记忆，运行时聚合不落库）。

```jsonc
{
  "user_id": "demo_user",
  "profile": { "skill_count": 3, "skills": [{ "skill_id", "name", "theory_score", "practice_score", "level" }] },
  "latest_plan": { "plan_id", "goal", "status", "total_tasks", "done_tasks", "progress" } | null,
  "latest_evaluation": { "evaluation_id", "skill_id", "overall_score", "replanned", "created_at" } | null,
  "growth": [{ "id", "event_type", "summary", "created_at" }],
  "facts": [{ "key", "text", "namespace" }]
}
```

无数据时各字段给空值/null（不返回 500），前端空态兜底。

### 9.3 计划列表（只读）

`GET /api/v1/plan/list?user_id=demo_user` → `[{ "plan_id", "goal", "status", "progress", "created_at" }]`（未知用户返回空列表）。

### 9.4 流式对话（SSE）

`POST /api/v1/chat/stream`（`Content-Type: text/event-stream`）

请求体与 `POST /api/v1/chat` 一致（`user_id` / `thread_id` / `message` / `intent_hint`）。

事件序列（每行 `data: <json>`，空行分隔）：

```
data: {"type":"meta","intent":"plan_generation","route":"plan","thread_id":"T1"}
data: {"type":"delta","text":"…"}     // 可多条，增量渲染
data: {"type":"done","thread_id":"T1","intent":"plan_generation","route":"plan"}
```

- `STREAM_ENABLED=false` 时退化为一次性 `delta`（仍是流式响应、前端无需改逻辑）。
- 异常时降级为 `data: {"type":"error","message":"…"}`，前端据此回退非流式 `/chat`。

### 9.5 阶段 8 错误码

| 场景 | HTTP | code |
| --- | --- | --- |
| user_id 非法 / 缺失参数 | 422 | 42200 |
| 聚合/图谱资源不可用（表未就绪） | 500 | 50080 |
| SSE 流式异常（降级为一次性 error 事件） | 500 | 50081 |

## 10. 阶段 1 错误码

| code | HTTP | 说明 |
| --- | --- | --- |
| 0 | 200 | 成功 |
| 40001 | 400 | JSON 格式错误 |
| 40400 | 404 | 资源不存在 |
| 42200 | 422 | 业务校验失败 |
| 50000 | 500 | 服务端未知错误 |
| 50001 | 500 | LLM 调用失败（当前由规则兜底，一般不会出现） |
| 50005 | 500 | Checkpointer/DB 初始化失败 |
| 50010 | 500 | Embedding 服务失败（阶段 2 RAG） |
| 50011 | 500 | 检索失败（阶段 2 RAG） |
| 50030 | 500 | 缺口计算失败（阶段 4 Gap，走兜底） |
| 40410 | 404 | 学习计划不存在（阶段 5 Todo） |
| 50040 | 500 | 学习计划生成/重规划/流转失败（阶段 5 Todo，走兜底） |
| 40420 | 404 | 实践任务不存在（阶段 6 Practice） |
| 50050 | 500 | 实践任务生成失败（阶段 6 Practice，走兜底） |
| 50060 | 500 | 能力评估失败（阶段 6 Evaluation，走兜底） |
| 40470 | 404 | 记忆记录不存在（阶段 7 Memory） |
| 50080 | 500 | 图谱/Dashboard 聚合资源不可用（阶段 8，表未就绪） |
| 50081 | 500 | SSE 流式异常（阶段 8，降级为一次性 error 事件） |
| 50070 | 500 | 记忆写入/召回/压缩失败（阶段 7 Memory，走兜底不阻断） |

## 11. 运行方式

```bash
# 1. 配置环境（复制模板；或直接使用已生成的 .env）
cp .env.example .env

# 2. 初始化数据库（配置了 DATABASE_URL 时执行一次）
.venv/bin/python -m scripts.init_db

# 3. 灌入技能字典与技能图/岗位种子（幂等；--dry-run 预览）
.venv/bin/python -m scripts.seed_skills
.venv/bin/python -m scripts.seed_skill_graph

# 3b.（阶段 8 演示，可选）一键造演示数据（含 demo_user 画像与示例代码）
.venv/bin/python -m scripts.demo_init

# 4. 启动（端口默认 5000；macOS 若被 AirPlay 占用可设 PORT，如 5050）
.venv/bin/python -m app
PORT=8081 .venv/bin/python -m app
# 或
flask --app app run

# 5.（阶段 8 演示，可选）服务启动后核对 3~5 分钟演示链路
.venv/bin/python -m scripts.run_demo
```
