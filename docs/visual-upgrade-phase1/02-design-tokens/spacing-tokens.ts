/**
 * SmartCare AI — 间距与布局Token
 *
 * 桌面端尺寸：
 * - 顶部栏高度：56px
 * - 左侧导航展开：224px / 收起：64px
 * - 内容区域内边距：24px
 * - 区块间距：16px
 * - 卡片内边距：16px或20px
 * - 常规卡片最小高度：120px
 * - 图表卡片建议高度：280-420px
 */

// ============================================
// 基础间距单位（4px网格）
// ============================================

export const SPACE = {
  /** 4px */
  xs: '4px',
  /** 8px */
  sm: '8px',
  /** 12px */
  md: '12px',
  /** 16px */
  lg: '16px',
  /** 20px */
  xl: '20px',
  /** 24px */
  '2xl': '24px',
  /** 32px */
  '3xl': '32px',
  /** 40px */
  '4xl': '40px',
  /** 48px */
  '5xl': '48px',
} as const

// ============================================
// 页面布局
// ============================================

export const LAYOUT = {
  /** 顶部栏高度 */
  topbarHeight: '56px',
  /** 左侧导航展开宽度 */
  sidebarExpandedWidth: '224px',
  /** 左侧导航收起宽度 */
  sidebarCollapsedWidth: '64px',
  /** 内容区域内边距 */
  contentPadding: '24px',
  /** 区块间距 */
  sectionGap: '16px',
  /** 同组元素间距 */
  elementGap: '8px',
  /** 卡片内边距 */
  cardPadding: '16px',
  /** 卡片内边距（宽松） */
  cardPaddingLarge: '20px',
  /** 常规卡片最小高度 */
  cardMinHeight: '120px',
  /** 图表卡片建议高度 */
  chartCardHeight: '360px',
  /** 图表卡片最小高度 */
  chartCardMinHeight: '280px',
  /** 图表卡片最大高度 */
  chartCardMaxHeight: '420px',
} as const

// ============================================
// 圆角
// ============================================

export const RADIUS = {
  /** 普通卡片 8px */
  card: '8px',
  /** 弹窗 10px */
  modal: '10px',
  /** 标签 4px */
  tag: '4px',
  /** 胶囊标签 */
  tagPill: '100px',
  /** 按钮 6px */
  button: '6px',
  /** 输入框 6px */
  input: '6px',
  /** 小元素 4px */
  sm: '4px',
} as const

// ============================================
// 阴影
// ============================================

export const SHADOW = {
  /** 默认卡片浅阴影 */
  card: '0 1px 3px rgba(16, 24, 40, 0.08)',
  /** 悬浮卡片 */
  cardHover: '0 6px 18px rgba(16, 24, 40, 0.10)',
  /** 弹窗 */
  modal: '0 20px 40px rgba(16, 24, 40, 0.12)',
  /** 下拉菜单 */
  dropdown: '0 8px 24px rgba(16, 24, 40, 0.10)',
  /** 禁止：大面积悬浮阴影、玻璃拟态、强烈发光 */
} as const

// ============================================
// 边框
// ============================================

export const BORDER = {
  /** 默认1px */
  default: '1px solid #DCE5EF',
  /** 焦点 */
  focus: '1px solid #1677FF',
  /** 危急卡片左侧状态条 4px */
  criticalRail: '4px solid #D92D20',
  /** 高风险左侧状态条 */
  highRiskRail: '4px solid #F79009',
  /** AI内容左侧状态条 */
  aiRail: '4px solid #6E5AE6',
  /** 已完成左侧状态条 */
  completedRail: '4px solid #12A66A',
} as const

// ============================================
// 栅格系统
// ============================================

export const GRID = {
  /** 总列数 */
  columns: 24,
  /** 栅格间距 */
  gutter: 16,
} as const

// ============================================
// 响应式断点
// ============================================

export const BREAKPOINTS = {
  /** 大屏 */
  '2xl': 2560,
  /** 桌面 */
  xl: 1920,
  /** 桌面 */
  lg: 1440,
  /** 桌面压缩 */
  md: 1200,
  /** 平板 */
  sm: 768,
  /** 移动端 */
  xs: 390,
} as const
