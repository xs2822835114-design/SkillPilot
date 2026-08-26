"""阶段 7 长期记忆与 Middleware 测试：TC-M1~M12。

规则用例（PII/摘要/状态机）纯单元运行；集成用例依赖真实 DB（表由 scripts.init_db 建），
DB 未配置则跳过。种子无需额外灌入（记忆为写入即得）。
"""
from __future__ import annotations

import uuid

import pytest

from app.config import Config


def U():  # noqa: N802
    return "tu_m_" + uuid.uuid4().hex[:10]


def _cfg_off():
    return Config(env="test", checkpointer_backend="memory")


def _cfg_db():
    from app.config import get_config

    if not get_config().database_url:
        pytest.skip("DATABASE_URL 未配置")
    return Config(
        env="test",
        database_url=get_config().database_url,
        llm_api_key="",
        checkpointer_backend="memory",
        embedding_provider="off",
        memory_embed_enabled=True,
        memory_pii_enabled=True,
        memory_hitl_enabled=True,
    )


# ---------------- 纯规则：PII ---------------

def test_tc_m1_pii_scrub():
    from app.memory.middleware import pii

    text = "联系我 test@example.com 或 13800138000，身份证 110101199003071234。"
    out, hits = pii.scrub(_cfg_off(), text)
    assert "test@example.com" not in out
    assert "13800138000" not in out
    assert "110101199003071234" not in out
    assert set(hits) == {"id_card", "phone", "email"}


def test_tc_m2_summary_template_fallback():
    from app.config import Config
    from app.memory.middleware import summary

    cfg = Config(
        env="test", llm_api_key="", checkpointer_backend="memory",
        memory_summary_llm_enabled=False,
    )
    msgs = [{"role": "user", "content": f"我想学 {i}"} for i in range(26)]
    s, enhanced = summary.summarize(cfg, U(), "T-EMPTY", msgs)
    assert s and not enhanced
    assert "26" in s or "对话共" in s


def test_tc_m3_hitl_state_machine():
    from app.memory.middleware import hitl
    from app.memory.schemas import PendingActionRequest

    cfg = _cfg_db()
    cfg_memory = cfg  # 纯状态机不落库，仅校验决策合法性
    with pytest.raises(ValueError):
        hitl.confirm(cfg_memory, "MISSING_PA", "approve")
    with pytest.raises(ValueError):
        hitl.confirm(cfg_memory, "MISSING_PA", "maybe")
    assert hitl.enabled(cfg_memory) is True


# ---------------- 集成：语义/偏好/经历/HITL/摘要路由 ----------------

@pytest.fixture()
def db():
    cfg = _cfg_db()
    from app.persistence import db as pgdb

    user = U()
    with pgdb.connect(cfg) as conn:
        _clean(conn, user)
    yield cfg, user
    with pgdb.connect(cfg) as conn:
        _clean(conn, user)


def _clean(conn, user):
    conn.execute("DELETE FROM memories WHERE user_id=%s", (user,))
    conn.execute("DELETE FROM memory_events WHERE user_id=%s", (user,))
    conn.execute("DELETE FROM pending_actions WHERE user_id=%s", (user,))
    conn.execute("DELETE FROM user_preferences WHERE user_id=%s", (user,))


def test_tc_m4_semantic_write_recall(db):
    from app.memory import service
    from app.memory.schemas import MemoryRememberRequest, MemorySearchRequest

    cfg, user = db
    service.remember(
        cfg,
        MemoryRememberRequest(
            user_id=user, namespace="semantic", key="goal", text="用户目标：转型 AI 应用开发"
        ),
    )
    rows = service.search(cfg, MemorySearchRequest(user_id=user, query="目标", top_k=5))
    assert rows and rows[0].key == "goal"


def test_tc_m5_key_idempotent_upsert(db):
    from app.memory import service
    from app.memory.schemas import MemoryRememberRequest

    cfg, user = db
    for _ in range(2):
        service.remember(
            cfg,
            MemoryRememberRequest(user_id=user, namespace="semantic", key="pref", text="偏好 A"),
        )
    items = service.list_memories(cfg, user, "semantic")
    assert len([i for i in items if i.key == "pref"]) == 1


def test_tc_m6_cross_thread_recall(db):
    from app.memory import service
    from app.memory.schemas import MemoryRememberRequest
    from app.memory.procedural import set_preference

    cfg, user = db
    service.remember(
        cfg,
        MemoryRememberRequest(user_id=user, namespace="semantic", key="goal", text="转型 AI 应用开发"),
    )
    set_preference(cfg, user, "learning_style", "实践优先")
    ctx = service.recall_for_user(cfg, user)
    assert any("转型" in s["text"] for s in ctx["semantic"])
    assert ctx["preferences"].get("learning_style") == "实践优先"


def test_tc_m7_record_and_query_events(db):
    from app.memory import service
    from app.memory.schemas import EpisodeRequest

    cfg, user = db
    eid = service.record_event(
        cfg,
        EpisodeRequest(
            user_id=user, event_type="evaluation_done",
            ref_ids={"evaluation_id": "EVL_1"}, summary="评估完成 overall=80",
        ),
    )
    assert eid
    rows = service.query_events(cfg, user, "evaluation_done")
    assert rows and rows[0]["event_type"] == "evaluation_done"


def test_tc_m8_procedural_preference_retained(db):
    from app.memory.procedural import all_preferences, get_preference, set_preference

    cfg, user = db
    set_preference(cfg, user, "learning_style", "动手实践")
    assert get_preference(cfg, user, "learning_style") == "动手实践"
    assert all_preferences(cfg, user).get("learning_style") == "动手实践"


def test_tc_m9_summary_injected_recall(db):
    from app.memory import service
    from app.memory.schemas import SummarizeRequest

    cfg, user = db
    msgs = [{"role": "user", "content": f"关于 {(i)} 我学到了 X"} for i in range(25)]
    result = service.summarize(cfg, SummarizeRequest(user_id=user, thread_id="TH_1", messages=msgs))
    assert result["stored"] and result["summary"]
    # 摘要作为记忆可被取出（namespace='summary'）
    rows = service.list_memories(cfg, user, "summary")
    assert rows and rows[0].key == "thread:TH_1"
    # 计划契约：recall_for_user 注入 memory_context.message_summary（用于新会话优先读数）
    ctx = service.recall_for_user(cfg, user)
    assert ctx.get("message_summary") == result["summary"]


def test_tc_m10_hitl_park_and_confirm(db):
    from app.memory import service
    from app.memory.schemas import PendingActionRequest

    cfg, user = db
    pa_id = service.pending_create(
        cfg, PendingActionRequest(user_id=user, action_type="plan_reset", summary="重置学习计划将丢弃当前进度")
    )
    pending = service.pending_list(cfg, user, status="pending")
    assert any(p["id"] == pa_id for p in pending)
    assert service.pending_confirm(cfg, pa_id, "approve") == "approved"
    # 重复决策应抛错（已被处置）
    with pytest.raises(ValueError):
        service.pending_confirm(cfg, pa_id, "reject")


def test_tc_m11_disabled_short_circuit(db):
    from app.memory import service
    from app.memory.schemas import MemoryRememberRequest

    cfg, user = db
    cfg.memory_enabled = False
    service.record_event_best_effort(
        cfg, user, "evaluation_done", summary="即使事件合法，关闭时也不写入"
    )
    identity = service.remember(
        cfg, MemoryRememberRequest(user_id=user, namespace="semantic", key="x", text="y")
    )
    assert identity["mem_id"] == ""  # 关闭短路为空，不抛错


# ---------------- 路由 ----------------

def test_tc_m12_routes_validation(app_client):
    pytest.skip("memory HTTP 路由已随精简移除")


@pytest.fixture()
def app_client():
    cfg = _cfg_db()
    if not cfg.database_url:
        pytest.skip("DATABASE_URL 未配置")
    from app import create_app

    return create_app(cfg).test_client()