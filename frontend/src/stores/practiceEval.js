import { defineStore } from 'pinia'
import { generatePractice, uploadArtifact, evaluateCode } from '@/api/practice'
import { DEMO_USER } from '@/utils/demo'

/** 实践 · 评估 Store（Practice·Evaluation 页）。 */
export const usePracticeEvalStore = defineStore('practiceEval', {
  state: () => ({
    userId: DEMO_USER,
    target: null, // { plan_id, task_id, skill_id }
    practice: null,
    evaluation: null,
    generating: false,
    evaluating: false,
    code: '',
    testCode: '',
    error: null,
    history: [],
  }),

  actions: {
    /** 由某条 LearningTask 发起实践 */
    async startPractice(task) {
      this.generating = true
      this.error = null
      try {
        this.practice = await generatePractice({
          userId: this.userId,
          taskId: task.task_id,
          skillId: task.skill_id,
        })
      } catch (err) {
        this.error = err?.message || '生成实践任务失败'
        return null
      } finally {
        this.generating = false
      }
      return this.practice
    },

    async uploadAndCodeFile({ filename, content, testContent }) {
      if (!this.practice) return null
      const result = await uploadArtifact({
        userId: this.userId,
        practiceId: this.practice.practice_id,
        filename,
        content,
        testContent,
      })
      return result
    },

    async evaluate({ code, testCode, filename = 'solution.py', triggerReplan = true } = {}) {
      if (!this.practice) return null
      const upload = await this.uploadAndCodeFile({ filename, content: code, testContent: testCode })
      if (!upload) return null
      this.evaluating = true
      this.error = null
      try {
        this.evaluation = await evaluateCode({
          userId: this.userId,
          practiceId: this.practice.practice_id,
          triggerReplan,
        })
        this.history.unshift(this.evaluation)
      } catch (err) {
        this.error = err?.message || '评估失败'
        return null
      } finally {
        this.evaluating = false
      }
      return this.evaluation
    },
  },
})