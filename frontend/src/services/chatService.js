import { sendChatMessage, toChatPayload } from '@/api/chat'

/**
 * 服务层 · 对话。
 * 负责：参数组装 → 调 API → 结果归一化 → 错误映射（供 UI 使用）。
 * 不持有任何会话状态（会话状态由 store 管理）。
 */

/**
 * 发送一条消息。
 * @param {Object} opts
 * @param {string} opts.userId
 * @param {string} opts.threadId
 * @param {string} opts.message
 * @param {string|null} [opts.intentHint]
 * @returns {Promise<ChatResultVO>}
 */
export async function sendUserMessage({ userId, threadId, message, intentHint = null }) {
  const payload = toChatPayload({ userId, threadId, message, intentHint })
  const data = await sendChatMessage(payload)
  return normalizeReply(data)
}

/** 后端 ChatResult → 前端视图模型 */
export function normalizeReply(raw) {
  return {
    route: raw.route ?? 'chat',
    steps: Array.isArray(raw.steps) ? raw.steps : [],
    reason: raw.reason ?? '',
    reply: raw.reply ?? '',
    workflowStatus: raw.workflow_status ?? 'done',
    artifacts: raw.artifacts ?? {},
    evidence: Array.isArray(raw.evidence) ? raw.evidence : [],
  }
}

/** 统一把 ApiError 映射为面向用户的消息文本 */
export function toUserFacingMessage(err) {
  if (err && err.code !== undefined) {
    // 业务/系统错误码 → 直出后端 message（含 trace_id 便于排查）
    return err.message || '请求失败'
  }
  return err?.message || '发生未知错误'
}