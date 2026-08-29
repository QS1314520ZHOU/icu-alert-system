/**
 * SmartCare AI — ECharts 统一主题Token
 *
 * 基于现有 icuTheme.ts 扩展，统一所有图表样式。
 * 覆盖：tooltip、legend、axis、grid、series颜色。
 *
 * 使用方式：
 *   import { useSmartCareChartTheme } from './chart-theme'
 *   const option = { ...useSmartCareChartTheme(), series: [...] }
 */

import {
  CHART_SERIES_COLORS,
  CLINICAL_METRIC_COLORS,
  COLOR_TEXT_PRIMARY,
  COLOR_TEXT_SECONDARY,
  COLOR_TEXT_TERTIARY,
  COLOR_BORDER,
  COLOR_DIVIDER,
  COLOR_PAGE_BG,
  COLOR_CARD_BG,
} from './color-tokens'
import { FONT_SIZE, FONT_FAMILY_PRIMARY } from './typography-tokens'

// ============================================
// Tooltip 统一样式
// ============================================

export function chartTooltip(extra: Record<string, any> = {}) {
  return {
    backgroundColor: 'rgba(255, 255, 255, 0.96)',
    borderColor: COLOR_BORDER,
    borderWidth: 1,
    padding: [10, 12],
    textStyle: {
      color: COLOR_TEXT_PRIMARY,
      fontSize: 12,
      lineHeight: 18,
      fontFamily: FONT_FAMILY_PRIMARY,
    },
    extraCssText: 'box-shadow: 0 4px 12px rgba(16, 24, 40, 0.08); border-radius: 8px;',
    axisPointer: {
      lineStyle: { color: 'rgba(22, 119, 255, 0.2)' },
      crossStyle: { color: 'rgba(22, 119, 255, 0.2)' },
      shadowStyle: { color: 'rgba(22, 119, 255, 0.04)' },
      label: {
        backgroundColor: '#F0F6FF',
        color: COLOR_TEXT_PRIMARY,
      },
    },
    ...extra,
  }
}

// ============================================
// Legend 统一样式
// ============================================

export function chartLegend(extra: Record<string, any> = {}) {
  return {
    top: 0,
    icon: 'roundRect',
    itemWidth: 10,
    itemHeight: 10,
    itemGap: 14,
    textStyle: {
      color: COLOR_TEXT_SECONDARY,
      fontSize: 12,
      fontFamily: FONT_FAMILY_PRIMARY,
      padding: [0, 0, 0, 4],
    },
    ...extra,
  }
}

// ============================================
// Grid 统一样式
// ============================================

export function chartGrid(extra: Record<string, any> = {}) {
  return {
    left: 12,
    right: 16,
    top: 40,
    bottom: 12,
    containLabel: true,
    ...extra,
  }
}

// ============================================
// X轴（类目轴）统一
// ============================================

export function chartXAxis(data: string[], extra: Record<string, any> = {}) {
  return {
    type: 'category',
    data,
    axisTick: { show: false },
    axisLine: { lineStyle: { color: COLOR_BORDER } },
    axisLabel: {
      color: COLOR_TEXT_TERTIARY,
      fontSize: 11,
      fontFamily: FONT_FAMILY_PRIMARY,
      margin: 10,
    },
    ...extra,
  }
}

// ============================================
// Y轴（数值轴）统一
// ============================================

export function chartYAxis(extra: Record<string, any> = {}) {
  return {
    type: 'value',
    axisLine: { show: false },
    axisLabel: {
      color: COLOR_TEXT_TERTIARY,
      fontSize: 11,
      fontFamily: FONT_FAMILY_PRIMARY,
    },
    splitLine: {
      lineStyle: { color: COLOR_DIVIDER, type: 'dashed' },
    },
    ...extra,
  }
}

// ============================================
// 系列颜色（按顺序循环）
// ============================================

export function getChartColor(index: number): string {
  return CHART_SERIES_COLORS[index % CHART_SERIES_COLORS.length]
}

/** 临床指标固定颜色 */
export const metricColors = CLINICAL_METRIC_COLORS

// ============================================
// 常用图表配置模板
// ============================================

/** 折线图基础配置 */
export function lineChartBase(xData: string[], extra: Record<string, any> = {}) {
  return {
    tooltip: chartTooltip({ trigger: 'axis' }),
    legend: chartLegend(),
    grid: chartGrid(),
    xAxis: chartXAxis(xData),
    yAxis: chartYAxis(),
    ...extra,
  }
}

/** 柱状图基础配置 */
export function barChartBase(xData: string[], extra: Record<string, any> = {}) {
  return {
    tooltip: chartTooltip({ trigger: 'axis' }),
    legend: chartLegend(),
    grid: chartGrid(),
    xAxis: chartXAxis(xData),
    yAxis: chartYAxis(),
    ...extra,
  }
}

/** 饼图/环图基础配置 */
export function pieChartBase(extra: Record<string, any> = {}) {
  return {
    tooltip: chartTooltip({ trigger: 'item' }),
    legend: chartLegend({ bottom: 0, top: 'auto' }),
    ...extra,
  }
}

/** 散点图基础配置 */
export function scatterChartBase(extra: Record<string, any> = {}) {
  return {
    tooltip: chartTooltip({ trigger: 'item' }),
    legend: chartLegend(),
    grid: chartGrid(),
    xAxis: { type: 'value', axisLabel: { color: COLOR_TEXT_TERTIARY, fontSize: 11 } },
    yAxis: { type: 'value', axisLabel: { color: COLOR_TEXT_TERTIARY, fontSize: 11 }, splitLine: { lineStyle: { type: 'dashed', color: COLOR_DIVIDER } } },
    ...extra,
  }
}

// ============================================
// 正常范围带（用于生命体征趋势图）
// ============================================

export function normalRangeMarkArea(min: number, max: number, color = 'rgba(18, 166, 106, 0.06)') {
  return {
    markArea: {
      silent: true,
      data: [[{ yAxis: min, itemStyle: { color } }, { yAxis: max }]],
    },
  }
}

// ============================================
// 事件标记线（用药、手术、插管等）
// ============================================

export function eventMarkLine(time: string, label: string, color = '#1677FF') {
  return {
    markLine: {
      silent: true,
      symbol: 'none',
      lineStyle: { color, type: 'dashed', width: 1 },
      data: [{ xAxis: time, label: { formatter: label, fontSize: 10, color } }],
    },
  }
}
