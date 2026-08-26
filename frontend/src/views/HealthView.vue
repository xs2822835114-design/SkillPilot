<script setup>
import { useHealthStore } from '@/stores/health'

const health = useHealthStore()

function toneClass(tone) {
  return `tone-${tone || 'muted'}`
}

function fmtTime(d) {
  if (!d) return '—'
  return d.toLocaleString()
}
</script>

<template>
  <div class="health-page">
    <div class="card-header">
      <h2>服务健康状态</h2>
      <button class="refresh" :disabled="health.loading" @click="health.check()">
        {{ health.loading ? '检查中…' : '重新检查' }}
      </button>
    </div>

    <div v-if="!health.isChecked && !health.error && health.loading" class="hint">正在探测后端服务…</div>
    <div v-else-if="health.error && !health.isChecked" class="error">
      <p>无法连接后端服务：{{ health.error }}</p>
      <p class="sub">请确认 Flask 后端已启动（默认 :5000 ，见后端 docs/api_v1.md），前端已通过 Vite 代理转发。</p>
    </div>

    <div v-else-if="health.health" class="grid">
      <div class="card" :class="toneClass(health.health.tone)">
        <div class="card-label">整体状态</div>
        <div class="card-value badge">{{ health.health.status }}
          <span class="dot" />
        </div>
        <div class="card-sub">{{ health.health.statusText }}</div>
      </div>

      <div class="card" :class="toneClass(health.health.db.tone)">
        <div class="card-label">数据库 db</div>
        <div class="card-value">{{ health.health.db.text }}</div>
      </div>

      <div class="card" :class="toneClass(health.health.llm.tone)">
        <div class="card-label">大模型 llm</div>
        <div class="card-value">{{ health.health.llm.text }}</div>
      </div>

      <div class="card">
        <div class="card-label">服务版本</div>
        <div class="card-value">{{ health.health.version }}</div>
      </div>
    </div>

    <div class="footer">
      最近检查：{{ health.isChecked ? fmtTime(health.lastCheckedAt) : (health.loading ? '进行中' : '未检查') }}
      <span v-if="health.error">｜检查出错：{{ health.error }}</span>
    </div>
  </div>
</template>

<style scoped>
.health-page {
  max-width: 860px;
  margin: 0 auto;
  padding: 28px 20px;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.card-header h2 {
  margin: 0;
}
.refresh {
  padding: 8px 16px;
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 8px;
  font-weight: 500;
}
.refresh:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 18px;
  box-shadow: var(--shadow);
}
.card-label {
  font-size: 12px;
  color: var(--text-2);
  margin-bottom: 8px;
}
.card-value {
  font-size: 22px;
  font-weight: 700;
}
.card-sub {
  font-size: 13px;
  color: var(--text-2);
}
.badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--ok);
}
.tone-err,
.tone-err .dot {
  color: var(--danger);
  background: var(--danger);
}
.tone-warn {
  color: var(--warn);
}
.tone-warn .dot {
  background: var(--warn);
}
.hint {
  color: var(--text-2);
}
.error {
  background: var(--surface);
  border: 1px solid #fecaca;
  color: var(--danger);
  border-radius: var(--radius-md);
  padding: 18px;
}
.error .sub {
  color: var(--text-2);
  font-size: 13px;
}
.footer {
  margin-top: 16px;
  font-size: 12px;
  color: var(--text-2);
}
</style>