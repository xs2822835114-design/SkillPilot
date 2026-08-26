"""统一错误处理：业务错误码、异常 → HTTP 映射、统一错误响应。"""
from __future__ import annotations

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from app.middleware.trace import get_trace_id

# ---- 业务错误码（阶段 1 启用子集，结构从第一天固定） ----
CODE_OK = 0
CODE_BAD_REQUEST = 40000
CODE_JSON_INVALID = 40001
CODE_NOT_FOUND = 40400
CODE_VALIDATION = 42200
CODE_INTERNAL = 50000
CODE_LLM_FAILED = 50001
CODE_DB_INIT_FAILED = 50005


class APIError(Exception):
    """业务异常：携带业务码与 HTTP 状态码。"""

    def __init__(self, code: int, message: str, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def ok_response(data) -> tuple:
    """统一成功响应：{"code":0,"message":"ok","data":...}"""
    return jsonify({"code": CODE_OK, "message": "ok", "data": data}), 200


def error_response(code: int, message: str, http_status: int) -> tuple:
    """统一错误响应：{"code":非0,"message":"...","data":null,"trace_id":"..."}"""
    payload = {
        "code": code,
        "message": message,
        "data": None,
        "trace_id": get_trace_id(),
    }
    return jsonify(payload), http_status


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(APIError)
    def handle_api_error(e: APIError):
        return error_response(e.code, e.message, e.http_status)

    @app.errorhandler(404)
    def handle_404(_):
        return error_response(CODE_NOT_FOUND, "资源不存在", 404)

    @app.errorhandler(HTTPException)
    def handle_http_exception(e: HTTPException):
        # 其余 HTTP 异常（405/415 等）统一返回标准 JSON 结构
        return error_response(CODE_BAD_REQUEST, e.description or e.name, e.code or 400)

    @app.errorhandler(Exception)
    def handle_exception(e: Exception):
        # 兜底：记录完整堆栈，但对外不泄露内部细节
        app.logger.exception("Unhandled error")
        return error_response(CODE_INTERNAL, "服务器内部错误", 500)
