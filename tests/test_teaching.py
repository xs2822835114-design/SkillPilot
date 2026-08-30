"""TeachingAgent（学习任务 → AI 教学）测试。

- 内存版（无 DB / 无 LLM）：验证 generate 规则兜底、多轮 continue_turn、教学消息接口；
- 数据库相关接口（/teach）在未配置 DATABASE_URL 时应 503 降级，不 500。
"""
from __future__ import annotations

from app.teaching.schemas import TeachingRequest, TeachingSession, TeachingTurn
from app.teaching import session_store


def _request(**overrides) -> TeachingRequest:
    base = dict(
        plan_id="PLAN_001",
        task_id="PLAN_001-T01",
        user_id="U10001",
        goal="掌握 LangGraph",
        skill_id="checkpoint",
        skill_name="Checkpoint",
        task_title="学习并掌握 Checkpoint",
        learning_objective="理解 LangGraph 状态持久化与恢复机制",
        acceptance_criteria="能配置 Checkpointer 并实现一次状态恢复",
        steps=["理解为什么需要 Checkpoint", "配置 MemorySaver", "验证状态恢复"],
    )
    base.update(overrides)
    return TeachingRequest(**base)


def test_teaching_generate_rule_fallback():
    """LLM 关闭（conftest llm_api_key='')→ 规则兜底生成完整、结构合法的 Session。"""
    from app.teaching import teaching_agent
    from app.config import Config

    cfg = Config(env="test", database_url="", llm_api_key="")
    session = teaching_agent.generate(cfg, _request())

    assert isinstance(session, TeachingSession)
    assert session.session_id.startswith("TEACH_")
    assert session.task_id == "PLAN_001-T01"
    assert session.opening
    assert session.content.concepts
    assert session.content.examples
    assert session.content.exercises
    # 验收标准被带进练习的期望结果
    assert session.acceptance_criteria == "能配置 Checkpointer 并实现一次状态恢复"


def test_teaching_continue_turn_rule_fallback():
    """LLM 关闭时 continue_turn 也应返回一个 non-empty 的 AI 轮。"""
    from app.teaching import teaching_agent
    from app.config import Config

    cfg = Config(env="test", database_url="", llm_api_key="")
    session = teaching_agent.generate(cfg, _request())
    turn = teaching_agent.continue_turn(cfg, session, "我理解了，继续")
    assert isinstance(turn, TeachingTurn)
    assert turn.role == "ai"
    assert turn.message


def test_teaching_message_endpoint(client):
    """POST /teaching/<session>/message：在内存放入会话后，多轮互动应返回 200 的 AI 轮。"""
    from app.teaching import teaching_agent
    from app.config import Config

    cfg = Config(env="test", database_url="", llm_api_key="")
    session = teaching_agent.generate(cfg, _request())
    session_store.put(session)

    resp = client.post(
        f"/api/v1/teaching/{session.session_id}/message",
        json={"message": "给我出题"},
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["role"] == "ai"
    assert data["message"]
    # 会话已追加两轮（用户 + AI）
    assert len(session_store.get(session.session_id).turns) == 2


def test_teaching_message_unknown_session(client):
    resp = client.post("/api/v1/teaching/TEACH_nope/message", json={"message": "hi"})
    assert resp.status_code == 404


def test_teach_requires_db(client):
    """无 DATABASE_URL 时 /teach 应 503 降级，而非 500。"""
    resp = client.post(
        "/api/v1/plan/PLAN_X/tasks/PLAN_X-T01/teach", json={"mode": "start"}
    )
    assert resp.status_code == 503