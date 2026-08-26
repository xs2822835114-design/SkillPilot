/**
 * API 层 · 学习计划（阶段 5 接口 + 阶段 8 plan/list）。
 */
import http from './http'

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

/** DELETE /api/v1/plan/clear?user_id= → 清空某用户的全部学习计划（清除缓存用） */
export function clearPlans(userId) {
  return http.delete('/api/v1/plan/clear', { params: { user_id: userId } })
}

/** POST /api/v1/plan/<id>/tasks/<task>/transition → 任务流转（action: start|complete） */
export function transitionTask(planId, taskId, action) {
  return http.post(
    `/api/v1/plan/${encodeURIComponent(planId)}/tasks/${encodeURIComponent(taskId)}/transition`,
    { action },
  )
}

/** POST /api/v1/plan/<id>/tasks/<task>/status → 直接设置任务状态（勾选「已掌握」用） */
export function setTaskStatus(planId, taskId, status) {
  return http.post(
    `/api/v1/plan/${encodeURIComponent(planId)}/tasks/${encodeURIComponent(taskId)}/status`,
    { status },
  )
}