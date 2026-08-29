import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { usePatientContext } from '../stores/patientContext'
import { canAccessPatientModule } from '../config/featureFlags'
import { PATIENT_MODULES } from '../config/patientModuleRegistry'

const routeComponents = {
  home: () => import('../views/HomeRedirect.vue'),
  doctorHome: () => import('../views/DoctorHome.vue'),
  nurseHome: () => import('../views/NurseHome.vue'),
  headNurseHome: () => import('../views/HeadNurseHome.vue'),
  directorHome: () => import('../views/DirectorHome.vue'),
  overview: () => import('../views/PatientOverview.vue'),
  patientDetail: () => import('../views/PatientDetail.vue'),
  patientDetailLayout: () => import('../views/patient-detail/PatientDetailLayout.vue'),
  patientOverview: () => import('../views/patient-detail/PatientOverviewView.vue'),
  patientMonitoring: () => import('../views/patient-detail/PatientMonitoringView.vue'),
  patientTreatment: () => import('../views/patient-detail/PatientTreatmentView.vue'),
  patientAlerts: () => import('../views/patient-detail/PatientAlertsView.vue'),
  patientDocuments: () => import('../views/patient-detail/PatientDocumentsView.vue'),
  patientIntelligence: () => import('../views/patient-detail/PatientIntelligenceView.vue'),
  patientFollowup: () => import('../views/patient-detail/PatientFollowupView.vue'),
  // Embed layout & modules
  embedLayout: () => import('../views/embed/EmbedLayout.vue'),
  embedRiskPrediction: () => import('../views/embed/risk-prediction/RiskPredictionView.vue'),
  embedSimilarCases: () => import('../views/embed/similar-cases/SimilarCasesView.vue'),
  embedCausalInference: () => import('../views/embed/causal-inference/CausalInferenceView.vue'),
  embedWhatIf: () => import('../views/embed/what-if/WhatIfView.vue'),
  embedIntegratedRisk: () => import('../views/embed/integrated-risk/IntegratedRiskView.vue'),
  embedDiseaseTrajectory: () => import('../views/embed/disease-trajectory/DiseaseTrajectoryView.vue'),
  embedEvidence: () => import('../views/embed/evidence/EvidenceView.vue'),
  embedDecisionAssistants: () => import('../views/embed/decision-assistants/DecisionAssistantsView.vue'),
  // Tool wrapper (loads iframe container)
  patientModuleFrame: () => import('../components/PatientModuleFrame.vue'),
  forbidden: () => import('../views/ForbiddenView.vue'),
  handoverOverview: () => import('../views/handover/HandoverOverview.vue'),
  handoverPatients: () => import('../views/handover/HandoverPatients.vue'),
  handoverPatientIsbar: () => import('../views/handover/HandoverPatientIsbar.vue'),
  handoverTasks: () => import('../views/handover/HandoverTasks.vue'),
  handoverHistory: () => import('../views/handover/HandoverHistory.vue'),
  handoverSettings: () => import('../views/handover/HandoverSettings.vue'),
  handoverLayout: () => import('../views/handover/HandoverLayout.vue'),
  bigScreen: () => import('../views/BigScreen.vue'),
  analytics: () => import('../views/Analytics.vue'),
  clinicalWorkflow: () => import('../views/ClinicalWorkflow.vue'),
  aiOps: () => import('../views/AiOps.vue'),
  scannerHealth: () => import('../views/ScannerHealth.vue'),
  runtimeConfig: () => import('../views/RuntimeConfigCenter.vue'),
  voiceCorrectionReview: () => import('../views/VoiceCorrectionReview.vue'),
  aiConsult: () => import('../views/AiConsult.vue'),
  roundingSheet: () => import('../views/RoundingSheetView.vue'),
  respiratoryDashboard: () => import('../views/RespiratoryTherapistDashboard.vue'),
  nutritionSupport: () => import('../views/NutritionSupportDashboard.vue'),
  academicResearch: () => import('../views/AcademicResearchDashboard.vue'),
  clinicalTrials: () => import('../views/ClinicalTrialScreening.vue'),
  researchExport: () => import('../views/ResearchExport.vue'),
  researchWorkbench: () => import('../views/ResearchWorkbench.vue'),
  mdtBoard: () => import('../views/MdtBoard.vue'),
  handover: () => import('../views/HandoverWorkbench.vue'),
  bedside: () => import('../views/BedSideScreen.vue'),
  diseaseCenterLayout: () => import('../views/disease-center/DiseaseCenterLayout.vue'),
  diseaseCenterOverview: () => import('../views/disease-center/DiseaseCenterOverview.vue'),
  diseaseCenterDiseases: () => import('../views/disease-center/DiseaseCenterDiseases.vue'),
  diseaseCenterTerminology: () => import('../views/disease-center/DiseaseCenterTerminology.vue'),
  diseaseCenterScores: () => import('../views/disease-center/DiseaseCenterScores.vue'),
  diseaseCenterPhenotypes: () => import('../views/disease-center/DiseaseCenterPhenotypes.vue'),
  diseaseCenterOffline: () => import('../views/disease-center/DiseaseCenterOffline.vue'),
  diseaseCenterReviews: () => import('../views/disease-center/DiseaseCenterReviews.vue'),
  diseaseCenterAi: () => import('../views/disease-center/DiseaseCenterAi.vue'),
  diseaseCenterQuality: () => import('../views/disease-center/DiseaseCenterQuality.vue'),
  mobileLayout: () => import('../mobile/MobileLayout.vue'),
  mobileHome: () => import('../mobile/MobileHome.vue'),
  mobilePatientList: () => import('../mobile/MobilePatientList.vue'),
  mobilePatientDetail: () => import('../mobile/MobilePatientDetail.vue'),
  mobileAlerts: () => import('../mobile/MobileAlerts.vue'),
  mobileTasks: () => import('../mobile/MobileTasks.vue'),
  mobileConsult: () => import('../mobile/MobileConsult.vue'),
  mobileMe: () => import('../mobile/MobileMe.vue'),
  sakiLayout: () => import('../views/saki/SAKILayout.vue'),
  sakiOverview: () => import('../views/saki/SAKIOverview.vue'),
  sakiCaseList: () => import('../views/saki/SAKICaseList.vue'),
  sakiCaseDetail: () => import('../views/saki/SAKICaseDetail.vue'),
  sakiCohortBuilder: () => import('../views/saki/SAKICohortBuilder.vue'),
  sakiAnalysis: () => import('../views/saki/SAKIAnalysis.vue'),
  sakiCharts: () => import('../views/saki/SAKICharts.vue'),
  sakiQuality: () => import('../views/saki/SAKIQuality.vue'),
  sakiFieldMapping: () => import('../views/saki/SAKIFieldMapping.vue'),
} as const

export function preloadRouteComponent(key: keyof typeof routeComponents) {
  return routeComponents[key]()
}

export function preloadCoreRouteComponents() {
  const run = () => {
    void routeComponents.doctorHome()
    void routeComponents.nurseHome()
    void routeComponents.overview()
    void routeComponents.clinicalWorkflow()
    void routeComponents.analytics()
  }
  const ric = (window as any).requestIdleCallback
  if (typeof ric === 'function') ric(run, { timeout: 2500 })
  else window.setTimeout(run, 1200)
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: routeComponents.home,
      meta: { title: '角色首页', navigationMode: 'global' }
    },
    {
      path: '/doctor-home',
      name: 'doctor-home',
      component: routeComponents.doctorHome,
      meta: { title: '医生首页', navigationMode: 'global' }
    },
    {
      path: '/nurse-home',
      name: 'nurse-home',
      component: routeComponents.nurseHome,
      meta: { title: '护士首页', navigationMode: 'global' }
    },
    {
      path: '/head-nurse-home',
      name: 'head-nurse-home',
      component: routeComponents.headNurseHome,
      meta: { title: '护士长首页', roles: ['head_nurse', 'charge_nurse'], navigationMode: 'global' }
    },
    {
      path: '/director-home',
      name: 'director-home',
      component: routeComponents.directorHome,
      meta: { title: '主任首页', roles: ['director'], navigationMode: 'global' }
    },
    {
      path: '/patients',
      name: 'overview',
      component: routeComponents.overview,
      meta: { title: '患者总览', navigationMode: 'global' }
    },
    // ═══ 患者详情路由（canonical: /patient/:patientId）═══
    {
      path: '/patient/:patientId',
      component: routeComponents.patientDetailLayout,
      meta: { title: '患者详情', useAntdTheme: true, navigationMode: 'patient' },
      children: [
        {
          path: '',
          redirect: (to: any) => ({ path: `/patient/${to.params.patientId}/overview`, query: to.query }),
        },
        {
          path: 'overview',
          name: 'patient-overview',
          component: routeComponents.patientOverview,
          meta: { title: '患者总览', useAntdTheme: true, navigationMode: 'patient' },
        },
        {
          path: 'monitoring',
          name: 'patient-monitoring',
          component: routeComponents.patientMonitoring,
          meta: { title: '患者监测', useAntdTheme: true, navigationMode: 'patient' },
        },
        {
          path: 'treatment',
          name: 'patient-treatment',
          component: routeComponents.patientTreatment,
          meta: { title: '治疗与护理', useAntdTheme: true, navigationMode: 'patient' },
        },
        {
          path: 'alerts',
          name: 'patient-alerts',
          component: routeComponents.patientAlerts,
          meta: { title: '预警与决策', useAntdTheme: true, navigationMode: 'patient' },
        },
        {
          path: 'documents',
          name: 'patient-documents',
          component: routeComponents.patientDocuments,
          meta: { title: '文书与AI', useAntdTheme: true, navigationMode: 'patient' },
        },
        {
          path: 'intelligence',
          name: 'patient-intelligence',
          component: routeComponents.patientIntelligence,
          meta: { title: 'AI分析', useAntdTheme: true, navigationMode: 'patient' },
        },
        {
          path: 'followup',
          name: 'patient-followup',
          component: routeComponents.patientFollowup,
          meta: { title: '随访管理', useAntdTheme: true, navigationMode: 'patient' },
        },
        {
          path: 'tool/:moduleKey',
          name: 'patient-tool',
          component: () => import('../views/patient-detail/PatientToolView.vue'),
          meta: { title: '工具模块', useAntdTheme: true, navigationMode: 'patient' },
        },
      ],
    },
    // ═══ 旧路由兼容重定向 ═══
    // /patient/:id → /patient/:patientId（保留 query）
    {
      path: '/patient/:id',
      redirect: (to: any) => ({
        path: `/patient/${to.params.id}/overview`,
        query: to.query,
      }),
    },
    // /patient/:id/intelligence → /patient/:patientId/tool/risk-prediction
    {
      path: '/patient/:id/intelligence',
      redirect: (to: any) => ({
        path: `/patient/${to.params.id}/tool/risk-prediction`,
        query: to.query,
      }),
    },
    // ═══ Embed 路由（iframe 内加载的独立模块页面）═══
    {
      path: '/embed/patient/:patientId',
      component: routeComponents.embedLayout,
      meta: { title: '嵌入模块', embed: true, navigationMode: 'embed' },
      children: [
        { path: '', redirect: (to: any) => `/embed/patient/${to.params.patientId}/risk-prediction` },
        { path: 'risk-prediction', name: 'embed-risk-prediction', component: routeComponents.embedRiskPrediction, meta: { title: '风险预测', moduleKey: 'risk-prediction', navigationMode: 'embed' } },
        { path: 'similar-cases', name: 'embed-similar-cases', component: routeComponents.embedSimilarCases, meta: { title: '相似病例', moduleKey: 'similar-cases', navigationMode: 'embed' } },
        { path: 'causal-inference', name: 'embed-causal-inference', component: routeComponents.embedCausalInference, meta: { title: '因果推断', moduleKey: 'causal-inference', navigationMode: 'embed' } },
        { path: 'what-if', name: 'embed-what-if', component: routeComponents.embedWhatIf, meta: { title: 'What-if模拟', moduleKey: 'what-if', navigationMode: 'embed' } },
        { path: 'integrated-risk', name: 'embed-integrated-risk', component: routeComponents.embedIntegratedRisk, meta: { title: '综合风险', moduleKey: 'integrated-risk', navigationMode: 'embed' } },
        { path: 'disease-trajectory', name: 'embed-disease-trajectory', component: routeComponents.embedDiseaseTrajectory, meta: { title: '病程推演', moduleKey: 'disease-trajectory', navigationMode: 'embed' } },
        { path: 'evidence', name: 'embed-evidence', component: routeComponents.embedEvidence, meta: { title: '循证证据', moduleKey: 'evidence', navigationMode: 'embed' } },
        { path: 'decision-assistants', name: 'embed-decision-assistants', component: routeComponents.embedDecisionAssistants, meta: { title: '专项决策', moduleKey: 'decision-assistants', navigationMode: 'embed' } },
      ],
    },
    // ═══ 403 页面 ═══
    {
      path: '/403',
      name: 'forbidden',
      component: routeComponents.forbidden,
      meta: { title: '权限不足', navigationMode: 'global' }
    },
    // ═══ 其他全局页面 ═══
    {
      path: '/bigscreen',
      name: 'bigscreen',
      component: routeComponents.bigScreen,
      meta: { title: '护士站大屏', fullscreen: true, navigationMode: 'global' }
    },
    {
      path: '/analytics',
      name: 'analytics',
      component: routeComponents.analytics,
      meta: { title: '历史预警分析', useAntdTheme: true, navigationMode: 'global' }
    },
    {
      path: '/clinical-workflow',
      name: 'clinical-workflow',
      component: routeComponents.clinicalWorkflow,
      meta: { title: '临床工作台', useAntdTheme: true, navigationMode: 'global' }
    },
    {
      path: '/ai-ops',
      name: 'ai-ops',
      component: routeComponents.aiOps,
      meta: { title: 'AI运营中心', useAntdTheme: true, navigationMode: 'global' }
    },
    {
      path: '/admin/scanner-health',
      name: 'scanner-health',
      component: routeComponents.scannerHealth,
      meta: { title: '规则健康', useAntdTheme: true, navigationMode: 'global' }
    },
    {
      path: '/admin/runtime-config',
      name: 'runtime-config',
      component: routeComponents.runtimeConfig,
      meta: { title: '配置中心', useAntdTheme: true, navigationMode: 'global' }
    },
    {
      path: '/admin/voice-correction-review',
      name: 'voice-correction-review',
      component: routeComponents.voiceCorrectionReview,
      meta: { title: '语音纠错Review', useAntdTheme: true, navigationMode: 'global' }
    },
    {
      path: '/ai-consult',
      name: 'ai-consult',
      component: routeComponents.aiConsult,
      meta: { title: 'AI问诊', useAntdTheme: true, navigationMode: 'global' }
    },
    {
      path: '/rounding-sheet',
      name: 'rounding-sheet',
      component: routeComponents.roundingSheet,
      meta: { title: '智能查房报告', useAntdTheme: true, navigationMode: 'global' }
    },
    {
      path: '/respiratory-dashboard',
      name: 'respiratory-dashboard',
      component: routeComponents.respiratoryDashboard,
      meta: { title: '呼吸治疗师工作面板', useAntdTheme: true, navigationMode: 'global' }
    },
    {
      path: '/nutrition-support',
      name: 'nutrition-support',
      component: routeComponents.nutritionSupport,
      meta: { title: '营养支持工作台', useAntdTheme: true, navigationMode: 'global' }
    },
    {
      path: '/academic-research',
      name: 'academic-research',
      component: routeComponents.academicResearch,
      meta: { title: '科室学术科研支撑', useAntdTheme: true, navigationMode: 'global' }
    },
    {
      path: '/clinical-trials',
      name: 'clinical-trials',
      component: routeComponents.clinicalTrials,
      meta: { title: '临床试验筛选', useAntdTheme: true, navigationMode: 'global' }
    },
    {
      path: '/research-export',
      name: 'research-export',
      component: routeComponents.researchExport,
      meta: { title: '科研导出', navigationMode: 'global' }
    },
    {
      path: '/research-workbench',
      name: 'research-workbench',
      component: routeComponents.researchWorkbench,
      meta: { title: '科研分析', navigationMode: 'global' }
    },
    {
      path: '/mdt',
      name: 'mdt-board',
      component: routeComponents.mdtBoard,
      meta: { title: 'MDT多智能体会诊', useAntdTheme: true, navigationMode: 'global' }
    },
    {
      path: '/handover',
      component: routeComponents.handoverLayout,
      meta: { title: '智能交接班', roles: ['nurse', 'head_nurse', 'doctor'], navigationMode: 'global' },
      children: [
        {
          path: '',
          redirect: '/handover/overview',
        },
        {
          path: 'overview',
          name: 'handover-overview',
          component: routeComponents.handoverOverview,
          meta: { title: '交班总览', roles: ['nurse', 'head_nurse', 'doctor'], navigationMode: 'global' },
        },
        {
          path: 'patients',
          name: 'handover-patients',
          component: routeComponents.handoverPatients,
          meta: { title: '患者交班', roles: ['nurse', 'head_nurse', 'doctor'], navigationMode: 'global' },
        },
        {
          path: 'patient/:patientId',
          name: 'handover-patient',
          component: routeComponents.handoverPatientIsbar,
          meta: { title: '患者ISBAR', roles: ['nurse', 'head_nurse', 'doctor'], navigationMode: 'global' },
        },
        {
          path: 'tasks',
          name: 'handover-tasks',
          component: routeComponents.handoverTasks,
          meta: { title: '待办与未闭环', roles: ['nurse', 'head_nurse', 'doctor'], navigationMode: 'global' },
        },
        {
          path: 'history',
          name: 'handover-history',
          component: routeComponents.handoverHistory,
          meta: { title: '交班历史', roles: ['nurse', 'head_nurse', 'doctor'], navigationMode: 'global' },
        },
        {
          path: 'settings',
          name: 'handover-settings',
          component: routeComponents.handoverSettings,
          meta: { title: '班次与诊断', roles: ['nurse', 'head_nurse'], navigationMode: 'global' },
        },
      ],
    },
    {
      path: '/bedside/:patientId',
      name: 'bedside',
      component: routeComponents.bedside,
      meta: { title: '床旁大屏', fullscreen: true, navigationMode: 'global' }
    },
    {
      path: '/disease-center',
      component: routeComponents.diseaseCenterLayout,
      meta: { title: '病种中心', useAntdTheme: true, navigationMode: 'global' },
      children: [
        {
          path: '',
          redirect: '/disease-center/overview',
        },
        {
          path: 'overview',
          name: 'disease-center-overview',
          component: routeComponents.diseaseCenterOverview,
          meta: { title: '病种中心总览', useAntdTheme: true, navigationMode: 'global' },
        },
        {
          path: 'diseases',
          name: 'disease-center-diseases',
          component: routeComponents.diseaseCenterDiseases,
          meta: { title: '病种目录', useAntdTheme: true, navigationMode: 'global' },
        },
        {
          path: 'terminology',
          name: 'disease-center-terminology',
          component: routeComponents.diseaseCenterTerminology,
          meta: { title: '术语编码', useAntdTheme: true, navigationMode: 'global' },
        },
        {
          path: 'scores',
          name: 'disease-center-scores',
          component: routeComponents.diseaseCenterScores,
          meta: { title: '评分规则', useAntdTheme: true, navigationMode: 'global' },
        },
        {
          path: 'phenotypes',
          name: 'disease-center-phenotypes',
          component: routeComponents.diseaseCenterPhenotypes,
          meta: { title: '表型规则', useAntdTheme: true, navigationMode: 'global' },
        },
        {
          path: 'offline-packages',
          name: 'disease-center-offline',
          component: routeComponents.diseaseCenterOffline,
          meta: { title: '离线知识包', useAntdTheme: true, navigationMode: 'global' },
        },
        {
          path: 'reviews',
          name: 'disease-center-reviews',
          component: routeComponents.diseaseCenterReviews,
          meta: { title: '审核发布', useAntdTheme: true, navigationMode: 'global' },
        },
        {
          path: 'ai',
          name: 'disease-center-ai',
          component: routeComponents.diseaseCenterAi,
          meta: { title: 'AI助手', useAntdTheme: true, navigationMode: 'global' },
        },
        {
          path: 'quality',
          name: 'disease-center-quality',
          component: routeComponents.diseaseCenterQuality,
          meta: { title: '质量监控', useAntdTheme: true, navigationMode: 'global' },
        },
      ],
    },
    {
      path: '/disease-center/saki',
      component: routeComponents.sakiLayout,
      meta: { title: 'S-AKI 单病种科研中心', useAntdTheme: true, navigationMode: 'global' },
      children: [
        { path: '', redirect: '/disease-center/saki/overview' },
        { path: 'overview', name: 'saki-overview', component: routeComponents.sakiOverview, meta: { title: 'S-AKI 总览', useAntdTheme: true, navigationMode: 'global' } },
        { path: 'cases', name: 'saki-cases', component: routeComponents.sakiCaseList, meta: { title: 'S-AKI 病例库', useAntdTheme: true, navigationMode: 'global' } },
        { path: 'cases/:caseId', name: 'saki-case-detail', component: routeComponents.sakiCaseDetail, meta: { title: 'S-AKI 病例详情', useAntdTheme: true, navigationMode: 'global' } },
        { path: 'cohorts', name: 'saki-cohorts', component: routeComponents.sakiCohortBuilder, meta: { title: 'S-AKI 队列构建', useAntdTheme: true, navigationMode: 'global' } },
        { path: 'analysis', name: 'saki-analysis', component: routeComponents.sakiAnalysis, meta: { title: 'S-AKI 统计分析', useAntdTheme: true, navigationMode: 'global' } },
        { path: 'charts', name: 'saki-charts', component: routeComponents.sakiCharts, meta: { title: 'S-AKI 图表', useAntdTheme: true, navigationMode: 'global' } },
        { path: 'quality', name: 'saki-quality', component: routeComponents.sakiQuality, meta: { title: 'S-AKI 数据质量', useAntdTheme: true, navigationMode: 'global' } },
        { path: 'field-mapping', name: 'saki-field-mapping', component: routeComponents.sakiFieldMapping, meta: { title: 'S-AKI 字段映射', useAntdTheme: true, navigationMode: 'global' } },
      ],
    },
    {
      path: '/m',
      component: routeComponents.mobileLayout,
      meta: { title: 'ICU移动工作台', useAntdTheme: true, mobile: true, navigationMode: 'global' },
      children: [
        {
          path: '',
          name: 'mobile-home',
          component: routeComponents.mobileHome,
          meta: { title: '移动首页', useAntdTheme: true, mobile: true, navigationMode: 'global' }
        },
        {
          path: 'clinical-workflow',
          name: 'mobile-clinical-workflow',
          component: routeComponents.mobileHome,
          meta: { title: '移动临床工作台', useAntdTheme: true, mobile: true, navigationMode: 'global' }
        },
        {
          path: 'patients',
          name: 'mobile-patients',
          component: routeComponents.mobilePatientList,
          meta: { title: '移动患者', useAntdTheme: true, mobile: true, navigationMode: 'global' }
        },
        {
          path: 'patient/:id',
          name: 'mobile-patient-detail',
          component: routeComponents.mobilePatientDetail,
          meta: { title: '移动患者详情', useAntdTheme: true, mobile: true, navigationMode: 'patient' }
        },
        {
          path: 'alerts',
          name: 'mobile-alerts',
          component: routeComponents.mobileAlerts,
          meta: { title: '移动告警', useAntdTheme: true, mobile: true, navigationMode: 'global' }
        },
        {
          path: 'tasks',
          name: 'mobile-tasks',
          component: routeComponents.mobileTasks,
          meta: { title: '移动任务', useAntdTheme: true, mobile: true, navigationMode: 'global' }
        },
        {
          path: 'consult',
          name: 'mobile-consult',
          component: routeComponents.mobileConsult,
          meta: { title: '移动AI问诊', useAntdTheme: true, mobile: true, navigationMode: 'global' }
        },
        {
          path: 'me',
          name: 'mobile-me',
          component: routeComponents.mobileMe,
          meta: { title: '我的', useAntdTheme: true, mobile: true, navigationMode: 'global' }
        }
      ]
    }
  ] satisfies RouteRecordRaw[]
})

// ── 守卫 1: 从 query 同步身份信息 ──
router.beforeEach((to) => {
  try { useAuthStore().hydrateFromQuery(to.query) } catch {}
})

// ── 守卫 2: 同步患者上下文 ──
router.beforeEach((to, from) => {
  try {
    const patientCtx = usePatientContext()
    const mode = to.meta?.navigationMode as string

    if (mode === 'patient') {
      // Entering patient workflow — record origin if coming from outside
      if (from.meta?.navigationMode !== 'patient') {
        patientCtx.setOriginRoute(from.fullPath)
      }
      patientCtx.syncFromRoute(to)
    } else if (mode === 'embed') {
      // Embed routes also have patientId
      patientCtx.syncFromRoute(to)
    } else {
      // Leaving patient workflow — clear context
      if (from.meta?.navigationMode === 'patient') {
        patientCtx.clearContext()
      }
    }
  } catch {}
})

// ── 守卫 3: 角色权限检查 ──
router.beforeEach((to, _from, next) => {
  const requiredRoles = to.meta?.roles as string[] | undefined
  if (requiredRoles && requiredRoles.length > 0) {
    const auth = useAuthStore()
    const userRole = String(auth.role || '').toLowerCase()
    if (!requiredRoles.includes(userRole)) {
      next({ path: '/403', query: to.query })
      return
    }
  }
  next()
})

// ── 守卫 4: 患者模块权限检查 ──
router.beforeEach((to, _from, next) => {
  const mode = to.meta?.navigationMode as string
  if (mode === 'patient') {
    const moduleKey = to.params.moduleKey as string
    if (moduleKey) {
      const mod = PATIENT_MODULES.find(m => m.moduleKey === moduleKey)
      if (mod) {
        const auth = useAuthStore()
        const userRole = String(auth.role || '').toLowerCase()
        if (!canAccessPatientModule(moduleKey, {
          featureFlag: mod.featureFlag,
          requiredRoles: mod.requiredRoles,
        }, userRole)) {
          next({ path: '/403', query: to.query })
          return
        }
      }
    }
  }
  next()
})

export default router
