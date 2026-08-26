/**
 * API 层基础：axios 实例 + 统一响应/错误解包。
 *
 * 职责边界：
 *  - 只关心「如何发出 HTTP 请求」与「统一信封 {code,message,data,trace_id} 的解壳」；
 *  - 不包含任何业务逻辑，业务判断一律下沉到 services 层。
 *
 * 约定（对齐 docs/api_v1.md）：
 *  - 成功：code === 0，直接返回 data；
 *  - 失败：code !== 0，抛出 ApiError（携带 code/message/trace_id）。
 */
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

/** 业务/系统异常（含后端统一错误信封） */
export class ApiError extends Error {
  constructor({ code, message, traceId, httpStatus, cause }) {
    super(message || '请求失败')
    this.name = 'ApiError'
    this.code = code ?? -1
    this.traceId = traceId ?? null
    this.httpStatus = httpStatus ?? null
    this.cause = cause ?? null
  }
}

const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
  headers: { 'Content-Type': 'application/json' },
})

// 请求拦截：可在此注入 trace_id / 鉴权头等（阶段 1 预留）
http.interceptors.request.use(
  (config) => {
    return config
  },
  (error) => Promise.reject(error),
)

// 响应拦截：统一解壳
http.interceptors.response.use(
  (response) => {
    const body = response.data
    // 非统一信封（如静态文件）原样返回
    if (body === null || typeof body !== 'object' || !('code' in body)) {
      return body
    }
    if (body.code !== 0) {
      throw new ApiError({
        code: body.code,
        message: body.message,
        traceId: body.trace_id,
        httpStatus: response.status,
      })
    }
    // 成功：只把 data 暴露给上层，屏蔽信封
    return body.data
  },
  (error) => {
    if (axios.isAxiosError(error)) {
      const res = error.response
      const body = res?.data
      // 后端返回统一错误信封 → 转成 ApiError
      if (body && typeof body === 'object' && 'code' in body) {
        throw new ApiError({
          code: body.code,
          message: body.message,
          traceId: body.trace_id,
          httpStatus: res.status,
          cause: error,
        })
      }
      // 网络层错误
      throw new ApiError({
        code: -2,
        message: error.code === 'ECONNABORTED' ? '请求超时' : '网络异常，请检查后端服务是否可用',
        httpStatus: res?.status ?? null,
        cause: error,
      })
    }
    throw error
  },
)

export default http