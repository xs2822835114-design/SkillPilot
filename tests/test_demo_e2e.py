"""阶段 8 Demo 端到端测试：TC-D1~D8。

依赖真实 PostgreSQL（DATABASE_URL）的用例自动跳过；无需 DB 的用例始终运行。
演示链路用例复用阶段 5 的 db_client 模式：LLM 关闭走规则兜底，保证确定性。
"""
from __future__ import annotations

import json
import os
import uuid

import pytest

DEMO = "demo_e2e_" + uuid.uuid4().hex[:8]
TARGET_ROLE = "RC013"  # Python 后端工程师（与 demo 画像的 python/sql/http 匹配）


def _cfg_db():
    from app.config import get_config

    if not get_config().database_url:
        pytest.skip("DATABASE_URL 未配置，跳过 DB 用例")
    return get_config()


@pytest.fixture()
def db_client():
    """真实 DB 的 Flask test_client（LLM 关闭，规则兜底）。"""
    cfg = _cfg_db()
    from scripts.seed_skill_graph import run as seed_graph
    from scripts.seed_skills import run as seed_skills

    seed_skills()
    seed_graph()

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


def _data(resp):
    body = resp.get_json()
    assert body is not None, "响应非 JSON"
    assert body.get("code") == 0, f"code != 0: {body}"
    return body["data"]


# ---------------- TC-D1 技能图谱 ----------------

def test_d1_graph_shape(db_client):
    data = _data(db_client.get("/api/v1/graph"))
    nodes, edges = data.get("nodes") or [], data.get("edges") or []
    assert nodes, "图谱节点不应为空"
    assert edges, "图谱边不应为空"
    for n in nodes:
        assert "id" in n and "name" in n
    for e in edges:
        assert "source" in e and "target" in e
    ids = {n["id"] for n in nodes}
    for e in edges:
        assert e["source"] in ids and e["target"] in ids, "边两端应指向存在的节点"


# ---------------- TC-D2 Dashboard ----------------

def test_d2_dashboard_shape(db_client):
    data = _data(db_client.get(f"/api/v1/dashboard/{DEMO}"))
    for key in ("user_id", "profile", "latest_plan", "latest_evaluation", "growth", "facts"):
        assert key in data, f"Dashboard 缺字段 {key}"
    assert data["user_id"] == DEMO
    assert data["latest_plan"] is None  # 新用户无计划，给空值而非 500
    assert data["latest_evaluation"] is None
    assert data["growth"] == []
    assert data["facts"] == []


def test_d2_dashboard_unknown_user_ok(db_client):
    """未知用户返回空数据而非 500。"""
    data = _data(db_client.get(f"/api/v1/dashboard/no_such_user_{uuid.uuid4().hex[:6]}"))
    assert data["profile"]["skill_count"] == 0


# ---------------- TC-D3 计划列表 ----------------

def test_d3_plan_list_empty_and_shape(db_client):
    data = _data(db_client.get(f"/api/v1/plan/list?user_id={DEMO}"))
    assert isinstance(data, list)
    assert data == []

    # 生成一个计划后再查列表
    gap = _data(db_client.post(
        "/api/v1/gap/request",
        json={"user_id": DEMO, "target_roles": [TARGET_ROLE]},
    ))
    assert gap["reports"]
    plan = _data(db_client.post(
        "/api/v1/plan/generate",
        json={"user_id": DEMO, "target_roles": [TARGET_ROLE]},
    ))
    lst = _data(db_client.get(f"/api/v1/plan/list?user_id={DEMO}"))
    assert any(p["plan_id"] == plan["plan_id"] for p in lst)
    for p in lst:
        assert "plan_id" in p and "goal" in p and "status" in p and "progress" in p


# ---------------- TC-D4 SSE 流式 ----------------

def test_d4_sse_stream_events(db_client):
    """能消费到 meta → delta → done 事件序列。"""
    app = db_client.application
    with app.app_context():
        resp = db_client.post(
            "/api/v1/chat/stream",
            json={"user_id": DEMO, "thread_id": f"T-{uuid.uuid4().hex[:6]}", "message": "你好"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.content_type

        events = []
        for line in resp.get_data(as_text=True).splitlines():
            if line.startswith("data:"):
                try:
                    events.append(json.loads(line[5:].strip()))
                except json.JSONDecodeError:
                    continue

    types = [e.get("type") for e in events]
    assert types[0] == "meta", f"首事件应为 meta: {types}"
    assert types[-1] == "done", f"末事件应为 done: {types}"
    assert "delta" in types
    assert types.count("meta") == 1 and types.count("done") == 1
    meta = events[0]
    assert "intent" in meta and "route" in meta


def test_d4_stream_disabled_falls_back_to_single_delta(db_client):
    """STREAM_ENABLED=false → 整个回复一次性下发（仍是 delta 事件）。"""
    app = db_client.application
    cfg = app.extensions["skillmap"]["config"]
    old = cfg.stream_enabled
    cfg.stream_enabled = False
    try:
        with app.app_context():
            resp = db_client.post(
                "/api/v1/chat/stream",
                json={"user_id": DEMO, "thread_id": f"T-{uuid.uuid4().hex[:6]}", "message": "你好"},
            )
            events = []
            for line in resp.get_data(as_text=True).splitlines():
                if line.startswith("data:"):
                    try:
                        events.append(json.loads(line[5:].strip()))
                    except json.JSONDecodeError:
                        continue
        types = [e.get("type") for e in events]
        assert types[0] == "meta" and types[-1] == "done"
        deltas = [e for e in events if e.get("type") == "delta"]
        assert len(deltas) == 1, "非流式应一次性返回"
        assert deltas[0]["text"], "非流式回复不应为空"
    finally:
        cfg.stream_enabled = old


# ---------------- TC-D5 demo_init 幂等 ----------------

def test_d5_demo_init_idempotent():
    """连跑两次 demo_init 不报错、不重复插入画像技能。"""
    _cfg_db()
    from app.config import Config
    from app.profile import skill_service, store
    from app.profile.schemas import PatchSkill, SkillProfilePatch

    demo_user = "demo_e2e_idem"
    patch = SkillProfilePatch(
        user_id=demo_user,
        skills=[
            PatchSkill(skill_id="python", name="Python", theory_score=78, practice_score=70, confidence=0.9),
            PatchSkill(skill_id="sql", name="SQL", theory_score=72, practice_score=60, confidence=0.85),
        ],
    )
    p1 = skill_service.apply_patch(Config(), patch)
    p2 = skill_service.apply_patch(Config(), patch)
    assert p2.version > p1.version  # 版本递增
    assert len(p2.skills) == 2      # 技能不重复
    # 清理
    import app.persistence.db as pgdb

    with pgdb.connect(Config()) as c:
        c.execute("DELETE FROM user_skills WHERE user_id=%s", (demo_user,))


# ---------------- TC-D6 演示五步链路 ----------------

def test_d6_demo_chain(db_client):
    """建数→gap→plan→practice→eval 逐接口 2xx 且核心字段非空。"""
    # 画像（演示用户初始技能）
    _data(db_client.post(
        "/api/v1/profile/upsert",
        json={
            "user_id": DEMO,
            "skills": [
                {"skill_id": "python", "theory_score": 78, "practice_score": 70, "confidence": 0.9},
                {"skill_id": "sql", "theory_score": 72, "practice_score": 60, "confidence": 0.85},
            ],
        },
    ))

    # gap
    gap = _data(db_client.post(
        "/api/v1/gap/request",
        json={"user_id": DEMO, "target_roles": [TARGET_ROLE]},
    ))
    assert gap["reports"] and gap["reports"][0]["gaps"]

    # plan
    plan = _data(db_client.post(
        "/api/v1/plan/generate",
        json={"user_id": DEMO, "target_roles": [TARGET_ROLE]},
    ))
    tasks = [t for ph in plan.get("phases", []) for t in ph.get("tasks", [])]
    assert tasks, "计划应有任务"
    first = tasks[0]

    # practice
    prac = _data(db_client.post(
        "/api/v1/practice/generate",
        json={"user_id": DEMO, "task_id": first["task_id"], "skill_id": first["skill_id"]},
    ))
    assert prac.get("practice_id")

    # artifact
    _data(db_client.post(
        "/api/v1/evaluation/artifact",
        json={
            "user_id": DEMO,
            "practice_id": prac["practice_id"],
            "language": "python",
            "filename": "calc.py",
            "content": "def add(a, b):\n    return a + b\n",
        },
    ))

    # evaluate（触发再规划）
    report = _data(db_client.post(
        "/api/v1/evaluation/evaluate",
        json={"user_id": DEMO, "practice_id": prac["practice_id"], "trigger_replan": True},
    ))
    assert report.get("overall_score", -1) >= 0
    assert "evidence" in report


# ---------------- TC-D7 再规划 + 记忆回写 ----------------

def test_d7_replan_writes_memory(db_client):
    """评估触发 replan 后，成长事件递增。"""
    events_before = _data(db_client.get(f"/api/v1/memory/events?user_id={DEMO}"))
    count_before = len(events_before if isinstance(events_before, list) else events_before.get("events", []))

    gap = _data(db_client.post(
        "/api/v1/gap/request",
        json={"user_id": DEMO, "target_roles": [TARGET_ROLE]},
    ))
    plan = _data(db_client.post(
        "/api/v1/plan/generate",
        json={"user_id": DEMO, "target_roles": [TARGET_ROLE]},
    ))
    tasks = [t for ph in plan.get("phases", []) for t in ph.get("tasks", [])]
    first = tasks[0]
    prac = _data(db_client.post(
        "/api/v1/practice/generate",
        json={"user_id": DEMO, "task_id": first["task_id"], "skill_id": first["skill_id"]},
    ))
    _data(db_client.post(
        "/api/v1/evaluation/artifact",
        json={
            "user_id": DEMO,
            "practice_id": prac["practice_id"],
            "language": "python",
            "filename": "solution.py",
            "content": "def f(x):\n    return x * 2\n",
        },
    ))
    report = _data(db_client.post(
        "/api/v1/evaluation/evaluate",
        json={"user_id": DEMO, "practice_id": prac["practice_id"], "trigger_replan": True},
    ))

    assert report.get("replanned") is True

    events_after = _data(db_client.get(f"/api/v1/memory/events?user_id={DEMO}"))
    count_after = len(events_after if isinstance(events_after, list) else events_after.get("events", []))
    assert count_after > count_before, "评估/再规划应回写成长事件"


# ---------------- TC-D8 前端路由可达 ----------------

def test_d8_frontend_routes_exist():
    """5 个核心视图的懒加载组件文件均存在，路由可解析。"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    router_file = os.path.join(root, "frontend", "src", "router", "index.js")
    assert os.path.exists(router_file)

    views_dir = os.path.join(root, "frontend", "src", "views")
    for name in (
        "DashboardView.vue",
        "SkillGraphView.vue",
        "GapReportView.vue",
        "LearningPlanView.vue",
        "PracticeEvalView.vue",
    ):
        assert os.path.exists(os.path.join(views_dir, name)), f"缺少视图 {name}"

    # 懒加载 import 路径均可解析
    import re

    src = open(router_file, encoding="utf-8").read()
    for m in re.finditer(r"import\('@/views/([\w./]+)'\)", src):
        rel = m.group(1)
        assert os.path.exists(os.path.join(views_dir, rel)), f"路由引用的视图不存在: {rel}"


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    try:
        from app.config import Config
        import app.persistence.db as pgdb

        with pgdb.connect(Config()) as c:
            c.execute("DELETE FROM learning_plans WHERE user_id=%s", (DEMO,))
            c.execute("DELETE FROM user_skills WHERE user_id=%s", (DEMO,))
            c.execute("DELETE FROM threads WHERE user_id=%s", (DEMO,))
    except Exception:  # noqa: BLE001 - 清理失败不阻断测试结果
        pass