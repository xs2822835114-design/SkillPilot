import { defineStore } from 'pinia'

import { streamChat, toChatPayload } from '@/api/chat'
import { sendUserMessage, toUserFacingMessage } from '@/services/chatService'
import {
  clearThreads,
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
 * 统一走流式（SSE /chat/stream），保留非流式仅作降级兜底。
 */
export const useChatStore = defineStore('chat', {
  state: () => ({
    threads: [],
    currentThreadId: null,
    sending: false,
    // 当前流式请求的取消控制器（用于“停止生成”）
    activeCtrl: null,
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

    /** 全部清空本地对话缓存，并新开一个会话 */
    clearAll() {
      clearThreads()
      this.threads = []
      this.currentThreadId = null
      this.createThread()
    },

    removeThread(threadId) {
      removeThread(threadId)
      this.threads = loadThreads()
      if (this.currentThreadId === threadId) {
        this.currentThreadId = this.threads[0]?.thread_id || null
        if (!this.currentThread) this.createThread()
      }
    },

    /** 取消当前流式输出（“停止生成”） */
    stopGenerating() {
      console.debug('[skillmap][stopGen] called', new Error().stack)
      this.activeCtrl?.abort()
    },

    /** 发送消息：本地追加 → 流式接收 → 更新结果 */
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
        await this.streamMessage(thread, content)
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
     * 流式发送：占位流式消息 → SSE 逐段追加 → done 补齐 trace / 状态。
     * 支持“停止生成”（AbortController）；SSE 异常时自动降级为非流式 /chat。
     */
    async streamMessage(thread, content) {
      const bubble = {
        id: nextMsgId(),
        role: 'assistant',
        content: '',
        status: 'streaming',
      }
      thread.messages.push(bubble)
      // 关键：通过响应式代理引用更新气泡。push 后数组内元素会被 Vue 包成代理，
      // 若继续用原始 bubble 引用直接改字段会绕过 Proxy 的 set 陷阱，导致视图不刷新（气泡停在「…」）。
      const bubbleRef = thread.messages[thread.messages.length - 1]

      const ctrl = new AbortController()
      this.activeCtrl = ctrl

      const done = new Promise((resolve) => {
        streamChat(
          toChatPayload({
            userId: thread.user_id,
            threadId: thread.thread_id,
            message: content,
          }),
          {
            signal: ctrl.signal,
            onEvent: (evt) => {
              if (evt.type === 'meta') {
                bubbleRef.route = evt.route
                bubbleRef.intent = evt.intent
              } else if (evt.type === 'intent') {
                // 计算完成后的真实意图/路由
                bubbleRef.route = evt.route
                bubbleRef.intent = evt.intent
              } else if (evt.type === 'delta') {
                bubbleRef.content += evt.text || ''
              } else if (evt.type === 'done') {
                bubbleRef.status = 'ok'
                bubbleRef.reason = bubbleRef.reason || ''
                bubbleRef.artifacts = evt.artifacts || {}
              } else if (evt.type === 'error') {
                // 后端已明确报错：把真实错误暴露为气泡错误态，避免误报「回复未完整返回」
                bubbleRef.status = 'error'
                bubbleRef.error = evt.message || '流式输出异常，请重试'
              }
            },
            onError: (err) => {
              // 调试：把确切错误暴露到 window 供定位
              try { window.__streamErr = { name: err?.name, message: err?.message, aborted: !!ctrl.signal.aborted } } catch (e) {}
              if (ctrl.signal.aborted) {
                // 用户主动停止：保留已生成内容
                resolve()
                return
              }
              // 流式失效 → 降级非流式
              this._fallbackNonStream(thread, content, bubbleRef, err)
              resolve()
            },
          },
        ).then(resolve)
      })
      await done
      if (ctrl.signal.aborted) {
        bubbleRef.status = 'ok'
        bubbleRef.interrupted = true
        bubbleRef.reason = bubbleRef.reason || ''
      } else if (bubbleRef.status === 'streaming') {
        bubbleRef.status = 'error'
        bubbleRef.error = '回复未完整返回，请重试'
      }
      this.activeCtrl = null
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
        bubble.artifacts = result.artifacts
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