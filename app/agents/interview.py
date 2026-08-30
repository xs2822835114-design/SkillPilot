"""技能访谈 Agent（方案第 9、10、11 节）：多轮自然对话 → UserSkillProfile。

职责边界（方案第 15 节）：
- 本 Agent 只负责「问什么」「怎么把回答变成证据」的对话侧编排；
- 「证据 → 等级」的确定性估算委托给 app/engines/skill_engine（Engine 侧）。

关键改进（解决「访谈问题像模子刻出来」）：
- 不再为每个技能生成同一套「勾选 0~5 熟练度」模板；
- 改为：SkillProfile（技能画像，来自 knowledge.learning_metadata）
        → InterviewStrategy（按 skill_type 决定问哪些能力点，来自 interview_strategy）
        → 逐能力点生成类型化问题（concept / api / scenario / experience …）
- 同一技能再多问几个能力点，题面锚定真实 core_concepts / core_apis / practice_context，
  不同技能（Checkpoint=mechanism vs LangGraph=framework vs LLM API=api）题面天然不同。
- 访谈意见收集后仍由 estimate_level（Skill Engine）从证据推导等级，不推翻原有机制。

状态机（跨轮，靠 Checkpointer 持久化 ``interview_state``）：
  无 active → 初始化技能队列，问第一个技能的「第一个能力点」→ need_input
  active + 本轮为回答 → 抽证据更新 user_profile → 若当前技能还有未问能力点 → 追问下一能力点；
      否则移到下一个技能；全部问完 → done
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

from app.config import Config
from app.domain import UserSkillProfile
from app.domain.interview import InterviewQuestionType
from app.agents.interview_strategy import build_strategy

logger = logging.getLogger(__name__)

# 访谈顺序：目标技能 > 前置 > 子能力 > 关联
_SOURCE_PRIORITY = {"target": 0, "prerequisite": 1, "composite": 2, "related": 3}

# 无法从图谱拿到核心概念/API/场景时的通用兜底能力点（避免题面空泛）
_GENERIC_SUBJECTS = {
    InterviewQuestionType.CONCEPT: "核心概念与作用边界",
    InterviewQuestionType.API: "核心接口的调用方式",
    InterviewQuestionType.SCENARIO: "典型业务场景中的落地",
}

# 默认每技能最多问几个能力点（避免无限追问；>3 时才会覆盖 implementation/open）
_DEFAULT_PER_SKILL = 4


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


# ---------------- 能力点规划：把 skill_type 策略锚定到真实技术对象 ----------------

def _capability_pool(profile) -> list[str]:
    """该技能的可验证能力点：practice 场景 > 核心概念 > 核心 API，去重。"""
    pool: list[str] = []
    for src in (
        list(getattr(profile, "practice_context", None) or []),
        list(getattr(profile, "core_concepts", None) or []),
        list(getattr(profile, "core_apis", None) or []),
    ):
        for s in src:
            s = str(s).strip()
            if s and s not in pool:
                pool.append(s)
    return pool


def _plan_capabilities(profile, strategy) -> list[tuple[InterviewQuestionType, str]]:
    """把策略的问题类型序列，逐个锚定到具体能力点。

    概念/API/场景 类型取能力池中未用过的真实技术点；经验/实现/开放 用该技能通用题面。
    """
    pool = _capability_pool(profile)
    used = 0
    slots: list[tuple[InterviewQuestionType, str]] = []
    for qt in strategy.question_types:
        if qt in (InterviewQuestionType.EXPERIENCE, InterviewQuestionType.IMPLEMENTATION, InterviewQuestionType.OPEN):
            slots.append((qt, ""))
            continue
        if used < len(pool):
            slots.append((qt, pool[used]))
            used += 1
        else:
            slots.append((qt, _GENERIC_SUBJECTS.get(qt, "")))
    # 能力点是空的（没有任何可验证技术点）时，退化为一条「经验」问题保证一定有题
    if all(not subj for _, subj in slots):
        slots = [(InterviewQuestionType.EXPERIENCE, "")]
    return slots


def _per_skill_limit(config: Config, strategy) -> int:
    n = len(strategy.question_types)
    cap = int(getattr(config, "interview_question_count", 0) or 0)
    per = n if cap <= 0 else min(n, cap)
    return max(1, min(per, _DEFAULT_PER_SKILL))


# ---------------- 题型化题目生成（规则实现；LLM 关闭时兜底） ----------------

def _band_options(qt: InterviewQuestionType, subject: str, name: str) -> list[dict]:
    """按题型生成一组技术化选项；选项内嵌行为证据关键词驱动 estimate_level。"""
    target = subject or name
    generic = [
        ("a", 4, f"我独立设计并搭建过 {target} 相关的完整方案/系统"),
        ("b", 3, f"在真实项目里用过/实现过 {target}，有实战经验"),
        ("c", 2, f"写过 {target} 的基础示例/脚本，练过手"),
        ("d", 1, f"看过/了解过 {target} 的资料和概念"),
        ("e", 0, f"完全没接触过 {target}"),
    ]
    by_type: dict[InterviewQuestionType, list[tuple[str, int, str]]] = {
        InterviewQuestionType.CONCEPT: [
            ("a", 4, f"我能讲清 {target} 的作用、原理与适用边界"),
            ("b", 2, f"我写过 {target} 相关的例子验证过它的行为"),
            ("c", 1, f"我看过 {target} 的资料，知道它是干嘛的"),
            ("d", 0, f"完全没接触过 {target}"),
        ],
        InterviewQuestionType.API: [
            ("a", 3, f"我实际配置/调用过 {target} 的接口，并在项目里用起来了"),
            ("b", 2, f"我写过 {target} 的最小调用来验证参数"),
            ("c", 1, f"我了解 {target} 大概怎么用，但没跑过"),
            ("d", 0, f"完全没接触过 {target}"),
        ],
        InterviewQuestionType.SCENARIO: [
            ("a", 3, f"遇到 {target} 这种场景时，我在真实项目里处理过"),
            ("b", 2, f"我在课设/练习里模拟过 {target} 的场景并跑通"),
            ("c", 1, f"我只知道 {target} 这类场景该考虑这些点，没实操"),
            ("d", 0, f"完全没接触过 {target}"),
        ],
    }
    rows = by_type.get(qt, generic)
    return [{"id": oid, "text": text, "band": band} for oid, band, text in rows]


def _question_text(qt: InterviewQuestionType, profile, subject: str) -> str:
    name = profile.skill_name or profile.skill_id
    parent = profile.parent_skill_name or ""
    target = subject or name
    ctx = (f"{parent} 上下文" if parent else "独立工程")
    where = f"在{ctx}中"
    paren = (f"（{parent}）" if parent else "")
    text = {
        InterviewQuestionType.CONCEPT: (
            f"关于 {name} 的「{target}」：《{where} 它解决什么问题、拆开来怎么运作》？"
            "请勾选符合你实际了解/动手情况的一项，可补充具体理解。"
        ),
        InterviewQuestionType.API: (
            f"关于 {name} 的 API「{target}」：《实际上手配置/调用过吗，参数影响结果吗》？"
            "请勾选符合你实际操作情况的一项，可补充具体用例。"
        ),
        InterviewQuestionType.SCENARIO: (
            f"设想一个「{target}」的真实业务场景：《{where} 你会怎么做，踩过什么坑》？"
            "请勾选你的实操程度，可补充场景细节。"
        ),
        InterviewQuestionType.EXPERIENCE: (
            f"你在真实项目里用 {name}{paren} 干过什么级别的活？"
            "请勾选最接近的一项，可在补充里写做过的东西。"
        ),
        InterviewQuestionType.IMPLEMENTATION: (
            f"你是否独立实现/搭建过 {name} 相关的功能或系统（{where}）？"
            "请勾选最接近的一项，可补充实现范围。"
        ),
        InterviewQuestionType.OPEN: (
            f"关于 {name}，还有哪些具体经历、项目或疑问想补充？（选「没接触」就填无）"
        ),
    }[qt]
    return text


# ---------------- LLM 现场针对性出题（interview_llm_enabled=true 时启用） ----------------

# band 满分档位的判据，供 LLM 生成「技术化 + 可判级」的选项时对齐行为证据。
_BAND_GUIDANCE = (
    "每个选项用第一人称写一段具体的技术性自述，让答案落在不同能力段位并让关键词可被提取：\n"
    "  band=4 独立设计/从零搭建/主导过/调优过（精通）；\n"
    "  band=3 在真实项目里实现过/落地过/接入了；\n"
    "  band=2 写过示例/脚本练过手/跑通最小调用；\n"
    "  band=1 看过/了解过资料和概念；\n"
    "  band=0 完全没接触过。\n"
    "选项必须紧扣该技能的真实概念/API/场景，而不是空泛的『我能做到』。"
)


def _parameterized_question(config: Config, profile, skill_id: str) -> tuple[list[str], list[str], str]:
    """把技能画像浓缩成语料：核心概念 / 核心 API / 实践场景 + 父技能上下文。"""
    concepts = list(getattr(profile, "core_concepts", None) or [])
    apis = list(getattr(profile, "core_apis", None) or [])
    practices = list(getattr(profile, "practice_context", None) or [])
    parent = getattr(profile, "parent_skill_name", None) or ""
    ctx = f"（该技能是 {parent} 下的机制/能力，需在 {parent} 上下文中考察）" if parent else ""
    return concepts, apis, practices, ctx


def _llm_available(config: Config) -> bool:
    return bool(config.interview_llm_enabled and config.llm_enabled)


def _parse_options(raw: list, name: str) -> list[dict]:
    """把 LLM 返回的选项归一化成 {id, text, band}；去重、兜底空选项。"""
    rows: list[dict] = []
    seen: set[str] = set()
    for o in raw or []:
        if isinstance(o, dict):
            text = str(o.get("text") or "").strip()
        else:
            text = str(o).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        band = o.get("band") if isinstance(o, dict) else None
        rows.append({"id": _LLM_OPTION_IDS[len(rows)], "text": text, "band": int(band) if isinstance(band, int) else 1})
    # 始终兜底「完全没接触过」挡位，保证等级 0 可被选中
    if not any(r["band"] == 0 for r in rows):
        rows.append({"id": _LLM_OPTION_IDS[len(rows)], "text": f"完全没接触过 {name}", "band": 0})
    if not rows:
        rows = [{"id": "a", "text": f"我了解过 {name} 的基础概念", "band": 1},
                {"id": "b", "text": f"完全没接触过 {name}", "band": 0}]
    return rows


_LLM_OPTION_IDS = "abcdefghij"


def _build_question_with_llm(
    config: Config, profile, skill_id: str, qt: InterviewQuestionType,
    subject: str, index: int, total: int,
) -> tuple[str, dict] | None:
    """让 LLM 现场理解技能画像，生成针对性题干 + 技术化选项；不可用/失败返回 None（走规则兜底）。"""
    if not _llm_available(config):
        return None
    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        name = profile.skill_name or profile.skill_id
        type_label = {"concept": "概念理解", "api": "接口实操", "scenario": "场景落地",
                      "experience": "实战经验", "implementation": "独立实现", "open": "开放追问"}.get(qt.value, qt.value)
        concepts, apis, practices, ctx = _parameterized_question(config, profile, skill_id)
        llm = ChatOpenAI(
            model=config.llm_model,
            base_url=config.llm_base_url,
            api_key=config.llm_api_key,
            temperature=0.5,
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一名资深技术面试官，正在为学习者的技能画像生成一道【{type_label}】型选择题。"
                    "要求：题干针对该技能的【核心概念 / 核心 API / 实践场景】提出，并结合父技能上下文，"
                    "不要泛泛问『你接触过 X 吗』；选项是技术化、可区分能力段位的具体自述，而不是空洞的程度词。\n"
                    "命中的能力点：{subject}。\n"
                    "只输出合法 JSON（不要 markdown 代码块），形如：{schema}",
                ),
                (
                    "human",
                    "技能：{name}；类型：{skill_type}；父技能上下文：{ctx}\n"
                    "核心概念：{concepts}\n核心 API：{apis}\n实践场景：{practices}\n\n"
                    "题目类型：{qtype_desc}。{band_guidance}",
                ),
            ]
        )
        schema = json.dumps(
            {"question": "针对性题干（自然口语，含该技能的具体词）",
             "options": [{"text": "第一人称技术自述选项",
                          "band": "0-4（4=独立设计/主导,3=项目实战,2=示例练手,1=看过资料,0=没接触）"}]}
        )
        content = (prompt | llm).invoke(
            {
                "type_label": type_label,
                "subject": subject or (concepts[0] if concepts else name),
                "name": name,
                "skill_type": profile.skill_type,
                "ctx": ctx,
                "concepts": "、".join(concepts) or "（无）",
                "apis": "、".join(apis) or "（无）",
                "practices": "、".join(practices) or "（无）",
                "qtype_desc": {
                    InterviewQuestionType.OPEN: "开放追问，问法应引导用户补充分享，但选项仍按能力段位给",
                    InterviewQuestionType.EXPERIENCE: "问真实项目里用该技能干过什么级别的活",
                    InterviewQuestionType.IMPLEMENTATION: "问是否独立实现/搭建过相关功能与系统",
                }.get(qt, "标准选择题"),
                "band_guidance": _BAND_GUIDANCE,
                "schema": schema,
            }
        )
        text = (content.content if hasattr(content, "content") else str(content)).strip()
        text = text.strip("` \n")
        if text.startswith("json"):
            text = text[4:].lstrip("` ")
        data = json.loads(text)
        question_text = str(data.get("question") or "").strip() or _question_text(qt, profile, subject)
        options = _parse_options(data.get("options") or [], name)
        prompt_text = f"（{index}/{total}）{question_text}"
        question = {
            "question_id": f"{skill_id}_q{qt.value}",
            "skill_id": skill_id,
            "skill_name": (profile.skill_name or skill_id),
            "question_type": qt.value,
            "capability": subject,
            "prompt": prompt_text,
            "question": question_text,
            "options": options,
            "allow_multiple": True,
            "allow_free_text": True,
            "index": index,
            "total": total,
            "generated_by": "llm",
        }
        return prompt_text, question
    except Exception:  # noqa: BLE001
        logger.warning("Interview LLM 现场出题失败，走规则兜底", exc_info=True)
        return None


def _build_question(
    config: Config, profile, skills_map: dict, skill_id: str, qt: InterviewQuestionType,
    subject: str, index: int, total: int,
) -> tuple[str, dict]:
    """生成一条访谈题目：优先 LLM 现场理解画像出针对性题，否则回退到规则化题面。"""
    llm_res = _build_question_with_llm(config, profile, skill_id, qt, subject, index, total)
    if llm_res is not None:
        return llm_res
    name = (skills_map.get(skill_id) or {}).get("skill_name") or profile.skill_name or skill_id
    qtext = _question_text(qt, profile, subject)
    prompt = f"（{index}/{total}）{qtext}"
    question = {
        "question_id": f"{skill_id}_q{qt.value}",
        "skill_id": skill_id,
        "skill_name": name,
        "question_type": qt.value,
        "capability": subject,
        "prompt": prompt,
        "question": qtext,
        "options": _band_options(qt, subject, name),
        "allow_multiple": True,
        "allow_free_text": True,
        "index": index,
        "total": total,
        "generated_by": "rule",
    }
    return prompt, question


def _profile_for(config: Config, skill_id: str):
    """加载技能学习画像（SkillProfile）：分类 + 父技能 + 核心概念/API/场景。"""
    from app.knowledge.learning_metadata import classify

    return classify(config, skill_id)


def _with_question(prev_artifacts: dict, question: dict) -> dict:
    """在既有 artifacts 基础上追加/更新访谈问题，保留 target_profile 等上游产物。"""
    out = {k: v for k, v in (prev_artifacts or {}).items() if k != "interview_question"}
    out["interview_question"] = question
    return out


def _empty_profile(user_id: str) -> dict:
    return {"user_id": user_id, "skills": []}


def _upsert_skill(profile: dict, skill_id: str, skill_name: str, level: int | None, confidence: float, evidence: list[str]) -> dict:
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
            "skill_name": skill_name,
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
        # 全量技能名映射（含关系里的子能力/前置），保证题面能提到真实技术名
        skills_map = {sid: {"skill_name": name} for sid, name in _name_map(config).items()}
        for s in target_skills:
            skills_map.setdefault(s["skill_id"], {"skill_name": s.get("skill_name") or s["skill_id"]})

        iv = state.get("interview_state") or {}
        profile = state.get("user_profile") or _empty_profile(state.get("user_id") or "")
        if "skills" not in profile:
            profile = _empty_profile(state.get("user_id") or "")
        if not profile.get("user_id"):
            profile["user_id"] = state.get("user_id") or ""

        def slots_for(sid: str) -> list:
            """某个技能最终会问的能力点（题面锚定真实技术点）。"""
            sp = _profile_for(config, sid)
            limit = _per_skill_limit(config, build_strategy(sp, config.interview_question_count))
            return _plan_capabilities(sp, build_strategy(sp, config.interview_question_count))[:limit]

        def count_for(sid: str) -> int:
            return max(1, len(slots_for(sid)))

        def ask(skill_id: str, cap_index: int) -> dict:
            """问某个技能的第 cap_index 个能力点，返回节点输出。"""
            sp = _profile_for(config, skill_id)
            strategy = build_strategy(sp, config.interview_question_count)
            slots = _plan_capabilities(sp, strategy)[: _per_skill_limit(config, strategy)]
            qt, subject = slots[cap_index]
            gindex = len(iv.get("asked_questions") or []) + 1
            gtotal = sum(count_for(sid) for sid in iv["skill_queue"])
            prompt, question = _build_question(config, sp, skills_map, skill_id, qt, subject, gindex, gtotal)
            iv["current_skill"] = skill_id
            iv["current_capabilities"] = [slot[1] or slot[0].value for slot in slots]
            iv["current_cap_index"] = cap_index
            return {
                "workflow_status": "need_input",
                "current_agent": "skill_interview_agent",
                "error": {"type": "need_input", "message": prompt},
                "summary": "",
                "interview_state": iv,
                "user_profile": profile,
                "artifacts": _with_question(state.get("artifacts"), question),
            }

        if not iv.get("active"):
            # 首次进入：初始化访谈队列并问第一个技能的第一个能力点
            queue = _interview_order(target, config.interview_question_count)
            if not queue:
                return {
                    "workflow_status": "done",
                    "current_agent": "skill_interview_agent",
                    "error": None,
                    "summary": "没有需要访谈的技能，直接进入缺口计算。",
                    "interview_state": {"active": False, "skill_queue": [], "finished": True},
                    "user_profile": profile,
                }
            iv = {
                "active": True,
                "skill_queue": queue,
                "asked_questions": [],
                "asked_capabilities": [],
                "evidence": [],
                "question_count": 0,
                "finished": False,
            }
            return ask(queue[0], 0)

        # 已激活：本轮消息是用户对当前技能当前能力点的回答
        current = iv.get("current_skill") or iv.get("skill_queue", [""])[0]
        answer = (state.get("message") or "").strip()
        level, confidence, evidence = estimate_level(answer)
        skill_name = (skills_map.get(current) or {}).get("skill_name") or current
        profile = _upsert_skill(profile, current, skill_name, level, confidence, evidence)
        iv["evidence"] = list(dict.fromkeys([*(iv.get("evidence") or []), *evidence]))
        iv["question_count"] = iv.get("question_count", 0) + 1
        asked_q = list(iv.get("asked_questions") or []) + [current]
        iv["asked_questions"] = asked_q
        iv["asked_capabilities"] = list(iv.get("asked_capabilities") or []) + [current]

        # 自适应：当前技能还有未问能力点 → 追问下一能力点；否则移到下一个技能
        cap_index = int(iv.get("current_cap_index") or 0) + 1
        sp = _profile_for(config, current)
        strategy = build_strategy(sp, config.interview_question_count)
        limit = _per_skill_limit(config, strategy)
        if cap_index < limit and limit > 1:
            return ask(current, cap_index)

        remaining = [sid for sid in iv["skill_queue"] if sid not in asked_q]
        if remaining:
            return ask(remaining[0], 0)

        # 访谈全部结束 → 交给缺口引擎
        iv["active"] = False
        iv["finished"] = True
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