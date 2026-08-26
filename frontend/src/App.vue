<script setup>
import { useHealthStore } from '@/stores/health'
import { onMounted } from 'vue'

const health = useHealthStore()

onMounted(() => {
  // 应用启动时做一次健康检查（静默，失败不阻断）
  health.check()
})
</script>

<template>
  <div class="app-shell">
    <RouterView />
  </div>
</template>

<style scoped>
.app-shell {
  height: 100%;
}
</style>