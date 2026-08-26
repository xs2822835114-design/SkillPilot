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