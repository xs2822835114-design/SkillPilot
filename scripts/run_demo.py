"""阶段 8 三分钟演示链路脚本（`python -m scripts.run_demo`）。

前置：先执行 `python -m scripts.demo_init` 造数；再启动服务：
    .venv/bin/python -m flask --app run.py run --port 8081

本脚本按演示分镜依次调用 8 个 HTTP 接口，逐段打印状态与核心字段，
用于比赛前快速核对链路可用性。服务未就绪时给出引导说明并安全退出。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE_URL = os.getenv("DEMO_BASE_URL", "http://127.0.0.1:8081")
DEMO_USER = "demo_user"
# role_id（SkillPilot_role_competencies.json）：RC013 = Python 后端工程师
TARGET_ROLE = os.getenv("DEMO_TARGET_ROLE", "RC013")


def _health() -> bool:
    try:
        import httpx

        return httpx.get(f"{BASE_URL}/health", timeout=3).status_code == 200
    except Exception:  # noqa: BLE001
        return False


def _call(client, method: str, path: str, body=None) -> dict:
    # LLM 增强接口（gap/plan/eval）可能较慢，超时放宽到 90s；如演示想更快更稳，
    # 可在 .env 关闭 LLM 增强（如 PLAN_LLM_ENABLED=false）走纯规则，秒级返回。
    resp = client.request(method, f"{BASE_URL}{path}", json=body, timeout=90)
    data = resp.json()
    if resp.status_code >= 400:
        print(f"      ✗ {method} {path} → {resp.status_code} {data}")
        sys.exit(f"链路在 {path} 中断，请检查服务与数据。")
    print(f"      ✓ {method} {path} → {resp.status_code}")
    return data.get("data", data)


def main() -> None:
    if not _health():
        print(f"服务 {BASE_URL} 不可达。请先启动服务后再运行本脚本。")
        print("  参考：.venv/bin/python -m flask --app run.py run --port 8081")
        sys.exit(0)

    import httpx

    print("=" * 56)
    print("SkillPilot 三分钟演示链路")
    print(f"用户 {DEMO_USER} / 目标 {TARGET_ROLE} / 服务 {BASE_URL}")
    print("=" * 56)

    with httpx.Client() as client:
        # 1) Dashboard 聚合
        print("\n[1/7] 工作台 Dashboard（画像 + 计划 + 评估 + 成长）")
        dash = _call(client, "GET", f"/api/v1/dashboard/{DEMO_USER}")
        print(f"      画像技能 {len(dash.get('profile', {}).get('skills', []))} 项")

        # 2) 技能图谱
        print("\n[2/7] 技能图谱 Skill Graph")
        g = _call(client, "GET", "/api/v1/graph")
        print(f"      节点 {len(g.get('nodes', []))}，边 {len(g.get('edges', []))}")

        # 3) 缺口报告 Gap
        print("\n[3/7] 缺口报告 Gap Report")
        gap = _call(
            client, "POST", "/api/v1/gap/request",
            {"user_id": DEMO_USER, "target_roles": [TARGET_ROLE]},
        )
        r0 = gap["reports"][0]
        print(f"      目标 {r0['target_role']}，缺口 {len(r0['gaps'])} 项")

        # 4) 学习计划（B 通道：自算缺口）
        print("\n[4/7] 学习计划 Learning Plan")
        plan = _call(
            client, "POST", "/api/v1/plan/generate",
            {"user_id": DEMO_USER, "target_roles": [TARGET_ROLE]},
        )
        pid = plan["plan_id"]
        print(f"      计划 {pid}，任务 {plan.get('metrics', {}).get('total_tasks', 0)} 项")

        # 5) 实践任务（取计划首条任务）
        print("\n[5/7] 实践任务 Practice")
        tasks = plan.get("tasks") or (plan.get("phases") or [{}])[0].get("tasks", [])
        task = (tasks or [{}])[0]
        tid = task.get("task_id") or "demo-task-1"
        sid = task.get("skill_id") or "python"
        prac = _call(
            client, "POST", "/api/v1/practice/generate",
            {"user_id": DEMO_USER, "task_id": tid, "skill_id": sid},
        )
        prac_id = prac["practice_id"]
        print(f"      实践 {prac_id}")

        # 6) 上传代码 + 评估
        print("\n[6/7] 代码评估 + 再规划 Evaluation")
        sample = Path(__file__).parent / "demo_code_sample"
        calc_src = (sample / "calc.py").read_text(encoding="utf-8")
        test_src = (sample / "test_calc.py").read_text(encoding="utf-8")
        _call(
            client, "POST", "/api/v1/evaluation/artifact",
            {"user_id": DEMO_USER, "practice_id": prac_id, "language": "python",
             "filename": "calc.py", "content": calc_src, "test_content": test_src},
        )
        rep = _call(
            client, "POST", "/api/v1/evaluation/evaluate",
            {"user_id": DEMO_USER, "practice_id": prac_id, "trigger_replan": True},
        )
        print(f"      overall={rep.get('overall_score')}, replanned={rep.get('replanned')}")

        # 7) 成长轨迹
        print("\n[7/7] 成长轨迹 Growth")
        ev = _call(client, "GET", f"/api/v1/memory/events?user_id={DEMO_USER}")
        print(f"      事件 {len(ev if isinstance(ev, list) else ev.get('events', []))} 条")

    print("\n演示链路 7/7 全部通过 ✅（3~5 分钟可达）")


if __name__ == "__main__":
    main()