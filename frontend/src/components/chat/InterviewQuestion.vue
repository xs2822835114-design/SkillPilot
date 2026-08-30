<script setup>
import { computed, ref } from 'vue'
import { useChatStore } from '@/stores/chat'

/**
 * 技能访谈题：把后端 interview_node 产出的结构化题目渲染成
 * 「类型化题面 + 可勾选技术性选项 + 自由填写补充说明」的交互卡片。
 *
 * 提交时把勾选的选项文案 + 补充说明拼成一条普通消息发送，
 * 交给 estimate_level（Skill Engine）从证据推导技能等级。
 */
const props = defineProps({
  question: { type: Object, required: true },
  messageId: { type: String, default: '' },
})

const chat = useChatStore()
const selected = ref([]) // 勾选项的 id
const freeText = ref('')
const submitted = ref(false)

const options = computed(() => props.question?.options || [])
const skillName = computed(() => props.question?.skill_name || '')
const question = computed(() => props.question?.question || props.question?.prompt || '')
const questionType = computed(() => props.question?.question_type || '')
const capability = computed(() => props.question?.capability || '')
const index = computed(() => props.question?.index || 0)
const total = computed(() => props.question?.total || 0)

const typeLabel = computed(() => {
  return (
    {
      concept: '概念',
      experience: '经验',
      api: 'API',
      implementation: '实现',
      scenario: '场景',
      open: '开放',
    }[questionType.value] || '能力'
  )
})

// 仅当它是「最新的那条 assistant 消息」且尚未作答时才可交互，避免旧题重复作答
const isActive = computed(() => {
  const last = [...chat.messages].reverse().find((m) => m.role === 'assistant')
  return last?.id === props.messageId && !submitted.value
})

function toggle(id) {
  if (!isActive.value) return
  selected.value = selected.value.includes(id)
    ? selected.value.filter((i) => i !== id)
    : [...selected.value, id]
}

function submit() {
  if (!isActive.value) return
  const chosen = options.value.filter((o) => selected.value.includes(o.id)).map((o) => o.text)
  let text = chosen.join('；')
  const note = freeText.value.trim()
  if (note) text += (text ? '。补充说明：' : '') + note
  text = text.trim()
  if (!text) return
  submitted.value = true
  chat.sendMessage(text)
}
</script>

<template>
  <div class="iq">
    <div class="iq-head">
      <span class="iq-tag">{{ typeLabel }}评估</span>
      <span class="iq-count">{{ index }}/{{ total }}</span>
    </div>
    <p class="iq-title">
      {{ question }}
      <span v-if="capability" class="iq-cap">（关于 <b>{{ skillName }}</b> 的「{{ capability }}」）</span>
    </p>

    <div class="iq-options">
      <label
        v-for="o in options"
        :key="o.id"
        class="iq-opt"
        :class="{ checked: selected.includes(o.id), disabled: !isActive }"
      >
        <input
          type="checkbox"
          :checked="selected.includes(o.id)"
          :disabled="!isActive"
          @change="toggle(o.id)"
        />
        <span class="iq-opt-text">{{ o.text }}</span>
      </label>
    </div>

    <textarea
      v-model="freeText"
      class="iq-free"
      rows="2"
      :disabled="!isActive"
      placeholder="补充说明：写下你的具体经历、做法或想澄清的技术点（可选）"
    />

    <div class="iq-foot">
      <button v-if="isActive" class="iq-submit" :disabled="!selected.length && !freeText.trim()" @click="submit">
        提交答案
      </button>
      <span v-else class="iq-done">已提交，等待下一题…</span>
    </div>
  </div>
</template>

<style scoped>
.iq {
  margin-top: 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
  padding: 12px 14px;
}
.iq-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.iq-tag {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
}
.iq-count {
  font-size: 12px;
  color: var(--text-3);
}
.iq-title {
  margin: 0 0 10px;
  font-size: 14px;
  color: var(--text);
  line-height: 1.6;
}
.iq-cap {
  color: var(--text-3);
  font-size: 12.5px;
}
.iq-cap b {
  color: var(--accent);
  font-weight: 600;
}
.iq-options {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.iq-opt {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 7px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 13.5px;
  line-height: 1.5;
  color: var(--text);
  transition: border-color 0.12s, background 0.12s;
}
.iq-opt:hover {
  border-color: var(--accent);
}
.iq-opt.checked {
  border-color: var(--accent);
  background: var(--accent-soft);
}
.iq-opt.disabled {
  cursor: default;
  opacity: 0.7;
}
.iq-opt input {
  margin-top: 3px;
  accent-color: var(--accent);
  flex: none;
}
.iq-opt-text {
  flex: 1;
  min-width: 0;
}
.iq-free {
  width: 100%;
  margin-top: 10px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text);
  font: inherit;
  font-size: 13.5px;
  line-height: 1.5;
  resize: vertical;
}
.iq-free:disabled {
  opacity: 0.7;
}
.iq-foot {
  margin-top: 10px;
  display: flex;
  align-items: center;
}
.iq-submit {
  padding: 6px 16px;
  font-size: 13px;
  border-radius: var(--radius-sm);
  background: var(--text);
  color: #fff;
}
.iq-submit:hover:not(:disabled) {
  opacity: 0.9;
}
.iq-submit:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.iq-done {
  font-size: 12.5px;
  color: var(--text-3);
}
</style>