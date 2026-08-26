import { getHealth } from '@/api/health'

/** 后端 db/llm 字段 → 前端展示文案与颜色 */
const STATE_LABEL = {
  ok: { text: '正常', tone: 'ok' },
  down: { text: '故障', tone: 'err' },
  disabled: { text: '未配置', tone: 'muted' },
}

/**
 * 服务层 · 健康检查。
 * 封装「拉数据 + 归一化为视图模型」，视图不直接依赖 API 层结构。
 */
export async function fetchHealthStatus() {
  const raw = await getHealth()
  return normalize(raw)
}

/** 将后端契约映射为前端视图模型（UI 只认此结构） */
export function normalize(raw) {
  const statusTone = raw.status === 'up' ? 'ok' : raw.status === 'degraded' ? 'warn' : 'err'
  return {
    status: raw.status,
    statusText: statusTone === 'ok' ? '运行正常' : statusTone === 'warn' ? '降级运行' : '异常',
    tone: statusTone,
    version: raw.version,
    db: buildState(raw.db),
    llm: buildState(raw.llm),
    // 补充时间戳，便于 UI 展示最近检查时间
    checkedAt: new Date(),
  }
}

function buildState(value) {
  const base = STATE_LABEL[value] || { text: value, tone: 'muted' }
  return { value, text: base.text, tone: base.tone }
}