/**
 * SmartCare AI — 间距与布局Token
 * 4px网格系统
 */

export const SPACE = {
  xs: 4,   sm: 8,   md: 12,  lg: 16,
  xl: 20,  '2xl': 24, '3xl': 32, '4xl': 40, '5xl': 48,
} as const

export const LAYOUT = {
  topbarHeight: 56,
  sidebarExpanded: 224,
  sidebarCollapsed: 64,
  contentPadding: 24,
  sectionGap: 16,
  elementGap: 8,
  cardPadding: 16,
  cardPaddingLarge: 20,
  cardMinHeight: 120,
  chartCardHeight: 360,
  chartCardMin: 280,
  chartCardMax: 420,
} as const

export const RADIUS = {
  card: 8, modal: 10, tag: 4, tagPill: 100,
  button: 6, input: 6, sm: 4,
} as const

export const SHADOW = {
  card: '0 1px 3px rgba(16, 24, 40, 0.08)',
  cardHover: '0 6px 18px rgba(16, 24, 40, 0.10)',
  modal: '0 20px 40px rgba(16, 24, 40, 0.12)',
  dropdown: '0 8px 24px rgba(16, 24, 40, 0.10)',
} as const

export const BORDER_STYLE = {
  default: '1px solid #DCE5EF',
  focus: '1px solid #1677FF',
  criticalRail: '4px solid #D92D20',
  highRiskRail: '4px solid #F79009',
  aiRail: '4px solid #6E5AE6',
  completedRail: '4px solid #12A66A',
} as const
