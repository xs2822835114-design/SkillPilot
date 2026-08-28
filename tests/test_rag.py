"""RAG 集成测试（对应计划书 8.2：TC-R1~TC-R10）。

基于真实 PostgreSQL + pgvector；本机/测试库不可用或无 vector 扩展时自动跳过。
统一使用 embedding_provider=off（确定性兜底向量），不依赖外部 Embedding API，
确保离线可测且结果确定。
"""
from __future__ import annotations

import os
import uuid

import pytest

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "postgresql://localhost:5432/skillmap_test")


def _ensure_database() -> None:
    import psycopg

    scheme, rest = TEST_DATABASE_URL.split("://", 1)
    host_part = rest.rsplit("/", 1)[0]
    dbname = rest.rsplit("/", 1)[-1]
    admin_dsn = f"{scheme}://{host_part}/postgres"

    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{dbname}"')

    from scripts.init_db import create_tables, create_rag_tables

    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        create_tables(conn)
        create_rag_tables(conn)


@pytest.fixture(scope="module")
def pg_ready():
    try:
        _ensure_database()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL 或 pgvector 不可用，跳过 RAG 集成测试: {exc}")
    return TEST_DATABASE_URL


def _make_app(database_url: str):
    from app import create_app
    from app.config import Config

    cfg = Config(
        env="test",
        database_url=database_url,
        llm_api_key="",          # 关闭 LLM，问答走规则兜底，保证确定性
        checkpointer_backend="memory",
        embedding_provider="off",  # 确定性兜底向量，离线可测
    )
    flask_app = create_app(cfg)
    flask_app.config["TESTING"] = True
    return flask_app


def _doc_count(database_url, doc_id: str) -> int:
    import psycopg

    with psycopg.connect(database_url, autocommit=True) as conn:
        return conn.execute(
            "SELECT count(*) FROM rag_chunks WHERE doc_id = %s", (doc_id,)
        ).fetchone()[0]


# ---------------- TC-R1：空库检索 ----------------
def test_tc_r1_empty_results(pg_ready):
    client = _make_app(pg_ready).test_client()
    # 用不存在的 doc_id 过滤，模拟"未命中任何资料"
    r = client.post(
        "/api/v1/rag/search",
        json={"query": "任意问题", "top_k": 5, "filter": {"doc_id": "DOC_NONEXIST"}},
    )
    assert r.status_code == 200
    assert r.get_json()["data"]["results"] == []


# ---------------- TC-R2：单文档入库 ----------------
def test_tc_r2_ingest(pg_ready):
    client = _make_app(pg_ready).test_client()
    r = client.post(
        "/api/v1/rag/ingest",
        json={
            "source_type": "text",
            "source": f"tc_r2://{uuid.uuid4().hex}.txt",
            "title": "TC-R2 文档",
            "content": "检索增强生成 RAG 结合检索与生成，广泛用于知识库问答。" * 20,
            "category": "ai",
        },
    )
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["status"] == "ok"
    assert data["doc_id"].startswith("DOC_")
    assert data["num_chunks"] > 0


# ---------------- TC-R3：重复入库幂等 ----------------
def test_tc_r3_idempotent_ingest(pg_ready):
    client = _make_app(pg_ready).test_client()
    source = f"tc_r3://{uuid.uuid4().hex}.txt"
    body = {
        "source_type": "text",
        "source": source,
        "title": "TC-R3 文档",
        "content": "相同的 source 重复入库应为替换式，不产生重复 chunk。" * 20,
        "category": "ai",
    }
    r1 = client.post("/api/v1/rag/ingest", json=body)
    d1 = r1.get_json()["data"]
    r2 = client.post("/api/v1/rag/ingest", json=body)
    d2 = r2.get_json()["data"]
    assert r1.status_code == 200 and r2.status_code == 200
    assert d1["doc_id"] == d2["doc_id"]  # 复用同一 doc_id
    # 第二次后 chunk 数与单次入库一致（未翻倍）
    assert _doc_count(pg_ready, d1["doc_id"]) == d1["num_chunks"]


# ---------------- TC-R4：Top-K 检索 ----------------
def test_tc_r4_topk_search(pg_ready):
    client = _make_app(pg_ready).test_client()
    client.post(
        "/api/v1/rag/ingest",
        json={
            "source_type": "text",
            "source": f"tc_r4://{uuid.uuid4().hex}.txt",
            "title": "TC-R4 文档",
            "content": "向量检索与 Top-K 相似度检索是 RAG 的核心步骤。" * 20,
            "category": "ai",
        },
    )
    r = client.post("/api/v1/rag/search", json={"query": "向量检索 Top-K", "top_k": 3})
    assert r.status_code == 200
    results = r.get_json()["data"]["results"]
    assert len(results) <= 3
    item = results[0]
    for key in ("chunk_id", "doc_id", "source", "title", "score"):
        assert key in item


# ---------------- TC-R5：过滤生效 ----------------
def test_tc_r5_filter_category(pg_ready):
    client = _make_app(pg_ready).test_client()
    client.post(
        "/api/v1/rag/ingest",
        json={
            "source_type": "text",
            "source": f"tc_r5://{uuid.uuid4().hex}.txt",
            "title": "TC-R5 AI 文档",
            "content": "人工智能智能体技术资料。" * 30,
            "category": "ai",
        },
    )
    client.post(
        "/api/v1/rag/ingest",
        json={
            "source_type": "text",
            "source": f"tc_r5b://{uuid.uuid4().hex}.txt",
            "title": "TC-R5 前端文档",
            "content": "人工智能智能体技术资料。" * 30,
            "category": "frontend",
        },
    )
    r = client.post(
        "/api/v1/rag/search",
        json={"query": "人工智能", "top_k": 20, "filter": {"category": "ai"}},
    )
    results = r.get_json()["data"]["results"]
    assert len(results) > 0
    assert {it["category"] for it in results} == {"ai"}


# ---------------- TC-R6：问答带证据 ----------------
def test_tc_r6_query_with_evidence(pg_ready):
    client = _make_app(pg_ready).test_client()
    client.post(
        "/api/v1/rag/ingest",
        json={
            "source_type": "text",
            "source": f"tc_r6://{uuid.uuid4().hex}.txt",
            "title": "TC-R6 文档",
            "content": "RAG 选取相关资料，问答链生成带来源的答案。" * 20,
            "category": "ai",
        },
    )
    r = client.post("/api/v1/rag/query", json={"query": "RAG 问答链", "top_k": 3})
    assert r.status_code == 200
    d = r.get_json()["data"]
    assert isinstance(d["answer"], str) and d["answer"]
    assert d["top_k_used"] > 0
    ev = d["evidence"][0]
    for key in ("chunk_id", "doc_id", "title", "source", "content"):
        assert key in ev


# ---------------- TC-R7：非法入参 ----------------
def test_tc_r7_bad_input(pg_ready):
    client = _make_app(pg_ready).test_client()
    r = client.post("/api/v1/rag/search", json={"query": "  ", "top_k": 5})
    assert r.status_code == 422
    body = r.get_json()
    assert body["code"] == 42200
    assert body["trace_id"]


# ---------------- TC-R8：坏 JSON ----------------
def test_tc_r8_bad_json(pg_ready):
    client = _make_app(pg_ready).test_client()
    r = client.post(
        "/api/v1/rag/search",
        data="{not valid json",
        content_type="application/json",
    )
    assert r.status_code == 400
    assert r.get_json()["code"] == 40001


# ---------------- TC-R9：Embedding 兜底 ----------------
def test_tc_r9_embedding_fallback_structure(pg_ready):
    # 全模块均以 embedding_provider=off 构造，故这里的断言即代表"无真实 API
    # 时仍返回标准结构"（search 有 results、query 有 answer+evidence）。
    client = _make_app(pg_ready).test_client()
    client.post(
        "/api/v1/rag/ingest",
        json={
            "source_type": "text",
            "source": f"tc_r9://{uuid.uuid4().hex}.txt",
            "title": "TC-R9 文档",
            "content": "Embedding 不可用时仍应返回标准结构，不报 5xx。" * 20,
            "category": "ai",
        },
    )
    assert client.post("/api/v1/rag/search", json={"query": "Embedding 兜底"}).status_code == 200
    q = client.post("/api/v1/rag/query", json={"query": "Embedding 兜底"}).get_json()["data"]
    assert q["answer"]
    assert isinstance(q["evidence"], list)


# ---------------- TC-R10：文档隔离 ----------------
def test_tc_r10_doc_isolation(pg_ready):
    client = _make_app(pg_ready).test_client()
    doc_id = client.post(
        "/api/v1/rag/ingest",
        json={
            "source_type": "text",
            "source": f"tc_r10://{uuid.uuid4().hex}.txt",
            "title": "TC-R10 文档",
            "content": "隔离测试文档内容。" * 40,
            "category": "ai",
        },
    ).get_json()["data"]["doc_id"]
    r = client.post(
        "/api/v1/rag/search",
        json={"query": "隔离测试", "top_k": 10, "filter": {"doc_id": doc_id}},
    )
    results = r.get_json()["data"]["results"]
    assert len(results) > 0
    assert all(it["doc_id"] == doc_id for it in results)


# ---------------- TC-R7 补充：top_k 越界 ----------------
def test_tc_r7_topk_out_of_range(pg_ready):
    client = _make_app(pg_ready).test_client()
    r = client.post("/api/v1/rag/search", json={"query": "技术", "top_k": 99})
    assert r.status_code == 422
    assert r.get_json()["code"] == 42200