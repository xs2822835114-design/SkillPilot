/**
 * ID 生成工具。
 * 约束对齐后端契约：`^[A-Za-z0-9_-]{1,64}$`（字母/数字/下划线/连字符）。
 */

/** 生成 thread_id，形如 T<时间戳毫秒>-<4位随机> */
export function generateThreadId() {
  return `T${Date.now()}-${randomBase36(4)}`
}

/** 生成 user_id，形如 U<时间戳毫秒> */
export function generateUserId() {
  return `U${Date.now()}`
}

/** 生成 base36 随机串（不含歧义数字） */
export function randomBase36(length) {
  const chars = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
  let out = ''
  for (let i = 0; i < length; i += 1) {
    out += chars[Math.floor(Math.random() * chars.length)]
  }
  return out
}

/** 从输入的首次消息截取会话标题 */
export function titleFromMessage(message) {
  const text = (message || '').replace(/\s+/g, ' ').trim()
  return text.length > 18 ? `${text.slice(0, 18)}…` : text || '新对话'
}