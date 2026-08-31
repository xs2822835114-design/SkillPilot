<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import ArtifactPanel from './ArtifactPanel.vue'
import TracePanel from './TracePanel.vue'
import MarkdownRenderer from './../MarkdownRenderer.vue'

const props = defineProps({
  message: { type: Object, required: true },
})
const router = useRouter()

// artifacts.goto → 跳转到对应页面查看完整结果
const PAGE_PATH = {
  chat: '/chat',
  plan: '/plan',
  graph: '/graph',
}
const GOTO_LABEL = {
  plan: '查看学习计划',
  graph: '查看技能图谱',
  chat: '继续对话',
}
const goto = computed(() => props.message?.artifacts?.goto || null)
const gotoPath = computed(() => (goto.value?.page ? PAGE_PATH[goto.value.page] || '/' : null))
const gotoLabel = computed(() => GOTO_LABEL[goto.value?.page] || '查看详情')

function goTo() {
  if (gotoPath.value) router.push(gotoPath.value)
}

// 阶段总预计小时数（用于卡片右上角概览）
function phaseHours(phase) {
  const tasks = phase?.tasks || []
  const total = tasks.reduce((s, t) => s + Number(t.estimated_hours || 0), 0)
  return Math.round(total)
}
</script>

<template>
  <div class="msg" :class="message.role">
    <!-- agent 头像在左 -->
    <span v-if="message.role === 'assistant'" class="avatar assistant">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
        <path d="M6 11.5h4.5V7H6v4.5zM13.5 7v4.5H18V7h-4.5zM6 17h4.5v-4.5H6V17zM13.5 17H18v-4.5h-4.5V17z" />
      </svg>
    </span>

    <div class="bubble-wrap">
      <div v-if="message.status === 'error'" class="error">
        {{ message.error || '请求失败，请稍后重试' }}
      </div>
      <!-- 用户消息：保持纯文本渲染，不做 Markdown / 不当作 HTML 执行 -->
      <p v-else-if="message.role === 'user'" class="text">
        {{ message.content }}<span v-if="message.status === 'streaming'" class="caret" />
      </p>
      <!-- Agent 消息：统一走 MarkdownRenderer 安全渲染 -->
      <div v-else class="text md-content">
        <MarkdownRenderer v-if="message.content" :content="message.content" />
        <span v-else>…</span>
        <span v-if="message.status === 'streaming'" class="caret" />
      </div>

      <!-- 计划正在生成：已预判定为计划意图但阶段尚未到达时，显示生动的生成中提示 -->
      <div
        v-if="
          message.role === 'assistant' &&
          message.status === 'streaming' &&
          message.planBuilding &&
          !(message.plan && message.plan.phases && message.plan.phases.length)
        "
        class="plan-building-card"
      >
        <span class="plan-spinner" />
        正在为你生成分阶段学习计划…
      </div>

      <!-- 学习计划：以卡片形式展示，结构化事件增量生成时实时生长 -->
      <div
        v-if="message.plan && message.plan.phases && message.plan.phases.length"
        class="plan-cards"
      >
        <div v-for="(phase, idx) in message.plan.phases" :key="phase.phase_id" class="plan-card">
          <div class="plan-card-head">
            <span class="plan-num">{{ idx + 1 }}</span>
            <span class="plan-title">{{ phase.title || '阶段' }}</span>
            <span class="plan-meta">{{ (phase.tasks || []).length }} 个任务 · {{ phaseHours(phase) }}h</span>
          </div>
          <div class="plan-card-body">
            <div v-for="t in phase.tasks" :key="t.task_id" class="plan-task">
              <span class="plan-check">☐</span>
              <span class="plan-task-title">{{ t.title }}</span>
              <em v-if="t.estimated_hours" class="plan-hours">{{ t.estimated_hours }}h</em>
            </div>
          </div>
        </div>
        <div v-if="message.status === 'streaming'" class="plan-building">正在生成…</div>
      </div>
      <span v-if="message.status === 'ok' && message.interrupted" class="interrupted">· 已停止输出</span>
      <button
        v-if="gotoPath && message.role === 'assistant' && message.status === 'ok'"
        class="goto-btn"
        @click="goTo"
      >
        {{ gotoLabel }} →
      </button>
      <ArtifactPanel
        v-if="message.role === 'assistant' && message.status === 'ok'"
        :artifacts="message.artifacts"
      />
      <TracePanel
        v-if="message.role === 'assistant' && (message.route || message.reason || (message.steps && message.steps.length))"
        :route="message.route"
        :reason="message.reason"
        :steps="message.steps"
      />
    </div>

    <!-- 用户头像在右 -->
    <span v-if="message.role === 'user'" class="avatar user">我</span>
  </div>
</template>

<style scoped>
.msg {
  display: flex;
  gap: 14px;
  padding: 20px 0;
}
/* 用户消息靠右 */
.msg.user {
  justify-content: flex-end;
}
.msg.user .bubble-wrap {
  display: flex;
  justify-content: flex-end;
}
.msg.user .text {
  max-width: 72%;
  background: #eceff5;
  border: 1px solid #e2e6ee;
  color: #111;
  padding: 10px 14px;
  border-radius: 18px 18px 4px 18px;
}
.msg.user .avatar {
  order: 2;
}
.avatar {
  flex: none;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 600;
  margin-top: 2px;
}
.avatar.assistant {
  background: var(--text);
  color: #fff;
}
.avatar.user {
  background: var(--text);
  color: #fff;
  font-size: 12px;
  order: 2;
}
.bubble-wrap {
  flex: 1;
  min-width: 0;
}
.text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.75;
  color: var(--text);
  font-size: 15px;
}
/* Agent 消息的 Markdown 容器：交给 .markdown-body 处理块级排版，避免继承 pre-wrap */
.md-content {
  white-space: normal;
  line-height: 1.7;
  font-size: 14px;
}
.md-content :deep(.markdown-body) { font-size: 14px; }
.meta {
  margin-top: 8px;
  font-size: 12.5px;
  color: var(--text-3);
  background: var(--bg-soft);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 6px 10px;
}
.error {
  color: var(--danger);
  font-size: 14px;
}
.caret {
  display: inline-block;
  margin-left: 1px;
  width: 2px;
  height: 1em;
  vertical-align: text-bottom;
  background: var(--text);
  animation: blink 1s steps(1) infinite;
}
@keyframes blink {
  0%, 50% { opacity: 1; }
  50.01%, 100% { opacity: 0; }
}
.interrupted {
  display: inline-block;
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-3);
}
/* 学习计划：卡片式可视化 */
.plan-building-card {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 10px 12px;
  font-size: 13px;
  color: var(--text-2);
  background: var(--bg-soft, #fafbfc);
  border: 1px dashed var(--border);
  border-radius: var(--radius-md);
}
.plan-spinner {
  flex: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.plan-cards {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.plan-card {
  background: var(--bg-soft, #fff);
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent);
  border-radius: var(--radius-md);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  overflow: hidden;
}
.plan-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px 8px;
}
.plan-num {
  flex: none;
  width: 20px;
  height: 20px;
  border-radius: 6px;
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  background: var(--accent);
}
.plan-title {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}
.plan-meta {
  flex: none;
  font-style: normal;
  font-size: 11px;
  color: var(--text-3);
  white-space: nowrap;
}
.plan-card-body {
  display: flex;
  flex-direction: column;
  padding: 2px 12px 10px;
}
.plan-task {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 4px 0;
  font-size: 13px;
  color: var(--text-2);
}
.plan-check { color: var(--text-3); flex: none; }
.plan-task-title { flex: 1; min-width: 0; }
.plan-hours {
  flex: none;
  font-style: normal;
  font-size: 11px;
  color: var(--text-3);
  background: var(--border);
  border-radius: 999px;
  padding: 1px 8px;
}
.plan-building { margin-top: 2px; font-size: 12px; color: var(--text-3); }
.goto-btn {
  display: inline-block;
  margin-top: 10px;
  padding: 6px 14px;
  font-size: 13px;
  color: var(--primary, #2563eb);
  background: var(--bg-soft);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s ease;
}
.goto-btn:hover {
  background: var(--border);
}
</style>