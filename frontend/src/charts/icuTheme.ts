/**
 * SmartCare AI — ECharts 统一主题
 *
 * 基于 design token 构建，所有图表必须通过本文件获取样式。
 * 禁止在组件内硬编码颜色、字号、间距。
 */

import { getThemeMode, useThemeMode } from '../composables/themeMode'
import {
  CHART_SERIES, METRIC, SCORE,
  TEXT_PRIMARY, TEXT_SECONDARY, TEXT_TERTIARY,
  BORDER as COLOR_BORDER, DIVIDER,
  PRIMARY, PRIMARY_LIGHT,
} from '../styles/tokens/colors'
import { FONT_FAMILY, FONT_SIZE } from '../styles/tokens/typography'

type AnyObj = Record<string, any>

// ── 主题模式检测 ──────────────────────────────────

function currentThemeMode() {
  const themeMode = useThemeMode()
  return themeMode.value || getThemeMode()
}

function isLight() {
  return currentThemeMode() === 'light'
}

// ── Token 获取 ────────────────────────────────────

export function icuChartTokens() {
  if (isLight()) {
    return {
      tooltipBg: 'rgba(255,255,255,0.96)',
      tooltipBorder: COLOR_BORDER,
      tooltipText: TEXT_PRIMARY,
      tooltipShadow: 'box-shadow: 0 4px 12px rgba(16,24,40,0.08); border-radius: 8px;',
      tooltipAxisLabelBg: PRIMARY_LIGHT,
      tooltipAxisLabelText: TEXT_PRIMARY,
      axisLine: COLOR_BORDER,
      axisLabel: TEXT_TERTIARY,
      axisLabelStrong: TEXT_SECONDARY,
      splitLine: DIVIDER,
      shadowArea: 'rgba(22,119,255,0.04)',
      crossLine: 'rgba(22,119,255,0.2)',
      legendText: TEXT_SECONDARY,
      heatmapText: TEXT_SECONDARY,
      heatmapRange: ['#F4F7FB', '#EAF3FF', '#1677FF', '#F79009', '#D92D20'],
      labelStrong: TEXT_PRIMARY,
    }
  }
  return {
    tooltipBg: 'rgba(4,14,24,.97)',
    tooltipBorder: 'rgba(88,225,255,.2)',
    tooltipText: '#e8fbff',
    tooltipShadow: 'box-shadow: 0 14px 30px rgba(0,0,0,.34); border-radius: 12px; backdrop-filter: blur(10px);',
    tooltipAxisLabelBg: 'rgba(8,31,47,0.96)',
    tooltipAxisLabelText: '#dffbff',
    axisLine: 'rgba(79,182,219,.18)',
    axisLabel: '#86d3e8',
    axisLabelStrong: '#b7ddec',
    splitLine: 'rgba(61,118,145,.14)',
    shadowArea: 'rgba(56,189,248,0.08)',
    crossLine: 'rgba(110,231,249,0.22)',
    legendText: '#9edff0',
    heatmapText: '#7fc7da',
    heatmapRange: ['#0a2234', '#0e4c68', '#15558D', '#E8901C', '#D9342B'],
    labelStrong: '#dffafc',
  }
}

// ── 组件工厂 ──────────────────────────────────────

function merge(base: AnyObj, extra: AnyObj = {}) {
  return { ...base, ...extra }
}

/** Tooltip 统一样式 */
export function icuTooltip(extra: AnyObj = {}) {
  const t = icuChartTokens()
  const base = {
    backgroundColor: t.tooltipBg,
    borderColor: t.tooltipBorder,
    borderWidth: 1,
    padding: [10, 12],
    textStyle: { color: t.tooltipText, fontSize: FONT_SIZE.chartTooltip, lineHeight: 18, fontFamily: FONT_FAMILY.primary },
    extraCssText: t.tooltipShadow,
    axisPointer: {
      lineStyle: { color: t.crossLine },
      crossStyle: { color: t.crossLine },
      shadowStyle: { color: t.shadowArea },
      label: { backgroundColor: t.tooltipAxisLabelBg, color: t.tooltipAxisLabelText },
    },
  }
  return {
    ...base, ...extra,
    textStyle: merge(base.textStyle, extra.textStyle ?? {}),
    axisPointer: merge(base.axisPointer, extra.axisPointer ?? {}),
  }
}

/** Legend 统一样式 */
export function icuLegend(extra: AnyObj = {}) {
  const t = icuChartTokens()
  return {
    top: 0,
    icon: 'roundRect',
    itemWidth: 10,
    itemHeight: 10,
    itemGap: 14,
    textStyle: { color: t.legendText, fontSize: FONT_SIZE.chartLegend, fontFamily: FONT_FAMILY.primary, padding: [0, 0, 0, 4] },
    ...extra,
  }
}

/** Grid 统一样式 */
export function icuGrid(extra: AnyObj = {}) {
  return { left: 12, right: 16, top: 40, bottom: 12, containLabel: true, ...extra }
}

/** X轴（类目轴） */
export function icuCategoryAxis(data: any[], extra: AnyObj = {}) {
  const t = icuChartTokens()
  return {
    type: 'category',
    data,
    axisTick: { show: false },
    axisLine: { lineStyle: { color: t.axisLine } },
    axisLabel: { color: t.axisLabel, fontSize: FONT_SIZE.chartAxis, fontFamily: FONT_FAMILY.primary, margin: 10 },
    ...extra,
  }
}

/** Y轴（数值轴） */
export function icuValueAxis(extra: AnyObj = {}) {
  const t = icuChartTokens()
  return {
    type: 'value',
    axisLine: { show: false },
    axisLabel: { color: t.axisLabel, fontSize: FONT_SIZE.chartAxis, fontFamily: FONT_FAMILY.primary },
    splitLine: { lineStyle: { color: t.splitLine, type: 'dashed' } },
    ...extra,
  }
}

// ── 图表序列颜色 ──────────────────────────────────

export function getChartColor(index: number): string {
  return CHART_SERIES[index % CHART_SERIES.length] ?? '#1677FF'
}

export { METRIC as metricColors, SCORE as scoreColors }

// ── 常用图表配置模板 ──────────────────────────────

/** 折线图基础配置 */
export function lineChartBase(xData: string[], extra: AnyObj = {}) {
  return {
    tooltip: icuTooltip({ trigger: 'axis' }),
    legend: icuLegend(),
    grid: icuGrid(),
    xAxis: icuCategoryAxis(xData),
    yAxis: icuValueAxis(),
    ...extra,
  }
}

/** 柱状图基础配置 */
export function barChartBase(xData: string[], extra: AnyObj = {}) {
  return {
    tooltip: icuTooltip({ trigger: 'axis' }),
    legend: icuLegend(),
    grid: icuGrid(),
    xAxis: icuCategoryAxis(xData),
    yAxis: icuValueAxis(),
    ...extra,
  }
}

/** 饼图/环图基础配置 */
export function pieChartBase(extra: AnyObj = {}) {
  return {
    tooltip: icuTooltip({ trigger: 'item' }),
    legend: icuLegend({ bottom: 0, top: 'auto' }),
    ...extra,
  }
}

/** 散点图基础配置 */
export function scatterChartBase(extra: AnyObj = {}) {
  return {
    tooltip: icuTooltip({ trigger: 'item' }),
    legend: icuLegend(),
    grid: icuGrid(),
    xAxis: { type: 'value', axisLabel: { color: TEXT_TERTIARY, fontSize: FONT_SIZE.chartAxis } },
    yAxis: { type: 'value', axisLabel: { color: TEXT_TERTIARY, fontSize: FONT_SIZE.chartAxis }, splitLine: { lineStyle: { type: 'dashed', color: DIVIDER } } },
    ...extra,
  }
}

// ── 正常范围带 ────────────────────────────────────

export function normalRangeMarkArea(min: number, max: number, color = 'rgba(18,166,106,0.06)') {
  return {
    markArea: {
      silent: true,
      data: [[{ yAxis: min, itemStyle: { color } }, { yAxis: max }]],
    },
  }
}

// ── 事件标记线 ────────────────────────────────────

export function eventMarkLine(time: string, label: string, color = PRIMARY) {
  return {
    markLine: {
      silent: true,
      symbol: 'none',
      lineStyle: { color, type: 'dashed', width: 1 },
      data: [{ xAxis: time, label: { formatter: label, fontSize: 10, color } }],
    },
  }
}
