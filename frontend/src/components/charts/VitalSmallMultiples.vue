<template>
  <div class="vsm">
    <div v-if="loading && !panels.length" class="vsm-state">趋势加载中…</div>
    <div v-else-if="!panels.length" class="vsm-state">该时间窗内无生命体征记录</div>
    <template v-else>
      <div v-if="findings.length" class="vsm-findings">
        <span class="vsm-findings__label">趋势提示</span>
        <span v-for="f in findings" :key="f.text" class="vsm-chip" :class="`vsm-chip--${f.tone}`">{{ f.text }}</span>
      </div>
      <div v-else class="vsm-findings vsm-findings--ok">
        <span class="vsm-findings__label">趋势提示</span>
        <span class="vsm-chip vsm-chip--ok">窗口内各项均在参考范围内</span>
      </div>
      <div class="vsm-grid">
        <div v-for="p in panels" :key="p.key" class="vsm-card" :class="`vsm-card--${p.tone}`">
          <div class="vsm-card__head">
            <span class="vsm-card__name">{{ p.name }}</span>
            <span class="vsm-card__range">参考 {{ p.range[0] }}–{{ p.range[1] }} {{ p.unit }}</span>
          </div>
          <div class="vsm-card__value">
            <b :class="`vsm-t-${p.tone}`">{{ p.latestText }}</b><small>{{ p.unit }}</small>
            <span v-if="p.deltaText" class="vsm-card__delta" :class="`dir-${p.dir}`">{{ p.deltaText }}</span>
          </div>
          <div class="vsm-card__meta">
            <span>最低 {{ p.minText }} · 最高 {{ p.maxText }}</span>
            <span v-if="p.abnormalPct > 0" :class="p.abnormalPct >= 30 ? 'vsm-t-critical' : 'vsm-t-warning'">超范围 {{ p.abnormalPct }}% 时间点</span>
          </div>
          <ClinicalChart :option="p.option" :height="height" :aria-label="`${p.name}趋势`" />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsOption } from 'echarts'
import ClinicalChart from './base/ClinicalChart.vue'

type Tone = 'critical' | 'warning' | 'ok'
interface Def {
  key: string; name: string; unit: string; digits: number
  get: (p: any) => any
  range: [number, number]
  crit: (v: number) => boolean
  warn: (v: number) => boolean
  high: string; low: string
}

const props = withDefaults(defineProps<{ points?: any[]; loading?: boolean; height?: number; windowLabel?: string }>(), {
  points: () => [], loading: false, height: 120, windowLabel: '',
})

const DEFS: Def[] = [
  { key: 'hr', name: '心率', unit: 'bpm', digits: 0, get: (p) => p.hr, range: [60, 100], crit: (v) => v > 140 || v < 40, warn: (v) => v > 100 || v < 60, high: '心率偏快', low: '心率偏慢' },
  { key: 'map', name: 'MAP', unit: 'mmHg', digits: 0, get: (p) => p.ibp_map ?? p.nibp_map ?? p.map, range: [65, 100], crit: (v) => v < 55, warn: (v) => v < 65 || v > 110, high: 'MAP偏高', low: 'MAP偏低' },
  { key: 'spo2', name: 'SpO₂', unit: '%', digits: 0, get: (p) => p.spo2, range: [92, 100], crit: (v) => v < 88, warn: (v) => v < 92, high: '', low: 'SpO₂偏低' },
  { key: 'rr', name: '呼吸频率', unit: '/min', digits: 0, get: (p) => p.rr, range: [12, 25], crit: (v) => v > 35 || v < 8, warn: (v) => v > 25 || v < 12, high: '呼吸偏快', low: '呼吸偏慢' },
  { key: 'temp', name: '体温', unit: '°C', digits: 1, get: (p) => p.temp, range: [36, 38.5], crit: (v) => v > 39.5 || v < 35, warn: (v) => v > 38.5 || v < 36, high: '体温升高', low: '体温偏低' },
  { key: 'lactate', name: '乳酸', unit: 'mmol/L', digits: 1, get: (p) => p.lactate, range: [0, 2], crit: (v) => v > 4, warn: (v) => v > 2, high: '乳酸升高', low: '' },
]
const TONE_COLOR: Record<Tone, string> = { critical: '#B91C1C', warning: '#B45309', ok: '#2F7D55' }

function num(v: any): number | null {
  if (v === null || v === undefined || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}
function fmt(v: number | null, d: number) { return v === null ? '—' : d ? v.toFixed(d) : String(Math.round(v)) }
function toneOf(def: Def, v: number | null): Tone { if (v === null) return 'ok'; return def.crit(v) ? 'critical' : def.warn(v) ? 'warning' : 'ok' }

const panels = computed(() => {
  const pts = (props.points || [])
    .map((p) => ({ p, t: new Date(p?.time || p?.timestamp).getTime() }))
    .filter((x) => Number.isFinite(x.t))
    .sort((a, b) => a.t - b.t)
  const out: any[] = []
  for (const def of DEFS) {
    const series: [number, number][] = []
    for (const { p, t } of pts) { const v = num(def.get(p)); if (v !== null) series.push([t, v]) }
    if (!series.length) continue
    const vals = series.map((s) => s[1])
    const first = vals[0] as number; const last = vals[vals.length - 1] as number
    const min = Math.min(...vals); const max = Math.max(...vals)
    const d = last - first
    const flat = Math.abs(d) < (def.digits ? 0.2 : 1)
    const abnormal = vals.filter((v) => def.warn(v) || def.crit(v)).length
    const tone = toneOf(def, last)
    const lo = Math.min(min, def.range[0]); const hi = Math.max(max, def.range[1])
    const pad = (hi - lo) * 0.12 || 1
    const option: EChartsOption = {
      animation: false,
      grid: { left: 36, right: 10, top: 8, bottom: 20 },
      tooltip: { trigger: 'axis', valueFormatter: (v: any) => `${fmt(num(v), def.digits)} ${def.unit}` },
      xAxis: { type: 'time', axisLabel: { fontSize: 10, color: '#7A7975', hideOverlap: true, formatter: '{HH}:{mm}' }, axisLine: { lineStyle: { color: '#E6E5E3' } }, splitLine: { show: false } },
      yAxis: { type: 'value', min: Math.floor((lo - pad) * 10) / 10, max: Math.ceil((hi + pad) * 10) / 10, splitNumber: 2, axisLabel: { fontSize: 10, color: '#7A7975', formatter: (v: number) => fmt(v, def.digits) }, splitLine: { lineStyle: { color: '#F1F0EE' } } },
      series: [{
        type: 'line', name: def.name, data: series, showSymbol: series.length < 30, symbolSize: 4, connectNulls: false,
        lineStyle: { width: 2 },
        markArea: { silent: true, itemStyle: { color: 'rgba(47,125,85,0.08)' }, data: [[{ yAxis: def.range[0] }, { yAxis: def.range[1] }]] },
      }],
      visualMap: { show: false, dimension: 1, seriesIndex: 0, pieces: [
        { lt: def.range[0], color: TONE_COLOR.warning }, { gte: def.range[0], lte: def.range[1], color: '#5392FF' }, { gt: def.range[1], color: TONE_COLOR.warning },
      ] } as any,
    }
    out.push({
      key: def.key, name: def.name, unit: def.unit, range: def.range, tone, def,
      latestText: fmt(last, def.digits), minText: fmt(min, def.digits), maxText: fmt(max, def.digits),
      deltaText: series.length > 1 ? (flat ? '窗口内平稳' : `较窗口起点 ${d > 0 ? '+' : ''}${fmt(d, def.digits)}`) : '',
      dir: flat ? 'flat' : d > 0 ? 'up' : 'down', d, first, last,
      abnormalPct: Math.round((abnormal / vals.length) * 100), option,
    })
  }
  return out
})

const findings = computed(() => {
  const list: { text: string; tone: Tone }[] = []
  for (const p of panels.value) {
    const def: Def = p.def
    if (p.tone !== 'ok') {
      const below = p.last < def.range[0]
      const word = below ? def.low : def.high
      if (word) list.push({ text: `${word}（当前 ${p.latestText}${p.unit}）`, tone: p.tone })
    }
    // 明显变化：相对参考区间宽度 ≥ 30%
    const width = def.range[1] - def.range[0]
    if (!['flat'].includes(p.dir) && width > 0 && Math.abs(p.d) / width >= 0.3) {
      list.push({ text: `${p.name}${p.d > 0 ? '上升' : '下降'} ${fmt(Math.abs(p.d), def.digits)}${p.unit}`, tone: 'warning' })
    }
  }
  return list.sort((a, b) => (a.tone === 'critical' ? -1 : 0) - (b.tone === 'critical' ? -1 : 0))
})
</script>

<style scoped>
.vsm-state { padding: 24px; text-align: center; color: #7A7975; font-size: 13px; }
.vsm-findings { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-bottom: 10px; }
.vsm-findings__label { font-size: 13px; font-weight: 600; color: #37352F; padding-left: 8px; border-left: 3px solid #5392FF; margin-right: 4px; }
.vsm-chip { font-size: 12px; padding: 2px 8px; border-radius: 10px; border: 1px solid; }
.vsm-chip--critical { background: #FEF2F2; color: #B91C1C; border-color: #FCA5A5; }
.vsm-chip--warning { background: #FFFBEB; color: #B45309; border-color: #FCD34D; }
.vsm-chip--ok { background: #E7F5EE; color: #2F7D55; border-color: #A7D9BF; }
.vsm-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 10px; }
.vsm-card { border: 1px solid #E6E5E3; border-radius: 10px; padding: 10px 12px 4px; background: #fff; }
.vsm-card--critical { border-color: #FCA5A5; box-shadow: inset 3px 0 0 #B91C1C; }
.vsm-card--warning { border-color: #FCD34D; box-shadow: inset 3px 0 0 #B45309; }
.vsm-card__head { display: flex; justify-content: space-between; align-items: baseline; }
.vsm-card__name { font-size: 13px; font-weight: 600; color: #37352F; }
.vsm-card__range { font-size: 11px; color: #7A7975; }
.vsm-card__value { display: flex; align-items: baseline; gap: 4px; margin-top: 2px; }
.vsm-card__value b { font-size: 24px; line-height: 1.2; font-variant-numeric: tabular-nums; }
.vsm-card__value small { font-size: 12px; color: #7A7975; }
.vsm-card__delta { margin-left: auto; font-size: 12px; color: #55534E; }
.vsm-card__meta { display: flex; justify-content: space-between; font-size: 11px; color: #7A7975; margin-top: 2px; }
.vsm-t-critical { color: #B91C1C; }
.vsm-t-warning { color: #B45309; }
.vsm-t-ok { color: #2F7D55; }
.dir-flat { color: #7A7975; }
</style>
