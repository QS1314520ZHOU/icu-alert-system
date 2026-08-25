export type NavItemKey =
  | 'doctor-home' | 'nurse-home' | 'head-nurse-home' | 'director-home'
  | 'overview' | 'clinical-workflow' | 'ai-consult' | 'rounding-sheet'
  | 'patient-documents' | 'bigscreen' | 'analytics' | 'scanner-health'
  | 'research-workbench' | 'research-export' | 'clinical-trials'
  | 'mdt' | 'respiratory-dashboard' | 'nutrition-support'
  | 'ai-ops' | 'runtime-config' | 'academic-research' | 'handover'

export type NavGroup = {
  key: string
  label: string
  items: Array<{
    key: NavItemKey
    lines: string[]
    label: string
    icon: string
    path: string
  }>
}

export const navGroups: NavGroup[] = [
  {
    key: 'daily',
    label: '日常工作',
    items: [
      { key: 'doctor-home',    lines: ['医生','首页'],   label: '医生首页',   icon: 'stethoscope',  path: '/doctor-home' },
      { key: 'nurse-home',     lines: ['护士','首页'],   label: '护士首页',   icon: 'nurse',        path: '/nurse-home' },
      { key: 'head-nurse-home',lines: ['护士长','首页'], label: '护士长首页', icon: 'shield',       path: '/head-nurse-home' },
      { key: 'director-home',  lines: ['主任','首页'],   label: '主任首页',   icon: 'crown',        path: '/director-home' },
      { key: 'overview',       lines: ['患者','总览'],   label: '患者总览',   icon: 'users',        path: '/patients' },
      { key: 'clinical-workflow',lines: ['临床','工作台'],label: '临床工作台', icon: 'activity',     path: '/clinical-workflow' },
      { key: 'handover',       lines: ['智能','交接班'], label: '智能交接班', icon: 'exchange',     path: '/handover' },
    ],
  },
  {
    key: 'ai',
    label: 'AI辅助',
    items: [
      { key: 'ai-consult',   lines: ['AI','问诊'],     label: 'AI问诊',     icon: 'sparkles',     path: '/ai-consult' },
      { key: 'rounding-sheet',lines: ['智能','查房'],   label: '智能查房',   icon: 'clipboard',    path: '/rounding-sheet' },
      { key: 'patient-documents',lines: ['病历','文书'],label: '病历文书',   icon: 'file',         path: '/patients' },
      { key: 'mdt',          lines: ['MDT','会诊'],     label: 'MDT会诊',    icon: 'network',      path: '/mdt' },
    ],
  },
  {
    key: 'management',
    label: '科室管理',
    items: [
      { key: 'bigscreen',    lines: ['护士站','大屏'],   label: '护士站大屏', icon: 'monitor',      path: '/bigscreen' },
      { key: 'analytics',    lines: ['质控','分析'],     label: '质控分析',   icon: 'chart',        path: '/analytics' },
      { key: 'scanner-health',lines: ['规则','健康'],    label: '规则健康',   icon: 'pulse',        path: '/admin/scanner-health' },
      { key: 'respiratory-dashboard',lines: ['呼吸','治疗'],label: '呼吸治疗', icon: 'lungs',       path: '/respiratory-dashboard' },
      { key: 'nutrition-support',lines: ['营养','支持'], label: '营养支持',   icon: 'apple',        path: '/nutrition-support' },
    ],
  },
  {
    key: 'research',
    label: '科研管理',
    items: [
      { key: 'research-workbench',lines: ['科研','工作台'],label: '科研工作台', icon: 'flask',       path: '/research-workbench' },
      { key: 'research-export',   lines: ['科研','导出'], label: '科研导出',   icon: 'download',    path: '/research-export' },
      { key: 'clinical-trials',   lines: ['临床','试验'], label: '临床试验',   icon: 'beaker',      path: '/clinical-trials' },
      { key: 'academic-research', lines: ['学术','科研'], label: '学术科研',   icon: 'book',        path: '/academic-research' },
      { key: 'ai-ops',            lines: ['AI','运营'],   label: 'AI运营',     icon: 'cpu',         path: '/ai-ops' },
      { key: 'runtime-config',    lines: ['配置','中心'], label: '配置中心',   icon: 'settings',    path: '/admin/runtime-config' },
    ],
  },
]

export const navItems = navGroups.flatMap((g) => g.items)

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