/**
 * SmartCare AI — 字体与文字Token
 *
 * 约束：
 * - 医院内网，禁止引用在线字体
 * - 优先使用系统字体
 * - 移动端正文字不小于14px
 * - 图表坐标轴11-12px
 */

// ============================================
// 字体栈
// ============================================

export const FONT_FAMILY_PRIMARY = '"Microsoft YaHei", "PingFang SC", "Noto Sans SC", "Segoe UI", Arial, sans-serif'
export const FONT_FAMILY_MONO = '"SF Mono", "Consolas", "Liberation Mono", "Menlo", monospace'
/** 监护数字专用 */
export const FONT_FAMILY_DIGIT = '"Rajdhani", "Microsoft YaHei", sans-serif'

// ============================================
// 字号
// ============================================

export const FONT_SIZE = {
  /** 系统名称 18px / 600 */
  systemName: '18px',
  /** 页面标题 20px / 600 */
  pageTitle: '20px',
  /** 患者姓名 18px / 600 */
  patientName: '18px',
  /** 区块标题 16px / 600 */
  sectionTitle: '16px',
  /** 卡片标题 14px / 600 */
  cardTitle: '14px',
  /** 正文 14px / 400 */
  body: '14px',
  /** 辅助说明 12px / 400 */
  caption: '12px',
  /** 表格内容 13px / 400 */
  table: '13px',
  /** 指标大数字 24-32px / 600 */
  metricLarge: '28px',
  /** ICU大屏数字 32-44px / 600 */
  monitorLarge: '36px',
  /** 图表坐标轴 11-12px */
  chartAxis: '11px',
  /** 图例 12px */
  chartLegend: '12px',
  /** Tooltip 12-13px */
  chartTooltip: '12px',
  /** 标签 12px */
  label: '12px',
} as const

// ============================================
// 字重
// ============================================

export const FONT_WEIGHT = {
  regular: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
} as const

// ============================================
// 行高
// ============================================

export const LINE_HEIGHT = {
  /** 正文 1.5-1.7 */
  body: 1.6,
  /** 表格 1.4 */
  table: 1.4,
  /** 标题 1.3 */
  title: 1.3,
  /** 大数字 1.15 */
  metric: 1.15,
} as const

// ============================================
// 文字规范（用于 lint/检查）
// ============================================

export const TEXT_RULES = {
  /** 卡片标题不超过16个汉字 */
  maxCardTitleChars: 16,
  /** 图表解释限制2-4行 */
  chartExplanationLines: { min: 2, max: 4 },
  /** 禁止连续超过300字 */
  maxContinuousChars: 300,
} as const
