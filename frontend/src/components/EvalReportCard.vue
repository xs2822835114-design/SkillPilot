<script setup>
defineProps({
  evaluation: { type: Object, default: null },
  evaluating: { type: Boolean, default: false },
  error: { type: String, default: '' },
})
defineEmits(['evaluate', 'startPractice'])
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h3>代码评估</h3>
      <button class="primary" :disabled="evaluating" @click="$emit('evaluate')">
        {{ evaluating ? '评估中…' : '评估这份代码' }}
      </button>
    </div>

    <div v-if="error" class="err">{{ error }}</div>

    <div v-if="!evaluation" class="empty">
      <p>上传/粘贴一段代码并运行评估，系统将给出结构化评分、证据与下一步建议。</p>
    </div>

    <template v-else>
      <div class="score-row">
        <div class="score-big">
          <strong>{{ evaluation.overall_score }}</strong>
          <span>综合得分</span>
        </div>
        <div class="score-list">
          <div v-for="s in evaluation.skill_scores || []" :key="s.skill_id" class="score-line">
            <span>{{ s.skill_id }}</span>
            <span class="mini">理论 {{ s.theory }} · 实践 {{ s.practice }}</span>
          </div>
        </div>
        <div class="flags">
          <span v-if="evaluation.profile_updated" class="chip good">画像已更新</span>
          <span v-if="evaluation.replanned" class="chip warn">已触发再规划</span>
        </div>
      </div>

      <div class="block">
        <b>证据：</b>
        <ul>
          <li
            v-for="(ev, i) in evaluation.evidence || []"
            :key="i"
            :class="{ pass: ev.passed, fail: !ev.passed }"
          >
            <span class="mark">{{ ev.passed ? '✓' : '✗' }}</span>
            {{ ev.type }} —— {{ ev.message || '—' }}
          </li>
        </ul>
      </div>

      <div class="block">
        <b>下一步建议：</b>
        <ul>
          <li v-for="(r, i) in evaluation.next_recommendations || []" :key="i">→ {{ r }}</li>
        </ul>
      </div>

      <button class="ghost" @click="$emit('startPractice')">基于此评估重新发起实践任务</button>
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
.primary {
  font-size: 13px;
  padding: 6px 12px;
  border-radius: var(--radius-sm);
  background: var(--text);
  color: #fff;
}
.primary:hover { opacity: 0.92; }
.primary:disabled { opacity: 0.5; cursor: default; }
.ghost {
  font-size: 12px;
  color: var(--text-2);
  padding: 5px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
}
.ghost:hover { background: var(--surface-hover); color: var(--text); }
.err {
  padding: 12px;
  border-radius: var(--radius-sm);
  background: rgba(226, 59, 59, 0.08);
  color: #c03a3a;
  font-size: 13px;
  margin-bottom: 10px;
}
.empty {
  padding: 26px 0;
  text-align: center;
  color: var(--text-2);
  font-size: 14px;
}
.score-row {
  display: flex;
  align-items: center;
  gap: 22px;
  flex-wrap: wrap;
  padding: 12px;
  border-radius: var(--radius-sm);
  background: var(--surface-hover);
  margin-bottom: 14px;
}
.score-big {
  display: flex;
  flex-direction: column;
  align-items: center;
}
.score-big strong {
  font-size: 34px;
  line-height: 1;
  color: var(--text);
}
.score-big span {
  font-size: 12px;
  color: var(--text-3);
}
.score-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}
.mini {
  color: var(--text-3);
  font-size: 12px;
  margin-left: 6px;
}
.flags {
  margin-left: auto;
  display: flex;
  gap: 8px;
}
.chip {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 999px;
}
.good { background: rgba(63, 178, 127, 0.15); color: #2f9e6f; }
.warn { background: rgba(224, 144, 4, 0.15); color: #c07a06; }
.block {
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--text-2);
}
.block ul {
  margin: 6px 0 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.mark {
  font-weight: 700;
}
.pass { color: #2f9e6f; }
.fail { color: #c03a3a; }
</style>