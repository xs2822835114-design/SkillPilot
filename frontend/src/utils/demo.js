/** 演示用默认用户（阶段 8 无鉴权，集中管理便于切换）。 */
export const DEMO_USER = import.meta.env.VITE_DEMO_USER_ID || 'demo_user'

/** 演示常用目标岗位 role_id（SkillPilot_role_competencies.json：RC013=Python 后端工程师）。 */
export const DEMO_TARGET_ROLE = import.meta.env.VITE_DEMO_TARGET_ROLE || 'RC013'