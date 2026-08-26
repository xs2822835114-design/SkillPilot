<script setup>
defineProps({
  message: { type: Object, required: true },
})
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
      <p v-else class="text">{{ message.content || '…' }}</p>
      <div v-if="message.reason && message.role === 'assistant'" class="meta">
        {{ message.reason }}
      </div>
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
</style>