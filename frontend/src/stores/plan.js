import { defineStore } from 'pinia'
import { fetchPlanList, generatePlan, requestGap, fetchPlanDetail, transitionTask } from '@/api/plan'
import { DEMO_USER, DEMO_TARGET_ROLE } from '@/utils/demo'

/** 缺口报告 + 学习计划 Store（Gap Report 页 / Learning Plan 页共用）。 */
export const usePlanStore = defineStore('plan', {
  state: () => ({
    userId: DEMO_USER,
    targetRole: DEMO_TARGET_ROLE,
    // Gap
    gapReport: null,
    gapLoading: false,
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
    async requestGap() {
      this.gapLoading = true
      this.error = null
      try {
        const resp = await requestGap({
          userId: this.userId,
          targetRoles: [this.targetRole],
        })
        this.gapReport = resp.reports?.[0] || resp
      } catch (err) {
        this.error = err?.message || '缺口分析失败'
        return null
      } finally {
        this.gapLoading = false
      }
      return this.gapReport
    },

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

    async transition(task, action) {
      if (!this.currentPlan) return
      this.transitioningTaskId = task.task_id
      try {
        await transitionTask(this.currentPlan.plan_id, task.task_id, action)
        await this.loadPlan(this.currentPlan.plan_id)
      } catch (err) {
        this.error = err?.message || '任务流转失败'
      } finally {
        this.transitioningTaskId = null
      }
    },
  },
})