"""能力评估层 Pydantic 契约（阶段 6，Evaluation Agent）。

EvaluationReport 是核心产物：结构化评分 + 证据 + 下一步建议；shop 区分理论/实践。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

VALID_ARTIFACT_TYPES = {"github", "snippet"}


class ArtifactUploadRequest(BaseModel):
    """POST /api/v1/evaluation/artifact（代码片段兜底录入）。"""

    user_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    practice_id: str = Field(min_length=1)
    language: str = Field(default="python", pattern=r"^[a-z0-9]{1,16}$")
    filename: str = Field(max_length=255)
    content: str = Field(min_length=1, max_length=200000)
    test_content: str | None = Field(default=None, max_length=200000)


class EvaluationRequest(BaseModel):
    """POST /api/v1/evaluation/evaluate 请求契约。"""

    user_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    practice_id: str = Field(min_length=1)
    artifact_type: str = Field(default="snippet")
    artifact_ref: str | None = Field(default=None, max_length=2048)
    repo_files: dict[str, str] = Field(default_factory=dict, max_length=100)
    trigger_replan: bool | None = None

    @field_validator("artifact_type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        if v not in VALID_ARTIFACT_TYPES:
            raise ValueError(f"artifact_type 暂不支持: {v}")
        return v


# ---------------- 输出 ----------------

class SkillScore(BaseModel):
    skill_id: str = ""
    theory: int = 0
    practice: int = 0


class EvidenceItem(BaseModel):
    type: str
    passed: bool
    message: str = ""


class EvaluationReport(BaseModel):
    evaluation_id: str = ""
    practice_id: str = ""
    skill_id: str = ""
    overall_score: int = 0
    skill_scores: list[SkillScore] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    next_recommendations: list[str] = Field(default_factory=list)
    profile_updated: bool = False
    replanned: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())


def as_dict(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")