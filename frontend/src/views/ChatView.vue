<script setup>
import { nextTick, ref, watch } from 'vue'

import ChatComposer from '@/components/chat/ChatComposer.vue'
import ChatMessageBubble from '@/components/chat/ChatMessageBubble.vue'
import ChatThreadsPanel from '@/components/chat/ChatThreadsPanel.vue'
import { useChatStore } from '@/stores/chat'

const chat = useChatStore()
const sidebarOpen = ref(true)

// 仅首次进入时恢复本地会话
if (!chat.$state.currentThreadId) {
  chat.init()
}

const listEl = ref(null)

function scrollToBottom() {
  nextTick(() => {
    if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
  })
}
watch(
  () => chat.messages.length,
  () => scrollToBottom(),
)

// 空状态起始提示（对齐阶段 1 意图枚举，模仿 ChatGPT 首页提问卡片）
const suggestions = [
  { emoji: '🎯', title: '我想转向 AI 应用开发', desc: '帮我梳理转型目标与能力盘点' },
  { emoji: '🗺️', title: '制定一个学习路线', desc: '根据我的技术基础规划学习路径' },
  { emoji: '🧩', title: '我已经会 Python', desc: '补充我的技术栈与项目经验' },
  { emoji: '📊', title: '评估我的能力水平', desc: '指出我的优势与差距并给建议' },
]

function useSuggestion(s) {
  chat.sendMessage(s.title)
}
</script>

<template>
  <div class="chat">
    <ChatThreadsPanel
      :threads="chat.threads"
      :current-thread-id="chat.currentThreadId"
      :hidden="!sidebarOpen"
      @select="chat.selectThread"
      @create="chat.createThread"
      @remove="chat.removeThread"
      @toggle="sidebarOpen = !sidebarOpen"
    />

    <section class="main">
      <button v-if="!sidebarOpen" class="hamburger" title="展开侧栏" @click="sidebarOpen = true">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>

      <div v-if="!chat.messages.length" ref="listEl" class="empty-wrap">
        <div class="empty">
          <!-- ChatGPT 风格彩色闪光 logo -->
          <svg class="sparkle" width="44" height="44" viewBox="0 0 24 24" fill="none" role="img">
            <defs>
              <linearGradient id="sparkleGrad" x1="0" y1="0" x2="24" y2="24">
                <stop offset="0" stop-color="#5ce1ff" />
                <stop offset="0.3" stop-color="#7c5cff" />
                <stop offset="0.6" stop-color="#ff5c8a" />
                <stop offset="1" stop-color="#ffd166" />
              </linearGradient>
            </defs>
            <path
              fill="url(#sparkleGrad)"
              d="M12 0 C12.9 5.9 16 10.9 24 12 C16 13.1 12.9 18.1 12 24 C11.1 18.1 8 13.1 0 12 C8 10.9 11.1 5.9 12 0 Z"
            />
          </svg>

          <h1 class="title">今天有什么可以帮你？</h1>
          <p class="subtitle">说出你的目标或技术背景，我来帮你梳理成长路线。</p>

          <div class="cards">
            <button
              v-for="s in suggestions"
              :key="s.title"
              class="card"
              :disabled="chat.sending"
              @click="useSuggestion(s)"
            >
              <span class="card-emoji">{{ s.emoji }}</span>
              <span class="card-text">
                <span class="card-title">{{ s.title }}</span>
                <span class="card-desc">{{ s.desc }}</span>
              </span>
            </button>
          </div>
        </div>
      </div>

      <div v-else ref="listEl" class="messages">
        <div class="thread">
          <ChatMessageBubble v-for="m in chat.messages" :key="m.id" :message="m" />
        </div>
      </div>

      <ChatComposer :sending="chat.sending" @send="chat.sendMessage" />

      <div class="stream-toggle">
        <button
          class="toggle"
          :class="{ on: chat.streamingEnabled }"
          title="流式开关：开=SSE 增量输出；关=一次性返回"
          @click="chat.toggleStreaming"
        >
          <span class="dot" />
          {{ chat.streamingEnabled ? '流式输出' : '非流式输出' }}
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.chat {
  display: flex;
  height: 100%;
  min-height: 0;
  position: relative;
}
.main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.hamburger {
  position: absolute;
  z-index: 5;
  top: 12px;
  left: 12px;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  display: grid;
  place-items: center;
  color: var(--text-2);
}
.hamburger:hover {
  background: var(--surface-hover);
}
/* 空状态 */
.empty-wrap {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.empty {
  max-width: 720px;
  width: 100%;
  text-align: center;
  padding-top: 24px;
}
.sparkle {
  display: inline-block;
  filter: drop-shadow(0 6px 16px rgba(124, 92, 255, 0.28));
}
.title {
  margin: 22px 0 8px;
  font-size: 32px;
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--text);
}
.subtitle {
  margin: 0 0 30px;
  font-size: 15px;
  color: var(--text-2);
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 14px;
}
.card {
  display: flex;
  align-items: center;
  gap: 16px;
  text-align: left;
  padding: 16px 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
  font-size: 14px;
  color: var(--text);
  transition: border-color 0.15s, box-shadow 0.2s, transform 0.15s;
}
.card:hover {
  border-color: var(--border-strong);
  box-shadow: var(--shadow);
}
.card:disabled {
  opacity: 0.6;
  cursor: default;
}
.card-emoji {
  font-size: 26px;
  line-height: 1;
}
.card-text {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.card-title {
  font-weight: 600;
}
.card-desc {
  font-size: 13px;
  color: var(--text-2);
}
/* 消息列表 */
.messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 0;
}
.thread {
  max-width: 768px;
  width: 100%;
  margin: 0 auto;
  padding: 0 20px;
}
.stream-toggle {
  flex: none;
  padding-bottom: 6px;
  display: flex;
  justify-content: center;
}
.toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-3);
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--bg);
}
.toggle .dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-3);
}
.toggle.on {
  color: var(--text-2);
  border-color: var(--border-strong);
}
.toggle.on .dot {
  background: #3fb27f;
  box-shadow: 0 0 0 3px rgba(63, 178, 127, 0.18);
}
</style>