import { defineStore } from 'pinia'

import { streamChat, toChatPayload, STREAM_FLAG_KEY } from '@/api/chat'
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
 * 支持流式（SSE，走 /chat/stream）与非流式（/chat）两种，由 streamingEnabled 开关控制。
 */
export const useChatStore = defineStore('chat', {
  state: () => ({
    threads: [],
    currentThreadId: null,
    sending: false,
    streamingEnabled: localStorage.getItem(STREAM_FLAG_KEY) === '1',
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

    /** 流式开关持久化 */
    toggleStreaming() {
      this.streamingEnabled = !this.streamingEnabled
      localStorage.setItem(STREAM_FLAG_KEY, this.streamingEnabled ? '1' : '0')
    },

    /** 发送消息：本地追加 → 按开关走流式/非流式 → 更新结果 */
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
        if (this.streamingEnabled) {
          await this.streamMessage(thread, content)
        } else {
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
        }
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

    /**
     * 流式发送：占位空消息 → SSE 逐段追加 → done 补齐 trace / 状态。
     * SSE 异常时自动降级为非流式 /chat。
     */
    async streamMessage(thread, content) {
      const bubble = {
        id: nextMsgId(),
        role: 'assistant',
        content: '',
        status: 'streaming',
      }
      thread.messages.push(bubble)

      const done = new Promise((resolve) => {
        streamChat(
          toChatPayload({
            userId: thread.user_id,
            threadId: thread.thread_id,
            message: content,
          }),
          {
            onEvent: (evt) => {
              if (evt.type === 'meta') {
                bubble.route = evt.route
                bubble.intent = evt.intent
              } else if (evt.type === 'delta') {
                bubble.content += evt.text || ''
              } else if (evt.type === 'done') {
                bubble.status = 'ok'
                bubble.reason = bubble.reason || ''
              }
            },
            onError: (err) => {
              // 流式失效 → 降级非流式
              this._fallbackNonStream(thread, content, bubble, err)
              resolve()
            },
          },
        ).then(resolve)
      })
      await done
      if (bubble.status === 'streaming') {
        bubble.status = 'error'
        bubble.error = '回复未完整返回，请重试'
      }
    },

    /** 流式失败且未产出内容时，降级到非流式补齐回复 */
    async _fallbackNonStream(thread, content, bubble, err) {
      if (bubble.content || this.sending) {
        // 已有部分流式内容 → 保留，标注降级
        bubble.status = bubble.content ? 'ok' : 'error'
        if (!bubble.content) bubble.error = toUserFacingMessage(err)
        return
      }
      try {
        const result = await sendUserMessage({
          userId: thread.user_id,
          threadId: thread.thread_id,
          message: content,
        })
        bubble.content = result.reply
        bubble.route = result.route
        bubble.reason = result.reason
        bubble.steps = result.steps
        bubble.status = 'ok'
      } catch (err2) {
        bubble.status = 'error'
        bubble.error = toUserFacingMessage(err2)
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