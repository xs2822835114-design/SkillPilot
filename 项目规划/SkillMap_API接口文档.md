# SkillMap 个人技术栈成长智能体 — RESTful API 接口文档

> 版本：V1.0  
> 依据：《SkillMap_个人技术栈成长智能体_项目计划书》V1.0  
> 接口风格：RESTful（资源化 URL + 标准 HTTP 方法 + 状态码）  
> 关联前端：Vue  
> 关联后端：Flask + LangGraph

---

## 1. 文档说明

本接口文档覆盖 SkillMap 全生命周期能力，包括：用户、会话/聊天、技术画像、技能缺口、学习计划、实践任务、能力评估、RAG 知识库、技能图谱、长期记忆、项目与成长报告。

所有接口遵循以下核心原则（源自计划书第 11 节「全局接口规范」）：

- JSON 字段使用 `snake_case`；ID 统一使用 `string`；时间使用 ISO 8601。
- 成功响应统一返回 `{"code":0,"message":"ok","data":...}`。
- 错误响应统一返回 `{"code":非0,"message":"...","data":null,"trace_id":"..."}`。
- 涉及 LLM 生成的接口均支持流式（SSE）与非流式两种模式。
- 需要 RAG 证据的结论必须携带 `source/title/chunk_id/score`。

---

## 2. 通用规范

### 2.1 Base URL 与版本

```
生产环境：https://api.skillmap.example.com/api/v1
本地开发：http://localhost:5000/api/v1
健康检查：http://localhost:5000/health
```

### 2.2 认证方式

采用 `Bearer Token` 认证。除 `/health`、`/api/v1/auth/login` 外，所有接口请求头需携带：

```
Authorization: Bearer <access_token>
X-User-ID: U10001          # 推荐显式传递，便于网关鉴权与审计
X-Trace-ID: 可选            # 不传则服务端自动生成并返回
```

Token 失效返回 HTTP `401`。

### 2.3 统一响应结构

| 场景 | HTTP 状态码 | body |
| --- | --- | --- |
| 成功 | 200 / 201 / 204 | `{"code":0,"message":"ok","data":...}` |
| 参数错误 | 400 | `{"code":40000,"message":"...","data":null,"trace_id":"..."}` |
| 未认证 | 401 | 同上 |
| 无权限 | 403 | 同上 |
| 资源不存在 | 404 | 同上 |
| 状态冲突 | 409 | 同上 |
| 校验失败 | 422 | 同上 |
| 服务端错误 | 500 | 同上 |

> 注：`code` 为业务错误码（见第 6 节），`data` 结构随接口而定。

### 2.4 分页规范

列表类接口统一使用 query 参数 `page`（默认 1）、`page_size`（默认 20，最大 100），返回：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "items": [],
    "pagination": { "page": 1, "page_size": 20, "total": 100, "total_pages": 5 }
  }
}
```

### 2.5 流式响应（SSE）

聊天 / Agent 工作流 / 评估等耗时接口支持流式，请求头增加：

```
Accept: text/event-stream
```

事件格式（`data:` 中的 JSON）：

```json
data: {"event":"agent_trace","data":{"agent":"gap_agent","workflow_status":"running"}}
data: {"event":"delta","data":{"content":"..."}}
data: {"event":"tool_call","data":{"tool":"rag_search","args":{"query":"..."}}}
data: {"event":"done","data":{"route":"gap_analysis","result":{...}}}
data: {"event":"error","data":{"code":50001,"message":"..."}}
```

### 2.6 幂等性

创建类接口（尤其涉及 Agent 触发的）支持请求头 `Idempotency-Key`。服务端对该 key 在同一时间窗内返回首次执行结果，避免重复触发 LLM / RAG 任务。

---

## 3. 接口总览

| 模块 | 方法 | 路径 | 说明 |
| --- | --- | --- | --- |
| 系统 | GET | `/health` | 健康检查 |
| 认证 | POST | `/api/v1/auth/login` | 登录获取 Token |
| 认证 | POST | `/api/v1/auth/logout` | 退出登录 |
| 用户 | POST/GET/PATCH/DELETE | `/api/v1/users` | 用户 CRUD |
| 聊天 | POST | `/api/v1/chat` | 对话 / Agent 编排入口（支持 SSE） |
| 会话 | GET/DELETE | `/api/v1/threads/{thread_id}` | 会话查询与删除 |
| 画像 | GET/PATCH | `/api/v1/users/{user_id}/profile` | 技术画像 |
| 画像 | POST | `/api/v1/users/{user_id}/profile/extract` | 从文本/项目提取画像 |
| 画像 | GET/PUT/DELETE | `/api/v1/users/{user_id}/skills/{skill_id}` | 用户技能 |
| 缺口 | POST | `/api/v1/users/{user_id}/gap-analysis` | 触发 Gap 分析 |
| 缺口 | GET | `/api/v1/users/{user_id}/gap-reports` | 缺口报告列表 |
| 计划 | POST | `/api/v1/users/{user_id}/plans` | 生成学习计划 |
| 计划 | GET/PATCH/DELETE | `/api/v1/plans/{plan_id}` | 计划详情/修改/删除 |
| 任务 | GET | `/api/v1/plans/{plan_id}/tasks` | 计划任务列表 |
| 任务 | PATCH | `/api/v1/tasks/{task_id}` | 任务状态流转 |
| 实践 | POST | `/api/v1/tasks/{task_id}/practice` | 生成实践任务 |
| 实践 | GET | `/api/v1/practices/{practice_id}` | 实践任务详情 |
| 评估 | POST | `/api/v1/evaluations` | 提交评估请求 |
| 评估 | POST | `/api/v1/evaluations/{evaluation_id}/run` | 触发评估 |
| 评估 | GET | `/api/v1/evaluations/{evaluation_id}` | 评估报告 |
| RAG | POST | `/api/v1/rag/ingest` | 文档入库 |
| RAG | POST | `/api/v1/rag/search` | 语义检索 |
| RAG | POST | `/api/v1/rag/ask` | 技术问答（带引用） |
| RAG | GET/DELETE | `/api/v1/rag/documents/{doc_id}` | 文档管理 |
| 图谱 | GET | `/api/v1/skills` | 技能字典 |
| 图谱 | GET | `/api/v1/skills/{skill_id}` | 技能详情 |
| 图谱 | GET | `/api/v1/skills/{skill_id}/prerequisites` | 前置技能 |
| 图谱 | GET | `/api/v1/roles` | 岗位列表 |
| 图谱 | GET | `/api/v1/roles/{role_id}/skills` | 岗位能力模型 |
| 记忆 | GET | `/api/v1/users/{user_id}/memory` | 记忆列表 |
| 记忆 | POST | `/api/v1/users/{user_id}/memory/search` | 记忆检索 |
| 记忆 | PATCH/DELETE | `/api/v1/memory/{memory_id}` | 记忆修正/删除 |
| 项目 | POST | `/api/v1/users/{user_id}/projects` | 创建项目 |
| 项目 | POST | `/api/v1/projects/{project_id}/analysis` | 分析项目 |
| 文件 | POST | `/api/v1/files/upload` | 文件上传（代码/资料） |
| 看板 | GET | `/api/v1/users/{user_id}/dashboard` | 仪表盘聚合 |
| 成长 | GET | `/api/v1/users/{user_id}/growth-report` | 成长报告 |
| 轨迹 | GET | `/api/v1/users/{user_id}/traces` | Agent 执行轨迹 |

---

## 4. 详细接口定义

### 4.1 系统

#### 4.1.1 健康检查

```
GET /health
```

**响应**

```json
{ "code": 0, "message": "ok", "data": { "status": "up", "version": "v1.0.0", "db": "ok", "llm": "ok" } }
```

---

### 4.2 认证

#### 4.2.1 登录

```
POST /api/v1/auth/login
```

**请求体**

```json
{ "username": "user01", "password": "***", "device": "web" }
```

**响应 200**

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "access_token": "eyJhbGciOi...",
    "expires_in": 7200,
    "user": { "user_id": "U10001", "name": "张三", "target_role": "ai_application_engineer" }
  }
}
```

---

### 4.3 用户

#### 4.3.1 创建用户

```
POST /api/v1/users
```

**请求体**

```json
{
  "name": "张三",
  "target_role": "ai_application_engineer",
  "bio": "我会 Java、Spring Boot、MySQL、Redis、Vue，做过后端项目",
  "meta": { "source": "demo" }
}
```

**响应 201**

```json
{ "code": 0, "message": "ok", "data": { "user_id": "U10001", "name": "张三", "created_at": "2026-08-26T10:00:00+08:00" } }
```

#### 4.3.2 获取用户

```
GET /api/v1/users/{user_id}
```

**响应 200**

```json
{
  "code": 0, "message": "ok",
  "data": {
    "user_id": "U10001", "name": "张三",
    "target_role": "ai_application_engineer",
    "profile_version": 12,
    "created_at": "2026-08-26T10:00:00+08:00"
  }
}
```

#### 4.3.3 更新用户

```
PATCH /api/v1/users/{user_id}
```

**请求体**（部分字段）

```json
{ "target_role": "ai_backend_engineer" }
```

---

### 4.4 会话与聊天（Orchestrator 入口）

#### 4.4.1 发送消息 / Agent 编排

```
POST /api/v1/chat
```

统一入口：识别用户意图 → Orchestrator 路由 → 调用对应 Agent → 返回结果。支持流式（见 2.5）。

**请求体**

```json
{
  "user_id": "U10001",
  "thread_id": "T20260826",
  "message": "我想在三个月内转向 AI 应用开发",
  "intent_hint": null,
  "attachments": []
}
```

**响应 200（非流式）**

```json
{
  "code": 0, "message": "ok",
  "data": {
    "route": "gap_analysis",
    "steps": ["profile_read", "gap_analysis", "plan_generation"],
    "reason": "用户已提供目标转型方向",
    "reply": "根据你的画像，关键缺口是 RAG 与向量检索，已为你生成学习路径…",
    "workflow_status": "done",
    "artifacts": { "gap_report_id": "GAP_001", "plan_id": "PLAN_001" },
    "evidence": [
      { "chunk_id": "C001", "title": "LangGraph Docs", "source": "official", "score": 0.87, "url": "https://..." }
    ]
  }
}
```

#### 4.4.2 获取会话消息

```
GET /api/v1/threads/{thread_id}/messages?page=1&page_size=20
```

**响应 200**

```json
{
  "code": 0, "message": "ok",
  "data": {
    "items": [
      { "message_id": "MSG_001", "role": "user", "content": "我想转向 AI 应用开发", "created_at": "..." },
      { "message_id": "MSG_002", "role": "assistant", "content": "...", "route": "gap_analysis", "created_at": "..." }
    ],
    "pagination": { "page": 1, "page_size": 20, "total": 2, "total_pages": 1 }
  }
}
```

#### 4.4.3 删除会话

```
DELETE /api/v1/threads/{thread_id}
```

**响应 204**（无 body）

---

### 4.5 技术画像（Profile Agent）

#### 4.5.1 获取技术画像

```
GET /api/v1/users/{user_id}/profile
```

**响应 200**

```json
{
  "code": 0, "message": "ok",
  "data": {
    "user_id": "U10001",
    "version": 12,
    "skills": [
      {
        "skill_id": "java", "name": "Java",
        "level": 4, "theory_score": 80, "practice_score": 85, "confidence": 0.95,
        "evidence": ["MSG_001", "PRJ_001"],
        "updated_at": "2026-08-26T10:00:00+08:00"
      }
    ],
    "preferences": { "learning_style": "project_driven", "available_hours_per_week": 8 }
  }
}
```

#### 4.5.2 提取 / 更新画像（Profile Agent）

```
POST /api/v1/users/{user_id}/profile/extract
```

支持从自述、项目简介、代码等提取技能。异步任务，返回 `task_id`，完成后可轮询或通过 SSE 订阅。

**请求体**

```json
{
  "source_type": "conversation",
  "content": "我会Java、Spring Boot、MySQL，做过订单系统",
  "evidence_id": "MSG_001",
  "mode": "incremental"
}
```

**响应 200**

```json
{
  "code": 0, "message": "ok",
  "data": {
    "task_id": "TASK_EX_001",
    "status": "processing",
    "extract_result": {
      "skills": [
        { "skill_id": "java", "level": 4, "theory_score": 80, "practice_score": 85, "confidence": 0.95, "evidence": ["MSG_001"] }
      ],
      "preferences": {}
    }
  }
}
```

#### 4.5.3 手动调整技能等级

```
PUT /api/v1/users/{user_id}/skills/{skill_id}
```

**请求体**

```json
{ "level": 3, "theory_score": 70, "practice_score": 75, "confidence": 0.9, "note": "用户手动确认" }
```

#### 4.5.4 删除技能

```
DELETE /api/v1/users/{user_id}/skills/{skill_id}
```

**响应 204**

---

### 4.6 技能缺口分析（Gap Agent）

#### 4.6.1 触发 Gap 分析

```
POST /api/v1/users/{user_id}/gap-analysis
```

**请求体**

```json
{
  "target_role": "ai_application_engineer",
  "current_profile_version": 12,
  "include_rag": true,
  "async": false
}
```

**响应 200**

```json
{
  "code": 0, "message": "ok",
  "data": {
    "gap_report_id": "GAP_001",
    "target_role": "ai_application_engineer",
    "generated_at": "2026-08-26T11:00:00+08:00",
    "gaps": [
      {
        "skill_id": "rag", "name": "RAG 应用开发",
        "priority": 0.89, "score": 42,
        "reason": "岗位要求高且用户缺少实践",
        "prerequisites": ["embedding", "vector_db"],
        "evidence": ["JOB_DOC_12"]
      }
    ],
    "summary": "共 4 个关键缺口，建议优先补齐 RAG 与向量检索"
  }
}
```

> `async=true` 时返回 `{"task_id":"TASK_GAP_001","status":"processing"}`，完成后写库，可轮询 `GET /api/v1/gap-reports/{gap_report_id}`。

#### 4.6.2 缺口报告列表 / 详情

```
GET /api/v1/users/{user_id}/gap-reports?page=1&page_size=20
GET /api/v1/gap-reports/{gap_report_id}
```

---

### 4.7 学习计划（Planner Agent）

#### 4.7.1 生成学习计划

```
POST /api/v1/users/{user_id}/plans
```

**请求体**

```json
{
  "gap_report_id": "GAP_001",
  "available_hours_per_week": 8,
  "deadline": "2026-11-30",
  "learning_style": "project_driven",
  "async": false
}
```

**响应 201**

```json
{
  "code": 0, "message": "ok",
  "data": {
    "plan_id": "PLAN_001",
    "user_id": "U10001",
    "goal": "AI 应用开发",
    "status": "active",
    "created_at": "2026-08-26T12:00:00+08:00",
    "phases": [
      {
        "phase_id": "P1", "title": "RAG 基础", "order": 1,
        "tasks": [
          {
            "task_id": "T1", "title": "实现 PDF 到 pgvector 入库",
            "status": "pending", "skill_id": "rag",
            "estimated_hours": 4,
            "resources": [{ "chunk_id": "C001", "title": "LangGraph Docs", "url": "..." }],
            "acceptance": "完成 Top-K 检索接口"
          }
        ]
      }
    ]
  }
}
```

#### 4.7.2 计划详情

```
GET /api/v1/plans/{plan_id}
```

#### 4.7.3 修改 / 重规划

```
PATCH /api/v1/plans/{plan_id}
```

用于用户反馈或评估后局部重规划。

**请求体**

```json
{ "action": "replan", "feedback": "希望减少纯课程，多安排项目", "keep_completed_tasks": true }
```

#### 4.7.4 删除计划

```
DELETE /api/v1/plans/{plan_id}
```

#### 4.7.5 任务列表

```
GET /api/v1/plans/{plan_id}/tasks
```

#### 4.7.6 任务状态流转

```
PATCH /api/v1/tasks/{task_id}
```

状态机：`pending → doing → done`，回退：`doing → pending`。

**请求体**

```json
{ "status": "doing", "started_at": "2026-08-27T09:00:00+08:00" }
```

**响应 200**

```json
{ "code": 0, "message": "ok", "data": { "task_id": "T1", "status": "doing", "updated_at": "..." } }
```

---

### 4.8 实践任务（Practice Agent）

#### 4.8.1 生成实践任务

```
POST /api/v1/tasks/{task_id}/practice
```

**请求体**

```json
{
  "skill_id": "rag",
  "level_target": 3,
  "format": "project"
}
```

**响应 201**

```json
{
  "code": 0, "message": "ok",
  "data": {
    "practice_id": "PR_001",
    "task_id": "T1",
    "deliverables": ["代码仓库", "README", "测试结果"],
    "rubric": [
      { "criterion": "Embedding", "weight": 0.2 },
      { "criterion": "Retriever", "weight": 0.3 },
      { "criterion": "验收标准满足度", "weight": 0.5 }
    ],
    "instructions": "…",
    "created_at": "..."
  }
}
```

#### 4.8.2 实践任务详情

```
GET /api/v1/practices/{practice_id}
```

---

### 4.9 能力评估（Evaluation Agent）

#### 4.9.1 提交评估请求

```
POST /api/v1/evaluations
```

**请求体**

```json
{
  "user_id": "U10001",
  "practice_id": "PR_001",
  "artifact_type": "github",
  "artifact_url": "https://github.com/example/rag-demo",
  "artifact_file_id": null,
  "languages": ["python"]
}
```

**响应 202（异步任务）**

```json
{
  "code": 0, "message": "ok",
  "data": { "evaluation_id": "EV_001", "status": "queued" }
}
```

#### 4.9.2 触发 / 重跑评估

```
POST /api/v1/evaluations/{evaluation_id}/run
```

#### 4.9.3 评估报告

```
GET /api/v1/evaluations/{evaluation_id}
```

**响应 200**

```json
{
  "code": 0, "message": "ok",
  "data": {
    "evaluation_id": "EV_001",
    "practice_id": "PR_001",
    "status": "done",
    "overall_score": 76,
    "skill_scores": [
      { "skill_id": "rag", "theory": 60, "practice": 78 }
    ],
    "evidence": [
      { "type": "code", "message": "使用 pgvector 进行相似度检索" },
      { "type": "test", "message": "检索接口 12/15 用例通过" }
    ],
    "next_recommendations": ["补充 metadata filter"],
    "profile_updated": true,
    "replanned_plan_id": "PLAN_001",
    "evaluated_at": "2026-08-28T18:00:00+08:00"
  }
}
```

> 评估完成后自动更新 `user_skills` 并触发 Gap 重算与计划调整。

---

### 4.10 RAG 知识库

#### 4.10.1 文档入库

```
POST /api/v1/rag/ingest
```

支持 URL 或已上传文件（`multipart/form-data`）。

**请求（application/json，URL 方式）**

```json
{
  "source_type": "url",
  "url": "https://docs.langchain.com/...",
  "category": "technology",
  "metadata": { "tags": ["langchain", "rag"], "author": "official" }
}
```

**响应 202**

```json
{
  "code": 0, "message": "ok",
  "data": {
    "document_id": "DOC_001",
    "status": "processing",
    "chunk_count": 0
  }
}
```

完成后可通过 `GET /api/v1/rag/documents/{doc_id}` 查询 `chunk_count` 与解析状态。

#### 4.10.2 语义检索

```
POST /api/v1/rag/search
```

**请求体**

```json
{
  "query": "LangGraph 学习前需要哪些基础？",
  "top_k": 5,
  "filters": { "category": "technology" },
  "hybrid": true
}
```

**响应 200**

```json
{
  "code": 0, "message": "ok",
  "data": {
    "results": [
      {
        "chunk_id": "C001",
        "document_id": "DOC_001",
        "title": "LangGraph Docs",
        "source": "official",
        "category": "technology",
        "url": "https://...",
        "score": 0.87,
        "content": "…",
        "metadata": {}
      }
    ]
  }
}
```

#### 4.10.3 技术问答（RAG 带引用）

```
POST /api/v1/rag/ask
```

**请求体**

```json
{ "query": "RAG 的 metadata filter 有什么用？", "top_k": 5, "filters": { "category": "technology" } }
```

**响应 200**

```json
{
  "code": 0, "message": "ok",
  "data": {
    "answer": "metadata filter 用于在向量检索前按元数据缩小候选集…",
    "evidence": [
      { "chunk_id": "C002", "title": "RAG Guide", "source": "official", "score": 0.91, "url": "..." }
    ]
  }
}
```

#### 4.10.4 文档管理

```
GET    /api/v1/rag/documents?category=technology&page=1&page_size=20
GET    /api/v1/rag/documents/{doc_id}
DELETE /api/v1/rag/documents/{doc_id}
```

---

### 4.11 技能图谱（Skill Graph）

#### 4.11.1 技能字典

```
GET /api/v1/skills?category=ai&page=1&page_size=20
```

**响应 200**

```json
{
  "code": 0, "message": "ok",
  "data": {
    "items": [
      { "skill_id": "rag", "name": "RAG 应用开发", "category": "ai", "description": "…" }
    ],
    "pagination": { "page": 1, "page_size": 20, "total": 120, "total_pages": 6 }
  }
}
```

#### 4.11.2 技能详情与依赖

```
GET /api/v1/skills/{skill_id}
GET /api/v1/skills/{skill_id}/prerequisites    # 前置技能（先学什么）
GET /api/v1/skills/{skill_id}/dependents       # 依赖它的技能
```

**响应（prerequisites 示例）**

```json
{
  "code": 0, "message": "ok",
  "data": {
    "skill_id": "rag",
    "prerequisites": [
      { "skill_id": "embedding", "relation_type": "requires", "weight": 0.9 },
      { "skill_id": "vector_db", "relation_type": "requires", "weight": 0.8 }
    ]
  }
}
```

#### 4.11.3 岗位与能力模型

```
GET /api/v1/roles
GET /api/v1/roles/{role_id}
GET /api/v1/roles/{role_id}/skills
```

**响应（role skills 示例）**

```json
{
  "code": 0, "message": "ok",
  "data": {
    "role_id": "ai_application_engineer",
    "name": "AI 应用开发工程师",
    "skills": [
      { "skill_id": "rag", "importance": 0.9, "target_level": 4 },
      { "skill_id": "python", "importance": 1.0, "target_level": 4 }
    ]
  }
}
```

---

### 4.12 长期记忆（Memory）

#### 4.12.1 记忆列表

```
GET /api/v1/users/{user_id}/memory?type=episodic&page=1&page_size=20
```

**响应 200**

```json
{
  "code": 0, "message": "ok",
  "data": {
    "items": [
      { "memory_id": "MEM_001", "type": "semantic", "key": "preference.learning_style", "content": { "learning_style": "project_driven" }, "updated_at": "..." }
    ],
    "pagination": { "page": 1, "page_size": 20, "total": 5, "total_pages": 1 }
  }
}
```

#### 4.12.2 记忆检索

```
POST /api/v1/users/{user_id}/memory/search
```

**请求体**

```json
{ "query": "这个用户以前做过什么项目？", "type": "episodic", "top_k": 5 }
```

**响应 200**

```json
{
  "code": 0, "message": "ok",
  "data": {
    "results": [
      { "memory_id": "MEM_002", "type": "episodic", "content": { "event": "完成 RAG 项目", "result": "通过基础评估" }, "score": 0.82 }
    ]
  }
}
```

#### 4.12.3 记忆修正 / 删除

```
PATCH  /api/v1/memory/{memory_id}
DELETE /api/v1/memory/{memory_id}
```

用户可修正或删除被判定为错误的长期记忆（防记忆污染）。

---

### 4.13 项目与文件

#### 4.13.1 创建项目

```
POST /api/v1/users/{user_id}/projects
```

**请求体**

```json
{
  "name": "RAG Demo",
  "description": "基于 pgvector 的检索增强生成项目",
  "repo_url": "https://github.com/example/rag-demo"
}
```

#### 4.13.2 分析项目（提取技能/证据）

```
POST /api/v1/projects/{project_id}/analysis
```

**请求体**

```json
{ "analysis_type": "skill_extraction" }
```

**响应 202**

```json
{ "code": 0, "message": "ok", "data": { "task_id": "TASK_AN_001", "status": "processing" } }
```

#### 4.13.3 文件上传

```
POST /api/v1/files/upload
```

`multipart/form-data`，字段：`file`（代码压缩包/文档）、`purpose`（`rag_document` | `evaluation_artifact`）。

**响应 201**

```json
{ "code": 0, "message": "ok", "data": { "file_id": "FILE_001", "filename": "rag-demo.zip", "size": 1024000, "url": "/api/v1/files/FILE_001" } }
```

---

### 4.14 看板与成长报告

#### 4.14.1 仪表盘聚合

```
GET /api/v1/users/{user_id}/dashboard
```

聚合画像、缺口、计划、评估进度，供 Vue Dashboard 一次加载。

**响应 200**

```json
{
  "code": 0, "message": "ok",
  "data": {
    "profile_version": 12,
    "skill_count": 8,
    "top_skills": [ { "skill_id": "java", "name": "Java", "practice_score": 85 } ],
    "active_gaps": 3,
    "active_plan": { "plan_id": "PLAN_001", "progress": 0.4, "done_tasks": 2, "total_tasks": 5 },
    "latest_evaluation": { "evaluation_id": "EV_001", "overall_score": 76 },
    "streak": { "learning_days": 14, "last_activity_at": "..." }
  }
}
```

#### 4.14.2 成长报告

```
GET /api/v1/users/{user_id}/growth-report?range=30d
```

**响应 200**

```json
{
  "code": 0, "message": "ok",
  "data": {
    "report_id": "GR_001",
    "range": "30d",
    "overview": "过去 30 天从 60 分提升至 76 分",
    "trend": [ { "date": "2026-08-01", "overall_score": 60 }, { "date": "2026-08-26", "overall_score": 76 } ],
    "skill_delta": [ { "skill_id": "rag", "before": 0, "after": 78 } ],
    "highlights": ["完成 1 个 RAG 项目并通过评估", "画像新增 2 项技能"]
  }
}
```

#### 4.14.3 Agent 执行轨迹（Trace）

```
GET /api/v1/users/{user_id}/traces?thread_id=T20260826&page=1&page_size=20
```

**响应 200**

```json
{
  "code": 0, "message": "ok",
  "data": {
    "items": [
      {
        "trace_id": "TR_001",
        "thread_id": "T20260826",
        "route": "gap_analysis",
        "steps": ["profile_read", "gap_analysis", "plan_generation"],
        "agents": ["profile_agent", "gap_agent", "planner_agent"],
        "status": "done",
        "started_at": "...", "finished_at": "...",
        "tool_calls": [ { "tool": "rag_search", "args": { "query": "..." } } ]
      }
    ],
    "pagination": { "page": 1, "page_size": 20, "total": 1, "total_pages": 1 }
  }
}
```

---

## 5. 核心数据模型（Schema 摘要）

### 5.1 User

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| user_id | string | 用户 ID |
| name | string | 姓名 |
| target_role | string? | 目标岗位 ID |
| profile_version | int | 画像版本号 |
| created_at | string(ISO8601) | 创建时间 |

### 5.2 SkillProfilePatch / Skill

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| skill_id | string | 技能 ID |
| level | int | 等级 1-5 |
| theory_score / practice_score | number | 理论/实践得分 |
| confidence | number | 置信度 0-1 |
| evidence | string[] | 证据 ID 列表 |
| updated_at | string | 更新时间 |

### 5.3 SkillGapReport

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| gap_report_id | string | 报告 ID |
| target_role | string | 目标岗位 |
| gaps[] | array | 缺口列表 |
| gaps[].priority | number | 优先级 0-1 |
| gaps[].score | number | 缺口分 |
| gaps[].prerequisites | string[] | 前置技能 |
| gaps[].evidence | string[] | 证据 ID |

### 5.4 LearningPlan / LearningTask

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| plan_id | string | 计划 ID |
| goal | string | 计划目标 |
| status | string | active / paused / completed |
| phases[].tasks[].task_id | string | 任务 ID |
| tasks[].status | string | pending / doing / done |
| tasks[].acceptance | string | 验收标准 |
| tasks[].estimated_hours | int | 预计时长 |

### 5.5 EvaluationReport

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| evaluation_id | string | 评估 ID |
| overall_score | int | 总分 |
| skill_scores[].theory/practice | int | 各技能得分 |
| evidence[] | array | 证据 |
| next_recommendations | string[] | 下一步建议 |

### 5.6 RAG Evidence

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| chunk_id | string | 分块 ID |
| title / source | string | 标题/来源 |
| category | string | 分类 |
| url | string | 引用链接 |
| score | number | 相关度 |
| content | string | 内容片段 |

---

## 6. 错误码表

| code | HTTP | 说明 |
| --- | --- | --- |
| 0 | 200 | 成功 |
| 40000 | 400 | 请求参数缺失或非法 |
| 40001 | 400 | JSON 格式错误 |
| 40100 | 401 | 未认证 / Token 失效 |
| 40300 | 403 | 无权限 |
| 40400 | 404 | 资源不存在 |
| 40900 | 409 | 状态冲突（如任务已 done 不可重复流转） |
| 42200 | 422 | 业务校验失败 |
| 42900 | 429 | 频率限制 / LLM 配额不足 |
| 50000 | 500 | 服务端未知错误 |
| 50001 | 500 | LLM 调用失败 |
| 50002 | 502 | RAG 检索失败 |
| 50003 | 500 | 评估执行失败 |
| 50004 | 500 | 外部仓库获取失败（GitHub 等） |

错误响应示例：

```json
{
  "code": 40400,
  "message": "gap_report GAP_999 not found",
  "data": null,
  "trace_id": "trc_8f3a2b"
}
```

---

## 7. 状态机与流转约定

```
任务状态：pending → doing → done
                     ↘ 回退 pending

评估任务：queued → running → done / failed

计划状态：active → paused → completed

Gap 触发后自动级联：Profile → Gap → Plan → Practice → Evaluation
评估完成后自动：更新 user_skills → 重算 Gap → 局部重规划（PATCH /plans/{plan_id}）
```

---

## 8. 附录：异步任务约定

耗时操作（画像提取、Gap 分析、计划生成、文档入库、项目分析、评估）统一采用以下模式：

1. 请求返回 `{"task_id":"...","status":"queued|processing"}`。
2. 客户端轮询任务状态：`GET /api/v1/tasks/{task_id}`（通用任务查询接口）。
3. 或通过 SSE 订阅：`POST /api/v1/chat` / 各异步接口 `Accept: text/event-stream`。
4. 任务完成事件 `event:done` 中包含最终业务对象 ID（如 `gap_report_id`、`evaluation_id`）。

通用任务查询：

```
GET /api/v1/tasks/{task_id}
```

**响应 200**

```json
{
  "code": 0, "message": "ok",
  "data": { "task_id": "TASK_GAP_001", "type": "gap_analysis", "status": "done", "result_ref": "GAP_001", "error": null }
}
```
