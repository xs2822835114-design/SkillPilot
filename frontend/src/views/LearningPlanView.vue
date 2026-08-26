<script setup>
import { onMounted, ref, watch } from 'vue'
import PlanTimeline from '@/components/PlanTimeline.vue'
import { usePlanStore } from '@/stores/plan'

const plan = usePlanStore()
const selected = ref('')

onMounted(async () => {
  await plan.loadPlanList()
  if (plan.planList.length) {
    selected.value = plan.planList[0].plan_id
    plan.loadPlan(selected.value)
  }
})

watch(selected, (id) => {
  if (id) plan.loadPlan(id)
})

async function generate() {
  const p = await plan.generatePlan()
  if (p) selected.value = p.plan_id
}

function onToggle(task, checked) {
  plan.setTaskStatus(task, checked)
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>学习计划</h1>
      <p>可执行 · 可验收 · 可聚焦的学习路线与进度跟踪</p>
      <div v-if="plan.planList.length" class="pick">
        <select v-model="selected" class="select">
          <option v-for="p in plan.planList" :key="p.plan_id" :value="p.plan_id">
            {{ p.goal }}（{{ p.status }}）
          </option>
        </select>
      </div>
    </header>

    <div v-if="plan.error" class="err">{{ plan.error }}</div>

    <PlanTimeline
      :plan="plan.currentPlan"
      :loading="plan.planLoading"
      :transitioning-task-id="plan.transitioningTaskId"
      @generate="generate"
      @toggle="onToggle"
    />
  </div>
</template>

<style scoped>
.page {
  max-width: 1080px;
  margin: 0 auto;
  padding: 24px 28px;
  height: 100%;
  overflow-y: auto;
}
.page-head h1 {
  font-size: 24px;
  margin: 0 0 4px;
}
.page-head p {
  margin: 0 0 16px;
  color: var(--text-2);
  font-size: 14px;
}
.pick {
  margin-bottom: 16px;
}
.select {
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg);
  color: var(--text);
  max-width: 420px;
}
.err {
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  background: rgba(226, 59, 59, 0.08);
  color: #c03a3a;
  font-size: 13px;
  margin-bottom: 12px;
}
</style>