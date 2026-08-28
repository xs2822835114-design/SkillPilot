/**
 * API 层 · 工作台 Dashboard + 技能图谱（阶段 8 只读聚合接口）。
 * 依赖 http 拦截器统一解壳：成功直接返回 data。
 */
import http from './http'

/**
 * GET /api/v1/dashboard/<user_id>
 * 返回 DashboardDTO：{ user_id, profile, latest_plan, latest_evaluation, growth, facts }
 * @param {string} userId
 */
export function fetchDashboard(userId) {
  return http.get(`/api/v1/dashboard/${encodeURIComponent(userId)}`)
}

/**
 * GET /api/v1/graph
 * 返回 { nodes:[{id,name,category}], edges:[{source,target}] }
 */
export function fetchSkillGraph() {
  return http.get('/api/v1/graph')
}