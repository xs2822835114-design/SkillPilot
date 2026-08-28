<script setup>
import { computed } from 'vue'

const props = defineProps({
  report: { type: Object, default: null },
  loading: { type: Boolean, default: false },
})

const emits = defineEmits(['refresh'])

const gapList = computed(() => props.report?.gaps || [])
const coverage = computed(() => props.report?.coverage || null)

const priorityTone = {
  P0: 'p0',
  P1: 'p1',
  P2: 'p2',
  P3: 'p3',
}
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h3>缺口报告</h3>
      <button v-if="report" class="ghost" @click="emits('refresh')">重新分析</button>
    </div>

    <div v-if="loading" class="empty">缺口分析中…</div>

    <div v-else-if="!report" class="empty">
      <p>尚未生成缺口报告。<b>点击“开始缺口分析”</b>，将基于你的技术画像与目标岗位计算能力缺口。</p>
    </div>

    <template v-else>
      <div class="meta">
        <span>目标岗位：<b>{{ report.target_role }}</b></span>
        <span v-if="coverage">覆盖度：<b>{{ Math.round((coverage.coverage_rate || 0) * 100) }}%</b></span>
        <span v-if="coverage">缺口：<b>{{ coverage.gap_total }}</b> 项</span>
      </div>

      <div class="table">
        <div class="row head">
          <span>技能</span>
          <span>当前/目标</span>
          <span>优先级</span>
          <span class="wide">依据 / 建议</span>
        </div>
        <div v-for="g in gapList" :key="g.skill_id" class="row">
          <span class="name">{{ g.name }}</span>
          <span>L{{ g.current_level }} → L{{ g.required_level }}</span>
          <span>
            <em class="prio" :class="priorityTone[g.priority] || 'p3'">{{ g.priority }}</em>
          </span>
          <span class="wide reason">{{ g.reason }}</span>
        </div>
      </div>

      <p v-if="report.suggestions" class="suggest">{{ report.suggestions }}</p>
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
  margin-bottom: 12px;
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
  margin-bottom: 12px;
}
.table {
  font-size: 13px;
}
.row {
  display: grid;
  grid-template-columns: 1.4fr 1fr 0.6fr 2.6fr;
  gap: 10px;
  align-items: center;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
}
.row.head {
  color: var(--text-3);
  font-size: 12px;
}
.row .name {
  font-weight: 600;
  color: var(--text);
}
.row .wide.reason {
  color: var(--text-2);
}
.prio {
  font-style: normal;
  font-weight: 700;
  font-size: 12px;
  padding: 2px 7px;
  border-radius: 999px;
}
.p0 { background: rgba(255, 80, 80, 0.14); color: #e23b3b; }
.p1 { background: rgba(255, 160, 40, 0.14); color: #e08b04; }
.p2 { background: rgba(76, 154, 255, 0.14); color: #2a7de0; }
.p3 { background: rgba(120, 130, 150, 0.14); color: #6a7485; }
.empty {
  padding: 28px 0;
  text-align: center;
  color: var(--text-2);
  font-size: 14px;
}
.ghost {
  font-size: 13px;
  color: var(--text-2);
  padding: 5px 10px;
  border-radius: var(--radius-sm);
}
.ghost:hover {
  background: var(--surface-hover);
  color: var(--text);
}
.suggest {
  margin: 12px 0 0;
  font-size: 13px;
  color: var(--text-2);
  white-space: pre-wrap;
}
</style>