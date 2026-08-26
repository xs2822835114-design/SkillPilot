import { createRouter, createWebHistory } from 'vue-router'

import AppLayout from '@/components/AppLayout.vue'

const routes = [
  {
    path: '/',
    component: AppLayout,
    children: [
      {
        path: '',
        name: 'dashboard',
        component: () => import('@/views/DashboardView.vue'),
        meta: { title: '工作台' },
      },
      {
        path: 'chat',
        name: 'chat',
        component: () => import('@/views/ChatView.vue'),
        meta: { title: '对话' },
      },
      {
        path: 'graph',
        name: 'graph',
        component: () => import('@/views/SkillGraphView.vue'),
        meta: { title: '技能图谱' },
      },
      {
        path: 'gap',
        name: 'gap',
        component: () => import('@/views/GapReportView.vue'),
        meta: { title: '缺口报告' },
      },
      {
        path: 'plan',
        name: 'plan',
        component: () => import('@/views/LearningPlanView.vue'),
        meta: { title: '学习计划' },
      },
      {
        path: 'practice',
        name: 'practice',
        component: () => import('@/views/PracticeEvalView.vue'),
        meta: { title: '实践 · 评估' },
      },
      {
        path: 'health',
        name: 'health',
        component: () => import('@/views/HealthView.vue'),
        meta: { title: '服务健康' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  const title = to.meta?.title
  document.title = title ? `SkillMap · ${title}` : 'SkillMap'
})

export default router