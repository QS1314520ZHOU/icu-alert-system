/**
 * ICU Alert System — 患者模块注册表
 *
 * 定义所有可通过 iframe 加载的独立AI/临床决策模块。
 * 每个模块包含路由、权限、iframe地址等元数据。
 */

export interface PatientModule {
  moduleKey: string
  title: string
  icon: string
  group: 'patient-detail' | 'alert-decision' | 'ai-analysis' | 'clinical-docs' | 'followup'
  route: string
  iframeUrl: (patientId: string) => string
  requiredRoles?: string[]
  featureFlag?: string
  preload?: boolean
  description?: string
  legacyRoutes?: string[]
  badge?: 'risk' | 'ai' | 'new'
}

// ── 模块注册 ──────────────────────────────────────

export const PATIENT_MODULES: PatientModule[] = [
  // 患者详情组
  {
    moduleKey: 'overview',
    title: '病情总览',
    icon: '📋',
    group: 'patient-detail',
    route: '/patient/:patientId/overview',
    iframeUrl: () => '',  // 原生页面，不使用iframe
    description: '患者核心生命体征、诊断、风险概览',
  },
  {
    moduleKey: 'monitoring',
    title: '实时监测',
    icon: '📈',
    group: 'patient-detail',
    route: '/patient/:patientId/monitoring',
    iframeUrl: () => '',
    description: '生命体征趋势、波形、检验趋势',
  },
  {
    moduleKey: 'treatment',
    title: '治疗与护理',
    icon: '💊',
    group: 'patient-detail',
    route: '/patient/:patientId/treatment',
    iframeUrl: () => '',
    description: '当前药物、输液、管路、护理评估',
  },

  // 预警与决策组
  {
    moduleKey: 'alerts',
    title: '临床预警',
    icon: '🚨',
    group: 'alert-decision',
    route: '/patient/:patientId/alerts',
    iframeUrl: () => '',
    description: '活跃预警、确认、证据',
  },
  {
    moduleKey: 'risk-prediction',
    title: '风险预测',
    icon: '📊',
    group: 'alert-decision',
    route: '/patient/:patientId/tool/risk-prediction',
    iframeUrl: (pid) => `/embed/patient/${pid}/risk-prediction`,
    description: '多时间窗恶化风险、影响因素、模型可信度',
    legacyRoutes: ['?tab=ai'],
    badge: 'risk',
  },
  {
    moduleKey: 'integrated-risk',
    title: '综合风险',
    icon: '🔗',
    group: 'alert-decision',
    route: '/patient/:patientId/tool/integrated-risk',
    iframeUrl: (pid) => `/embed/patient/${pid}/integrated-risk`,
    description: '因果链、多器官关联、行动优先级',
    badge: 'risk',
  },
  {
    moduleKey: 'decision-assistants',
    title: '专项决策',
    icon: '⚕️',
    group: 'alert-decision',
    route: '/patient/:patientId/tool/decision-assistants',
    iframeUrl: (pid) => `/embed/patient/${pid}/decision-assistants`,
    description: '撤机SBT、ARDS、CRRT、血流动力学等专项工作台',
  },

  // AI智能分析组
  {
    moduleKey: 'similar-cases',
    title: '相似病例',
    icon: '👥',
    group: 'ai-analysis',
    route: '/patient/:patientId/tool/similar-cases',
    iframeUrl: (pid) => `/embed/patient/${pid}/similar-cases`,
    description: '特征匹配、结局分布、可比性分析',
    legacyRoutes: ['?tab=similar'],
    badge: 'ai',
  },
  {
    moduleKey: 'causal-inference',
    title: '因果推断',
    icon: '🔬',
    group: 'ai-analysis',
    route: '/patient/:patientId/tool/causal-inference',
    iframeUrl: (pid) => `/embed/patient/${pid}/causal-inference`,
    description: '因果DAG、倾向匹配、效应估计',
    badge: 'ai',
  },
  {
    moduleKey: 'what-if',
    title: 'What-if模拟',
    icon: '🧪',
    group: 'ai-analysis',
    route: '/patient/:patientId/tool/what-if',
    iframeUrl: (pid) => `/embed/patient/${pid}/what-if`,
    description: '治疗情景模拟、参数调整、风险比较',
    badge: 'ai',
  },
  {
    moduleKey: 'disease-trajectory',
    title: '病程推演',
    icon: '📉',
    group: 'ai-analysis',
    route: '/patient/:patientId/tool/disease-trajectory',
    iframeUrl: (pid) => `/embed/patient/${pid}/disease-trajectory`,
    description: '病程时间轴、状态转移、未来路径预测',
    badge: 'ai',
  },
  {
    moduleKey: 'evidence',
    title: '循证证据',
    icon: '📚',
    group: 'ai-analysis',
    route: '/patient/:patientId/tool/evidence',
    iframeUrl: (pid) => `/embed/patient/${pid}/evidence`,
    description: '证据等级、指南推荐、适用性评估',
  },

  // 临床文书组
  {
    moduleKey: 'documents',
    title: 'AI文书',
    icon: '📑',
    group: 'clinical-docs',
    route: '/patient/:patientId/tool/documents',
    iframeUrl: (pid) => `/embed/patient/${pid}/documents`,
    description: '查房摘要、AI文书、交接班、MDT材料',
    legacyRoutes: ['/patient/:id/documents'],
  },

  // 随访管理组
  {
    moduleKey: 'followup',
    title: '随访管理',
    icon: '📋',
    group: 'followup',
    route: '/patient/:patientId/tool/followup',
    iframeUrl: (pid) => `/embed/patient/${pid}/followup`,
    description: 'PICS评估、随访任务、康复转诊',
    legacyRoutes: ['?tab=followup'],
  },
]

// ── 模块分组 ──────────────────────────────────────

export interface ModuleGroup {
  key: string
  label: string
  icon: string
  modules: PatientModule[]
}

export const MODULE_GROUPS: ModuleGroup[] = [
  {
    key: 'patient-detail',
    label: '患者详情',
    icon: '📋',
    modules: PATIENT_MODULES.filter(m => m.group === 'patient-detail'),
  },
  {
    key: 'alert-decision',
    label: '预警与决策',
    icon: '🚨',
    modules: PATIENT_MODULES.filter(m => m.group === 'alert-decision'),
  },
  {
    key: 'ai-analysis',
    label: 'AI智能分析',
    icon: '🤖',
    modules: PATIENT_MODULES.filter(m => m.group === 'ai-analysis'),
  },
  {
    key: 'clinical-docs',
    label: '临床文书',
    icon: '📑',
    modules: PATIENT_MODULES.filter(m => m.group === 'clinical-docs'),
  },
  {
    key: 'followup',
    label: '随访管理',
    icon: '📋',
    modules: PATIENT_MODULES.filter(m => m.group === 'followup'),
  },
]

// ── 工具函数 ──────────────────────────────────────

export function getModuleByKey(key: string): PatientModule | undefined {
  return PATIENT_MODULES.find(m => m.moduleKey === key)
}

export function isIframeModule(moduleKey: string): boolean {
  const mod = getModuleByKey(moduleKey)
  return mod ? mod.iframeUrl('') !== '' : false
}

export function getModuleRoute(moduleKey: string, patientId: string): string {
  const mod = getModuleByKey(moduleKey)
  if (!mod) return `/patient/${patientId}/overview`
  return mod.route.replace(':patientId', patientId)
}

export function getIframeUrl(moduleKey: string, patientId: string): string {
  const mod = getModuleByKey(moduleKey)
  if (!mod || !isIframeModule(moduleKey)) return ''
  return mod.iframeUrl(patientId)
}
