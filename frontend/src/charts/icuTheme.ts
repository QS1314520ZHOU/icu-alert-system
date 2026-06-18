import { getThemeMode, useThemeMode } from '../composables/themeMode'

type AnyObj = Record<string, any>

function merge(base: AnyObj, extra: AnyObj = {}) {
  return { ...base, ...extra }
}

function currentThemeMode() {
  const themeMode = useThemeMode()
  return themeMode.value || getThemeMode()
}

function themeTokens() {
  const light = currentThemeMode() === 'light'
  if (light) {
    return {
      tooltipBg: 'rgba(255,255,255,.98)',
      tooltipBorder: '#E8E8EF',
      tooltipText: '#1A1A2E',
      tooltipShadow: 'box-shadow: 0 1px 2px rgba(0,0,0,.06); border-radius: 4px; backdrop-filter: blur(10px);',
      tooltipAxisLabelBg: '#F7F8FC',
      tooltipAxisLabelText: '#1A1A2E',
      axisLine: 'rgba(232, 232, 239, 0.92)',
      axisLabel: '#8E8EA9',
      axisLabelStrong: '#4A4A68',
      splitLine: 'rgba(232, 232, 239, 0.92)',
      shadowArea: 'rgba(46, 91, 255, 0.06)',
      crossLine: 'rgba(46, 91, 255, 0.18)',
      legendText: '#4A4A68',
      heatmapText: '#4A4A68',
      heatmapRange: ['#F0F4FF', '#D6E0FF', '#8FB0FF', '#F59E0B', '#EF4444'],
      labelStrong: '#1A1A2E',
    }
  }
  return {
    tooltipBg: 'rgba(4,14,24,.97)',
    tooltipBorder: 'rgba(88,225,255,.2)',
    tooltipText: '#e8fbff',
    tooltipShadow: 'box-shadow: 0 1px 2px rgba(0,0,0,.06); border-radius: 4px; backdrop-filter: blur(10px);',
    tooltipAxisLabelBg: 'rgba(8, 31, 47, 0.96)',
    tooltipAxisLabelText: '#dffbff',
    axisLine: 'rgba(79,182,219,.18)',
    axisLabel: '#86d3e8',
    axisLabelStrong: '#b7ddec',
    splitLine: 'rgba(61,118,145,.14)',
    shadowArea: 'rgba(56, 189, 248, 0.08)',
    crossLine: 'rgba(110, 231, 249, 0.22)',
    legendText: '#9edff0',
    heatmapText: '#7fc7da',
    heatmapRange: ['#0a2234', '#0e4c68', '#15558D', '#f59e0b', '#fb5a7a'],
    labelStrong: '#dffafc',
  }
}

export function icuChartTokens() {
  return themeTokens()
}

export function icuTooltip(extra: AnyObj = {}) {
  const tokens = themeTokens()
  const base = {
    backgroundColor: tokens.tooltipBg,
    borderColor: tokens.tooltipBorder,
    borderWidth: 1,
    padding: [10, 12],
    textStyle: { color: tokens.tooltipText, fontSize: 11, lineHeight: 18 },
    extraCssText: tokens.tooltipShadow,
    axisPointer: {
      lineStyle: { color: tokens.crossLine },
      crossStyle: { color: tokens.crossLine },
      shadowStyle: { color: tokens.shadowArea },
      label: {
        backgroundColor: tokens.tooltipAxisLabelBg,
        color: tokens.tooltipAxisLabelText,
      },
    },
  }
  return {
    ...base,
    ...extra,
    textStyle: merge(base.textStyle, extra.textStyle),
    axisPointer: merge(base.axisPointer, extra.axisPointer),
  }
}

export function icuLegend(extra: AnyObj = {}) {
  const tokens = themeTokens()
  const base = {
    top: 0,
    icon: 'roundRect',
    itemWidth: 10,
    itemHeight: 10,
    itemGap: 14,
    textStyle: { color: tokens.legendText, fontSize: 10, padding: [0, 0, 0, 4] },
  }
  return {
    ...base,
    ...extra,
    textStyle: merge(base.textStyle, extra.textStyle),
  }
}

export function icuGrid(extra: AnyObj = {}) {
  return {
    containLabel: false,
    ...extra,
  }
}

export function icuCategoryAxis(data: any[], extra: AnyObj = {}) {
  const tokens = themeTokens()
  const base = {
    type: 'category',
    data,
    axisTick: { show: false },
    axisLine: { lineStyle: { color: tokens.axisLine } },
    axisLabel: { color: tokens.axisLabel, fontSize: 10, margin: 10 },
  }
  return {
    ...base,
    ...extra,
    axisTick: merge(base.axisTick, extra.axisTick),
    axisLine: merge(base.axisLine, extra.axisLine),
    axisLabel: merge(base.axisLabel, extra.axisLabel),
  }
}

export function icuValueAxis(extra: AnyObj = {}) {
  const tokens = themeTokens()
  const base = {
    type: 'value',
    axisLine: { show: false, lineStyle: { color: tokens.axisLine } },
    axisLabel: { color: tokens.axisLabel, fontSize: 10 },
    splitLine: { lineStyle: { color: tokens.splitLine, type: 'dashed' } },
  }
  return {
    ...base,
    ...extra,
    axisLine: merge(base.axisLine, extra.axisLine),
    axisLabel: merge(base.axisLabel, extra.axisLabel),
    splitLine: merge(base.splitLine, extra.splitLine),
  }
}
