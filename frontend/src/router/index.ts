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
      path: '/ai-consult',
      name: 'ai-consult',
      component: () => import('../views/AiConsult.vue'),
      meta: { title: 'AI问诊', useAntdTheme: true }
    },
    {
      path: '/rounding-sheet',
      name: 'rounding-sheet',
      component: () => import('../views/RoundingSheetView.vue'),
      meta: { title: '智能查房报告', useAntdTheme: true }
    },
    {
      path: '/respiratory-dashboard',
      name: 'respiratory-dashboard',
      component: () => import('../views/RespiratoryTherapistDashboard.vue'),
      meta: { title: '呼吸治疗师工作面板', useAntdTheme: true }
    },
    {
      path: '/academic-research',
      name: 'academic-research',
      component: () => import('../views/AcademicResearchDashboard.vue'),
      meta: { title: '科室学术科研支撑', useAntdTheme: true }
    },
    {
      path: '/clinical-trials',
      name: 'clinical-trials',
      component: () => import('../views/ClinicalTrialScreening.vue'),
      meta: { title: '临床试验筛选', useAntdTheme: true }
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
