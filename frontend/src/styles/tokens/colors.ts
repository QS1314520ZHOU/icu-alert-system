/**
 * SmartCare AI — 统一颜色Token
 *
 * 蓝白医疗基调，专业克制。
 * 红色仅用于危急/失败，紫色表示AI内容，灰色表示未知/缺失。
 * 所有状态必须同时提供：颜色 + 图标 + 文字。
 */

// ── 基础色板 ──────────────────────────────────────

/** 主色蓝 — 操作、选中、信息 */
export const PRIMARY = '#1677FF'
export const PRIMARY_DARK = '#0B3A6E'
export const PRIMARY_LIGHT = '#EAF3FF'
export const PRIMARY_HOVER = '#4096FF'
export const PRIMARY_ACTIVE = '#0958D9'

/** AI紫色 — AI生成内容、模型状态 */
export const AI = '#6E5AE6'
export const AI_LIGHT = '#F0EDFF'
export const AI_HOVER = '#8B7AED'
export const AI_ACTIVE = '#5241C8'

// ── 页面背景与表面 ────────────────────────────────

export const PAGE_BG = '#F4F7FB'
export const SIDEBAR_BG = '#EAF1F8'
export const CARD_BG = '#FFFFFF'
export const HOVER_BG = '#F0F6FF'
export const SELECTED_BG = '#DCEBFF'

// ── 文字 ──────────────────────────────────────────

export const TEXT_PRIMARY = '#17233D'
export const TEXT_SECONDARY = '#5F6B7A'
export const TEXT_TERTIARY = '#8A94A6'
export const TEXT_DISABLED = '#B6BEC9'
export const TEXT_INVERSE = '#FFFFFF'

// ── 边框与分割线 ──────────────────────────────────

export const BORDER = '#DCE5EF'
export const DIVIDER = '#E8EEF5'
export const BORDER_FOCUS = '#1677FF'

// ── 临床状态色 ────────────────────────────────────

/** 危急 — 红色 */
export const CRITICAL = '#D92D20'
export const CRITICAL_BG = '#FEECEB'
export const CRITICAL_BORDER = '#FDA29B'

/** 高风险 — 橙色 */
export const HIGH_RISK = '#F79009'
export const HIGH_RISK_BG = '#FFF3E0'
export const HIGH_RISK_BORDER = '#FEC84B'

/** 警告 — 黄色 */
export const WARNING = '#E5B700'
export const WARNING_BG = '#FFF9D8'
export const WARNING_BORDER = '#FFE58F'

/** 正常 — 绿色 */
export const NORMAL = '#12A66A'
export const NORMAL_BG = '#E8F7F0'
export const NORMAL_BORDER = '#84E1BC'

/** 信息 — 蓝色 */
export const INFO = '#2E90FA'
export const INFO_BG = '#EAF4FF'
export const INFO_BORDER = '#84CAFF'

/** 未知 — 灰色 */
export const UNKNOWN = '#98A2B3'
export const UNKNOWN_BG = '#F2F4F7'
export const UNKNOWN_BORDER = '#D0D5DD'

// ── 图表序列颜色（8色循环）──────────────────────

export const CHART_SERIES = [
  '#1677FF', '#12A66A', '#6E5AE6', '#F79009',
  '#27B3B8', '#8B6FD6', '#5B8FF9', '#98A2B3',
] as const

// ── 临床指标固定颜色（跨页面一致）────────────────

export const METRIC = {
  heartRate: '#E05252',
  systolicBP: '#1677FF',
  diastolicBP: '#5B8FF9',
  map: '#4096FF',
  spo2: '#27B3B8',
  respiratoryRate: '#6E5AE6',
  temperature: '#F79009',
  lactate: '#D92D20',
  creatinine: '#8B6FD6',
  platelet: '#12A66A',
  wbc: '#DC6803',
  hemoglobin: '#B54708',
  fio2: '#98A2B3',
  peep: '#667085',
  urineOutput: '#27B3B8',
  gcs: '#1677FF',
} as const

// ── 评分颜色 ──────────────────────────────────────

export const SCORE = {
  sofa: '#1677FF',
  sofa2: '#0958D9',
  news2: '#F79009',
  qsofa: '#6E5AE6',
  mews: '#27B3B8',
  gcs: '#12A66A',
  aki: '#D92D20',
} as const

// ── 状态映射 ──────────────────────────────────────

export type ClinicalStatus = 'critical' | 'high-risk' | 'warning' | 'normal' | 'info' | 'unknown'

export interface StatusConfig {
  color: string
  bgColor: string
  borderColor: string
  icon: string
  label: string
}

export const STATUS_MAP: Record<ClinicalStatus, StatusConfig> = {
  'critical':  { color: CRITICAL,  bgColor: CRITICAL_BG,  borderColor: CRITICAL_BORDER,  icon: 'CloseCircleFilled',      label: '危急' },
  'high-risk': { color: HIGH_RISK, bgColor: HIGH_RISK_BG, borderColor: HIGH_RISK_BORDER, icon: 'ExclamationCircleFilled', label: '高风险' },
  'warning':   { color: WARNING,   bgColor: WARNING_BG,   borderColor: WARNING_BORDER,   icon: 'WarningFilled',           label: '提醒' },
  'normal':    { color: NORMAL,    bgColor: NORMAL_BG,    borderColor: NORMAL_BORDER,    icon: 'CheckCircleFilled',       label: '正常' },
  'info':      { color: INFO,      bgColor: INFO_BG,      borderColor: INFO_BORDER,      icon: 'InfoCircleFilled',        label: '信息' },
  'unknown':   { color: UNKNOWN,   bgColor: UNKNOWN_BG,   borderColor: UNKNOWN_BORDER,   icon: 'QuestionCircleFilled',    label: '未知' },
}

// ── 流程节点状态 ──────────────────────────────────

export type FlowNodeStatus = 'pending' | 'running' | 'completed' | 'warning' | 'failed' | 'skipped' | 'blocked' | 'unknown'

export const FLOW_STATUS_MAP: Record<FlowNodeStatus, { color: string; bgColor: string; label: string }> = {
  pending:   { color: '#8A94A6', bgColor: '#F2F4F7', label: '待处理' },
  running:   { color: '#1677FF', bgColor: '#EAF4FF', label: '进行中' },
  completed: { color: '#12A66A', bgColor: '#E8F7F0', label: '已完成' },
  warning:   { color: '#F79009', bgColor: '#FFF3E0', label: '有警告' },
  failed:    { color: '#D92D20', bgColor: '#FEECEB', label: '失败' },
  skipped:   { color: '#98A2B3', bgColor: '#F2F4F7', label: '已跳过' },
  blocked:   { color: '#D92D20', bgColor: '#FEECEB', label: '被阻断' },
  unknown:   { color: '#98A2B3', bgColor: '#F2F4F7', label: '未知' },
}

// ── AI内容标识 ────────────────────────────────────

export const AI_BORDER = `3px solid ${AI}`
export const AI_BG = AI_LIGHT
export const DETERMINISTIC_BORDER = `3px solid ${PRIMARY}`
export const HUMAN_CONFIRMED_BORDER = `3px solid ${NORMAL}`
