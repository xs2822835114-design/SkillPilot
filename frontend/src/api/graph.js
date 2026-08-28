/**
 * API 层 · 技能图谱（只读）。
 * GET /api/v1/graph → { nodes:[{id,name,category}], edges:[{source,target}] }
 */
import http from './http'

export function fetchSkillGraph() {
  return http.get('/api/v1/graph')
}