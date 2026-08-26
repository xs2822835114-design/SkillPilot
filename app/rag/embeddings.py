"""Embedding 客户端抽象：Qwen/DashScope 兼容端点 + 确定性兜底。

- provider=openai（且配置了 key）：调 OpenAI 兼容 embeddings 接口；
- 否则（off / 未配置）：返回确定性哈希向量，保证检索链路在无 key/离线时仍返回标准结构。
"""
from __future__ import annotations

import hashlib
import logging

import requests

from app.api.errors import CODE_EMBEDDING
from app.config import Config
from app.rag.schemas import RagError

logger = logging.getLogger(__name__)


class EmbeddingClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._http = requests.Session()
        self._http.trust_env = False  # 跳过系统代理，避免失效代理导致长时间重试

    def embed(self, texts: list[str]) -> list[list[float]]:
        """把一批文本向量化。失败或未配置时走确定性兜底。"""
        if self.config.embedding_enabled:
            try:
                return self._embed_api(texts)
            except RagError:
                raise
            except Exception as exc:  # noqa: BLE001 - 网络/解析异常统一映射
                logger.warning("Embedding API 调用失败，使用确定性兜底向量", exc_info=True)
                return [self._hash_embedding(t) for t in texts]
        return [self._hash_embedding(t) for t in texts]

    _BATCH = 16  # DashScope 等端点对单次 batch 有上限，分批请求避免 400

    def _embed_api(self, texts: list[str]) -> list[list[float]]:
        url = self.config.embedding_base_url.rstrip("/") + "/embeddings"
        out: list[list[float]] = []
        for start in range(0, len(texts), self._BATCH):
            batch = texts[start : start + self._BATCH]
            resp = self._http.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.config.embedding_api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self.config.embedding_model, "input": batch},
                timeout=15,
            )
            if resp.status_code != 200:
                raise RagError(CODE_EMBEDDING, f"Embedding 服务返回 {resp.status_code}")
            data = resp.json().get("data", [])
            if not data:
                raise RagError(CODE_EMBEDDING, "Embedding 响应为空")
            out.extend(item["embedding"] for item in data)
        return out

    def _hash_embedding(self, text: str, dim: int | None = None) -> list[float]:
        """确定性哈希向量（测试/离线兜底）。

        对中文以字符为粒度，拉丁以词为粒度，并叠加相邻二元组，使同义短文本稳定、
        不同文本可区分，保证在无 API/离线时检索依然有意义。
        """
        dim = dim or self.config.embedding_dim
        vec = [0.0] * dim
        tokens = self._tokens(text)
        if not tokens:
            return vec
        for tok in tokens:
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            vec[h % dim] += 1.0
        norm = sum(x * x for x in vec) ** 0.5
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    @staticmethod
    def _tokens(text: str) -> list[str]:
        cjk = lambda ch: "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf"
        # 中文/日文假名等：按字符拆，并补相邻二元组
        if any(cjk(ch) for ch in text):
            chars = [ch for ch in text if ch.strip() or cjk(ch)]
            return chars + [c1 + c2 for c1, c2 in zip(chars, chars[1:])]
        return text.lower().split()