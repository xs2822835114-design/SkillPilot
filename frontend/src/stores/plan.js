import { defineStore } from 'pinia'
import { fetchPlanList, generatePlan, fetchPlanDetail, setTaskStatus, clearPlans } from '@/api/plan'
import { DEMO_USER, DEMO_TARGET_ROLE } from '@/utils/demo'

/** 学习计划 Store（Learning Plan 页使用）。 */
export const usePlanStore = defineStore('plan', {
  state: () => ({
    userId: DEMO_USER,
    targetRole: DEMO_TARGET_ROLE,
    // Plan
    planList: [],
    currentPlan: null,
    planLoading: false,
    transitioningTaskId: null,
    error: null,
  }),

  getters: {
    progress(state) {
      if (!state.currentPlan) return 0
      const m = state.currentPlan.metrics || {}
      return m.total_tasks ? Math.round((m.done_tasks / m.total_tasks) * 100) : 0
    },
    taskTree(state) {
      const phases = state.currentPlan?.phases || []
      return phases.map((p) => p.tasks || []).flat()
    },
  },

  actions: {
    async loadPlanList() {
      try {
        this.planList = await fetchPlanList(this.userId)
      } catch (err) {
        this.error = err?.message || '加载计划列表失败'
      }
      return this.planList
    },

    async generatePlan() {
      this.planLoading = true
      this.error = null
      try {
        this.currentPlan = await generatePlan({
          userId: this.userId,
          targetRoles: [this.targetRole],
        })
        await this.loadPlanList()
      } catch (err) {
        this.error = err?.message || '生成计划失败'
        return null
      } finally {
        this.planLoading = false
      }
      return this.currentPlan
    },

    async loadPlan(planId) {
      this.planLoading = true
      this.error = null
      try {
        this.currentPlan = await fetchPlanDetail(planId)
      } catch (err) {
        this.error = err?.message || '加载计划失败'
      } finally {
        this.planLoading = false
      }
      return this.currentPlan
    },

    async clearAll() {
      try {
        await clearPlans(this.userId)
      } catch (err) {
        this.error = err?.message || '清空学习计划失败'
      }
      this.planList = []
      this.currentPlan = null
      this.transitioningTaskId = null
      this.error = null
    },

    async setTaskStatus(task, mastered) {
      if (!this.currentPlan) return
      this.transitioningTaskId = task.task_id
      try {
        await setTaskStatus(this.currentPlan.plan_id, task.task_id, mastered ? 'done' : 'pending')
        await this.loadPlan(this.currentPlan.plan_id)
      } catch (err) {
        this.error = err?.message || '更新掌握状态失败'
      } finally {
        this.transitioningTaskId = null
      }
    },
  },
})