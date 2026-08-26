"""阶段 3 用户技术画像接口（HTTP 入出；业务在 app/profile 层）。

POST /api/v1/profile/extract   -- 自然语言抽取（返回待确认 patch）
POST /api/v1/profile/upsert    -- 增量合并画像
GET  /api/v1/profile/<user_id> -- 查询画像
POST /api/v1/profile/projects  -- 登记项目并关联技能
"""
from __future__ import annotations

from flask import Blueprint, current_app, request

from app.api.errors import (
    CODE_JSON_INVALID,
    CODE_PROFILE_EXTRACT,
    CODE_VALIDATION,
    APIError,
    ok_response,
)
from app.api.schemas import first_validation_error
from app.profile import extractor, skill_service, store
from app.profile.schemas import (
    ProfileExtractionRequest,
    ProjectCreateRequest,
    SkillProfilePatch,
)

profile_bp = Blueprint("profile", __name__)


def _config():
    return current_app.extensions["skillmap"]["config"]


def _ensure_db():
    cfg = _config()
    if not cfg.database_url:
        raise APIError(CODE_PROFILE_EXTRACT, "画像服务不可用：未配置 DATABASE_URL", 503)


def _validate(raw, model):
    try:
        return model.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        raise APIError(CODE_VALIDATION, first_validation_error(exc), 422)


@profile_bp.post("/api/v1/profile/extract")
def profile_extract():
    raw = request.get_json(silent=True)
    if raw is None:
        raise APIError(CODE_JSON_INVALID, "请求体必须为合法 JSON", 400)
    req = _validate(raw, ProfileExtractionRequest)
    _ensure_db()
    cfg = _config()
    skill_names = [row["name"] for row in store.load_skill_names(cfg)]
    result = extractor.extract(cfg, req, skill_names)
    result.patch.skills[:] = result.patch.skills[:cfg.profile_soft_cap_skills]
    return ok_response(result.model_dump())


@profile_bp.post("/api/v1/profile/upsert")
def profile_upsert():
    raw = request.get_json(silent=True)
    if raw is None:
        raise APIError(CODE_JSON_INVALID, "请求体必须为合法 JSON", 400)
    patch = _validate(raw, SkillProfilePatch)
    _ensure_db()
    profile = skill_service.apply_patch(_config(), patch)
    from app.memory.service import record_event_best_effort

    record_event_best_effort(
        _config(), patch.user_id, "profile_updated",
        summary=f"画像更新，共 {len(patch.skills)} 项技能",
        payload={"skill_ids": [s.skill_id for s in patch.skills]},
    )
    return ok_response(profile.model_dump())


@profile_bp.get("/api/v1/profile/<user_id>")
def profile_get(user_id: str):
    _ensure_db()
    from app.profile.store import load_profile

    profile = load_profile(_config(), user_id)
    return ok_response(profile.model_dump())


@profile_bp.post("/api/v1/profile/projects")
def profile_projects():
    raw = request.get_json(silent=True)
    if raw is None:
        raise APIError(CODE_JSON_INVALID, "请求体必须为合法 JSON", 400)
    req = _validate(raw, ProjectCreateRequest)
    _ensure_db()
    profile = skill_service.register_project(
        _config(), req.user_id, req.project_id, req.name, req.description, req.skills
    )
    return ok_response(profile.model_dump())