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

## 3. 阶段 1 错误码

| code | HTTP | 说明 |
| --- | --- | --- |
| 0 | 200 | 成功 |
| 40001 | 400 | JSON 格式错误 |
| 40400 | 404 | 资源不存在 |
| 42200 | 422 | 业务校验失败 |
| 50000 | 500 | 服务端未知错误 |
| 50001 | 500 | LLM 调用失败（当前由规则兜底，一般不会出现） |
| 50005 | 500 | Checkpointer/DB 初始化失败 |

## 4. 运行方式

```bash
# 1. 配置环境（复制模板；或直接使用已生成的 .env）
cp .env.example .env

# 2. 初始化数据库（配置了 DATABASE_URL 时执行一次）
.venv/bin/python -m scripts.init_db

# 3. 启动（端口默认 5000；macOS 若被 AirPlay 占用可设 PORT，如 5050）
.venv/bin/python -m app
PORT=8081 .venv/bin/python -m app
# 或
flask --app app run
```
