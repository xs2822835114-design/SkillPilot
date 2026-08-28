"""RAG 问答链：检索 → 组 prompt → LLM → 答案 + evidence（容错）。"""
from __future__ import annotations

import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.config import Config
from app.rag import retriever
from app.rag.schemas import RagFilter, RagQueryResponse

logger = logging.getLogger(__name__)


def _get_llm(config: Config):
    if not config.llm_enabled:
        return None
    try:
        return ChatOpenAI(
            model=config.llm_model,
            base_url=config.llm_base_url,
            api_key=config.llm_api_key,
            temperature=0,
        )
    except Exception:  # noqa: BLE001
        return None


def answer(
    config: Config,
    query: str,
    top_k: int,
    rag_filter: RagFilter | None = None,
) -> RagQueryResponse:
    evidence = retriever.retrieve(config, query, top_k, rag_filter)

    if not evidence:
        return RagQueryResponse(
            answer="未检索到相关资料，暂时无法基于知识库回答。",
            evidence=[],
            qa_model=config.llm_model,
            top_k_used=0,
        )

    llm = _get_llm(config)
    try:
        if llm:
            context = "\n\n".join(
                f"[{i + 1}] {e.content}\n来源: {e.source or e.title or e.doc_id}"
                for i, e in enumerate(evidence)
            )
            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        "你是 SkillMap 的技术问答助手。只能依据给定的资料回答，不要编造。"
                        "回答末尾用 [1][2]… 引用对应资料编号。",
                    ),
                    ("human", "资料:\n{context}\n\n问题: {query}"),
                ]
            )
            chain = prompt | llm
            resp = chain.invoke({"context": context, "query": query})
            answer_text = resp.content if hasattr(resp, "content") else str(resp)
        else:
            answer_text = _fallback_answer(query, evidence)
    except Exception:  # noqa: BLE001
        logger.warning("RAG 问答 LLM 失败，使用规则兜底答案", exc_info=True)
        answer_text = _fallback_answer(query, evidence)

    return RagQueryResponse(
        answer=answer_text,
        evidence=evidence,
        qa_model=config.llm_model if llm else None,
        top_k_used=len(evidence),
    )


def _fallback_answer(query: str, evidence) -> str:
    top = evidence[0]
    return (
        f"未启用 LLM 或调用失败，以下基于检索结果提供规则回复。\n"
        f"关于「{query}」，可参考资料：{top.source or top.title or top.doc_id}。"
    )