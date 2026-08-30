<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import SkillGraph from '@/components/SkillGraph.vue'
import { usePlanStore } from '@/stores/plan'
import { useGraphStore } from '@/stores/graph'

const plan = usePlanStore()
const graph = useGraphStore()
const selected = ref('')

onMounted(async () => {
  await graph.load() // 全局技能词表：提供 id→name/category + 前置关系边
  await plan.loadPlanList()
  if (plan.planList.length) {
    selected.value = plan.planList[0].plan_id
    plan.loadPlan(selected.value)
  }
})

watch(selected, (id) => {
  if (id) plan.loadPlan(id)
})

/** 单一技能的掌握状态：该技能的每个任务都 done 才算已掌握 */
function masteredOf(taskMap) {
  return (skillId) => {
    const tasks = taskMap[skillId]
    if (!tasks || !tasks.length) return false
    return tasks.every((t) => t.status === 'done')
  }
}

const planNodes = computed(() => {
  if (!plan.currentPlan) return []
  const taskMap = {}
  for (const phase of plan.currentPlan.phases) {
    for (const task of phase.tasks || []) {
      if (!task.skill_id) continue
      ;(taskMap[task.skill_id] = taskMap[task.skill_id] || []).push(task)
    }
  }
  const isMastered = masteredOf(taskMap)
  const seen = new Set()
  const byId = graph.byId
  const out = []
  for (const phase of plan.currentPlan.phases) {
    for (const task of phase.tasks || []) {
      const sid = task.skill_id
      if (!sid || seen.has(sid)) continue
      seen.add(sid)
      const g = byId[sid]
      out.push({
        id: sid,
        name: g?.name || sid,
        category: g?.category || 'other',
        mastered: isMastered(sid),
      })
    }
  }
  return out
})

const planEdges = computed(() => {
  const ids = new Set(planNodes.value.map((n) => n.id))
  return graph.edges.filter((e) => ids.has(e.source) && ids.has(e.target))
})

const planNotFound = computed(() => !plan.planLoading && !planNodes.value.length && plan.planList.length === 0)
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>学习计划图谱</h1>
      <p>你学习计划里的技能及其前置关系（绿色=已掌握，勾选后在「学习计划」页更新）</p>
      <div v-if="plan.planList.length" class="pick">
        <select v-model="selected" class="select">
          <option v-for="p in plan.planList" :key="p.plan_id" :value="p.plan_id">
            {{ p.goal }}（{{ p.status }}）
          </option>
        </select>
      </div>
    </header>

    <div v-if="plan.error" class="err">{{ plan.error }}</div>
    <div v-if="planNotFound" class="empty">暂无学习计划，先在「对话」中生成一份吧。</div>

    <SkillGraph :nodes="planNodes" :edges="planEdges" :loading="plan.planLoading || graph.loading" />
    <p class="meta">计划技能 {{ planNodes.length }} · 前置关系 {{ planEdges.length }} · 已掌握 {{ planNodes.filter((n) => n.mastered).length }}</p>

    <section v-if="plan.currentPlan && plan.currentPlan.phases" class="detail">
      <h2>学习环节明细</h2>
      <p class="detail-hint">每个技能到可执行环节：做什么 / 产出什么 / 怎么验证，照着就能开工。</p>
          <div v-for="(phase, pi) in plan.currentPlan.phases" :key="phase.phase_id || pi" class="detail-phase">
            <h3 class="detail-phase-title">{{ phase.title || `阶段 ${pi + 1}` }}</h3>
            <div v-for="task in phase.tasks" :key="task.task_id" class="detail-task">
              <div class="detail-task-head">
                <span class="detail-skill">{{ task.title }}</span>
                <span class="detail-status" :class="{ done: task.status === 'done' }">
                  {{ task.status === 'done' ? '已掌握' : '待学习' }}
                </span>
              </div>
              <!-- 执行级步骤（优先）；回退到粗粒度 steps -->
              <div v-if="(task.execution_steps || []).length" class="dex">
                <div v-for="es in task.execution_steps" :key="es.step_id" class="dex-step">
                  <div class="dex-head">
                    <span class="dex-idx">{{ es.step_id }}</span>
                    <span class="dex-title">{{ es.title }}<em class="dex-min" v-if="es.estimated_minutes">约 {{ es.estimated_minutes }} 分钟</em></span>
                  </div>
                  <p v-if="es.action" class="dex-line"><b>做什么：</b>{{ es.action }}</p>
                  <ul v-if="es.instructions && es.instructions.length" class="dex-ins">
                    <li v-for="(ins, k) in es.instructions" :key="k">{{ ins }}</li>
                  </ul>
                  <p v-if="es.deliverable" class="dex-line"><b>产出：</b>{{ es.deliverable }}</p>
                  <p v-if="es.verification" class="dex-line v"><b>验证：</b>{{ es.verification }}</p>
                </div>
              </div>
              <ol v-else-if="task.steps && task.steps.length" class="detail-steps">
                <li v-for="(s, si) in task.steps" :key="si">{{ s }}</li>
              </ol>
            </div>
          </div>
    </section>
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
  margin: 0 0 12px;
  color: var(--text-2);
  font-size: 14px;
}
.pick {
  margin-bottom: 12px;
}
.select {
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg);
  color: var(--text);
  max-width: 420px;
}
.meta {
  margin: 10px 4px 0;
  color: var(--text-3);
  font-size: 13px;
}
.detail {
  margin-top: 20px;
}
.detail h2 {
  margin: 0 0 4px;
  font-size: 17px;
}
.detail-hint {
  margin: 0 0 14px;
  color: var(--text-3);
  font-size: 12.5px;
}
.detail-phase {
  margin-bottom: 14px;
}
.detail-phase-title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
}
.detail-task {
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  margin-bottom: 8px;
}
.detail-task-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.detail-skill {
  font-size: 13.5px;
  font-weight: 500;
}
.detail-status {
  flex: none;
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--bg-soft);
  border: 1px solid var(--border);
  color: var(--text-3);
}
.detail-status.done {
  background: rgba(63, 178, 127, 0.14);
  border-color: rgba(63, 178, 127, 0.35);
  color: #1f9d56;
}
.detail-steps {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  counter-reset: step;
}
.detail-steps li {
  position: relative;
  padding-left: 22px;
  margin-bottom: 4px;
  font-size: 12.5px;
  color: var(--text-2);
  line-height: 1.55;
}
.detail-steps li::before {
  content: counter(step);
  counter-increment: step;
  position: absolute;
  left: 0;
  top: 2px;
  width: 15px;
  height: 15px;
  border-radius: 50%;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 10px;
  font-weight: 600;
  text-align: center;
  line-height: 15px;
}
/* 执行级步骤 */
.dex {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.dex-step {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  background: var(--bg-soft, #fafbfc);
}
.dex-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dex-idx {
  flex: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 10px;
  font-weight: 600;
  display: grid;
  place-items: center;
}
.dex-title {
  font-size: 13px;
  font-weight: 600;
}
.dex-min {
  font-style: normal;
  font-size: 11px;
  color: var(--text-3);
  font-weight: 400;
  margin-left: 6px;
}
.dex-line {
  margin: 5px 0 0;
  font-size: 12.5px;
  color: var(--text-2);
  line-height: 1.5;
}
.dex-line.v {
  color: var(--accent);
}
.dex-ins {
  margin: 4px 0 0;
  padding-left: 16px;
  font-size: 12.5px;
  color: var(--text-2);
  line-height: 1.5;
}
.err {
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  background: rgba(226, 59, 59, 0.08);
  color: #c03a3a;
  font-size: 13px;
  margin-bottom: 12px;
}
.empty {
  padding: 40px 0;
  text-align: center;
  color: var(--text-2);
  font-size: 14px;
}
</style>