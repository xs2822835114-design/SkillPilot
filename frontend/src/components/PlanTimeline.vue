<script setup>
defineProps({
  plan: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  transitioningTaskId: { type: String, default: null },
})
defineEmits(['generate', 'toggle'])
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h3>学习计划</h3>
      <button class="primary" @click="$emit('generate')">生成 / 更新计划</button>
    </div>

    <div v-if="loading" class="empty">计划生成中…</div>

    <div v-else-if="!plan" class="empty">
      <p>尚无学习计划。在「对话」中告诉我目标岗位或想学的技能，即可生成学习路线。</p>
    </div>

    <template v-else>
      <div class="meta">
        <span>目标：<b>{{ plan.goal }}</b></span>
        <span class="hint">（勾选表示该项你已掌握）</span>
      </div>

      <div v-for="(phase, idx) in plan.phases" :key="phase.phase_id || idx" class="phase">
        <div class="phase-head">
          <span class="phase-title">{{ phase.title || `阶段 ${idx + 1}` }}</span>
        </div>
        <div v-for="task in phase.tasks" :key="task.task_id" class="task">
          <label class="row">
            <input
              type="checkbox"
              class="check"
              :checked="task.status === 'done'"
              :disabled="transitioningTaskId === task.task_id"
              @change="$emit('toggle', task, $event.target.checked)"
            />
            <span class="title" :class="{ done: task.status === 'done' }">{{ task.title }}</span>
            <span v-if="task.estimated_hours" class="hours">约 {{ task.estimated_hours }}h</span>
          </label>
          <p v-if="task.acceptance_criteria" class="acc">{{ task.acceptance_criteria }}</p>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.panel {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
  padding: 18px;
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.panel-head h3 {
  margin: 0;
  font-size: 16px;
}
.meta {
  display: flex;
  gap: 10px;
  align-items: center;
  font-size: 13px;
  color: var(--text-2);
  margin-bottom: 16px;
}
.hint {
  color: var(--text-3);
  font-size: 12px;
}
.phase {
  margin-bottom: 16px;
}
.phase-head {
  margin-bottom: 6px;
}
.phase-title {
  font-weight: 600;
  font-size: 14px;
}
.task {
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  margin-bottom: 8px;
}
.row {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}
.check {
  width: 17px;
  height: 17px;
  accent-color: #3fb27f;
  cursor: pointer;
  flex: none;
}
.check:disabled { opacity: 0.5; cursor: default; }
.title {
  flex: 1;
  font-size: 14px;
  color: var(--text);
}
.title.done {
  color: var(--text-3);
  text-decoration: line-through;
}
.hours {
  font-size: 12px;
  color: var(--text-3);
  flex: none;
}
.acc {
  margin: 6px 0 0 27px;
  font-size: 12px;
  color: var(--text-3);
}
.primary {
  font-size: 13px;
  padding: 6px 12px;
  border-radius: var(--radius-sm);
  background: var(--text);
  color: #fff;
}
.primary:hover { opacity: 0.92; }
.empty {
  padding: 28px 0;
  text-align: center;
  color: var(--text-2);
  font-size: 14px;
}
</style>