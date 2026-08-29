/**
 * clinicalThemes.ts — 注册 clinical-light / clinical-dark ECharts 主题
 *
 * 所有图表必须使用这两个主题之一，禁止在组件内硬编码颜色。
 */

import * as echarts from 'echarts'
import { FONT_FAMILY, FONT_SIZE } from '../styles/tokens/typography'

const LIGHT = {
  color: ['#2563EB', '#16A34A', '#0891B2', '#F59E0B', '#7C3AED', '#DC2626', '#0284C7', '#94A3B8'],
  backgroundColor: 'transparent',
  textStyle: {
    fontFamily: FONT_FAMILY.primary,
    color: '#182230',
  },
  title: {
    textStyle: { color: '#182230', fontSize: 14, fontWeight: 600, fontFamily: FONT_FAMILY.primary },
    subtextStyle: { color: '#52606D', fontSize: 12, fontFamily: FONT_FAMILY.primary },
  },
  line: {
    itemStyle: { borderWidth: 2 },
    lineStyle: { width: 2 },
    symbolSize: 6,
    symbol: 'circle',
    smooth: true,
  },
  bar: {
    itemStyle: { barBorderWidth: 0, barBorderRadius: [3, 3, 0, 0] },
  },
  pie: {
    itemStyle: { borderWidth: 1, borderColor: '#fff' },
  },
  scatter: {
    itemStyle: { borderWidth: 0 },
  },
  categoryAxis: {
    axisLine: { show: true, lineStyle: { color: '#DCE3EC' } },
    axisTick: { show: false },
    axisLabel: { color: '#94A3B8', fontSize: FONT_SIZE.chartAxis, fontFamily: FONT_FAMILY.primary },
    splitLine: { show: false },
  },
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: '#94A3B8', fontSize: FONT_SIZE.chartAxis, fontFamily: FONT_FAMILY.primary },
    splitLine: { lineStyle: { color: '#E8EEF5', type: 'dashed' } },
  },
  tooltip: {
    backgroundColor: 'rgba(255,255,255,0.96)',
    borderColor: '#DCE3EC',
    borderWidth: 1,
    textStyle: { color: '#182230', fontSize: 12, fontFamily: FONT_FAMILY.primary },
    extraCssText: 'box-shadow: 0 4px 12px rgba(16,24,40,0.08); border-radius: 8px;',
  },
  legend: {
    textStyle: { color: '#52606D', fontSize: FONT_SIZE.chartLegend, fontFamily: FONT_FAMILY.primary },
  },
  grid: {
    left: 12, right: 16, top: 40, bottom: 12, containLabel: true,
  },
}

const DARK = {
  color: ['#3B82F6', '#22C55E', '#06B6D4', '#FBBF24', '#A78BFA', '#EF4444', '#38BDF8', '#64748B'],
  backgroundColor: 'transparent',
  textStyle: {
    fontFamily: FONT_FAMILY.primary,
    color: '#E2E8F0',
  },
  title: {
    textStyle: { color: '#E2E8F0', fontSize: 14, fontWeight: 600, fontFamily: FONT_FAMILY.primary },
    subtextStyle: { color: '#94A3B8', fontSize: 12, fontFamily: FONT_FAMILY.primary },
  },
  line: {
    itemStyle: { borderWidth: 2 },
    lineStyle: { width: 2 },
    symbolSize: 6,
    symbol: 'circle',
    smooth: true,
  },
  bar: {
    itemStyle: { barBorderWidth: 0, barBorderRadius: [3, 3, 0, 0] },
  },
  pie: {
    itemStyle: { borderWidth: 1, borderColor: '#1E293B' },
  },
  scatter: {
    itemStyle: { borderWidth: 0 },
  },
  categoryAxis: {
    axisLine: { show: true, lineStyle: { color: '#334155' } },
    axisTick: { show: false },
    axisLabel: { color: '#94A3B8', fontSize: FONT_SIZE.chartAxis, fontFamily: FONT_FAMILY.primary },
    splitLine: { show: false },
  },
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: '#94A3B8', fontSize: FONT_SIZE.chartAxis, fontFamily: FONT_FAMILY.primary },
    splitLine: { lineStyle: { color: '#334155', type: 'dashed' } },
  },
  tooltip: {
    backgroundColor: 'rgba(15,23,42,0.95)',
    borderColor: '#334155',
    borderWidth: 1,
    textStyle: { color: '#E2E8F0', fontSize: 12, fontFamily: FONT_FAMILY.primary },
    extraCssText: 'box-shadow: 0 8px 24px rgba(0,0,0,0.3); border-radius: 8px;',
  },
  legend: {
    textStyle: { color: '#94A3B8', fontSize: FONT_SIZE.chartLegend, fontFamily: FONT_FAMILY.primary },
  },
  grid: {
    left: 12, right: 16, top: 40, bottom: 12, containLabel: true,
  },
}

// 注册主题（幂等）
let registered = false

export function registerClinicalThemes() {
  if (registered) return
  echarts.registerTheme('clinical-light', LIGHT)
  echarts.registerTheme('clinical-dark', DARK)
  registered = true
}
