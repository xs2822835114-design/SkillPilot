"""阶段 8 一键初始化演示数据（`python -m scripts.demo_init`，幂等可重复执行）。

步骤：
  1) 初始化/校验全部数据表（init_db）
  2) 灌技能字典 / 技能图种子（幂等）
  3) 灌本地知识库语料（best-effort，为 Chat 答疑演示准备 RAG 数据）
  4) 创建演示用户 demo_user 的初始画像
  5) 生成示例代码文件（供实践/评估演示）

重复执行不报错、不产生重复数据。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_config

ROOT = Path(__file__).resolve().parent.parent

DEMO_USER = "demo_user"

# 演示用户初始画像（技能 id 与 SkillPilot_role_competencies.json 的 slug 一致）
# confidence 需 >= PROFILE_MIN_CONFIDENCE(默认 0.4) 才会进入画像，否则默认 0 会被过滤
DEMO_SKILLS = [
    {"skill_id": "python", "name": "Python", "theory_score": 78, "practice_score": 70, "confidence": 0.9},
    {"skill_id": "sql", "name": "SQL", "theory_score": 72, "practice_score": 60, "confidence": 0.85},
    {"skill_id": "http_api", "name": "HTTP/API", "theory_score": 65, "practice_score": 55, "confidence": 0.8},
]


def _run(module: str) -> None:
    print(f"\n=== {module} ===")
    subprocess.run([sys.executable, "-m", module], check=True, cwd=ROOT)


def ensure_code_sample() -> None:
    """生成示例代码（若不存在）：一个含重复逻辑的可评估模块 + 通过/失败混合的测试。"""
    out_dir = ROOT / "scripts" / "demo_code_sample"
    out_dir.mkdir(exist_ok=True)
    calc = out_dir / "calc.py"
    if not calc.exists():
        calc.write_text(
            "def add(a, b):\n"
            "    return a + b\n"
            "\n"
            "def multiply(a, b):\n"
            "    total = 0\n"
            "    for _ in range(b):  # 演示：乘法用循环实现，逻辑正确但风格可优化\n"
            "        total = add(total, a)\n"
            "    return total\n",
            encoding="utf-8",
        )
        print(f"  已生成 {calc.relative_to(ROOT)}")
    test = out_dir / "test_calc.py"
    if not test.exists():
        test.write_text(
            "from calc import add, multiply\n"
            "\n"
            "\n"
            "def test_add():\n"
            "    assert add(1, 2) == 3\n"
            "\n"
            "def test_multiply():\n"
            "    assert multiply(3, 4) == 12\n"
            "\n"
            "def test_multiply_zero():\n"
            "    assert multiply(5, 0) == 0\n",
            encoding="utf-8",
        )
        print(f"  已生成 {test.relative_to(ROOT)}")


def create_demo_profile() -> None:
    """用阶段 3 的 apply_patch 为演示用户写入初始画像（幂等覆盖）。"""
    from app.config import Config
    from app.profile import skill_service, store
    from app.profile.schemas import PatchSkill, SkillProfilePatch

    for s in DEMO_SKILLS:
        store.ensure_skill_in_dict(Config(), s["skill_id"])
    patch = SkillProfilePatch(
        user_id=DEMO_USER,
        skills=[PatchSkill(**s) for s in DEMO_SKILLS],
    )
    profile = skill_service.apply_patch(Config(), patch)
    print(f"  演示用户 {DEMO_USER} 画像已写入，版本 {profile.version} / {len(profile.skills)} 技能")


def main() -> None:
    cfg = get_config()
    if not cfg.database_url:
        raise SystemExit("DATABASE_URL 未配置，无法初始化演示数据")

    _run("scripts.init_db")
    _run("scripts.seed_skills")
    _run("scripts.seed_skill_graph")
    ensure_code_sample()
    # 本地语料入库（best-effort）：Chat 答疑演示需要 RAG 数据；失败不阻断主链路
    try:
        _run("scripts.ingest_materials")
    except Exception as exc:  # noqa: BLE001
        print(f"  警告：知识库语料入库失败（{exc}），Chat 答疑演示可能无检索上下文")
    try:
        create_demo_profile()
    except Exception as exc:  # noqa: BLE001 - 画像失败不影响其余数据
        print(f"  警告：演示画像写入失败（{exc}），可稍后重试")
    print("\n演示数据准备完成。启动服务后访问前端即可开始 3~5 分钟演示链。")
    print("可运行 `python -m scripts.run_demo` 预览三步链路（需服务已启动）。")


if __name__ == "__main__":
    main()