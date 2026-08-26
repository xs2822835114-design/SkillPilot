/**
 * API 层 · 实践任务 + 能力评估（阶段 6 + 阶段 8 演示收口）。
 */
import http from './http'

/** POST /api/v1/practice/generate → 任务 → 实践计划 */
export function generatePractice({ userId, taskId, skillId }) {
  return http.post('/api/v1/practice/generate', {
    user_id: userId,
    task_id: taskId,
    skill_id: skillId,
  })
}

/** GET /api/v1/practice/<practice_id> → 实践详情 */
export function fetchPractice(practiceId) {
  return http.get(`/api/v1/practice/${encodeURIComponent(practiceId)}`)
}

/** POST /api/v1/evaluation/artifact → 上传代码片段 */
export function uploadArtifact({ userId, practiceId, language = 'python', filename, content, testContent }) {
  return http.post('/api/v1/evaluation/artifact', {
    user_id: userId,
    practice_id: practiceId,
    language,
    filename,
    content,
    test_content: testContent ?? null,
  })
}

/** POST /api/v1/evaluation/evaluate → 评估（可触发再规划） */
export function evaluateCode({ userId, practiceId, triggerReplan = true }) {
  return http.post('/api/v1/evaluation/evaluate', {
    user_id: userId,
    practice_id: practiceId,
    trigger_replan: triggerReplan,
  })
}