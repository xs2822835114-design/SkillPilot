"""Splitter：把长文本切成带顺序号的 chunk（RecursiveCharacterTextSplitter）。"""
from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import Config


def split(
    config: Config,
    text: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size or config.rag_chunk_size,
        chunk_overlap=chunk_overlap or config.rag_chunk_overlap,
    )
    return splitter.split_text(text)


def estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))