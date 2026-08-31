"""多 Agent 路由测试（精简后仅保留 chat 与 plan_generation 两条主线）。

分层：
- 内存版用例（conftest 无 DB/LLM）：验证确定性路由、追问、降级、纯 chat 兼容 —— 始终运行；
- DB 版用例（需 DATABASE_URL，未配置自动 skip）：验证 plan 成功路径与流式 artifacts。
"""
from __future__ import annotations

import json
import uuid

import pytest


# ---------------- 内存版：路由 / 追问 / 降级 / 兼容（始终运行） ----------------


def _chat(client, thread_id: str, message: str, **overrides):
    body = {"user_id": "U10001", "thread_id": thread_id, "message": message, **overrides}
    return client.post("/api/v1/chat", json=body)


def test_a8_pure_chat_stays_compatible(client):
    """TC-A8：纯聊天 → route=chat、artifacts={}，阶段 1 行为不变。"""
    resp = _chat(client, "A_T8", "你好，今天天气怎么样")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["route"] == "chat"
    assert data["workflow_status"] == "done"
    assert data["artifacts"] == {}
    assert data["steps"] == ["intent_recognize", "reply"]
    assert data["reply"]


def test_a6b_plan_without_role_asks(client):
    """TC-A6b：学习计划缺目标岗位 → 轻量追问。"""
    resp = _chat(client, "A_T6B", "帮我生成学习计划")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["route"] == "plan_generation"
    assert data["workflow_status"] == "need_input"
    assert "可选岗位" in data["reply"]


def test_a6c_tech_learning_without_skill_asks(client):
    """TC-A6c：「我想学」无技能名 → 技术学习意图，追问想学哪个技术/技能。"""
    resp = _chat(client, "A_T6C", "我想学")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["route"] == "tech_learning"
    assert data["workflow_status"] == "need_input"
    assert "学习" in data["reply"]
    assert "技能" in data["reply"]


def test_a2b_tech_learning_by_skill(client):
    """TC-A2b（直出默认）：说「我想学 Flask」→ 技术学习意图 → 默认 direct 直出结构化学习计划。"""
    resp = _chat(client, "A_T2B", "我想学 Flask")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["route"] == "tech_learning"
    assert data["workflow_status"] == "done"
    assert "learning_plan_agent" in data["steps"]
    art = data["artifacts"]
    assert art["intent"] == "tech_learning"
    assert art.get("learning_plan"), "直出模式应携带结构化 learning_plan"
    assert art["learning_plan"].get("phases")
    assert art["target_profile"]["goal_name"] == "Flask"
    skill_ids = {s["skill_id"] for s in art["target_profile"]["skills"]}
    assert "flask" in skill_ids


def test_a7_plan_degraded_without_db(client):
    """TC-A7 降级：无 DB 时 plan_node → degraded 文案，HTTP 200 不 500。"""
    resp = _chat(client, "A_T7", "帮我生成学习计划，目标是 AI 应用工程师")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["route"] == "plan_generation"
    assert data["workflow_status"] == "degraded"
    assert data["artifacts"] == {}
    assert "数据库" in data["reply"]


def test_a10_multi_turn_context_and_routing(client):
    """TC-A10：同一 thread 多轮——第一轮缺入参追问，第二轮只补说岗位名（裸续接）仍能续接意图。"""
    first = _chat(client, "A_T10", "帮我生成学习计划")
    assert first.get_json()["data"]["workflow_status"] == "need_input"
    assert first.get_json()["data"]["route"] == "plan_generation"

    second = _chat(client, "A_T10", "AI Agent 工程师")  # 不重复业务关键词，仅补入参
    assert second.status_code == 200
    data = second.get_json()["data"]
    assert data["route"] == "plan_generation"
    # 业务节点已进入（无 DB 时降级，但绝不 500/need_input）
    assert data["workflow_status"] in ("done", "degraded")
    assert "plan_agent" in data["steps"]


def test_a9_stream_done_carries_artifacts_field(client):
    """TC-A9（内存版）：流式 done 事件带 artifacts 字段。"""
    app = client.application
    with app.app_context():
        resp = client.post(
            "/api/v1/chat/stream",
            json={"user_id": "U10001", "thread_id": "A_T9", "message": "你好"},
        )
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
    assert '"type": "meta"' in body or '"type":"meta"' in body
    assert '"type": "done"' in body or '"type":"done"' in body
    assert '"artifacts"' in body
    assert '"artifacts": {}' in body or '"artifacts":{}' in body


# ---------------- 技能识别回归（未知技能 / 目标提取 / 状态隔离，始终运行） ----------------

def _tech_goal(data):
    """从 chat 响应里取目标画像 goal_name（未知技能也保留用户原始目标）。"""
    return ((data.get("artifacts") or {}).get("target_profile") or {}).get("goal_name")


@pytest.mark.parametrize("msg", [
    "我想学PHP",
    "我想学PHP语言",
    "我要学习PHP",
    "我想入门PHP",
    "我准备学PHP",
    "我想学 PHP 后端",
    "我想学 PHP 开发",
    "PHP 怎么学",
])
def test_php_variants_recognized(client, msg):
    """PHP 各种说法都应识别为 tech_learning、目标为 PHP，而非追问「你想学哪个技术」。"""
    data = _chat(client, "PHPVAR", msg).get_json()["data"]
    assert data["route"] == "tech_learning"
    assert data["workflow_status"] == "done"
    assert _tech_goal(data) == "PHP"


def test_unknown_skill_preserved(client):
    """技能库没有 Rust 时，也要保留用户目标 Rust，而不是追问。"""
    data = _chat(client, "RUST1", "我想学 Rust").get_json()["data"]
    assert data["route"] == "tech_learning"
    assert data["workflow_status"] == "done"
    assert _tech_goal(data) == "Rust"
    skills = ((data.get("artifacts") or {}).get("target_profile") or {}).get("skills") or []
    assert any(s["skill_id"] == "Rust" and s.get("source") == "target" for s in skills)


def test_unknown_skill_with_suffix_stripped(client):
    """「PHP语言 / 后端」等尾缀应剥离，目标仍为 PHP。"""
    data = _chat(client, "PHP2", "我想学PHP语言").get_json()["data"]
    assert data["route"] == "tech_learning"
    assert data["workflow_status"] == "done"
    assert _tech_goal(data) == "PHP"


def test_state_isolation_go_to_php(client):
    """Go→PHP 切换学习目标：新的 target_profile 只含 PHP，不残留 Go。"""
    g = _chat(client, "ISO1", "我想学 Go").get_json()["data"]
    assert g["workflow_status"] == "done"
    assert _tech_goal(g) == "Go"
    p = _chat(client, "ISO1", "我想学 PHP").get_json()["data"]
    assert p["workflow_status"] == "done"
    assert _tech_goal(p) == "PHP"
    ids = {s["skill_id"] for s in (((p.get("artifacts") or {}).get("target_profile") or {}).get("skills") or [])}
    assert "PHP" in ids
    assert "go" not in ids and "GO" not in ids


def test_tech_learning_no_target_still_asks(client):
    """「我想学」无目标 → 追问；绝不出计划。"""
    data = _chat(client, "NT1", "我想学").get_json()["data"]
    assert data["route"] == "tech_learning"
    assert data["workflow_status"] == "need_input"


def test_tech_learning_known_skill_uses_catalog_id(client):
    """已知技能（LangGraph）走标准 skill_id，无需 unknown 标记。"""
    data = _chat(client, "KO1", "我想学 LangGraph").get_json()["data"]
    assert data["workflow_status"] == "done"
    assert _tech_goal(data) == "LangGraph"
    skills = ((data.get("artifacts") or {}).get("target_profile") or {}).get("skills") or []
    assert any(s["skill_id"] == "langgraph" and s.get("source") == "target" for s in skills)


# ---------------- DB 版：plan 成功路径（需 DATABASE_URL，自动 skip） ----------------


def _cfg_db():
    from app.config import get_config

    if not get_config().database_url:
        pytest.skip("DATABASE_URL 未配置，跳过 DB 用例")
    return get_config()


@pytest.fixture()
def route_db_client():
    """真实 DB + 演示用户画像的 test_client（LLM 关闭，规则兜底）。"""
    cfg = _cfg_db()
    from scripts.seed_skill_graph import run as seed_graph
    from scripts.seed_skills import run as seed_skills

    seed_skills()
    seed_graph()
    from scripts.demo_init import create_demo_profile

    create_demo_profile()

    from app import create_app
    from app.config import Config

    test_cfg = Config(
        env="test",
        database_url=cfg.database_url,
        llm_api_key="",
        checkpointer_backend="memory",
        embedding_provider="off",
    )
    flask_app = create_app(test_cfg)
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


DEMO_USER = "demo_user"


def _data(resp):
    body = resp.get_json()
    assert body is not None, "响应非 JSON"
    assert body.get("code") == 0, f"code != 0: {body}"
    return body["data"]


def test_a2_plan_routed_to_business(route_db_client):
    """TC-A2：说「帮我生成学习计划」→ plan_node 执行，artifacts 含 plan_id。"""
    data = _data(
        route_db_client.post(
            "/api/v1/chat",
            json={
                "user_id": DEMO_USER,
                "thread_id": "A_T2",
                "message": "帮我生成学习计划，目标是 AI 应用工程师",
            },
        )
    )
    assert data["route"] == "plan_generation"
    assert data["workflow_status"] == "done"
    assert "任务" in data["reply"]
    art = data["artifacts"]
    assert art["intent"] == "plan_generation"
    assert art["plan_id"]
    assert art["goto"]["page"] == "plan"