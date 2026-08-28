import { defineStore } from 'pinia'
import { fetchDashboard } from '@/api/dashboard'
import { DEMO_USER } from '@/utils/demo'

/** 工作台 Store：聚合画像 / 计划 / 评估 / 成长 / 长期记忆（只读快照）。 */
export const useDashboardStore = defineStore('dashboard', {
  state: () => ({
    userId: DEMO_USER,
    dashboard: null,
    loading: false,
    error: null,
  }),

  getters: {
    profile(state) {
      return state.dashboard?.profile || { skills: [], skill_count: 0 }
    },
    latestPlan(state) {
      return state.dashboard?.latest_plan || null
    },
    latestEvaluation(state) {
      return state.dashboard?.latest_evaluation || null
    },
    growth(state) {
      return state.dashboard?.growth || []
    },
    facts(state) {
      return state.dashboard?.facts || []
    },
  },

  actions: {
    async load() {
      this.loading = true
      this.error = null
      try {
        this.dashboard = await fetchDashboard(this.userId)
      } catch (err) {
        this.error = err?.message || '加载工作台失败'
        return null
      } finally {
        this.loading = false
      }
      return this.dashboard
    },
  },
})