<script setup>
import { onMounted, ref } from 'vue'
import EvalReportCard from '@/components/EvalReportCard.vue'
import { usePlanStore } from '@/stores/plan'
import { usePracticeEvalStore } from '@/stores/practiceEval'

const planStore = usePlanStore()
const pe = usePracticeEvalStore()

const taskId = ref('')
const code = ref('')
const testCode = ref('')

onMounted(async () => {
  await planStore.loadPlanList()
  if (planStore.planList.length) {
    await planStore.loadPlan(planStore.planList[0].plan_id)
  }
})

const taskOptions = () => {
  const tasks = []
  for (const phase of planStore.currentPlan?.phases || []) {
    for (const t of phase.tasks || []) tasks.push(t)
  }
  return tasks
}

async function startPractice() {
  const task = taskOptions().find((t) => t.task_id === taskId.value)
  if (!task) return
  await pe.startPractice(task)
}

async function runEvaluate() {
  await pe.evaluate({ code: code.value, testCode: testCode.value, filename: 'solution.py' })
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>实践 · 评估</h1>
      <p>把学习任务变成实操，用代码验证能力并在评估后自动再规划</p>
    </header>

    <div class="cards">
      <!-- 发起实践 -->
      <section class="panel">
        <div class="panel-head"><h3>1 · 发起实践任务</h3></div>
        <label>选择学习任务</label>
        <select v-model="taskId" class="select">
          <option v-for="t in taskOptions()" :key="t.task_id" :value="t.task_id">
            {{ t.title }}（{{ t.skill_id }}）
          </option>
        </select>
        <button class="primary" :disabled="!taskId || pe.generating" @click="startPractice">
          {{ pe.generating ? '生成中…' : '生成实践计划' }}
        </button>
        <div v-if="pe.practice" class="practice-info">
          <b>实践计划：</b>{{ pe.practice.title || pe.practice.practice_id }}
          <p class="brief">{{ pe.practice.brief || pe.practice.description || '见实践详情' }}</p>
        </div>
      </section>

      <!-- 上传代码 -->
      <section v-if="pe.practice" class="panel">
        <div class="panel-head"><h3>2 · 提交代码</h3></div>
        <label>实现代码</label>
        <textarea v-model="code" class="code" rows="8" placeholder="粘贴你的实现代码（如 calc.py）" />
        <label>单元测试</label>
        <textarea v-model="testCode" class="code" rows="4" placeholder="粘贴测试代码（可选）" />
        <button class="primary" :disabled="!code || pe.evaluating" @click="runEvaluate">
          {{ pe.evaluating ? '评估中…' : '评估这份代码' }}
        </button>
      </section>
    </div>

    <div v-if="pe.error" class="err">{{ pe.error }}</div>

    <EvalReportCard
      v-if="pe.practice"
      :evaluation="pe.evaluation"
      :evaluating="pe.evaluating"
      :error="pe.error"
      @evaluate="runEvaluate"
      @start-practice="startPractice"
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
  margin: 0 0 18px;
  color: var(--text-2);
  font-size: 14px;
}
.cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.panel {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
  padding: 18px;
}
.panel-head {
  margin-bottom: 12px;
}
.panel-head h3 {
  margin: 0;
  font-size: 16px;
}
label {
  display: block;
  font-size: 13px;
  color: var(--text-2);
  margin: 8px 0 4px;
}
.select {
  width: 100%;
  padding: 7px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg);
  color: var(--text);
  margin-bottom: 10px;
}
.code {
  width: 100%;
  font-family: var(--mono, monospace);
  font-size: 12px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-hover);
  color: var(--text);
  resize: vertical;
  margin-bottom: 10px;
}
.primary {
  font-size: 13px;
  padding: 7px 14px;
  border-radius: var(--radius-sm);
  background: var(--text);
  color: #fff;
}
.primary:hover { opacity: 0.92; }
.primary:disabled { opacity: 0.5; cursor: default; }
.practice-info {
  margin-top: 12px;
  font-size: 13px;
  color: var(--text);
}
.brief {
  margin: 4px 0 0;
  color: var(--text-2);
}
.err {
  margin: 14px 0 0;
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  background: rgba(226, 59, 59, 0.08);
  color: #c03a3a;
  font-size: 13px;
}
</style>