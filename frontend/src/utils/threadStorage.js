/**
 * 会话/线程记录本地持久化。
 *
 * 阶段 1 后端不提供「线程列表」接口，故由前端在浏览器本地维护线程目录与消息历史；
 * 真正的上下文恢复契约在后端（同一 thread_id 的后端会话 Checkpoint）。
 * 后续后端提供列表接口时，仅替换本模块实现，不改上层调用。
 */
const STORAGE_KEY = 'skillmap.threads.v1'

/** 读取本地线程记录（按最近使用排序） */
export function loadThreads() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const list = raw ? JSON.parse(raw) : []
    return Array.isArray(list) ? list : []
  } catch (e) {
    return []
  }
}

/**
 * 线程结构：
 * { thread_id, user_id, title, created_at, updated_at, messages: Message[] }
 * Message: { id, role: 'user'|'assistant', content, route?, reason?, steps?, status, error? }
 */
export function saveThread(thread) {
  const list = loadThreads()
  const idx = list.findIndex((t) => t.thread_id === thread.thread_id)
  if (idx >= 0) list[idx] = thread
  else list.unshift(thread)
  persist(list)
}

export function removeThread(threadId) {
  const list = loadThreads().filter((t) => t.thread_id !== threadId)
  persist(list)
}

export function clearThreads() {
  persist([])
}

function persist(list) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list))
  } catch (e) {
    // 存储不可用（隐私模式/超限）时静默失败，不影响会话
  }
}

/** 全局用户当前用户态（开发态默认用户，阶段 1 无鉴权） */
export function getDevUserId() {
  return import.meta.env.VITE_DEFAULT_USER_ID || 'U10001'
}