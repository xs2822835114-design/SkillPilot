/**
 * API 层 · 健康检查接口模块。
 * 只声明请求路径与返回结构，不含业务判断（状态归因在 services 层）。
 */
import http from './http'

/**
 * GET /health
 * @returns {Promise<{status:string,version:string,db:string,llm:string}>}
 */
export function getHealth() {
  return http.get('/health')
}