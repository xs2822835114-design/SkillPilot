"""评估编排（阶段 6，evaluation/service）：artifact → EvaluationReport（含回写+再规划）。

流程：取实践→收集代码→静态分析→规则评分→（可选 LLM 润色建议）→回写画像 → 触发再
规划→落库。业务异常抛 ValueError，由调用方映射 HTTP。
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from app.config import Config
from app.evaluation import analyzers, scorer, store, update
from app.evaluation.schemas import ArtifactUploadRequest, EvaluationReport, EvaluationRequest
from app.practice import store as practice_store

logger = logging.getLogger(__name__)


def run_evaluation(config: Config, request: EvaluationRequest) -> EvaluationReport:
    practice = practice_store.load_practice(config, request.practice_id)
    if practice is None:
        raise ValueError("实践任务不存在")
    if not practice.skill_id:
        raise ValueError("实践任务缺少 skill_id，无法评估")

    files = _gather_files(config, request)
    checks = analyzers.analyze(files, strict=config.eval_static_strict)
    theory, p_score, overall, recs = scorer.score(config, practice.skill_id, checks)

    polished = scorer.llm_polish_recommendations(recs, config)
    report = EvaluationReport(
        evaluation_id=_new_id(),
        practice_id=request.practice_id,
        skill_id=practice.skill_id,
        overall_score=overall,
        skill_scores=scorer.build_skill_scores(practice.skill_id, theory, p_score),
        evidence=scorer.build_evidence(checks, config.eval_static_strict),
        next_recommendations=polished or recs,
    )

    report = update.apply_report(config, report, request)
    store.save_evaluation(
        config, report, request.user_id, request.artifact_type, request.artifact_ref
    )
    return report


def ingest_snippet(config: Config, req: ArtifactUploadRequest) -> dict[str, Any]:
    """录入代码片段；返回片段中文档文件名。"""
    store.create_snippet(config, req, f"SNP_{uuid.uuid4().hex[:12]}")
    if req.test_content:
        store.create_snippet(config, req.model_copy(update={"content": req.test_content, "filename": "test_" + req.filename}), f"SNP_{uuid.uuid4().hex[:12]}")
    return {"status": "ok", "filename": req.filename}


def _gather_files(config: Config, request: EvaluationRequest) -> dict[str, str]:
    if request.repo_files:
        return request.repo_files
    if request.artifact_type == "snippet":
        files = store.load_snippets_for_practice(config, request.practice_id)
        if files:
            return files
        # 无已上传片段且未内联：返回空，由 analyzer 给出 empty
        return {}
    if request.artifact_type == "github" and request.artifact_ref:
        return _fetch_github(request.artifact_ref)
    return {}


def _fetch_github(repo_url: str) -> dict[str, str]:
    """best-effort 拉取 github 仓库主要 .py 文件（raw），失败返回空 dict。"""
    import urllib.request

    files: dict[str, str] = {}
    base = repo_url.replace("https://github.com/", "").replace("/tree/", "/").rstrip("/")
    if "/" not in base:
        return files
    owner_repo, _, path = base.partition("/")
    # 解析 owner/repo，尝试读取根目录常见入口
    for fname in ("main.py", "app.py", "skill.py"):
        raw = f"https://raw.githubusercontent.com/{owner_repo}/main/{path}/{fname}".replace("//", "/")
        try:
            with urllib.request.urlopen(raw, timeout=5) as resp:
                if resp.status == 200:
                    files[fname] = resp.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            continue
    return files


def _new_id() -> str:
    return f"EVL_{uuid.uuid4().hex[:12]}"