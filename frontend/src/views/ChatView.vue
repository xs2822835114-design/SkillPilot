<script setup>
import { nextTick, ref, watch } from 'vue'

import ChatComposer from '@/components/chat/ChatComposer.vue'
import ChatMessageBubble from '@/components/chat/ChatMessageBubble.vue'
import { useChatStore } from '@/stores/chat'

const chat = useChatStore()

// 仅首次进入时恢复本地会话
if (!chat.$state.currentThreadId) {
  chat.init()
}

const listEl = ref(null)
// 智能跟随滚动：仅在用户靠近底部时自动下滚，用户上翻时暂停跟随
const stick = ref(true)

function nearBottom() {
  const el = listEl.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight < 48
}
function onScroll() {
  stick.value = nearBottom()
}
function scrollToBottom(smooth = false) {
  nextTick(() => {
    if (listEl.value && stick.value) {
      listEl.value.scrollTo({ top: listEl.value.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
    }
  })
}
// 新消息 & 流式增量时跟随滚动（只在靠近底部时）
watch(
  () => chat.messages.length,
  () => scrollToBottom(),
)
watch(
  () => chat.messages?.[chat.messages.length - 1]?.content,
  () => scrollToBottom(true),
)

// 空状态起始提示（仅保留对话与学习计划能力）
const suggestions = [
  { emoji: '🎯', title: '我想转向 AI 应用开发', desc: '帮我梳理转型目标与学习路线' },
  { emoji: '🗺️', title: '制定一个学习路线', desc: '根据我的技术基础规划学习路径' },
  { emoji: '🐍', title: '我想学 Python', desc: '帮我生成入门到进阶的学习计划' },
  { emoji: '🌐', title: '什么是向量数据库', desc: '联网检索最新资料并解答' },
]

function useSuggestion(s) {
  chat.sendMessage(s.title)
}
</script>

<template>
  <div class="chat">
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

    <div v-else ref="listEl" class="messages" @scroll="onScroll">
      <div class="thread">
        <ChatMessageBubble v-for="m in chat.messages" :key="m.id" :message="m" />
      </div>
    </div>

    <ChatComposer :sending="chat.sending" @send="chat.sendMessage" @stop="chat.stopGenerating" />
  </div>
</template>

<style scoped>
.chat {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
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
</style>