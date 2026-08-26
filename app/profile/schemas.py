"""角色画像层 Pydantic 契约（阶段 3）：SkillProfile / SkillProfilePatch / SkillEvidence 等。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---------------- 输出结构：SkillProfile ----------------

class ProfileSkill(BaseModel):
    """画像中单条技能（查询/合并后输出）。"""

    skill_id: str
    name: str = ""
    level: int = 0
    theory_score: int = 0
    practice_score: int = 0
    confidence: float = 0.0
    last_proven_at: datetime | None = None
    evidence: list[str] = Field(default_factory=list)


class ProjectInfo(BaseModel):
    project_id: str
    name: str = ""
    skills: list[str] = Field(default_factory=list)


class SkillProfile(BaseModel):
    """完整画像快照（同时是阶段 4 的确定性输入）。"""

    user_id: str
    version: int = 0
    updated_at: datetime | None = None
    skills: list[ProfileSkill] = Field(default_factory=list)
    projects: list[ProjectInfo] = Field(default_factory=list)
    preferences: dict[str, Any] = Field(default_factory=dict)


# ---------------- 输入结构：Patch / ExtractRequest ----------------

class PatchSkill(BaseModel):
    """增量更新中某技能字段（未提供的字段保持原值）。"""

    skill_id: str = Field(min_length=1, max_length=64)
    theory_score: int | None = Field(default=None, ge=0, le=100)
    practice_score: int | None = Field(default=None, ge=0, le=100)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)


class SkillProfilePatch(BaseModel):
    """增量更新载荷：只含本次要变更的技能与偏好。"""

    user_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    skills: list[PatchSkill] = Field(default_factory=list, max_length=30)
    preferences: dict[str, Any] = Field(default_factory=dict)


class ProfileExtractionRequest(BaseModel):
    """POST /api/v1/profile/extract 请求契约。"""

    user_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    source_type: str = Field(default="conversation", pattern=r"^(conversation|self_report|project)$")
    source_ref: str | None = Field(default=None, max_length=255)
    content: str = Field(min_length=1, max_length=20000)
    project_id: str | None = None

    @field_validator("content")
    @classmethod
    def _strip_content(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("content 不能为空")
        return v


class ProjectCreateRequest(BaseModel):
    """POST /api/v1/profile/projects 请求契约。"""

    user_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    project_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    name: str = ""
    description: str = ""
    repo_url: str | None = None
    skills: list[str] = Field(default_factory=list)


class ExtractResult(BaseModel):
    """extract 响应：待确认 patch + 未命中片段。"""

    status: str = "extracted"
    patch: SkillProfilePatch
    unmatched_tokens: list[str] = Field(default_factory=list)