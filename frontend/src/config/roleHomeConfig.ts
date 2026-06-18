export type NavItemKey =
  | 'doctor-home'
  | 'nurse-home'
  | 'head-nurse-home'
  | 'director-home'
  | 'overview'
  | 'clinical-workflow'
  | 'ai-consult'
  | 'rounding-sheet'
  | 'patient-documents'
  | 'bigscreen'
  | 'analytics'
  | 'scanner-health'
  | 'research-workbench'
  | 'research-export'
  | 'clinical-trials'
  | 'mdt'
  | 'respiratory-dashboard'
  | 'nutrition-support'
  | 'ai-ops'
  | 'runtime-config'
  | 'academic-research'

export type NavGroup = {
  key: string
  label: string
  items: Array<{
    key: NavItemKey
    lines: string[]
    path: string
  }>
}

export const navGroups: NavGroup[] = [
  {
    key: 'daily',
    label: '日常工作',
    items: [
      { key: 'doctor-home', lines: ['医生', '首页'], path: '/doctor-home' },
      { key: 'nurse-home', lines: ['护士', '首页'], path: '/nurse-home' },
      { key: 'head-nurse-home', lines: ['护士长', '首页'], path: '/head-nurse-home' },
      { key: 'director-home', lines: ['主任', '首页'], path: '/director-home' },
      { key: 'overview', lines: ['患者', '总览'], path: '/patients' },
      { key: 'clinical-workflow', lines: ['临床', '工作台'], path: '/clinical-workflow' },
    ],
  },
  {
    key: 'ai',
    label: '临床工具',
    items: [
      { key: 'ai-consult', lines: ['辅助', '问诊'], path: '/ai-consult' },
      { key: 'rounding-sheet', lines: ['查房'], path: '/rounding-sheet' },
      { key: 'patient-documents', lines: ['病历', '文书'], path: '/patients' },
      { key: 'mdt', lines: ['MDT', '会诊'], path: '/mdt' },
    ],
  },
  {
    key: 'management',
    label: '科室管理',
    items: [
      { key: 'bigscreen', lines: ['护士站', '大屏'], path: '/bigscreen' },
      { key: 'analytics', lines: ['质控', '分析'], path: '/analytics' },
      { key: 'scanner-health', lines: ['规则', '健康'], path: '/admin/scanner-health' },
      { key: 'respiratory-dashboard', lines: ['呼吸', '治疗'], path: '/respiratory-dashboard' },
      { key: 'nutrition-support', lines: ['营养', '支持'], path: '/nutrition-support' },
    ],
  },
  {
    key: 'research',
    label: '科研管理',
    items: [
      { key: 'research-workbench', lines: ['科研', '工作台'], path: '/research-workbench' },
      { key: 'research-export', lines: ['科研', '导出'], path: '/research-export' },
      { key: 'clinical-trials', lines: ['临床', '试验'], path: '/clinical-trials' },
      { key: 'academic-research', lines: ['学术', '科研'], path: '/academic-research' },
      { key: 'ai-ops', lines: ['运营', '管理'], path: '/ai-ops' },
      { key: 'runtime-config', lines: ['配置', '中心'], path: '/admin/runtime-config' },
    ],
  },
]

export const navItems = navGroups.flatMap((group) => group.items)

export const roleHomeConfig = {
  doctor: {
    title: '今日查房工作台',
    startHint: '今天从这里开始：先看重点患者，再处理待办，最后进入患者详情完成查房和文书。',
    onboardingKey: 'icu_onboarding_seen_doctor',
    onboardingSteps: ['先看重点患者', '处理待办和高危预警', '进入患者详情完成查房/文书'],
  },
  nurse: {
    title: '本班执行工作台',
    startHint: '今天从这里开始：先看我的床位，再处理本班提醒，下班前生成交班单。',
    onboardingKey: 'icu_onboarding_seen_nurse',
    onboardingSteps: ['先看我的床位', '处理本班提醒和安全清单', '下班前生成交班单'],
  },
  headNurse: {
    title: '护士长看板',
    startHint: '今天从这里开始：先看全科床位，再看工作负荷，最后追踪未闭环护理事件。',
    onboardingKey: 'icu_onboarding_seen_head_nurse',
    onboardingSteps: ['先看全科床位', '查看工作负荷和异常事件', '追踪未闭环护理问题'],
  },
  director: {
    title: '主任看板',
    startHint: '今天从这里开始：先看科室概览，再看质控大屏，最后追踪KPI和科研动态。',
    onboardingKey: 'icu_onboarding_seen_director',
    onboardingSteps: ['先看科室概览', '查看质控大屏', '追踪KPI和科研动态'],
  },
}
