<script setup>
import { onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useDashboardStore } from '@/stores/dashboard'

const dash = useDashboardStore()
onMounted(() => dash.load())

const typeLabel = {
  profile_updated: '画像更新',
  gap_reported: '缺口分析',
  plan_created: '计划生成',
  practice_created: '实践任务',
  evaluation_done: '能力评估',
  replan: '再规划',
}
function labelOf(t) {
  return typeLabel[t] || t || '事件'
}
function pct(p) {
  return Math.round((p || 0) * 100)
}
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>工作台</h1>
      <p>技能画像 · 学习进度 · 评估结果 · 成长轨迹</p>
    </header>

    <div v-if="dash.loading" class="empty">加载中…</div>
    <div v-else-if="dash.error && !dash.dashboard" class="empty err">
      {{ dash.error }}
      <p class="hint">请先运行 <code>python -m scripts.demo_init</code> 初始化演示数据。</p>
    </div>

    <div v-else class="grid">
      <!-- 技能画像 -->
      <section class="card card-profile">
        <div class="card-head">
          <h3>技能画像</h3>
          <RouterLink to="/gap" class="link">去缺口分析 →</RouterLink>
        </div>
        <div class="skills">
          <div v-for="s in dash.profile.skills" :key="s.skill_id" class="skill">
            <div class="skill-top">
              <span class="skill-name">{{ s.name }}</span>
              <span class="skill-level">L{{ s.level }}</span>
            </div>
            <div class="meter">
              <span class="m-theory" :style="{ width: (s.theory_score || 0) + '%' }" />
              <span class="m-practice" :style="{ width: (s.practice_score || 0) + '%' }" />
            </div>
            <div class="skill-sub">
              <span>理论 {{ s.theory_score }}</span>
              <span>实践 {{ s.practice_score }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- 计划 + 评估 -->
      <section class="card">
        <div class="card-head"><h3>学习计划</h3><RouterLink to="/plan" class="link">详情 →</RouterLink></div>
        <template v-if="dash.latestPlan">
          <div class="big" :data-empty="false">{{ pct(dash.latestPlan.progress) }}%</div>
          <p class="goal">{{ dash.latestPlan.goal }}</p>
          <div class="line"><span>{{ dash.latestPlan.done_tasks }}/{{ dash.latestPlan.total_tasks }} 任务</span></div>
        </template>
        <p v-else class="none">暂无计划</p>
      </section>

      <section class="card">
        <div class="card-head"><h3>最近评估</h3><RouterLink to="/practice" class="link">去实践 →</RouterLink></div>
        <template v-if="dash.latestEvaluation">
          <div class="big">{{ dash.latestEvaluation.overall_score }}</div>
          <p class="goal">{{ dash.latestEvaluation.skill_id }}</p>
          <div class="line">
            <span>已{{ dash.latestEvaluation.replanned ? '触发' : '未触发' }}再规划</span>
          </div>
        </template>
        <p v-else class="none">暂无评估</p>
      </section>

      <!-- 成长轨迹 -->
      <section class="card card-growth">
        <div class="card-head">
          <h3>成长轨迹</h3>
          <RouterLink to="/chat" class="link">去对话 →</RouterLink>
        </div>
        <div v-if="!dash.growth.length" class="none">暂无明显事件</div>
        <ol class="timeline">
          <li v-for="g in dash.growth" :key="g.id">
            <span class="tl-dot" />
            <div class="tl-body">
              <span class="tl-type">{{ labelOf(g.event_type) }}</span>
              <span class="tl-summary">{{ g.summary }}</span>
            </div>
          </li>
        </ol>

        <div v-if="dash.facts.length" class="facts">
          <b>长期记忆</b>
          <p v-for="f in dash.facts" :key="f.key">· {{ f.text }}</p>
        </div>
      </section>
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
  margin: 0 0 20px;
  color: var(--text-2);
  font-size: 14px;
}
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.grid .card-growth,
.grid .card-profile {
  grid-column: 1 / -1;
}
.card {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
  padding: 18px;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.card-head h3 {
  margin: 0;
  font-size: 16px;
}
.link {
  font-size: 13px;
  color: var(--text-2);
}
.link:hover { color: var(--text); }
.skills {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 12px;
}
.skill {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
}
.skill-top {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  margin-bottom: 6px;
}
.skill-name { font-weight: 600; }
.skill-level { color: var(--text-3); }
.meter {
  height: 6px;
  border-radius: 999px;
  overflow: hidden;
  background: var(--surface-hover);
  display: flex;
}
.m-theory { background: linear-gradient(90deg, #5ce1ff, #7c5cff); height: 100%; }
.m-practice { background: #ffd166; height: 100%; }
.skill-sub {
  display: flex;
  gap: 10px;
  font-size: 11px;
  color: var(--text-3);
  margin-top: 4px;
}
.big {
  font-size: 36px;
  font-weight: 700;
}
.goal {
  margin: 4px 0 6px;
  color: var(--text-2);
  font-size: 13px;
}
.line {
  font-size: 13px;
  color: var(--text-2);
}
.none {
  color: var(--text-3);
  font-size: 13px;
  padding: 8px 0;
}
.timeline {
  list-style: none;
  margin: 0;
  padding: 0;
}
.timeline li {
  display: flex;
  gap: 10px;
  padding: 6px 0;
}
.tl-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #7c5cff;
  margin-top: 5px;
  flex: none;
}
.tl-body {
  display: flex;
  flex-direction: column;
  font-size: 13px;
}
.tl-type {
  color: var(--text-3);
  font-size: 11px;
}
.facts {
  margin-top: 14px;
  border-top: 1px solid var(--border);
  padding-top: 10px;
  font-size: 13px;
  color: var(--text-2);
}
.facts p { margin: 4px 0; }
.empty {
  text-align: center;
  color: var(--text-2);
  padding: 60px 0;
}
.err { color: #c03a3a; }
.hint {
  color: var(--text-2);
  font-size: 13px;
  margin-top: 8px;
}
code {
  background: var(--surface-hover);
  padding: 1px 6px;
  border-radius: 6px;
}
</style>