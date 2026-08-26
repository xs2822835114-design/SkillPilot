"""阶段 2 RAG 接口契约（对齐《SkillMap_阶段2_技术知识库与RAG_详细计划》第 5、6 节）。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

SourceType = Literal["url", "file", "text"]
EmbeddingProvider = Literal["openai", "off"]

MAX_DOC_TEXT = 100_000
MAX_QUERY_LEN = 8000


class RagFilter(BaseModel):
    """检索过滤条件（任一 null 即不过滤该维度）。"""

    category: str | None = None
    source_type: SourceType | None = None
    doc_id: str | None = None
    skill_tags: list[str] | None = None
    role_target: str | None = None


class RagIngestRequest(BaseModel):
    """POST /api/v1/rag/ingest 请求。"""

    source_type: SourceType = "text"
    source: str | None = Field(default=None, max_length=2048)  # url 或文件标识
    content: str | None = None  # source_type=text 时必填；url/file 时为空（由 loader 抓取）
    category: str | None = Field(default=None, max_length=64)
    title: str | None = Field(default=None, max_length=255)
    lang: str | None = Field(default=None, max_length=16)
    role_target: str | None = Field(default=None, max_length=64)
    skill_tags: list[str] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)  # 结构化附属元数据（source_id/type/priority/technology 等），落 doc.meta jsonb

    @field_validator("source_type")
    @classmethod
    def _strip_source_type(cls, v: str) -> str:
        return (v or "text").strip()

    @field_validator("content")
    @classmethod
    def _check_content(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
        return v

    @field_validator("skill_tags")
    @classmethod
    def _strip_tags(cls, v: list[str]) -> list[str]:
        return [t.strip() for t in v if t and t.strip()]


class RagIngestResponse(BaseModel):
    doc_id: str
    num_chunks: int
    status: Literal["ok"] = "ok"


class RagSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=MAX_QUERY_LEN)
    top_k: int = Field(default=5, ge=1, le=20)
    filter: RagFilter = Field(default_factory=RagFilter)

    @field_validator("query")
    @classmethod
    def _strip_query(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("query 不能为空")
        return v


class EvidenceItem(BaseModel):
    chunk_id: str
    doc_id: str
    title: str | None
    source: str | None
    url: str | None
    source_type: str | None
    category: str | None
    role_target: str | None
    content: str
    score: float | None = None
    content_preview: str | None = None


class RagSearchResponse(BaseModel):
    results: list[EvidenceItem] = Field(default_factory=list)


class RagQueryRequest(RagSearchRequest):
    """问答请求：复用检索入参，额外可指定 model。"""

    model: str | None = None


class RagQueryResponse(BaseModel):
    answer: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    qa_model: str | None = None
    top_k_used: int = 0


# ---- 错误（供 routes 映射）----
class RagError(RuntimeError):
    """RAG 业务异常：携带错误码与更具体的消息。"""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message