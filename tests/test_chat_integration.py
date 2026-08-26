"""阶段 1 集成测试 TC1~TC8（基于内存 checkpointer，无外部依赖）。"""
from __future__ import annotations

import pytest


def _chat(client, thread_id: str, message: str, **overrides):
    body = {"user_id": "U10001", "thread_id": thread_id, "message": message, **overrides}
    return client.post("/api/v1/chat", json=body)


# ---------------- TC1 健康检查 ----------------

def test_tc1_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["code"] == 0
    assert data["data"]["status"] == "up"
    assert data["data"]["db"] == "disabled"  # 测试未配置 DATABASE_URL


# ---------------- TC2 正常对话 ----------------

def test_tc2_chat_ok(client):
    # 「我想转向 AI 应用开发」阶段 9 起路由到 gap_analysis，此处用纯闲聊句验证 chat 兼容
    resp = _chat(client, "T_T2", "你好，今天天气怎么样")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["code"] == 0
    result = data["data"]
    assert result["workflow_status"] == "done"
    assert result["route"] == "chat"
    assert "intent_recognize" in result["steps"]
    assert result["reply"]


# ---------------- TC3 上下文恢复 ----------------

def test_tc3_context_recovery(client):
    first = "我想转向 AI 应用开发"
    _chat(client, "T_T3", first)
    second = _chat(client, "T_T3", "我还需要做什么准备？")
    assert second.status_code == 200
    reply = second.get_json()["data"]["reply"]
    assert "继续这个话题" in reply          # 已恢复历史，引导继续
    assert "想转向 AI 应用开发" in reply   # 引用了第一轮消息


# ---------------- TC5 非法入参 ----------------

@pytest.mark.parametrize(
    "payload, expected",
    [
        ({"user_id": "U1", "thread_id": "T1"}, 422),                       # 缺 message
        ({"user_id": "U1", "thread_id": "T1", "message": "   "}, 422),     # 全空白
        ({"user_id": "U1", "thread_id": "T1", "message": "x" * 8001}, 422),  # 超长
        ({"user_id": "非法!!", "thread_id": "T1", "message": "hi"}, 422),  # user_id 非法
    ],
)
def test_tc5_invalid_input(client, payload, expected):
    resp = client.post("/api/v1/chat", json=payload)
    assert resp.status_code == expected
    body = resp.get_json()
    assert body["code"] == 42200
    assert body["data"] is None
    assert body["trace_id"]


# ---------------- TC6 坏 JSON ----------------

def test_tc6_bad_json(client):
    resp = client.post(
        "/api/v1/chat",
        data="not-json",
        content_type="application/json",
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == 40001
    assert body["trace_id"]


# ---------------- TC7 不同 thread 隔离 ----------------

def test_tc7_thread_isolation(client):
    _chat(client, "T_T7_A", "我想转向 AI 应用开发")
    resp_b = _chat(client, "T_T7_B", "今天天气怎么样")
    reply_b = resp_b.get_json()["data"]["reply"]
    assert "收到你的消息" in reply_b         # 新会话，未污染（仅通用兜底）
    assert "想转向 AI 应用开发" not in reply_b


# ---------------- TC8 异常兜底 ----------------

def test_tc8_unexpected_error_returns_500_without_detail(client, monkeypatch):
    """未预期异常 → 500 + code 50000 + trace_id，且不泄露内部细节。

    通过 monkeypatch 类方法（在懒构建 graph 之前生效，使编排节点抛错）。
    """

    def boom(state):
        raise RuntimeError("secret internal detail")

    from app.agents import orchestrator_agent as oa

    monkeypatch.setattr(oa.OrchestratorAgent, "invoke", boom)
    resp = _chat(client, "T_T8", "hello")
    assert resp.status_code == 500
    body = resp.get_json()
    assert body["code"] == 50000
    assert body["data"] is None
    assert body["trace_id"]
    assert "secret internal detail" not in body["message"]


def test_tc8b_llm_failure_falls_back(client, monkeypatch):
    """LLM 调用失败应回退到规则实现（不抛裸异常到 HTTP 层）。

    「什么是 RAG」为 question 意图，阶段 9 起路由到 rag_node；无 DB 时按设计降级为
    degraded（HTTP 仍 200、code 仍 0），本用例守护的核心是"失败不抛裸异常"。
    """
    from app.agents import orchestrator_agent as oa

    class _BoomLLM:
        def with_structured_output(self, schema):
            raise RuntimeError("llm boom")

    # 让 _get_llm 返回一个调用即抛错的假 LLM，触发 _run_with_llm 内部兜底
    monkeypatch.setattr(oa.OrchestratorAgent, "_get_llm", lambda self: _BoomLLM())
    resp = _chat(client, "T_T8B", "什么是 RAG")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["code"] == 0
    assert body["data"]["workflow_status"] in ("done", "degraded")
