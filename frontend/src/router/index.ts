import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'overview',
      component: () => import('../views/PatientOverview.vue'),
      meta: { title: '患者总览' }
    },
    {
      path: '/patient/:id',
      name: 'patient-detail',
      component: () => import('../views/PatientDetail.vue'),
      meta: { title: '患者详情' }
    },
    {
      path: '/bigscreen',
      name: 'bigscreen',
      component: () => import('../views/BigScreen.vue'),
      meta: { title: '护士站大屏' }
    }
  ]
})

export default router
