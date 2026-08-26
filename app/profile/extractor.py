"""抽取器（阶段 3）：content → SkillProfilePatch（LLM 结构化输出 + 确定性兜底）。"""
from __future__ import annotations

import json
import logging
import re

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.config import Config
from app.profile.schemas import ExtractResult, PatchSkill, ProfileExtractionRequest, SkillProfilePatch

logger = logging.getLogger(__name__)


class _LLMOutput(BaseModel):
    """LLM 结构化输出：只抽技能，不及时打分由规则接管。"""

    skills: list[dict] = Field(default_factory=list)  # [{skill, theory_score, practice_score, confidence}]


def extract(config: Config, req: ProfileExtractionRequest, skill_names: list[str]) -> ExtractResult:
    """抽取技能。LLM 可用走 LLM；LLM 返回为空或异常时，用字典兜底补全。"""
    if config.profile_llm_enabled and config.llm_enabled:
        try:
            raw = _llm_extract(config, req.content)
        except Exception:  # noqa: BLE001
            logger.warning("Profile 抽取 LLM 失败，使用字典兜底", exc_info=True)
            raw = []
        if not raw:
            raw = _fallback_extract(req.content, skill_names)
    else:
        raw = _fallback_extract(req.content, skill_names)

    return _to_result(req, raw, skill_names)


def _llm_extract(config: Config, content: str) -> list[dict]:
    llm = ChatOpenAI(
        model=config.llm_model,
        base_url=config.llm_base_url,
        api_key=config.llm_api_key,
        temperature=0,
    )
    parser = PydanticOutputParser(pydantic_object=_LLMOutput)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是技能解析器。从用户描述中抽取其会使用的技术栈。"
                "规则：技能名标准化（如 'Spring Boot'、'python'），分数 theory/practice 取 0-100，"
                "confidence 0-1。只输出 JSON。\n{format_instructions}",
            ),
            ("human", "{content}"),
        ]
    )
    chain = prompt | llm | parser
    resp: _LLMOutput = chain.invoke(
        {"content": content, "format_instructions": parser.get_format_instructions()}
    )
    return resp.skills


def _fallback_extract(content: str, skill_names: list[str]) -> list[dict]:
    """字典子串匹配兜底：返回命中技能与启发式分数。"""
    text = content.lower()
    found: list[dict] = []
    for name in skill_names:
        nm = (name or "").strip().lower()
        if name and nm in text:
            found.append(
                {
                    "skill": name,
                    "theory_score": 60,
                    "practice_score": 60,
                    "confidence": 0.6,
                }
            )
    return found


def _to_result(req, raw_skills, skill_names) -> ExtractResult:
    known_names = {str(s).strip().lower() for s in skill_names}
    patches: list[PatchSkill] = []

    for item in raw_skills:
        name = str(item.get("skill") or item.get("name") or "").strip()
        if not name or name.lower() not in known_names:
            continue
        patches.append(
            PatchSkill(
                skill_id=name,
                theory_score=min(100, max(0, int(item.get("theory_score") or 0))),
                practice_score=min(100, max(0, int(item.get("practice_score") or 0))),
                confidence=min(1.0, max(0.0, float(item.get("confidence") or 0.6))),
                evidence=[req.source_ref] if req.source_ref else [],
            )
        )

    unmatched = [
        t for t in re.split(r"[，,。；;、\s]+", req.content)
        if t and t.strip().lower() not in known_names
    ]
    return ExtractResult(
        status="extracted",
        patch=SkillProfilePatch(user_id=req.user_id, skills=patches),
        unmatched_tokens=unmatched[:25],
    )