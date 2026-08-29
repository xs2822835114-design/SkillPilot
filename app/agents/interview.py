"""技能访谈 Agent（方案第 9、10、11 节）：多轮自然对话 → UserSkillProfile。

职责边界（方案第 15 节）：
- 本 Agent 只负责「问什么」「怎么把回答变成证据」的对话侧编排；
- 「证据 → 等级」的确定性估算委托给 app/engines/skill_engine（Engine 侧）。

状态机（跨轮，靠 Checkpointer 持久化 ``interview_state``）：
  无 active → 初始化访谈队列，问第一个技能 → need_input
  active + 本轮为回答 → 抽证据、更新 user_profile → 问下一个 / 全部问完 → done
"""
from __future__ import annotations

from typing import Any, Callable

from app.config import Config
from app.domain import UserSkillProfile

# 访谈顺序：目标技能 > 前置 > 子能力 > 关联
_SOURCE_PRIORITY = {"target": 0, "prerequisite": 1, "composite": 2, "related": 3}


def _interview_order(target: dict, limit: int) -> list[str]:
    """访谈顺序：目标技能 > 前置 > 子能力 > 关联；``limit`` ≤0 表示不设上限（询问全部）。"""
    skills = sorted(
        target.get("skills") or [],
        key=lambda s: (
            _SOURCE_PRIORITY.get(s.get("source"), 9),
            -float(s.get("weight", 0) or 0),
            -int(s.get("required_level", 0) or 0),
        ),
    )
    ids = [s["skill_id"] for s in skills]
    if limit and limit > 0:
        ids = ids[:limit]
    return ids


def _name_map(config: Config) -> dict[str, str]:
    """技能 id → 名称 全量映射（用于把关系里的子能力/前置 id 渲染成可读技术名）。"""
    try:
        from app.knowledge import list_skills

        return {s["id"]: s["name"] or s["id"] for s in list_skills(config)}
    except Exception:  # noqa: BLE001 - 仅文案增强，缺失不阻断
        return {}


def _skill_options(config: Config, skills_map: dict, skill_id: str) -> list[dict]:
    """为一个技能生成「与实际技术高度相关」的熟练度选择题选项（可多选 + 自由填写）。

    选项文案刻意嵌入与 skill_engine.estimate_level 一致的行为证据关键词，使勾选答案
    能被确定性推导为 level（0~5）；技术相关性来自该技能的 composite_of/related/requires
    关联技术名（提到真实子能力/前置技术，而非泛泛的「了解/会用」）。
    """
    name = (skills_map.get(skill_id) or {}).get("skill_name") or skill_id
    comps: list[str] = []
    try:
        from app.knowledge import relations

        rel = relations(config, skill_id)
        comp_ids = [
            *(rel.get("composite_of") or []),
            *(rel.get("related") or []),
            *(rel.get("requires") or []),
        ]
        comps = [(skills_map.get(c) or {}).get("skill_name") or c for c in comp_ids][:3]
    except Exception:  # noqa: BLE001 - 子能力名仅作文案增强，缺失不阻断
        comps = []
    tech = f"（如 {'、'.join(comps)}）" if comps else ""
    return [
        {"level": 0, "label": "完全没接触过，不太清楚这个方向"},
        {"level": 1, "label": f"了解 {name} 的核心概念，知道它能做什么"},
        {"level": 2, "label": f"会用 {name} 基础 API，能写简单示例/脚本{tech}"},
        {"level": 3, "label": f"在真实项目里用过 {name}{tech}，有实战经验"},
        {"level": 4, "label": f"能独立设计并搭建 {name} 相关系统"},
        {"level": 5, "label": f"精通 {name}，能主导架构设计与复杂系统优化"},
    ]


def _build_question(config: Config, skills_map: dict, skill_id: str, idx: int, total: int) -> tuple[str, dict]:
    """组装一条访谈问题：自然语言提示 + 结构化选择题（供前端渲染勾选 + 自由填写）。"""
    name = (skills_map.get(skill_id) or {}).get("skill_name") or skill_id
    prompt = (
        f"（{idx}/{total}）你之前接触过 {name} 吗？请勾选符合你实际情况的选项（可多选），"
        "并可在「补充说明」里填写具体经历或项目。"
    )
    question = {
        "skill_id": skill_id,
        "skill_name": name,
        "index": idx,
        "total": total,
        "prompt": prompt,
        "options": _skill_options(config, skills_map, skill_id),
        "allow_multiple": True,
        "free_text": True,
    }
    return prompt, question


def _with_question(prev_artifacts: dict, question: dict) -> dict:
    """在既有 artifacts 基础上追加/更新访谈问题，保留 target_profile 等上游产物。"""
    out = {k: v for k, v in (prev_artifacts or {}).items() if k != "interview_question"}
    out["interview_question"] = question
    return out


def _empty_profile(user_id: str) -> dict:
    return {"user_id": user_id, "skills": []}


def _upsert_skill(profile: dict, skills_map: dict, skill_id: str, level: int | None, confidence: float, evidence: list[str]) -> dict:
    name = skills_map.get(skill_id, {}).get("skill_name") or skill_id
    skills: list[dict] = list(profile.get("skills") or [])
    for s in skills:
        if s.get("skill_id") == skill_id:
            s["level"] = level
            s["confidence"] = confidence
            s["evidence"] = list(dict.fromkeys([*(s.get("evidence") or []), *evidence]))
            return {**profile, "skills": skills}
    skills.append(
        {
            "skill_id": skill_id,
            "skill_name": name,
            "level": level,
            "confidence": confidence,
            "evidence": evidence,
            "source": "interview",
        }
    )
    return {**profile, "skills": skills}


def make_interview_node(config: Config) -> Callable[[dict], dict]:
    """技能访谈节点：跨轮推进访谈，产出/更新 user_profile。"""
    from app.engines import estimate_level

    def node(state: dict) -> dict:
        target = state.get("target_profile") or {}
        target_skills = target.get("skills") or []
        if not target_skills:
            return {
                "workflow_status": "degraded",
                "current_agent": "skill_interview_agent",
                "error": {"type": "service_error", "message": "目标画像缺失，无法开始访谈。"},
                "summary": "",
            }
        # 全量技能名映射（含关系里的子能力/前置），保证选择题文案能提到真实技术名
        skills_map = {sid: {"skill_name": name} for sid, name in _name_map(config).items()}
        for s in target_skills:
            skills_map.setdefault(s["skill_id"], {"skill_name": s.get("skill_name") or s["skill_id"]})

        iv = state.get("interview_state") or {}
        profile = state.get("user_profile") or _empty_profile(state.get("user_id") or "")
        if "skills" not in profile:
            profile = _empty_profile(state.get("user_id") or "")
        if not profile.get("user_id"):
            profile["user_id"] = state.get("user_id") or ""

        if not iv.get("active"):
            # 首次进入：初始化访谈队列并问第一个技能
            queue = _interview_order(target, config.interview_question_count)
            iv = {"active": True, "skill_queue": queue, "asked": [], "current_skill": queue[0]}
            prompt, question = _build_question(config, skills_map, queue[0], 1, len(queue))
            return {
                "workflow_status": "need_input",
                "current_agent": "skill_interview_agent",
                "error": {"type": "need_input", "message": prompt},
                "summary": "",
                "interview_state": iv,
                "user_profile": profile,
                "artifacts": _with_question(state.get("artifacts"), question),
            }

        # 已激活：本轮消息是用户对当前技能的回答
        current = iv.get("current_skill")
        answer = (state.get("message") or "").strip()
        level, confidence, evidence = estimate_level(answer)
        profile = _upsert_skill(profile, skills_map, current, level, confidence, evidence)

        asked = list(iv.get("asked") or []) + [current]
        iv["asked"] = asked
        remaining = [sid for sid in iv["skill_queue"] if sid not in asked]

        if remaining:
            nxt = remaining[0]
            iv["current_skill"] = nxt
            prompt, question = _build_question(config, skills_map, nxt, len(asked) + 1, len(iv["skill_queue"]))
            return {
                "workflow_status": "need_input",
                "current_agent": "skill_interview_agent",
                "error": {"type": "need_input", "message": prompt},
                "summary": "",
                "interview_state": iv,
                "user_profile": profile,
                "artifacts": _with_question(state.get("artifacts"), question),
            }

        # 访谈结束 → 交给缺口引擎
        iv["active"] = False
        return {
            "workflow_status": "done",
            "current_agent": "skill_interview_agent",
            "error": None,
            "summary": "技术栈访谈完成，正在计算技能缺口…",
            "interview_state": iv,
            "user_profile": profile,
        }

    return node


def profile_from_state(user_id: str, user_profile: dict) -> UserSkillProfile:
    """State 中的 user_profile dict → UserSkillProfile 领域契约。"""
    data = {"user_id": user_id, "skills": (user_profile or {}).get("skills") or []}
    return UserSkillProfile.model_validate(data)