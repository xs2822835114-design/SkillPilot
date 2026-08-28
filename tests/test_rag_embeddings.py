"""RAG Embedding 兜底向量单元测试（不依赖数据库/外部 API）。

验证确定性哈希向量：维度正确、同文本稳定、可区分不同文本，且对中文文档与
查询的相似度能反映语义重叠（保证无 API/离线时检索依然有意义）。
"""
from __future__ import annotations

from app.config import Config
from app.rag.embeddings import EmbeddingClient


def _client() -> EmbeddingClient:
    cfg = Config(env="test", embedding_provider="off", embedding_dim=1024)
    return EmbeddingClient(cfg)


def test_hash_embedding_dim():
    vecs = _client().embed(["你好", "世界"])
    assert len(vecs) == 2
    assert all(len(v) == 1024 for v in vecs)


def test_hash_same_text_stable():
    c = _client()
    assert c.embed(["技术知识库"])[0] == c.embed(["技术知识库"])[0]


def test_different_texts_diff_vectors():
    c = _client()
    a = c.embed(["SkillMap 是能力规划智能体"])[0]
    b = c.embed(["今天天气很好适合出游"])[0]
    assert a != b


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot  # 兜底向量已归一化


def test_chinese_semantic_overlap_ranks_higher():
    """与查询共享更多字/字组的文档，相似度应高于无关文档。"""
    c = _client()
    doc = "SkillMap 帮助工程师规划学习路径并沉淀技术资料"
    unrelated = "常山赵子龙单骑救主七进七出"
    qv = c.embed(["SkillMap 如何规划学习路径"])[0]
    dv = c.embed([doc])[0]
    uv = c.embed([unrelated])[0]
    assert _cosine(qv, dv) > _cosine(qv, uv)