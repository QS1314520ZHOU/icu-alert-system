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
      meta: { title: '患者详情', useAntdTheme: true }
    },
    {
      path: '/bigscreen',
      name: 'bigscreen',
      component: () => import('../views/BigScreen.vue'),
      meta: { title: '护士站大屏' }
    },
    {
      path: '/analytics',
      name: 'analytics',
      component: () => import('../views/Analytics.vue'),
      meta: { title: '历史预警分析', useAntdTheme: true }
    },
    {
      path: '/ai-ops',
      name: 'ai-ops',
      component: () => import('../views/AiOps.vue'),
      meta: { title: 'AI运营中心', useAntdTheme: true }
    },
    {
      path: '/research-export',
      name: 'research-export',
      component: () => import('../views/ResearchExport.vue'),
      meta: { title: '科研导出' }
    },
    {
      path: '/research-workbench',
      name: 'research-workbench',
      component: () => import('../views/ResearchWorkbench.vue'),
      meta: { title: '科研分析' }
    },
    {
      path: '/mdt',
      name: 'mdt-board',
      component: () => import('../views/MdtBoard.vue'),
      meta: { title: 'MDT多智能体会诊', useAntdTheme: true }
    },
    {
      path: '/bedside/:patientId',
      name: 'bedside',
      component: () => import('../views/BedSideScreen.vue'),
      meta: { title: '床旁大屏' }
    }
  ]
})

export default router
