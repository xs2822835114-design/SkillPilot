/**
 * API 层 · AI 技术教学（阶段 5 三级结构第三级）。
 */
import http from './http'

/**
 * POST /api/v1/plan/<id>/tasks/<task>/teach → 启动教学，返回结构化 TeachingSession。
 */
export function startTeach(planId, taskId) {
  return http.post(
    `/api/v1/plan/${encodeURIComponent(planId)}/tasks/${encodeURIComponent(taskId)}/teach`,
    { mode: 'start' },
  )
}

/**
 * POST /api/v1/plan/<id>/tasks/<task>/teach/stream —— SSE 流式首节教学。
 * 事件：meta → delta*（opening 文本）→ done（携带完整 TeachingSession）。
 */
export async function streamTeach(planId, taskId, { onEvent, onError, signal } = {}) {
  const base = import.meta.env.VITE_API_STREAM_URL || import.meta.env.VITE_API_BASE_URL || ''
  try {
    const resp = await fetch(
      `${base}/api/v1/plan/${encodeURIComponent(planId)}/tasks/${encodeURIComponent(taskId)}/teach/stream`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'start' }),
        signal,
      },
    )
    if (!resp.ok || !resp.body) throw new Error(`流式接口异常（${resp.status}）`)
    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let idx
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const raw = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        for (const line of raw.split('\n')) {
          if (!line.startsWith('data:')) continue
          const json = line.slice(5).trim()
          if (!json) continue
          let evt
          try {
            evt = JSON.parse(json)
          } catch {
            continue
          }
          if (evt && evt.type) onEvent?.(evt)
        }
      }
    }
  } catch (err) {
    onError?.(err)
  }
}

/**
 * POST /api/v1/teaching/<session_id>/message → 多轮互动。
 * @param {{sessionId:string, message:string}} payload
 * @returns {Promise<{role:string, message:string, mode:string}>}
 */
export function sendTeachingMessage({ sessionId, message }) {
  return http.post(
    `/api/v1/teaching/${encodeURIComponent(sessionId)}/message`,
    { message },
  )
}