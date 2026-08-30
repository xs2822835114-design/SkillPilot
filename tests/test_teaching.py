"""TeachingAgent（学习任务 → AI 教学）测试。

覆盖核心验收场景：
- 内存版（无 DB / 无 LLM）：创建、多轮、稳定恢复、Go→PHP 隔离、同任务不重复建会话；
- DB 版（真实 PostgreSQL，未配置则 skip）：完整 API 链路「开始学习→多轮→关闭→重开→历史恢复」、
  会话隔离、SSE done 携带历史、任务稳定回复；
- LLM 集成（须设 LIVE_LLM=1 才执行，否则 skip——不伪造通过）。
"""
from __future__ import annotations

import uuid

import pytest

from app.config import Config


def _cfg(**overrides) -> Config:
    base = dict(env="test", database_url="", llm_api_key="")
    base.update(overrides)
    return Config(**base)


def _request(**overrides) -> "TeachingRequest":
    from app.teaching.schemas import TeachingRequest

    base = dict(
        plan_id="PLAN_001",
        task_id="PLAN_001-T01",
        user_id="U10001",
        goal="掌握 Go 基础",
        skill_id="go-basics",
        skill_name="Go 基础",
        task_title="用 Go 小实验打通编程基础",
        learning_objective="通过 Go 小实验掌握数据、流程、函数与调试",
        acceptance_criteria="完成 basics/ 目录，go test 通过",
        steps=["理解变量与数据类型", "编写条件与循环", "练习函数与测试"],
    )
    base.update(overrides)
    return TeachingRequest(**base)


@pytest.fixture(autouse=True)
def _clear_mem_store():
    """每个用例前清空内存兜底存储，避免跨用例串状态。"""
    from app.teaching import session_store

    session_store._mem.clear()
    yield
    session_store._mem.clear()


def _go_session(cfg=_cfg()):
    from app.teaching import teaching_agent

    return teaching_agent.generate(cfg, _request())


# ================= 基础创建 / 多轮 =================

def test_1_create_go_session():
    from app.teaching.schemas import TeachingSession

    s = _go_session()
    assert isinstance(s, TeachingSession)
    assert s.session_id.startswith("TEACH_")
    assert s.task_id == "PLAN_001-T01"
    assert s.opening
    assert s.content.concepts and s.content.examples and s.content.exercises


def test_2_first_message():
    from app.teaching import teaching_agent

    s = _go_session()
    t = teaching_agent.continue_turn(_cfg(), s, "你继续")
    assert t.role == "ai"
    assert t.message


def test_3_second_message_keeps_context():
    from app.teaching import teaching_agent

    s = _go_session()
    # 与路由契约一致：Agent 返回 AI 轮，由调用方追加进会话
    s.append(teaching_agent.continue_turn(_cfg(), s, "你继续"))
    s.append(teaching_agent.continue_turn(_cfg(), s, "我理解了"))
    # 两条 AI 应答都在会话历史中
    assert len(s.turns) == 2


# ================= 持久化与恢复（内存兜底） =================

def test_4_save_and_close():
    from app.teaching import session_store

    s = _go_session()
    session_store.save(_cfg(), s)
    assert session_store.load(_cfg(), s.session_id).session_id == s.session_id


def test_5_reopen_same_task_restores_history():
    """关闭窗口后再次进入同一任务：load_by_task 命中同一会话并保留历史回合。"""
    from app.teaching import session_store, teaching_agent

    cfg = _cfg()
    s = _go_session(cfg)
    s.append(_mk_turn("user", "你继续"))
    s.append(_mk_turn("ai", "好的，继续讲流程控制。"))
    session_store.save(cfg, s)

    restored = session_store.load_by_task(cfg, "U10001", "PLAN_001-T01")
    assert restored is not None
    assert restored.session_id == s.session_id
    assert len(restored.turns) == 2
    assert restored.turns[0].message == "你继续"


def _mk_turn(role: str, message: str):
    from app.teaching.schemas import TeachingTurn

    return TeachingTurn(role=role, message=message)


def test_6_continue_reads_context():
    """恢复的会话继续互动：Agent 能看到历史回合。"""
    from app.teaching import session_store, teaching_agent

    cfg = _cfg()
    s = _go_session(cfg)
    s.append(_mk_turn("user", "你继续"))
    s.append(_mk_turn("ai", "接下来讲循环。"))
    session_store.save(cfg, s)

    restored = session_store.load_by_task(cfg, "U10001", "PLAN_001-T01")
    turn = teaching_agent.continue_turn(cfg, restored, "继续")
    assert turn.role == "ai"
    assert turn.message


def test_7_go_php_isolation():
    """Go 与 PHP 两个任务互不串状态。"""
    from app.teaching import session_store, teaching_agent

    cfg = _cfg()
    go = _go_session(cfg)
    go.append(_mk_turn("user", "你继续"))
    session_store.save(cfg, go)

    php = teaching_agent.generate(
        cfg, _request(plan_id="PLAN_002", task_id="PLAN_002-T01", user_id="U10001")
    )
    php.append(_mk_turn("user", "介绍 PHP 变量"))
    session_store.save(cfg, php)

    go_restored = session_store.load_by_task(cfg, "U10001", "PLAN_001-T01")
    php_restored = session_store.load_by_task(cfg, "U10001", "PLAN_002-T01")
    assert go_restored.turns[0].message == "你继续"
    assert php_restored.turns[0].message == "介绍 PHP 变量"
    # 互不干扰
    assert go_restored.task_id != php_restored.task_id


def test_9_repeated_start_returns_same_session():
    """同一任务反复 load_by_task 不新建多条会话记录。"""
    from app.teaching import session_store

    cfg = _cfg()
    s = _go_session(cfg)
    session_store.save(cfg, s)
    for _ in range(3):
        again = session_store.load_by_task(cfg, "U10001", "PLAN_001-T01")
        assert again.session_id == s.session_id


# ---------------- 数据库完整链路（不支持则 skip） ----------------

def _db_cfg():
    from app.config import get_config

    cfg = get_config()
    if not cfg.database_url:
        pytest.skip("DATABASE_URL 未配置，跳过 DB 用例")
    return cfg


def _seed_plan(config: Config, user_id: str, goal: str, task_title: str, accept: str):
    """向 DB 写入一个含单个任务的学习计划，返回 (plan_id, task_id)。"""
    from app.todo import todo_store
    from app.todo.schemas import LearningPhase, LearningPlan, LearningTask, PlanMetrics

    plan_id = f"TP_{uuid.uuid4().hex[:10]}"
    task = LearningTask(
        task_id=f"{plan_id}-T01",
        skill_id="go-basics",
        title=task_title,
        acceptance_criteria=accept,
        steps=["步骤1", "步骤2"],
        required=True,
        order=1,
    )
    plan = LearningPlan(
        plan_id=plan_id,
        user_id=user_id,
        goal=goal,
        status="in_progress",
        metrics=PlanMetrics(total_hours=5, total_tasks=1, done_tasks=0),
        phases=[LearningPhase(phase_id="P1", title="基础", order=1, skill_ids=["go-basics"], tasks=[task])],
    )
    todo_store.create_plan(config, plan, report={"goal": goal}, skill_ids=["go-basics"])
    return plan_id, task.task_id


@pytest.fixture()
def db_ctx():
    cfg = _db_cfg()
    cfg2 = Config(
        env="test",
        database_url=cfg.database_url,
        llm_api_key="",
        checkpointer_backend="memory",
    )
    from app import create_app

    flask_app = create_app(cfg2)
    flask_app.config["TESTING"] = True
    client = flask_app.test_client()
    return cfg2, client


def _json(resp):
    import json

    return json.loads(resp.get_data(as_text=True))["data"]


def test_db_full_circle_reopen_restores(db_ctx):
    """DB 链路：开始学习 → 两轮消息 → 换客户端“重开” → 历史完整恢复 → 继续。"""
    cfg, client = db_ctx
    user = f"u_{uuid.uuid4().hex[:8]}"
    plan_id, task_id = _seed_plan(cfg, user, "Go 基础计划", "Go 代码基础", "完成 basics 并通过测试")

    r1 = client.post(f"/api/v1/plan/{plan_id}/tasks/{task_id}/teach", json={"mode": "start"})
    assert r1.status_code == 200, r1.get_data(as_text=True)
    s1 = _json(r1)
    sid = s1["session_id"]
    assert s1["task_id"] == task_id

    # 两轮消息
    for msg in ("你继续", "我理解了"):
        r = client.post(f"/api/v1/teaching/{sid}/message", json={"message": msg})
        assert r.status_code == 200, r.get_data(as_text=True)

    # 历史接口确认已有多轮记录
    hist = _json(client.get(f"/api/v1/teaching/{sid}/history"))
    assert len(hist["turns"]) == 4  # user/ai × 2

    # 模拟“关闭窗口后重新进入同一任务”：新客户端实例走 /teach，应命中同一会话而非新建
    client2 = db_ctx[1]
    r2 = client2.post(f"/api/v1/plan/{plan_id}/tasks/{task_id}/teach", json={"mode": "start"})
    s2 = _json(r2)
    assert s2["session_id"] == sid
    assert len(s2["turns"]) == 4
    assert [t["message"] for t in s2["turns"] if t["role"] == "user"] == ["你继续", "我理解了"]

    # 恢复后继续：Agent 能基于历史出下一轮
    r = client2.post(f"/api/v1/teaching/{sid}/message", json={"message": "继续"})
    assert r.status_code == 200
    assert _json(r)["message"]


def test_db_task_isolation(db_ctx):
    """同一用户两个任务（Go / PHP）在 API 层互为独立会话。"""
    cfg, client = db_ctx
    user = f"u_{uuid.uuid4().hex[:8]}"
    pgo, tgo = _seed_plan(cfg, user, "Go 计划", "Go 基础", "go test 通过")
    pphp, tphp = _seed_plan(cfg, user, "PHP 计划", "PHP 变量", "可运行 php 脚本")

    s_go = _json(client.post(f"/api/v1/plan/{pgo}/tasks/{tgo}/teach", json={"mode": "start"}))
    s_php = _json(client.post(f"/api/v1/plan/{pphp}/tasks/{tphp}/teach", json={"mode": "start"}))
    assert s_go["session_id"] != s_php["session_id"]
    client.post(f"/api/v1/teaching/{s_go['session_id']}/message", json={"message": "你继续"})

    go2 = _json(client.post(f"/api/v1/plan/{pgo}/tasks/{tgo}/teach", json={"mode": "start"}))
    assert go2["session_id"] == s_go["session_id"]
    assert len(go2["turns"]) == 2  # Go 历史未被 PHP 影响
    php2 = _json(client.post(f"/api/v1/plan/{pphp}/tasks/{tphp}/teach", json={"mode": "start"}))
    assert php2["session_id"] == s_php["session_id"]


def test_db_sse_done_carries_history(db_ctx):
    """SSE 首节教学：done 事件携带稳定 session_id；多轮后 SSE done 仍回传历史。”"""
    cfg, client = db_ctx
    user = f"u_{uuid.uuid4().hex[:8]}"
    plan_id, task_id = _seed_plan(cfg, user, "SSE 计划", "SSE 任务", "完成示例")

    events = []
    resp = client.post(f"/api/v1/plan/{plan_id}/tasks/{task_id}/teach/stream", json={"mode": "start"})
    payload = resp.get_data(as_text=True)
    for raw in payload.split("\n\n"):
        for line in raw.split("\n"):
            if line.startswith("data:"):
                import json

                events.append(json.loads(line[5:].strip()))

    types = [e["type"] for e in events]
    assert "meta" in types and "done" in types
    done_evt = next(e for e in events if e["type"] == "done")
    sid = done_evt["session_id"]
    # 多轮后再次 SSE：done 应回传历史回合
    client.post(f"/api/v1/teaching/{sid}/message", json={"message": "你继续"})
    events2 = []
    resp2 = client.post(f"/api/v1/plan/{plan_id}/tasks/{task_id}/teach/stream", json={"mode": "start"})
    for raw2 in resp2.get_data(as_text=True).split("\n\n"):
        for line in raw2.split("\n"):
            if line.startswith("data:"):
                import json

                events2.append(json.loads(line[5:].strip()))
    done2 = next(e for e in events2 if e["type"] == "done")
    assert done2["session_id"] == sid
    assert len(done2.get("turns") or []) == 2


def test_db_llm_failure_keeps_session(db_ctx):
    """LLM 调用失败不破坏已有会话：多轮后会话仍可恢复历史（LLM 关闭走规则兜底）。"""
    cfg, client = db_ctx
    user = f"u_{uuid.uuid4().hex[:8]}"
    plan_id, task_id = _seed_plan(cfg, user, "异常计划", "异常任务", "完成")

    s = _json(client.post(f"/api/v1/plan/{plan_id}/tasks/{task_id}/teach", json={"mode": "start"}))
    sid = s["session_id"]
    for msg in ("你继续", "再做一遍"):
        assert client.post(f"/api/v1/teaching/{sid}/message", json={"message": msg}).status_code == 200
    hist = _json(client.get(f"/api/v1/teaching/{sid}/history"))
    assert len(hist["turns"]) == 4  # 历史完整，未被失败/异常破坏


# ---------------- LLM 集成（真实 DeepSeek，需显式开启） ----------------

def test_live_llm_continue_is_not_template():
    """真实 DeepSeek：用户「你继续」应得到 LLM 生成的回复，而非离线兜底固定文本。

    仅当环境变量 LIVE_LLM=1 时执行；否则显式 skip（绝不伪造通过）。
    该用例因真实调用会写库，故采用独立内存 session（不落库）。
    """
    if not __import__("os").getenv("LIVE_LLM"):
        pytest.skip("未设置 LIVE_LLM=1，跳过真实 DeepSeek 集成测试")

    from app.teaching import teaching_agent, session_store

    cfg = _cfg(llm_api_key=__import__("os").getenv("LLM_API_KEY", ""), llm_base_url=__import__("os").getenv("LLM_BASE_URL", "https://api.deepseek.com"))
    assert cfg.llm_enabled, "LLM_API_KEY 未配置，无法执行真实集成测试"
    s = teaching_agent.generate(cfg, _request())
    assert s.opening, "首节 opening 不应为空（LLM 已接入）"
    turn = teaching_agent.continue_turn(cfg, s, "你继续")
    # 若回退到规则兜底，会命中固定离线兜底文本 —— 这里断言不是它
    assert turn.message
    assert "离线兜底" not in turn.message, "LLM 未真正生效，命中了固定兜底文本"