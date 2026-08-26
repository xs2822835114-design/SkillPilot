<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  edges: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

const box = { w: 940, h: 560 }
const palette = ['#7c5cff', '#2a7de0', '#2f9e6f', '#e08b04', '#e23b3b', '#00aba9']

const positions = reactive({})
const catOrder = computed(() => [...new Set(props.nodes.map((n) => n.category).filter(Boolean))])

/** category → 颜色（computed：数据异步到达后自动重建，避免 setup 期空列表导致全灰） */
const colorBy = computed(() => {
  const map = {}
  let idx = 0
  for (const n of props.nodes) {
    if (n.category && !(n.category in map)) map[n.category] = palette[idx++ % palette.length]
  }
  return map
})

/** 简易力导向：斥力 + 向心 + 连线拉力，运行少量迭代得到稳定布局 */
function layout() {
  const byId = {}
  for (const n of props.nodes) {
    byId[n.id] = { ...n }
    positions[n.id] = {
      x: box.w / 2 + (Math.random() - 0.5) * box.w * 0.6,
      y: box.h / 2 + (Math.random() - 0.5) * box.h * 0.6,
      vx: 0,
      vy: 0,
    }
  }
  const REP = 900
  const SPRING = 0.05
  const CENTER = 0.01
  const damp = 0.85
  for (let iter = 0; iter < 120; iter++) {
    for (const a of props.nodes) {
      const pa = positions[a.id]
      pa.vx += (box.w / 2 - pa.x) * CENTER
      pa.vy += (box.h / 2 - pa.y) * CENTER
      for (const b of props.nodes) {
        if (a.id === b.id) continue
        const pb = positions[b.id]
        let dx = pa.x - pb.x
        let dy = pa.y - pb.y
        const d2 = dx * dx + dy * dy || 1
        const d = Math.sqrt(d2)
        const f = REP / d2
        pa.vx += (dx / d) * f
        pa.vy += (dy / d) * f
      }
    }
    for (const e of props.edges) {
      const a = byId[e.source]
      const b = byId[e.target]
      if (!a || !b) continue
      const pa = positions[a.id]
      const pb = positions[b.id]
      const dx = pb.x - pa.x
      const dy = pb.y - pa.y
      const d = Math.sqrt(dx * dx + dy * dy) || 1
      pa.vx += (dx / d) * SPRING
      pa.vy += (dy / d) * SPRING
      pb.vx -= (dx / d) * SPRING
      pb.vy -= (dy / d) * SPRING
    }
    for (const n of props.nodes) {
      const p = positions[n.id]
      p.vx *= damp
      p.vy *= damp
      p.x += p.vx
      p.y += p.vy
    }
  }
}

const edgeColors = computed(() =>
  props.edges.map((e) => {
    const src = props.nodes.find((n) => n.id === e.source)
    const p = src?.category ? colorBy.value[src.category] : undefined
    return { ...e, color: p || 'rgba(120,130,150,0.5)' }
  }),
)

onMounted(() => {
  if (props.nodes.length) layout()
})

watch(
  () => props.nodes.length,
  (n) => {
    if (n) layout()
  },
)
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h3>技能图谱</h3>
      <span class="legend">
        <i v-for="c in catOrder" :key="c" :style="{ background: colorBy[c] }">{{ c }}</i>
      </span>
    </div>

    <div v-if="loading" class="empty">图谱加载中…</div>
    <div v-else-if="!nodes.length" class="empty">暂无图谱数据，请先运行 demo_init 初始化。</div>

    <svg v-else :viewBox="`0 0 ${box.w} ${box.h}`" class="graph">
      <g>
        <line
          v-for="(e, i) in edgeColors"
          :key="i"
          :x1="positions[e.source]?.x || 0"
          :y1="positions[e.source]?.y || 0"
          :x2="positions[e.target]?.x || 0"
          :y2="positions[e.target]?.y || 0"
          :stroke="e.color"
          stroke-width="1.2"
          opacity="0.55"
        />
      </g>
      <g>
        <g
          v-for="n in nodes"
          :key="n.id"
          :transform="`translate(${positions[n.id]?.x || 0}, ${positions[n.id]?.y || 0})`"
        >
          <title>{{ n.name }}</title>
          <circle
            :r="n.name.length > 8 ? 11 : 9"
            :fill="colorBy[n.category] || '#888'"
            fill-opacity="0.9"
            stroke="#fff"
            stroke-width="1.5"
          />
          <text
            y="20"
            text-anchor="middle"
            font-size="10"
            fill="var(--text-2, #666)"
          >{{ n.name.length > 10 ? n.name.slice(0, 10) + '…' : n.name }}</text>
        </g>
      </g>
    </svg>
  </section>
</template>

<style scoped>
.panel {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg);
  padding: 18px;
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.panel-head h3 {
  margin: 0;
  font-size: 16px;
}
.legend {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 11px;
  color: var(--text-3);
}
.legend i {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-style: normal;
  padding: 2px 8px;
  border-radius: 999px;
  color: #fff;
}
.graph {
  width: 100%;
  height: 520px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-hover);
}
.empty {
  padding: 60px 0;
  text-align: center;
  color: var(--text-2);
  font-size: 14px;
}
</style>