<script setup>
/**
 * MarkdownRenderer —— 统一的安全 Markdown 渲染组件（所有 Agent 消息共用）。
 *
 * 管线（职责分离）：后端永远返回 Markdown 字符串
 *   LLM → Markdown → API/SSE → Vue → MarkdownRenderer → HTML
 *
 * 安全：markdown-it 关闭 raw HTML → 输出 HTML 仅含解析产物；
 * DOMPurify 二次清洗，拦截 javascript: 等危险链接 / 残余事件属性。
 * content 为响应式数据，流式增量追加时 computed 自动重解析重渲染。
 */
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import taskLists from 'markdown-it-task-lists'

const props = defineProps({
  content: { type: String, default: '' },
})

const md = new MarkdownIt({
  html: false, // 禁止把消息中的原始 HTML 当作结构执行，统一交由 Markdown 语法 + DOMPurify
  linkify: true, // 自动把裸 URL / 邮箱转为链接
  breaks: false,
  typographer: false,
})
md.use(taskLists, { enabled: true, label: true, labelAfter: true })

const rendered = computed(() => {
  const src = props.content || ''
  if (!src) return ''
  const html = md.render(src) // Markdown → HTML（原样保留空格/换行结构）
  return DOMPurify.sanitize(html, {
    ADD_ATTR: ['target', 'rel', 'checked', 'disabled'],
  })
})
</script>

<template>
  <div class="markdown-body" v-html="rendered" />
</template>

<style scoped>
/* 统一 Markdown 正文样式。子元素由 v-html 生成，用 :deep 使其生效 */
.markdown-body {
  color: var(--text);
  font-size: 14px;
  line-height: 1.7;
  word-break: break-word;
  overflow-wrap: break-word;
}
.markdown-body :deep(> :first-child) { margin-top: 0; }
.markdown-body :deep(> :last-child) { margin-bottom: 0; }

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  color: var(--text);
  line-height: 1.3;
  margin: 1.1em 0 0.5em;
  font-weight: 650;
}
.markdown-body :deep(h1) { font-size: 1.4em; padding-bottom: 0.3em; border-bottom: 1px solid var(--border); }
.markdown-body :deep(h2) { font-size: 1.22em; }
.markdown-body :deep(h3) { font-size: 1.08em; }
.markdown-body :deep(h4) { font-size: 1em; }

.markdown-body :deep(p) { margin: 0.5em 0; }
.markdown-body :deep(a) {
  color: var(--primary, #2563eb);
  text-decoration: underline;
  overflow-wrap: break-word;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) { margin: 0.5em 0; padding-left: 1.5em; }
.markdown-body :deep(li) { margin: 0.25em 0; }
.markdown-body :deep(li > ul),
.markdown-body :deep(li > ol) { margin: 0.2em 0; }

.markdown-body :deep(blockquote) {
  margin: 0.6em 0;
  padding: 0.1em 1em;
  color: var(--text-2);
  border-left: 3px solid var(--border-strong);
  background: var(--bg-soft, #fafbfc);
}

/* 行内代码 */
.markdown-body :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
  font-size: 0.88em;
  background: var(--border);
  color: var(--text);
  padding: 0.15em 0.4em;
  border-radius: 4px;
}

/* 代码块（含语言标签 <pre><code>） */
.markdown-body :deep(pre) {
  max-width: 100%;
  overflow-x: auto;
  margin: 0.6em 0;
  padding: 12px 14px;
  background: #0f1720;
  color: #d6e2ea;
  border-radius: 8px;
  line-height: 1.55;
  white-space: pre;
}
.markdown-body :deep(pre code) {
  background: transparent;
  padding: 0;
  font-size: 12.5px;
}
.markdown-body :deep(pre code::before),
.markdown-body :deep(pre code::after) { content: none; }

/* 表格：允许横向滚动 */
.markdown-body :deep(table) {
  border-collapse: collapse;
  margin: 0.6em 0;
  display: block;
  max-width: 100%;
  overflow-x: auto;
  border-spacing: 0;
}
.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--border);
  padding: 6px 12px;
  text-align: left;
  font-size: 13px;
}
.markdown-body :deep(th) {
  background: var(--bg-soft, #f2f4f7);
  font-weight: 600;
}
.markdown-body :deep(tbody tr:nth-child(even)) { background: var(--bg-soft, #fafbfc); }

/* 任务列表复选框 */
.markdown-body :deep(.task-list-item) { list-style: none; }
.markdown-body :deep(.task-list-item input[type="checkbox"]) {
  margin: 0 0.35em 0 -1.2em;
  vertical-align: middle;
  accent-color: var(--accent);
}

/* 强调/删除线文字 */
.markdown-body :deep(del) { color: var(--text-3); }
</style>