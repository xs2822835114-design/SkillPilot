<script setup>
defineProps({
  threads: { type: Array, required: true },
  currentThreadId: { type: String, default: null },
  hidden: { type: Boolean, default: false },
})

const emit = defineEmits(['select', 'create', 'remove', 'toggle'])
</script>

<template>
  <aside class="sidebar" :class="{ hidden }">
    <div class="side-head">
      <button class="new-chat" @click="emit('create')">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
        <span>新建会话</span>
      </button>
      <button class="collapse" title="收起侧栏" @click="emit('toggle')">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="15 6 9 12 15 18" />
        </svg>
      </button>
    </div>

    <div class="side-label">会话</div>

    <ul class="list">
      <li
        v-for="t in threads"
        :key="t.thread_id"
        class="item"
        :class="{ active: t.thread_id === currentThreadId }"
        @click="emit('select', t.thread_id)"
      >
        <svg class="chat-icon" viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
          <path d="M12 3c-5 0-9 3.4-9 7.6 0 2.4 1.3 4.6 3.4 6l-.6 3.4 3.1-1.6c.9.2 1.9.4 3 .4 5 0 9-3.4 9-7.6S17 3 12 3z" />
        </svg>
        <span class="title">{{ t.title }}</span>
        <button class="del" title="删除会话" @click.stop="emit('remove', t.thread_id)">×</button>
      </li>
    </ul>

    <div v-if="!threads.length" class="empty">暂无会话</div>

    <div class="side-foot">
      <RouterLink class="foot-link" to="/health">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
        服务健康
      </RouterLink>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 264px;
  flex: none;
  height: 100%;
  min-height: 0;
  background: var(--bg-soft);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  transition: width 0.18s ease, margin 0.18s ease;
}
.sidebar.hidden {
  width: 0;
  margin-left: -264px;
  overflow: hidden;
  border-right: none;
}
.side-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 14px 8px;
}
.new-chat {
  flex: 1;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-strong);
  background: var(--bg);
  font-size: 14px;
  font-weight: 500;
  transition: background 0.15s;
}
.new-chat:hover {
  background: var(--surface-hover);
}
.collapse {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  display: grid;
  place-items: center;
  color: var(--text-2);
}
.collapse:hover {
  background: var(--surface-hover);
}
.side-label {
  padding: 8px 16px 4px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-3);
}
.list {
  list-style: none;
  margin: 0;
  padding: 4px 8px;
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--text-2);
  transition: background 0.12s;
}
.item:hover {
  background: var(--surface-hover);
}
.item.active {
  background: var(--text);
  color: #fff;
}
.chat-icon {
  flex: none;
  opacity: 0.9;
}
.title {
  flex: 1;
  min-width: 0;
  font-size: 13.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.del {
  flex: none;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  color: inherit;
  opacity: 0;
  font-size: 16px;
  line-height: 1;
}
.del:hover {
  background: rgba(0, 0, 0, 0.08);
}
.item:hover .del {
  opacity: 0.7;
}
.empty {
  padding: 16px;
  text-align: center;
  color: var(--text-3);
  font-size: 13px;
}
.side-foot {
  padding: 10px;
  border-top: 1px solid var(--border);
}
.foot-link {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border-radius: var(--radius-sm);
  color: var(--text-2);
  font-size: 13.5px;
  transition: background 0.12s;
}
.foot-link:hover {
  background: var(--surface-hover);
  color: var(--text);
}
</style>