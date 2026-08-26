<script setup>
import { ref, watch } from 'vue'
defineProps({
  route: { type: String, default: '' },
  reason: { type: String, default: '' },
  steps: { type: Array, default: () => [] },
})
const open = ref(true)
</script>

<template>
  <div class="trace">
    <button class="trace-head" @click="open = !open" title="展开/收起 Agent 推理轨迹">
      <span class="tl">Agent Trace</span>
      <span class="route" v-if="route">{{ route }}</span>
      <span class="caret">{{ open ? '▾' : '▸' }}</span>
    </button>
    <div v-if="open" class="trace-body">
      <p v-if="reason" class="reason">推理：{{ reason }}</p>
      <ol v-if="steps && steps.length" class="steps">
        <li v-for="(s, i) in steps" :key="i">{{ s }}</li>
      </ol>
      <p v-if="!steps || !steps.length" class="muted">无额外推理步骤</p>
    </div>
  </div>
</template>

<style scoped>
.trace {
  margin-top: 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: var(--bg-soft);
}
.trace-head {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  font-size: 12px;
  color: var(--text-3);
  background: transparent;
}
.trace-head:hover {
  background: var(--surface-hover);
}
.tl {
  font-weight: 600;
  color: var(--text-2);
}
.route {
  margin-left: auto;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(124, 92, 255, 0.14);
  color: #6b5fd0;
}
.caret {
  font-size: 11px;
}
.trace-body {
  padding: 6px 12px 10px;
  border-top: 1px solid var(--border);
  font-size: 12.5px;
  color: var(--text-2);
}
.reason {
  margin: 4px 0;
}
.steps {
  margin: 6px 0 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.muted {
  margin: 4px 0;
  color: var(--text-3);
}
</style>