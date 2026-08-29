/**
 * SmartCare AI — 字体与文字Token
 * 医院内网，禁止引用在线字体。优先系统字体。
 */

export const FONT_FAMILY = {
  primary: '"Microsoft YaHei", "PingFang SC", "Noto Sans SC", "Segoe UI", Arial, sans-serif',
  mono: '"SF Mono", "Consolas", "Liberation Mono", "Menlo", monospace',
  digit: '"Rajdhani", "Microsoft YaHei", sans-serif',
} as const

export const FONT_SIZE = {
  systemName: 18,
  pageTitle: 20,
  patientName: 18,
  sectionTitle: 16,
  cardTitle: 14,
  body: 14,
  caption: 12,
  table: 13,
  metricLarge: 28,
  monitorLarge: 36,
  chartAxis: 11,
  chartLegend: 12,
  chartTooltip: 12,
  label: 12,
} as const

export const FONT_WEIGHT = {
  regular: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
} as const

export const LINE_HEIGHT = {
  body: 1.6,
  table: 1.4,
  title: 1.3,
  metric: 1.15,
} as const
