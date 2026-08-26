<script setup>
defineProps({
  plan: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  transitioningTaskId: { type: String, default: null },
})
defineEmits(['generate', 'transition'])
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h3>学习计划</h3>
      <button class="primary" @click="$emit('generate')">生成 / 更新计划</button>
    </div>

    <div v-if="loading" class="empty">计划生成中…</div>

    <div v-else-if="!plan" class="empty">
      <p>尚无学习计划。基于<router-link to="/gap">缺口报告</router-link>生成一条可执行、可验收的学习路线。</p>
    </div>

    <template v-else>
      <div class="meta">
        <span>目标：<b>{{ plan.goal }}</b></span>
        <span>质量：<em v-if="plan.is_llm_enhanced" class="tag">LLM 增强</em><em v-else class="tag rule">规则</em></span>
        <span>进度：<b>{{ plan.metrics?.done_tasks }}/{{ plan.metrics?.total_tasks }}</b></span>
      </div>

      <div class="bar"><i :style="{ width: plan.metrics?.total_tasks ? (plan.metrics.done_tasks / plan.metrics.total_tasks) * 100 + '%' : '0%' }" /></div>

      <div class="phases">
        <div v-for="(phase, idx) in plan.phases" :key="phase.phase_id || idx" class="phase">
          <div class="phase-head">
            <span class="dot" :data-phase="String(idx + 1)" />
            <span class="phase-title">{{ phase.title || `阶段 ${idx + 1}` }}</span>
          </div>
          <div v-for="task in phase.tasks" :key="task.task_id" class="task">
            <span class="check" :class="{ done: task.status === 'done', doing: task.status === 'doing' }">
              {{ task.status === 'done' ? '✓' : task.status === 'doing' ? '●' : '○' }}
            </span>
            <div class="task-main">
              <span class="task-title">{{ task.title }}</span>
              <span v-if="task.acceptance_criteria" class="acc">{{ task.acceptance_criteria }}</span>
              <span v-if="task.estimated_hours" class="hours">约 {{ task.estimated_hours }}h</span>
            </div>
            <div class="task-actions">
              <span class="status-chip" :data-st="task.status">{{ task.status }}</span>
              <button
                v-if="task.status === 'pending'"
                class="ghost" :disabled="transitioningTaskId === task.task_id"
                @click="$emit('transition', task, 'start')"
              >开始</button>
              <button
                v-else-if="task.status === 'doing'"
                class="ghost" :disabled="transitioningTaskId === task.task_id"
                @click="$emit('transition', task, 'complete')"
              >完成</button>
            </div>
          </div>
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
  gap: 18px;
  flex-wrap: wrap;
  font-size: 13px;
  color: var(--text-2);
  margin-bottom: 10px;
  align-items: center;
}
.bar {
  height: 6px;
  background: var(--surface-hover);
  border-radius: 999px;
  overflow: hidden;
  margin-bottom: 16px;
}
.bar i {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #5ce1ff, #7c5cff);
  border-radius: 999px;
  transition: width 0.3s;
}
.phases {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.phase-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.phase-title {
  font-weight: 600;
  font-size: 14px;
}
.dot {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--surface-hover);
  color: var(--text-2);
  font-size: 11px;
  display: grid;
  place-items: center;
}
.task {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 9px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  margin-bottom: 8px;
}
.check {
  width: 18px;
  height: 18px;
  border: 1px solid var(--border-strong);
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 12px;
  color: var(--text-3);
  flex: none;
  margin-top: 2px;
}
.check.done {
  background: #3fb27f;
  border-color: #3fb27f;
  color: #fff;
}
.check.doing {
  border-color: #2a7de0;
  color: #2a7de0;
}
.task-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.task-title {
  font-size: 14px;
  color: var(--text);
}
.acc {
  font-size: 12px;
  color: var(--text-3);
}
.hours {
  font-size: 12px;
  color: var(--text-3);
}
.task-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}
.status-chip {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--surface-hover);
  color: var(--text-2);
}
.status-chip[data-st='done'] { background: rgba(63, 178, 127, 0.15); color: #2f9e6f; }
.status-chip[data-st='doing'] { background: rgba(42, 125, 224, 0.15); color: #2a7de0; }
.ghost {
  font-size: 12px;
  color: var(--text-2);
  padding: 4px 9px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
}
.ghost:hover { background: var(--surface-hover); color: var(--text); }
.ghost:disabled { opacity: 0.5; cursor: default; }
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
.tag {
  font-style: normal;
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 999px;
  background: rgba(124, 92, 255, 0.14);
  color: #6b5fd0;
}
.tag.rule {
  background: var(--surface-hover);
  color: var(--text-2);
}
</style>