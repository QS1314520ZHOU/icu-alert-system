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
      tooltipBg: 'rgba(255,253,247,.98)',
      tooltipBorder: '#D7DED3',
      tooltipText: '#16241E',
      tooltipShadow: 'box-shadow: 0 10px 24px rgba(54,69,58,.10); border-radius: 12px; backdrop-filter: blur(10px);',
      tooltipAxisLabelBg: '#F6F3EA',
      tooltipAxisLabelText: '#16241E',
      axisLine: 'rgba(215, 222, 211, 0.95)',
      axisLabel: '#718176',
      axisLabelStrong: '#3F564B',
      splitLine: 'rgba(215, 222, 211, 0.86)',
      shadowArea: 'rgba(29, 111, 99, 0.07)',
      crossLine: 'rgba(29, 111, 99, 0.2)',
      legendText: '#3F564B',
      heatmapText: '#3F564B',
      heatmapRange: ['#F6F3EA', '#E2F0EA', '#1D6F63', '#B47A24', '#B5483F'],
      labelStrong: '#16241E',
    }
  }
  return {
    tooltipBg: 'rgba(4,14,24,.97)',
    tooltipBorder: 'rgba(88,225,255,.2)',
    tooltipText: '#e8fbff',
    tooltipShadow: 'box-shadow: 0 14px 30px rgba(0,0,0,.34); border-radius: 12px; backdrop-filter: blur(10px);',
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
    heatmapRange: ['#0a2234', '#0e4c68', '#15558D', '#E8901C', '#D9342B'],
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
