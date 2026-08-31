<script setup>
import { ref, watch, nextTick, onBeforeUnmount } from 'vue'
import { streamTeach, sendTeachingMessage } from '@/api/teaching'
import MarkdownRenderer from './MarkdownRenderer.vue'

const props = defineProps({
  plan: { type: Object, default: null },
  task: { type: Object, default: null },
})
const emit = defineEmits(['close', 'complete'])

const session = ref(null)
const opening = ref('')
const streaming = ref(false)
const error = ref('')
const turns = ref([])
const draft = ref('')
const sending = ref(false)

// 结构化内容按「概念→示例→练习」逐类增量补全（SSE content_part 事件逐个 push）
const concepts = ref([])
const examples = ref([])
const exercises = ref([])

const _bucket = { concepts, examples, exercises }

let aborter = null
let tStart = 0

const planId = () => props.plan?.plan_id

// 后端 turn {role,message,mode} → 前端 {role,content}
function toTurn(t) {
  return { role: t.role, content: t.message }
}

function applySession(sess) {
  session.value = sess
  opening.value = sess.opening || ''
  // 恢复历史回合（用户关闭窗口后再进入同一任务时由后端回传）
  turns.value = (sess.turns || []).map(toTurn)
  // done 携带完整 content，全量覆盖增量 refs，保证最终一致
  const c = sess.content || {}
  concepts.value = c.concepts || []
  examples.value = c.examples || []
  exercises.value = c.exercises || []
  console.debug(`[Teaching] done TTF(第一token)≈${tFirstToken ?? 'n/a'}ms TTC(完整内容)≈${tStart ? Math.round(performance.now() - tStart) : 'n/a'}ms`)
}

let tFirstToken = null

function start() {
  if (!props.task || !props.plan) return
  session.value = null
  opening.value = ''
  turns.value = []
  concepts.value = []
  examples.value = []
  exercises.value = []
  error.value = ''
  streaming.value = true
  tStart = performance.now()
  tFirstToken = null
  aborter?.abort()
  aborter = new AbortController()
  streamTeach(planId(), props.task.task_id, {
    signal: aborter.signal,
    onEvent: (evt) => {
      if (evt.type === 'delta') {
        if (tFirstToken === null) {
          tFirstToken = Math.round(performance.now() - tStart)
          console.debug(`[Teaching] 首 delta 到达：${tFirstToken}ms`)
        }
        opening.value += evt.text
      } else if (evt.type === 'content_part') {
        // 单个类生成完成 → 增量补齐对应数组
        const bucket = _bucket[evt.kind]
        if (bucket) bucket.value = bucket.value.concat(evt.items || [])
      } else if (evt.type === 'done') {
        applySession(evt)
        streaming.value = false
      } else if (evt.type === 'error') {
        error.value = evt.message || 'AI 教学生成失败'
        streaming.value = false
      }
    },
    onError: () => {
      error.value = '网络异常或流式失败，请重试'
      streaming.value = false
    },
  })
}

watch(() => [props.task?.task_id, props.task?.status], () => start(), { immediate: true })

onBeforeUnmount(() => aborter?.abort())

function pushTurn(role, content) {
  turns.value.push({ role, content })
  nextTick(() => {
    const el = document.getElementById('teach-chat')
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function send(raw) {
  const msg = (raw ?? draft.value).trim()
  if (!msg || sending.value || !session.value) return
  draft.value = ''
  pushTurn('user', msg)
  sending.value = true
  try {
    const turn = await sendTeachingMessage({ sessionId: session.value.session_id, message: msg })
    pushTurn('ai', turn.message)
  } catch (err) {
    pushTurn('ai', `（出错）${err?.message || '对话失败'}`)
  } finally {
    sending.value = false
  }
}

function quick(mode) {
  const map = { understand: '我理解了，继续讲下一部分', next: '继续', quiz: '给我出题' }
  send(map[mode])
}
</script>

<template>
  <Teleport to="body">
    <div v-if="task && plan" class="overlay" @click.self="emit('close')">
      <div class="panel">
        <header class="head">
          <div>
            <h3>{{ task.title }}</h3>
            <p v-if="session?.learning_objective" class="goal">🎯 {{ session.learning_objective }}</p>
          </div>
          <button class="close" @click="emit('close')">×</button>
        </header>

        <div class="body">
          <!-- 教学主体：首节流式 + 结构化内容 -->
          <div class="teach-main" id="teach-chat">
            <div class="block">
              <span class="label">AI 教学</span>
              <div class="ai-text">
                <span v-if="streaming && !opening" class="prep">
                  正在准备本次学习内容<span class="dots">…</span><span class="cursor2">▍</span>
                </span>
                <MarkdownRenderer v-if="opening" :content="opening" />
                <span class="cursor" v-else-if="streaming && opening">▍</span>
              </div>
            </div>

            <div v-if="error" class="err">{{ error }}<button class="link" @click="start">重试</button></div>

            <!-- 结构化内容按类独立展示：某类经 content_part 到达即显示，不依赖 done/session -->
            <div v-if="concepts.length" class="block">
              <span class="label">核心概念</span>
              <div v-for="c in concepts" :key="c.title" class="card">
                <b>{{ c.title }}</b>
                <p>{{ c.explanation }}</p>
              </div>
            </div>

            <div v-if="examples.length" class="block">
              <span class="label">代码示例</span>
              <div v-for="e in examples" :key="e.title" class="card">
                <b>{{ e.title }}</b>
                <p v-if="e.explanation">{{ e.explanation }}</p>
                <pre v-if="e.code" class="code">{{ e.code }}</pre>
              </div>
            </div>

            <div v-if="exercises.length" class="block">
              <span class="label">练习与验收</span>
              <div v-for="x in exercises" :key="x.title" class="card">
                <b>{{ x.title }}</b>
                <p>{{ x.instruction }}</p>
                <p v-if="x.expected_result" class="hint">期望结果：{{ x.expected_result }}</p>
              </div>
            </div>

            <!-- 多轮互动 -->
            <div v-for="(t, i) in turns" :key="i" class="turn" :class="t.role">
              <b>{{ t.role === 'user' ? '你' : 'AI' }}</b>
              <MarkdownRenderer v-if="t.role === 'ai'" class="turn-md" :content="t.content" />
              <p v-else>{{ t.content }}</p>
            </div>
            <div v-if="sending" class="turn ai"><p class="cursor-blank">正在思考…</p></div>
          </div>

          <!-- 快捷互动 + 输入 -->
          <div class="composer">
            <div class="quick" v-if="session && !streaming">
              <button class="chip" @click="quick('understand')">我理解了</button>
              <button class="chip" @click="quick('next')">继续</button>
              <button class="chip" @click="quick('quiz')">给我出题</button>
            </div>
            <div class="row">
              <input
                v-model="draft"
                class="input"
                :disabled="!session || streaming || sending"
                placeholder="追问、或输入“完成了”"
                @keyup.enter="send()"
              />
              <button class="primary" :disabled="!session || streaming || sending" @click="send()">发送</button>
            </div>
            <div class="foot">
              <button
                class="done"
                :disabled="task.status === 'done'"
                @click="emit('complete', task)"
              >
                {{ task.status === 'done' ? '已完成' : '完成本目标' }}
              </button>
              <span class="hint">完成教学后可将该小目标标记完成</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 30, 0.45);
  display: grid;
  place-items: center;
  z-index: 1000;
  padding: 24px;
}
.panel {
  width: 760px;
  max-width: 96vw;
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.25);
  overflow: hidden;
}
.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 16px 18px;
  border-bottom: 1px solid var(--border);
}
.head h3 { margin: 0; font-size: 16px; }
.goal { margin: 4px 0 0; font-size: 13px; color: var(--text-2); }
.close {
  border: none;
  background: transparent;
  font-size: 22px;
  line-height: 1;
  color: var(--text-2);
  cursor: pointer;
}
.body { display: flex; flex-direction: column; min-height: 0; }
.teach-main {
  overflow-y: auto;
  padding: 16px 18px;
  max-height: 52vh;
}
.block { margin-bottom: 16px; }
.label {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--accent);
  background: var(--accent-soft);
  padding: 2px 8px;
  border-radius: 999px;
  margin-bottom: 8px;
}
.ai-text { font-size: 14px; line-height: 1.7; color: var(--text); }
.prep { color: var(--text-2); font-size: 13px; }
.dots { animation: blink 1.2s infinite; }
.cursor2 { margin-left: 2px; animation: blink 0.9s infinite; color: var(--accent); }
.cursor { display: inline-block; margin-left: 1px; animation: blink 0.9s infinite; color: var(--accent); }
@keyframes blink { 50% { opacity: 0; } }
.card {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  margin-bottom: 8px;
  background: var(--bg-soft, #fafbfc);
  font-size: 13px;
}
.card p { margin: 4px 0 0; color: var(--text-2); line-height: 1.6; }
.code {
  background: #0f1720;
  color: #d6e2ea;
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 12px;
  overflow-x: auto;
  margin: 8px 0 0;
}
.hint { color: var(--accent); }
.err { font-size: 13px; color: #c03a3a; margin-bottom: 8px; }
.link { color: var(--accent); background: none; border: none; cursor: pointer; }
.turn { margin-bottom: 10px; font-size: 13px; }
.turn.user { text-align: right; }
.turn b { display: inline-block; margin-bottom: 2px; font-size: 12px; color: var(--text-3); }
.turn p {
  display: inline-block;
  max-width: 85%;
  text-align: left;
  margin: 0;
  padding: 8px 12px;
  border-radius: 10px;
  background: var(--accent-soft);
  color: var(--text);
  line-height: 1.6;
  white-space: pre-wrap;
}
.turn.user p { background: var(--accent); color: #fff; }
/* AI 回合的 Markdown 气泡：与 .turn p 保持一致的视觉（背景/圆角/内边距/限宽） */
.turn-md {
  display: inline-block;
  max-width: 85%;
  text-align: left;
  margin: 0;
  padding: 8px 12px;
  border-radius: 10px;
  background: var(--accent-soft);
  color: var(--text);
  line-height: 1.6;
}
.turn-md :deep(.markdown-body) { font-size: 13px; }
.cursor-blank { background: transparent !important; color: var(--text-3); }
.composer { border-top: 1px solid var(--border); padding: 12px 18px; }
.quick { display: flex; gap: 8px; margin-bottom: 10px; }
.chip {
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text);
  border-radius: 999px;
  padding: 4px 12px;
  font-size: 12px;
  cursor: pointer;
}
.chip:hover { border-color: var(--accent); color: var(--accent); }
.row { display: flex; gap: 8px; }
.input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg);
  color: var(--text);
  font-size: 13px;
}
.primary {
  padding: 8px 16px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--text);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
}
.primary:disabled { opacity: 0.5; cursor: not-allowed; }
.foot { display: flex; align-items: center; gap: 10px; margin-top: 12px; }
.done {
  padding: 7px 14px;
  border: none;
  border-radius: var(--radius-sm);
  background: #3fb27f;
  color: #fff;
  font-size: 13px;
  cursor: pointer;
}
.done:disabled { opacity: 0.6; cursor: default; }
.hint { font-size: 12px; color: var(--text-3); }
</style>