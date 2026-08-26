/**
 * API 层 · 学习计划（阶段 5 接口 + 阶段 8 plan/list）。
 */
import http from './http'

/** POST /api/v1/gap/request → 缺口报告（Gap 页复用该服务端能力） */
export function requestGap({ userId, targetRoles = [], targetSkills = [] }) {
  return http.post('/api/v1/gap/request', {
    user_id: userId,
    target_roles: targetRoles,
    target_skills: targetSkills,
  })
}

/** POST /api/v1/plan/generate → 生成学习计划（B 通道：自算缺口） */
export function generatePlan({ userId, targetRoles = [], targetSkills = [], hoursPerWeek = 5 }) {
  return http.post('/api/v1/plan/generate', {
    user_id: userId,
    target_roles: targetRoles,
    target_skills: targetSkills,
    available_hours_per_week: hoursPerWeek,
  })
}

/** GET /api/v1/plan/list?user_id= → 计划摘要列表 */
export function fetchPlanList(userId) {
  return http.get('/api/v1/plan/list', { params: { user_id: userId } })
}

/** GET /api/v1/plan/<plan_id> → 计划详情 */
export function fetchPlanDetail(planId) {
  return http.get(`/api/v1/plan/${encodeURIComponent(planId)}`)
}

/** POST /api/v1/plan/<id>/tasks/<task>/transition → 任务流转（action: start|complete） */
export function transitionTask(planId, taskId, action) {
  return http.post(
    `/api/v1/plan/${encodeURIComponent(planId)}/tasks/${encodeURIComponent(taskId)}/transition`,
    { action },
  )
}