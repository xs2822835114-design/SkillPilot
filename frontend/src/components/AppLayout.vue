<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { useChatStore } from '@/stores/chat'
import { useHealthStore } from '@/stores/health'
import { usePlanStore } from '@/stores/plan'

const health = useHealthStore()
const chat = useChatStore()
const planStore = usePlanStore()
const route = useRoute()

const isChat = computed(() => route.name === 'chat')

const tone = {
  ok: 'tone-ok',
  warn: 'tone-warn',
  err: 'tone-err',
}

const navItems = [
  {
    to: '/chat',
    label: '对话',
    icon: 'M12 3c-5 0-9 3.6-9 8s4 8 9 8c1 0 1.9-.2 2.8-.5l3.7 2.3-.8-3.3C19.3 16.3 21 14.2 21 11c0-4.4-4-8-9-8z',
  },
  {
    to: '/plan',
    label: '学习计划',
    icon: 'M4 5h16v2H4zm0 6h16v2H4zm0 6h10v2H4zM21 5l-1.4 1.4-2-2L16.2 3l2 2L21 5zm-1 6 2.2 2.2-1.4 1.4-2.2-2.2 1.4-1.4z',
  },
  {
    to: '/graph',
    label: '学习计划图谱',
    icon: 'M12 2a2 2 0 0 1 2 2c0 .5-.2 1-.5 1.3l1.2 2.1a2 2 0 0 1 2.4.6l2.1-1.2a2 2 0 1 1 1.7 1l-2.1 1.2a2 2 0 0 1 0 1.9l2.1 1.2a2 2 0 1 1-1.7 1l-2.1-1.2a2 2 0 0 1-2.4.6l-1.2 2.1a2 2 0 1 1-1.7-1l1.2-2.1a2 2 0 0 1 0-1.9l-1.2-2.1A2 2 0 0 1 12 2z',
  },
  {
    to: '/health',
    label: '服务健康',
    icon: 'M12 3a9 9 0 0 0-9 9 9 9 0 0 0 1.4 4.8L3.6 21l4.2-.8A9 9 0 1 0 12 3zm-1 13.5h2v2h-2zm0-9h2v6.5h-2z',
  },
]

async function clearCache() {
  const ok = window.confirm(
    '确定清除所有本地缓存吗？将清空全部对话记录与学习计划（含图谱），且无法恢复。',
  )
  if (!ok) return
  chat.clearAll()
  await planStore.clearAll()
}
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <RouterLink class="brand" to="/chat">
        <span class="brand-mark">S</span>
        <span class="model">SkillMap <em>v1</em></span>
      </RouterLink>

      <nav class="nav">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="nav-item"
          active-class="active"
        >
          <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
            <path :d="item.icon" />
          </svg>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>

      <!-- 会话列表：仅在对话页显示，与导航合并进同一个侧栏 -->
      <div v-if="isChat" class="sessions">
        <button class="new-chat" @click="chat.createThread()">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          <span>新建会话</span>
        </button>

        <div class="sessions-label">会话</div>

        <ul class="sessions-list">
          <li
            v-for="t in chat.threads"
            :key="t.thread_id"
            class="sessions-item"
            :class="{ active: t.thread_id === chat.currentThreadId }"
            @click="chat.selectThread(t.thread_id)"
          >
            <svg class="chat-icon" viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
              <path d="M12 3c-5 0-9 3.4-9 7.6 0 2.4 1.3 4.6 3.4 6l-.6 3.4 3.1-1.6c.9.2 1.9.4 3 .4 5 0 9-3.4 9-7.6S17 3 12 3z" />
            </svg>
            <span class="sessions-title">{{ t.title }}</span>
            <button class="sessions-del" title="删除会话" @click.stop="chat.removeThread(t.thread_id)">×</button>
          </li>
        </ul>

        <div v-if="!chat.threads.length" class="sessions-empty">暂无会话</div>
      </div>

      <div class="sidebar-footer">
        <button class="clear-cache" @click="clearCache">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
            <line x1="10" y1="11" x2="10" y2="17" />
            <line x1="14" y1="11" x2="14" y2="17" />
          </svg>
          清除缓存
        </button>
        <span class="health-pill" :class="tone[health.health?.tone || 'muted']">
          <span class="dot" />
          {{ health.health ? health.health.statusText : health.loading ? '检查中' : '离线' }}
        </span>
      </div>
    </aside>

    <main class="body">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.layout {
  height: 100%;
  display: flex;
  flex-direction: row;
}
.sidebar {
  width: 264px;
  flex: none;
  height: 100%;
  min-height: 0;
  background: var(--bg-soft);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 16px 14px;
  flex: none;
}
.brand-mark {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: var(--text);
  color: #fff;
  font-weight: 700;
  font-size: 16px;
  display: grid;
  place-items: center;
  flex: none;
}
.model {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}
.model em {
  font-style: normal;
  font-weight: 400;
  color: var(--text-3);
  font-size: 12px;
  margin-left: 4px;
}
.nav {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 12px 10px;
  border-bottom: 1px solid var(--border);
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border-radius: var(--radius-sm);
  font-size: 14px;
  color: var(--text-2);
  transition: background 0.15s, color 0.15s;
}
.nav-item svg {
  flex: none;
}
.nav-item:hover {
  background: var(--surface-hover);
  color: var(--text);
}
.nav-item.active {
  background: var(--text);
  color: #fff;
}
/* 会话列表区：占据剩余空间并可滚动 */
.sessions {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 10px 12px;
  overflow-y: auto;
}
.new-chat {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-strong);
  background: var(--bg);
  font-size: 14px;
  font-weight: 500;
  flex: none;
  transition: background 0.15s;
}
.new-chat:hover {
  background: var(--surface-hover);
}
.sessions-label {
  padding: 10px 4px 4px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-3);
  flex: none;
}
.sessions-list {
  list-style: none;
  margin: 0;
  padding: 4px 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.sessions-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--text-2);
  transition: background 0.12s;
}
.sessions-item:hover {
  background: var(--surface-hover);
}
.sessions-item.active {
  background: var(--text);
  color: #fff;
}
.chat-icon {
  flex: none;
  opacity: 0.9;
}
.sessions-title {
  flex: 1;
  min-width: 0;
  font-size: 13.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sessions-del {
  flex: none;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  color: inherit;
  opacity: 0;
  font-size: 16px;
  line-height: 1;
}
.sessions-del:hover {
  background: rgba(0, 0, 0, 0.08);
}
.sessions-item:hover .sessions-del {
  opacity: 0.7;
}
.sessions-empty {
  padding: 16px;
  text-align: center;
  color: var(--text-3);
  font-size: 13px;
}
.sidebar-footer {
  flex: none;
  margin-top: auto;
  padding: 12px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.clear-cache {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border-radius: var(--radius-sm);
  color: var(--text-2);
  font-size: 13.5px;
  text-align: left;
  transition: background 0.12s, color 0.12s;
}
.clear-cache:hover {
  background: var(--surface-hover);
  color: #c03a3a;
}
.health-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-2);
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg);
}
.health-pill .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-3);
  flex: none;
}
.tone-ok .dot {
  background: var(--ok);
}
.tone-warn .dot {
  background: var(--warn);
}
.tone-err .dot {
  background: var(--danger);
}
.body {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
</style>