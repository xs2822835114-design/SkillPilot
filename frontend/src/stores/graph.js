import { defineStore } from 'pinia'
import { fetchSkillGraph } from '@/api/dashboard'

/** 技能图谱 Store：全量 nodes + edges，供 SVG 可视化布局。 */
export const useGraphStore = defineStore('graph', {
  state: () => ({
    nodes: [],
    edges: [],
    loading: false,
    error: null,
    loaded: false,
  }),

  getters: {
    /** 按 category 分组的节点（用于配色/图例） */
    categories(state) {
      return [...new Set(state.nodes.map((n) => n.category).filter(Boolean))]
    },
    byId(state) {
      const map = {}
      for (const n of state.nodes) map[n.id] = n
      return map
    },
  },

  actions: {
    async load(force = false) {
      if (this.loaded && !force) return this.nodes
      this.loading = true
      this.error = null
      try {
        const g = await fetchSkillGraph()
        this.nodes = g.nodes || []
        this.edges = g.edges || []
        this.loaded = true
      } catch (err) {
        this.error = err?.message || '加载技能图谱失败'
        return null
      } finally {
        this.loading = false
      }
      return this.nodes
    },
  },
})