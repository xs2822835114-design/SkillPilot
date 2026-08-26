<script setup>
import { useHealthStore } from '@/stores/health'

const health = useHealthStore()

const tone = {
  ok: 'tone-ok',
  warn: 'tone-warn',
  err: 'tone-err',
}
</script>

<template>
  <div class="layout">
    <header class="topbar">
      <div class="topbar-left">
        <RouterLink class="brand" to="/">
          <span class="brand-mark">S</span>
        </RouterLink>
        <span class="model">SkillMap <em>v1</em></span>
      </div>

      <nav class="nav">
        <RouterLink to="/" exact-active-class="active">工作台</RouterLink>
        <RouterLink to="/graph" active-class="active">技能图谱</RouterLink>
        <RouterLink to="/gap" active-class="active">缺口报告</RouterLink>
        <RouterLink to="/plan" active-class="active">学习计划</RouterLink>
        <RouterLink to="/practice" active-class="active">实践·评估</RouterLink>
        <RouterLink to="/chat" active-class="active">对话</RouterLink>
        <RouterLink to="/health" active-class="active">服务健康</RouterLink>
      </nav>

      <div class="topbar-right">
        <span class="health-pill" :class="tone[health.health?.tone || 'muted']">
          <span class="dot" />
          {{ health.health ? health.health.statusText : health.loading ? '检查中' : '离线' }}
        </span>
      </div>
    </header>

    <main class="body">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.layout {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.topbar {
  height: 52px;
  flex: none;
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 0 16px;
  background: var(--bg);
  border-bottom: 1px solid var(--border);
}
.topbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.brand-mark {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: var(--text);
  color: #fff;
  font-weight: 700;
  font-size: 16px;
  display: grid;
  place-items: center;
}
.model {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}
.model em {
  font-style: normal;
  font-weight: 400;
  color: var(--text-3);
  font-size: 12px;
  margin-left: 4px;
}
.nav {
  margin-left: 12px;
  display: flex;
  gap: 2px;
}
.nav a {
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 14px;
  color: var(--text-2);
  transition: background 0.15s, color 0.15s;
}
.nav a:hover {
  background: var(--surface-hover);
  color: var(--text);
}
.nav a.active {
  background: var(--surface-hover);
  color: var(--text);
  font-weight: 600;
}
.topbar-right {
  margin-left: auto;
}
.health-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-2);
  padding: 5px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
}
.health-pill .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-3);
}
.tone-ok .dot {
  background: var(--ok);
}
.tone-warn .dot {
  background: var(--warn);
}
.tone-err .dot {
  background: var(--danger);
}
.body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
</style>