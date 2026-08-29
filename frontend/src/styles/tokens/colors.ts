/**
 * ICU Clinical Intelligence — 统一颜色Token
 *
 * 专业、安静、清晰的临床工作台风格。
 * 红色仅用于危急/高风险，避免装饰性使用。
 * 所有状态必须同时提供：颜色 + 图标 + 文字。
 */

// ── 基础色板 ──────────────────────────────────────

/** 主色蓝 — 操作、选中、信息 */
export const PRIMARY = '#2563EB'
export const PRIMARY_DARK = '#1E40AF'
export const PRIMARY_LIGHT = '#EFF6FF'
export const PRIMARY_HOVER = '#3B82F6'
export const PRIMARY_ACTIVE = '#1D4ED8'

/** 辅助青色 — 数据、趋势、辅助操作 */
export const ACCENT = '#0891B2'
export const ACCENT_LIGHT = '#ECFEFF'
export const ACCENT_HOVER = '#06B6D4'
export const ACCENT_ACTIVE = '#0E7490'

/** AI紫色 — AI生成内容、模型状态 */
export const AI = '#7C3AED'
export const AI_LIGHT = '#F5F3FF'
export const AI_HOVER = '#8B5CF6'
export const AI_ACTIVE = '#6D28D9'

// ── 页面背景与表面 ────────────────────────────────

export const PAGE_BG = '#F4F7FB'
export const SIDEBAR_BG = '#0F1F33'
export const SIDEBAR_TEXT = '#94A3B8'
export const SIDEBAR_TEXT_ACTIVE = '#FFFFFF'
export const SIDEBAR_HOVER = 'rgba(255,255,255,0.06)'
export const CARD_BG = '#FFFFFF'
export const HOVER_BG = '#F0F6FF'
export const SELECTED_BG = '#DBEAFE'

// ── 文字 ──────────────────────────────────────────

export const TEXT_PRIMARY = '#182230'
export const TEXT_SECONDARY = '#52606D'
export const TEXT_TERTIARY = '#94A3B8'
export const TEXT_DISABLED = '#94A3B8'
export const TEXT_INVERSE = '#FFFFFF'

// ── 边框与分割线 ──────────────────────────────────

export const BORDER = '#DCE3EC'
export const DIVIDER = '#E8EEF5'
export const BORDER_FOCUS = '#2563EB'

// ── 临床状态色 ────────────────────────────────────

/** 正常 — 绿色 */
export const NORMAL = '#16A34A'
export const NORMAL_BG = '#F0FDF4'
export const NORMAL_BORDER = '#BBF7D0'

/** 信息/提示 — 蓝色 */
export const INFO = '#0284C7'
export const INFO_BG = '#E0F2FE'
export const INFO_BORDER = '#7DD3FC'

/** 警告 — 琥珀色 */
export const WARNING = '#F59E0B'
export const WARNING_BG = '#FFFBEB'
export const WARNING_BORDER = '#FDE68A'

/** 高风险 — 红色 */
export const HIGH_RISK = '#DC2626'
export const HIGH_RISK_BG = '#FEF2F2'
export const HIGH_RISK_BORDER = '#FECACA'

/** 严重风险 — 深红色 */
export const CRITICAL = '#991B1B'
export const CRITICAL_BG = '#FEF2F2'
export const CRITICAL_BORDER = '#FCA5A5'

/** 未知 — 灰色 */
export const UNKNOWN = '#94A3B8'
export const UNKNOWN_BG = '#F1F5F9'
export const UNKNOWN_BORDER = '#CBD5E1'

// ── 图表序列颜色（8色循环）──────────────────────

export const CHART_SERIES = [
  '#2563EB', '#16A34A', '#0891B2', '#F59E0B',
  '#7C3AED', '#DC2626', '#0284C7', '#94A3B8',
] as const

// ── 临床指标固定颜色（跨页面一致）────────────────

export const METRIC = {
  heartRate: '#DC2626',
  systolicBP: '#2563EB',
  diastolicBP: '#3B82F6',
  map: '#1D4ED8',
  spo2: '#0891B2',
  respiratoryRate: '#7C3AED',
  temperature: '#F59E0B',
  lactate: '#DC2626',
  creatinine: '#7C3AED',
  platelet: '#16A34A',
  wbc: '#EA580C',
  hemoglobin: '#B45309',
  fio2: '#94A3B8',
  peep: '#64748B',
  urineOutput: '#0891B2',
  gcs: '#2563EB',
} as const

// ── 评分颜色 ──────────────────────────────────────

export const SCORE = {
  sofa: '#2563EB',
  sofa2: '#1D4ED8',
  news2: '#F59E0B',
  qsofa: '#7C3AED',
  mews: '#0891B2',
  gcs: '#16A34A',
  aki: '#DC2626',
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
  pending:   { color: '#94A3B8', bgColor: '#F1F5F9', label: '待处理' },
  running:   { color: '#2563EB', bgColor: '#EFF6FF', label: '进行中' },
  completed: { color: '#16A34A', bgColor: '#F0FDF4', label: '已完成' },
  warning:   { color: '#F59E0B', bgColor: '#FFFBEB', label: '有警告' },
  failed:    { color: '#DC2626', bgColor: '#FEF2F2', label: '失败' },
  skipped:   { color: '#94A3B8', bgColor: '#F1F5F9', label: '已跳过' },
  blocked:   { color: '#DC2626', bgColor: '#FEF2F2', label: '被阻断' },
  unknown:   { color: '#94A3B8', bgColor: '#F1F5F9', label: '未知' },
}

// ── AI内容标识 ────────────────────────────────────

export const AI_BORDER = `3px solid ${AI}`
export const AI_BG = AI_LIGHT
export const DETERMINISTIC_BORDER = `3px solid ${PRIMARY}`
export const HUMAN_CONFIRMED_BORDER = `3px solid ${NORMAL}`

// ── 深色导航栏 ────────────────────────────────────

export const NAV_BG = '#0F1F33'
export const NAV_BG_ACTIVE = 'rgba(37,99,235,0.15)'
export const NAV_TEXT = '#94A3B8'
export const NAV_TEXT_ACTIVE = '#FFFFFF'
export const NAV_BORDER = 'rgba(255,255,255,0.08)'
