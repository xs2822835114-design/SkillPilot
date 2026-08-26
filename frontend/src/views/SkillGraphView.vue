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