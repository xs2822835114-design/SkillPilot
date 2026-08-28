<script setup>
import { onMounted } from 'vue'
import GapReportTable from '@/components/GapReportTable.vue'
import { usePlanStore } from '@/stores/plan'

const plan = usePlanStore()
const gap = () => plan.requestGap()
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>缺口报告</h1>
      <p>画像 vs 目标岗位：差距清单 · 优先级 · 建议学习序</p>
      <div class="head-actions">
        <label>目标岗位</label>
        <input v-model="plan.targetRole" class="input" />
        <button class="primary" :disabled="plan.gapLoading" @click="gap">
          {{ plan.gapLoading ? '分析中…' : '开始缺口分析' }}
        </button>
      </div>
    </header>

    <div v-if="plan.error" class="err">{{ plan.error }}</div>

    <GapReportTable :report="plan.gapReport" :loading="plan.gapLoading" @refresh="gap" />

    <div v-if="plan.gapReport" class="seq">
      <h3>推荐学习顺序</h3>
      <ol>
        <li v-for="(s, i) in plan.gapReport.recommended_sequence || []" :key="i">{{ s }}</li>
      </ol>
    </div>
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
.head-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 18px;
}
.head-actions label {
  font-size: 13px;
  color: var(--text-2);
}
.input {
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg);
  color: var(--text);
  width: 180px;
}
.primary {
  font-size: 13px;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  background: var(--text);
  color: #fff;
}
.primary:hover { opacity: 0.92; }
.primary:disabled { opacity: 0.5; cursor: default; }
.err {
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  background: rgba(226, 59, 59, 0.08);
  color: #c03a3a;
  font-size: 13px;
  margin-bottom: 12px;
}
.seq {
  margin-top: 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
  padding: 18px;
}
.seq h3 {
  margin: 0 0 10px;
  font-size: 16px;
}
.seq ol {
  margin: 0;
  padding-left: 22px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: var(--text-2);
}
</style>