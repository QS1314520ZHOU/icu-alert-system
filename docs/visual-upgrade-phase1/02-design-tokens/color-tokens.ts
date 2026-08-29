/**
 * SmartCare AI — 统一颜色Token
 *
 * 设计原则：
 * - 蓝白医疗基调，专业克制
 * - 红色仅用于危急/失败/强制阻断
 * - 紫色表示AI生成/AI建议
 * - 灰色表示缺失/未知/不可用
 * - 所有状态必须同时提供颜色+图标+文字
 *
 * 注意：此文件为草案，待确认后合并到 design-system.css
 */

// ============================================
// 基础色板
// ============================================

/** 主色蓝 — 操作、选中、信息 */
export const COLOR_PRIMARY = '#1677FF'
export const COLOR_PRIMARY_DARK = '#0B3A6E'
export const COLOR_PRIMARY_LIGHT = '#EAF3FF'
export const COLOR_PRIMARY_HOVER = '#4096FF'
export const COLOR_PRIMARY_ACTIVE = '#0958D9'

/** AI紫色 — AI生成内容、模型状态 */
export const COLOR_AI = '#6E5AE6'
export const COLOR_AI_LIGHT = '#F0EDFF'
export const COLOR_AI_HOVER = '#8B7AED'
export const COLOR_AI_ACTIVE = '#5241C8'

// ============================================
// 页面背景与表面
// ============================================

export const COLOR_PAGE_BG = '#F4F7FB'
export const COLOR_SIDEBAR_BG = '#EAF1F8'
export const COLOR_CARD_BG = '#FFFFFF'
export const COLOR_HOVER_BG = '#F0F6FF'
export const COLOR_SELECTED_BG = '#DCEBFF'
export const COLOR_MASK_BG = 'rgba(0, 0, 0, 0.45)'

// ============================================
// 文字
// ============================================

export const COLOR_TEXT_PRIMARY = '#17233D'
export const COLOR_TEXT_SECONDARY = '#5F6B7A'
export const COLOR_TEXT_TERTIARY = '#8A94A6'
export const COLOR_TEXT_DISABLED = '#B6BEC9'
export const COLOR_TEXT_INVERSE = '#FFFFFF'

// ============================================
// 边框与分割线
// ============================================

export const COLOR_BORDER = '#DCE5EF'
export const COLOR_DIVIDER = '#E8EEF5'
export const COLOR_BORDER_FOCUS = '#1677FF'

// ============================================
// 临床状态色
// ============================================

/** 危急 — 红色：需要立即干预、生命威胁 */
export const COLOR_CRITICAL = '#D92D20'
export const COLOR_CRITICAL_BG = '#FEECEB'
export const COLOR_CRITICAL_HOVER = '#B42318'
export const COLOR_CRITICAL_BORDER = '#FDA29B'

/** 高风险 — 橙色：需要尽快处理 */
export const COLOR_HIGH_RISK = '#F79009'
export const COLOR_HIGH_RISK_BG = '#FFF3E0'
export const COLOR_HIGH_RISK_HOVER = '#DC6803'
export const COLOR_HIGH_RISK_BORDER = '#FEC84B'

/** 警告/提醒 — 黄色：需要关注 */
export const COLOR_WARNING = '#E5B700'
export const COLOR_WARNING_BG = '#FFF9D8'
export const COLOR_WARNING_HOVER = '#C9A100'
export const COLOR_WARNING_BORDER = '#FFE58F'

/** 正常/完成/恢复 — 绿色 */
export const COLOR_NORMAL = '#12A66A'
export const COLOR_NORMAL_BG = '#E8F7F0'
export const COLOR_NORMAL_HOVER = '#0E8A58'
export const COLOR_NORMAL_BORDER = '#84E1BC'

/** 信息 — 蓝色：一般趋势、选择 */
export const COLOR_INFO = '#2E90FA'
export const COLOR_INFO_BG = '#EAF4FF'
export const COLOR_INFO_HOVER = '#1570EF'
export const COLOR_INFO_BORDER = '#84CAFF'

/** 未知/缺失 — 灰色 */
export const COLOR_UNKNOWN = '#98A2B3'
export const COLOR_UNKNOWN_BG = '#F2F4F7'
export const COLOR_UNKNOWN_HOVER = '#667085'
export const COLOR_UNKNOWN_BORDER = '#D0D5DD'

// ============================================
// 图表序列颜色（固定8色，按使用顺序循环）
// ============================================

export const CHART_SERIES_COLORS = [
  '#1677FF', // 蓝 — 主要指标
  '#12A66A', // 绿 — 正常/对比
  '#6E5AE6', // 紫 — AI/辅助
  '#F79009', // 橙 — 警告/高风险
  '#27B3B8', // 青 — SpO₂/呼吸
  '#8B6FD6', // 浅紫 — 辅助
  '#5B8FF9', // 浅蓝 — 辅助
  '#98A2B3', // 灰 — 未知/缺失
] as const

// ============================================
// 临床指标固定颜色（跨页面一致）
// ============================================

export const CLINICAL_METRIC_COLORS = {
  /** 心率 */
  heartRate: '#E05252',
  /** 血压（收缩压） */
  systolicBP: '#1677FF',
  /** 血压（舒张压） */
  diastolicBP: '#5B8FF9',
  /** 平均动脉压 */
  map: '#4096FF',
  /** 血氧饱和度 */
  spo2: '#27B3B8',
  /** 呼吸频率 */
  respiratoryRate: '#6E5AE6',
  /** 体温 */
  temperature: '#F79009',
  /** 乳酸 */
  lactate: '#D92D20',
  /** 肌酐 */
  creatinine: '#8B6FD6',
  /** 血小板 */
  platelet: '#12A66A',
  /** 白细胞 */
  wbc: '#DC6803',
  /** 血红蛋白 */
  hemoglobin: '#B54708',
  /** FiO2 */
  fio2: '#98A2B3',
  /** PEEP */
  peep: '#667085',
  /** 尿量 */
  urineOutput: '#27B3B8',
  /** GCS */
  gcs: '#1677FF',
} as const

// ============================================
// 评分颜色
// ============================================

export const SCORE_COLORS = {
  sofa: '#1677FF',
  sofa2: '#0958D9',
  news2: '#F79009',
  qsofa: '#6E5AE6',
  mews: '#27B3B8',
  gcs: '#12A66A',
  aki: '#D92D20',
} as const

// ============================================
// 状态映射（颜色+图标+文字，禁止仅依靠颜色）
// ============================================

export type ClinicalStatus = 'critical' | 'high-risk' | 'warning' | 'normal' | 'info' | 'unknown'

export interface StatusConfig {
  color: string
  bgColor: string
  borderColor: string
  icon: string // Ant Design Icon 名称
  label: string
}

export const CLINICAL_STATUS_MAP: Record<ClinicalStatus, StatusConfig> = {
  'critical': {
    color: COLOR_CRITICAL,
    bgColor: COLOR_CRITICAL_BG,
    borderColor: COLOR_CRITICAL_BORDER,
    icon: 'CloseCircleFilled',
    label: '危急',
  },
  'high-risk': {
    color: COLOR_HIGH_RISK,
    bgColor: COLOR_HIGH_RISK_BG,
    borderColor: COLOR_HIGH_RISK_BORDER,
    icon: 'ExclamationCircleFilled',
    label: '高风险',
  },
  'warning': {
    color: COLOR_WARNING,
    bgColor: COLOR_WARNING_BG,
    borderColor: COLOR_WARNING_BORDER,
    icon: 'WarningFilled',
    label: '提醒',
  },
  'normal': {
    color: COLOR_NORMAL,
    bgColor: COLOR_NORMAL_BG,
    borderColor: COLOR_NORMAL_BORDER,
    icon: 'CheckCircleFilled',
    label: '正常',
  },
  'info': {
    color: COLOR_INFO,
    bgColor: COLOR_INFO_BG,
    borderColor: COLOR_INFO_BORDER,
    icon: 'InfoCircleFilled',
    label: '信息',
  },
  'unknown': {
    color: COLOR_UNKNOWN,
    bgColor: COLOR_UNKNOWN_BG,
    borderColor: COLOR_UNKNOWN_BORDER,
    icon: 'QuestionCircleFilled',
    label: '未知',
  },
}

// ============================================
// 流程节点状态颜色
// ============================================

export type FlowNodeStatus = 'pending' | 'running' | 'completed' | 'warning' | 'failed' | 'skipped' | 'blocked' | 'unknown'

export const FLOW_NODE_STATUS_MAP: Record<FlowNodeStatus, { color: string; bgColor: string; label: string }> = {
  pending:   { color: '#8A94A6', bgColor: '#F2F4F7', label: '待处理' },
  running:   { color: '#1677FF', bgColor: '#EAF4FF', label: '进行中' },
  completed: { color: '#12A66A', bgColor: '#E8F7F0', label: '已完成' },
  warning:   { color: '#F79009', bgColor: '#FFF3E0', label: '有警告' },
  failed:    { color: '#D92D20', bgColor: '#FEECEB', label: '失败' },
  skipped:   { color: '#98A2B3', bgColor: '#F2F4F7', label: '已跳过' },
  blocked:   { color: '#D92D20', bgColor: '#FEECEB', label: '被阻断' },
  unknown:   { color: '#98A2B3', bgColor: '#F2F4F7', label: '未知' },
}

// ============================================
// AI内容标识
// ============================================

export const AI_CONTENT_BORDER = `3px solid ${COLOR_AI}`
export const AI_CONTENT_BG = COLOR_AI_LIGHT
export const DETERMINISTIC_CONTENT_BORDER = `3px solid ${COLOR_PRIMARY}`
export const HUMAN_CONFIRMED_BORDER = `3px solid ${COLOR_NORMAL}`
