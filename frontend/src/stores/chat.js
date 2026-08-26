import { defineStore } from 'pinia'

import { sendUserMessage, toUserFacingMessage } from '@/services/chatService'
import {
  getDevUserId,
  loadThreads,
  removeThread,
  saveThread,
} from '@/utils/threadStorage'
import { generateThreadId, titleFromMessage } from '@/utils/id'

let msgSeq = 0

function nextMsgId() {
  msgSeq += 1
  return `m${Date.now()}-${msgSeq}`
}

/**
 * 聊天 Store：管理会话线程目录 + 当前线程 + 发送流程。
 * 数据来源两层：
 *  - 后端：消息真实处理结果（经 chatService）；
 *  - 本地：线程目录与消息历史（threadStorage，阶段 1 后端无列表接口）。
 */
export const useChatStore = defineStore('chat', {
  state: () => ({
    threads: [],
    currentThreadId: null,
    sending: false,
  }),

  getters: {
    currentThread(state) {
      return state.threads.find((t) => t.thread_id === state.currentThreadId) || null
    },
    messages(state) {
      return state.currentThread?.messages || []
    },
  },

  actions: {
    /** 启动加载：恢复本地线程并指向最近一个 */
    init() {
      this.threads = loadThreads()
      if (!this.currentThreadId && this.threads.length) {
        this.currentThreadId = this.threads[0].thread_id
      }
      if (!this.currentThread) {
        this.createThread()
      }
    },

    /** 新建会话 */
    createThread() {
      const thread = {
        thread_id: generateThreadId(),
        user_id: getDevUserId(),
        title: '新对话',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        messages: [],
      }
      this.threads.unshift(thread)
      this.currentThreadId = thread.thread_id
      saveThread(thread)
    },

    selectThread(threadId) {
      if (threadId !== this.currentThreadId) {
        this.currentThreadId = threadId
      }
    },

    removeThread(threadId) {
      removeThread(threadId)
      this.threads = loadThreads()
      if (this.currentThreadId === threadId) {
        this.currentThreadId = this.threads[0]?.thread_id || null
        if (!this.currentThread) this.createThread()
      }
    },

    /** 发送消息：本地追加 → 调服务 → 更新结果 */
    async sendMessage(text) {
      const content = (text || '').trim()
      if (!content || this.sending) return
      const thread = this.currentThread
      if (!thread) return

      // 首次消息自动命名会话
      if (thread.messages.length === 0) {
        thread.title = titleFromMessage(content)
      }

      thread.messages.push({ id: nextMsgId(), role: 'user', content, status: 'ok' })
      this._touch(thread)

      this.sending = true
      try {
        const result = await sendUserMessage({
          userId: thread.user_id,
          threadId: thread.thread_id,
          message: content,
        })
        thread.messages.push({
          id: nextMsgId(),
          role: 'assistant',
          content: result.reply,
          route: result.route,
          reason: result.reason,
          steps: result.steps,
          status: 'ok',
        })
      } catch (err) {
        thread.messages.push({
          id: nextMsgId(),
          role: 'assistant',
          content: '',
          status: 'error',
          error: toUserFacingMessage(err),
        })
      } finally {
        this.sending = false
        this._touch(thread)
      }
    },

    _touch(thread) {
      thread.updated_at = new Date().toISOString()
      // 保持最近使用的线程置顶
      const idx = this.threads.findIndex((t) => t.thread_id === thread.thread_id)
      if (idx > 0) {
        this.threads.splice(idx, 1)
        this.threads.unshift(thread)
      }
      saveThread(thread)
    },
  },
})