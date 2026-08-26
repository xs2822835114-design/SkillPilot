import { defineStore } from 'pinia'

import { fetchHealthStatus } from '@/services/healthService'
import { toUserFacingMessage } from '@/services/chatService'

export const useHealthStore = defineStore('health', {
  state: () => ({
    /** 视图模型：{status,statusText,tone,version,db,llm,checkedAt} */
    health: null,
    loading: false,
    error: null,
    lastCheckedAt: null,
  }),

  getters: {
    isChecked: (s) => s.health !== null,
  },

  actions: {
    async check() {
      this.loading = true
      this.error = null
      try {
        this.health = await fetchHealthStatus()
        this.lastCheckedAt = new Date()
        // eslint-disable-next-line no-empty
      } catch (err) {
        this.error = toUserFacingMessage(err)
      } finally {
        this.loading = false
      }
    },
  },
})