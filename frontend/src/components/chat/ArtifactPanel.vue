<script setup>
import { computed } from 'vue'

/**
 * 结构化业务结果面板：把 Agent 产出的 artifacts 渲染成卡片。
 * 覆盖四类结果（来自后端 gap_node 的 artifacts）：
 * - target_profile   目标画像（目标技能 + 要求等级/权重）
 * - skill_gaps       技能缺口（当前/目标等级 + 优先级）
 * - learning_plan    学习计划（按学习路径排序 + 资源推荐）
 * - recommended_roles 岗位推荐（仅岗位求职场景）
 */
const props = defineProps({
  artifacts: { type: Object, default: null },
})

const target = computed(() => props.artifacts?.target_profile || null)
const gaps = computed(() => (Array.isArray(props.artifacts?.skill_gaps) ? props.artifacts.skill_gaps : []))
const plan = computed(() => (Array.isArray(props.artifacts?.learning_plan) ? props.artifacts.learning_plan : []))
const roles = computed(() => (Array.isArray(props.artifacts?.recommended_roles) ? props.artifacts.recommended_roles : []))

const GOAL_TYPE_LABEL = { tech_learning: '技术学习', job_search: '岗位求职' }
const goalTypeLabel = (t) => GOAL_TYPE_LABEL[t] || ''

// 缺口详情按 skill_id 建索引，供学习计划条目回填「当前 → 目标」等级
const gapBySkill = computed(() => {
  const m = {}
  for (const g of gaps.value) m[g.skill_id] = g
  return m
})

function priorityTone(p) {
  if (p >= 0.6) return 'high'
  if (p >= 0.3) return 'mid'
  return 'low'
}
function priorityLabel(p) {
  if (p == null) return ''
  if (p >= 0.6) return '高优先'
  if (p >= 0.3) return '中优先'
  return '低优先'
}
function pct(n) {
  if (n == null || Number.isNaN(Number(n))) return '—'
  return `${Math.round(Number(n) * 100)}%`
}

const hasContent = computed(
  () => !!(target.value || gaps.value.length || plan.value.length || roles.value.length),
)
</script>

<template>
  <div v-if="hasContent" class="artifact">
    <!-- 目标画像 -->
    <section v-if="target" class="block">
      <div class="head">
        <span class="tag">{{ goalTypeLabel(target.goal_type) }}</span>
        <h4>{{ target.goal_name || '目标画像' }}</h4>
      </div>
      <ul v-if="target.skills && target.skills.length" class="req-list">
        <li v-for="s in target.skills" :key="s.skill_id" class="req">
          <span class="req-name">{{ s.skill_name || s.skill_id }}</span>
          <span class="req-meta">
            <em class="lv">L{{ s.required_level }}</em>
            <em v-if="s.weight != null" class="wt">权重 {{ pct(s.weight) }}</em>
          </span>
        </li>
      </ul>
      <p v-else class="muted">目标技能待识别</p>
    </section>

    <!-- 技能缺口 -->
    <section v-if="gaps.length" class="block">
      <h4>技能缺口 <span class="cnt">{{ gaps.length }}</span></h4>
      <ul class="gap-list">
        <li v-for="g in gaps" :key="g.skill_id" class="gap">
          <div class="gap-main">
            <span class="gap-name">{{ g.skill_name || g.skill_id }}</span>
            <span class="gap-lv">L{{ g.current_level ?? 0 }} → L{{ g.target_level }}</span>
          </div>
          <span class="prio" :class="priorityTone(g.priority)">{{ priorityLabel(g.priority) }}</span>
        </li>
      </ul>
    </section>

    <!-- 学习计划 -->
    <section v-if="plan.length" class="block">
      <h4>学习计划 <span class="cnt">{{ plan.length }} 步</span></h4>
      <ol class="plan-list">
        <li v-for="(p, i) in plan" :key="p.skill_id || i" class="plan-item">
          <span class="step">{{ i + 1 }}</span>
          <div class="plan-body">
            <div class="plan-head">
              <span class="plan-name">{{ p.skill_name || p.skill_id }}</span>
              <span
                v-if="gapBySkill[p.skill_id]"
                class="gap-lv"
              >L{{ gapBySkill[p.skill_id].current_level ?? 0 }} → L{{ gapBySkill[p.skill_id].target_level }}</span>
              <span class="prio" :class="priorityTone(p.priority)">{{ priorityLabel(p.priority) }}</span>
            </div>
            <ul v-if="p.resources && p.resources.length" class="res-list">
              <li v-for="(r, j) in p.resources" :key="j" class="res">
                <a v-if="r.url" :href="r.url" target="_blank" rel="noopener noreferrer" class="res-title">
                  {{ r.title || r.url }}
                </a>
                <span v-else class="res-title">{{ r.title }}</span>
                <span v-if="r.type || r.category" class="res-tag">{{ r.type || r.category }}</span>
              </li>
            </ul>
          </div>
        </li>
      </ol>
    </section>

    <!-- 岗位推荐 -->
    <section v-if="roles.length" class="block">
      <h4>推荐岗位</h4>
      <ul class="role-list">
        <li v-for="r in roles" :key="r.role_id" class="role">
          <span class="role-name">{{ r.role_name }}</span>
          <span class="role-meta">覆盖度 {{ pct(r.coverage) }} · 缺口 {{ r.gap_count }} 项</span>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.artifact {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.block {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
  padding: 12px 14px;
}
.head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
h4 {
  margin: 0;
  font-size: 13.5px;
  font-weight: 600;
}
.head h4 {
  margin: 0;
}
.tag {
  flex: none;
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
}
.cnt {
  margin-left: 4px;
  font-size: 11.5px;
  font-weight: 500;
  color: var(--text-3);
}
.muted {
  margin: 0;
  font-size: 12.5px;
  color: var(--text-3);
}
/* 目标画像 */
.req-list,
.gap-list,
.role-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.req {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 13px;
}
.req-name {
  font-weight: 500;
}
.req-meta {
  display: flex;
  gap: 10px;
  font-size: 12px;
  color: var(--text-2);
}
.req-meta em {
  font-style: normal;
}
.lv {
  font-weight: 600;
  color: var(--accent);
}
.wt {
  color: var(--text-3);
}
/* 缺口 & 计划 & 岗位 */
.gap {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 13px;
}
.gap-main {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.gap-name {
  font-weight: 500;
}
.gap-lv {
  font-size: 12px;
  color: var(--text-2);
  white-space: nowrap;
}
.prio {
  flex: none;
  font-style: normal;
  font-weight: 600;
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 999px;
}
.prio.high { background: rgba(255, 80, 80, 0.14); color: #e23b3b; }
.prio.mid { background: rgba(255, 160, 40, 0.14); color: #e08b04; }
.prio.low { background: rgba(120, 130, 150, 0.14); color: #6a7485; }
/* 计划步骤 */
.plan-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.plan-item {
  display: flex;
  gap: 10px;
}
.step {
  flex: none;
  width: 20px;
  height: 20px;
  border-radius: 6px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 12px;
  font-weight: 600;
  display: grid;
  place-items: center;
}
.plan-body {
  flex: 1;
  min-width: 0;
}
.plan-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.plan-name {
  font-weight: 500;
  font-size: 13px;
}
.res-list {
  list-style: none;
  margin: 6px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.res {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
}
.res-title {
  color: var(--accent);
  word-break: break-all;
}
.res-title:hover {
  text-decoration: underline;
}
.res-tag {
  flex: none;
  font-size: 11px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--bg-soft);
  border: 1px solid var(--border);
  color: var(--text-3);
}
.role {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 13px;
}
.role-name {
  font-weight: 500;
}
.role-meta {
  font-size: 12px;
  color: var(--text-2);
}
</style>