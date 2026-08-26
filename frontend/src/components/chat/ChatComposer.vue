<script setup>
import { ref } from 'vue'

const props = defineProps({
  sending: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['send'])

const draft = ref('')

function submit() {
  const text = (draft.value || '').trim()
  if (!text || props.sending || props.disabled) return
  emit('send', text)
  draft.value = ''
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    submit()
  }
}
</script>

<template>
  <div class="composer">
    <div class="box" :class="{ focus: false }">
      <textarea
        v-model="draft"
        rows="1"
        :disabled="sending || disabled"
        placeholder="给 SkillMap 发送消息…"
        @keydown="onKeydown"
      />
      <button class="send" :disabled="sending || disabled || !draft.trim()" :title="sending ? '正在回复' : '发送'" @click="submit">
        <svg v-if="!sending" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="22" y1="2" x2="11" y2="13" />
          <polygon points="22 2 15 22 11 13 2 9 22 2" />
        </svg>
        <span v-else class="spinner" />
      </button>
    </div>
    <p class="hint">SkillMap 可能会犯错，请核查重要信息。</p>
  </div>
</template>

<style scoped>
.composer {
  max-width: 768px;
  width: 100%;
  margin: 0 auto;
  padding: 0 20px 12px;
}
.box {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 10px 10px 10px 16px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow);
  transition: box-shadow 0.15s, border-color 0.15s;
}
.box:focus-within {
  border-color: var(--text-2);
  box-shadow: var(--shadow-md);
}
textarea {
  flex: 1;
  resize: none;
  border: none;
  outline: none;
  background: transparent;
  font: inherit;
  font-size: 15px;
  line-height: 1.6;
  max-height: 200px;
  color: var(--text);
  padding: 6px 0;
}
textarea:disabled {
  opacity: 0.7;
}
.send {
  flex: none;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: var(--text);
  color: #fff;
  transition: opacity 0.15s;
}
.send:hover:not(:disabled) {
  opacity: 0.85;
}
.send:disabled {
  opacity: 0.2;
  cursor: not-allowed;
}
.spinner {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.hint {
  margin: 8px 0 0;
  text-align: center;
  font-size: 12px;
  color: var(--text-3);
}
</style>