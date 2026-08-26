<script setup>
import { onMounted } from 'vue'
import SkillGraph from '@/components/SkillGraph.vue'
import { useGraphStore } from '@/stores/graph'

const graph = useGraphStore()
onMounted(() => graph.load())
</script>

<template>
  <div class="page">
    <header class="page-head">
      <h1>技能图谱</h1>
      <p>目标岗位所需技能的层级结构（节点=技能，边=前置/组合关系）</p>
    </header>
    <SkillGraph :nodes="graph.nodes" :edges="graph.edges" :loading="graph.loading" />
    <p class="meta">节点 {{ graph.nodes.length }} · 边 {{ graph.edges.length }}</p>
  </div>
</template>

<style scoped>
.page {
  max-width: 1080px;
  margin: 0 auto;
  padding: 24px 28px;
  height: 100%;
  overflow-y: auto;
}
.page-head h1 {
  font-size: 24px;
  margin: 0 0 4px;
}
.page-head p {
  margin: 0 0 18px;
  color: var(--text-2);
  font-size: 14px;
}
.meta {
  margin: 10px 4px 0;
  color: var(--text-3);
  font-size: 13px;
}
</style>