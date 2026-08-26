/**
 * API 层 · 对话/编排接口模块。
 * 仅做入参序列化与请求，业务编排（会话状态等）在 services 层完成。
 */
import http from './http'

/**
 * 构造 POST /api/v1/chat 请求体（snake_case，对齐后端 UserRequest 契约）。
 * @typedef {Object} ChatRequest
 * @property {string} userId
 * @property {string} threadId
 * @property {string|null} [intentHint]
 * @property {string} message
 * @property {Array} [attachments]
 */
export function toChatPayload({ userId, threadId, intentHint = null, message, attachments = [] }) {
  return {
    user_id: userId,
    thread_id: threadId,
    intent_hint: intentHint ?? null,
    message,
    attachments,
  }
}

/**
 * POST /api/v1/chat
 * @returns {Promise<{
 *   route:string, steps:string[], reason:string, reply:string,
 *   workflow_status:string, artifacts:Object, evidence:Array
 * }>}
 */
export function sendChatMessage(payload) {
  return http.post('/api/v1/chat', payload)
}

/**
 * POST /api/v1/chat/stream —— SSE 流式回复。
 *
 * 用 fetch + ReadableStream 消费 `text/event-stream`，逐事件回调：
 *   ctx.onEvent({ type: 'meta', intent, route, thread_id })
 *   ctx.onEvent({ type: 'delta', text })
 *   ctx.onEvent({ type: 'done', thread_id })
 * 出错时（含 SSE 失效）通过 ctx.onError 降级，由调用方决定回退非流式。
 *
 * @param {Object} payload      与 /chat 相同的请求体
 * @param {Object} [ctx]
 * @param {(e:Object):void} [ctx.onEvent]
 * @param {(err:Error):void} [ctx.onError]
 * @param {AbortSignal} [ctx.signal]
 */
export async function streamChat(payload, { onEvent, onError, signal } = {}) {
  // SSE 流式走同源相对路径，由 vite 开发代理(/api)转发到后端 8081（代理已关闭压缩，SSE chunked 流可安全透传）；
  // 也可用 VITE_API_STREAM_URL / VITE_API_BASE_URL 显式覆盖。
  const base = import.meta.env.VITE_API_STREAM_URL || import.meta.env.VITE_API_BASE_URL || ''
  try {
    const resp = await fetch(`${base}/api/v1/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    })
    if (!resp.ok || !resp.body) {
      throw new Error(`流式接口异常（${resp.status}）`)
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let idx
      // 按空行切分 SSE 事件
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