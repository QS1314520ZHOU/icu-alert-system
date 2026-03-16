<template>
  <div class="analytics-page">
    <a-card :bordered="false" class="filter-card">
      <div class="filter-row">
        <div class="left-tools">
          <a-space wrap>
            <span class="label">时间窗口</span>
            <a-segmented
              v-model:value="windowRange"
              :options="windowOptions"
              size="small"
            />
            <span class="label">粒度</span>
            <a-segmented
              v-model:value="bucket"
              :options="bucketOptions"
              size="small"
            />
            <span class="label">TopN</span>
            <a-input-number v-model:value="topN" :min="5" :max="30" size="small" />
            <button
              :class="['rescue-toggle', { active: rescueOnly }]"
              @click="rescueOnly = !rescueOnly"
            >
              🚨 抢救期风险快筛
            </button>
          </a-space>
        </div>
        <div class="right-tools">
          <a-button size="small" :loading="loading" @click="loadAll">刷新统计</a-button>
        </div>
      </div>
    </a-card>

    <section class="kpi-strip">
      <div class="kpi-tile">
        <div class="kpi-head">
          <span class="kpi-label">监测窗口</span>
          <span class="kpi-code">WINDOW</span>
        </div>
        <div class="kpi-value">{{ analyticsWindowLabel }}</div>
        <div class="kpi-sub">粒度 {{ bucket === 'hour' ? '小时' : '天' }} · Top {{ topN }}</div>
      </div>

      <div class="kpi-tile">
        <div class="kpi-head">
          <span class="kpi-label">{{ topRuleHeadline }}</span>
          <span class="kpi-code">RULE</span>
        </div>
        <div class="kpi-value kpi-value--rule">{{ topRuleSummary.name }}</div>
        <div class="kpi-sub">{{ topRuleSummary.meta }}</div>
      </div>

      <div class="kpi-tile">
        <div class="kpi-head">
          <span class="kpi-label">峰值时段</span>
          <span class="kpi-code">PEAK SLOT</span>
        </div>
        <div class="kpi-value">{{ peakSlotSummary.slot }}</div>
        <div class="kpi-sub">{{ peakSlotSummary.meta }}</div>
      </div>

      <div class="kpi-tile kpi-tile--risk">
        <div class="kpi-head">
          <span class="kpi-label">{{ rescueOnly ? '抢救期占比' : '高危占比' }}</span>
          <span class="kpi-code">HIGH+CRIT</span>
        </div>
        <div class="kpi-value">{{ highRiskRatio.ratio }}</div>
        <div class="kpi-sub">{{ highRiskRatio.meta }}</div>
      </div>

      <div class="kpi-tile kpi-tile--bundle">
        <div class="kpi-head">
          <span class="kpi-label">Sepsis 1h Bundle</span>
          <span class="kpi-code">{{ sepsisBundleMonthCode }}</span>
        </div>
        <div class="kpi-value">{{ sepsisBundleKpi.rate }}</div>
        <div class="kpi-sub">{{ sepsisBundleKpi.meta }}</div>
      </div>

      <div class="kpi-tile kpi-tile--weaning">
        <div class="kpi-head">
          <span class="kpi-label">本月再插管风险</span>
          <span class="kpi-code">{{ analyticsMonthCode }}</span>
        </div>
        <div class="kpi-value">{{ reintubationRiskKpi.rate }}</div>
        <div class="kpi-sub">{{ reintubationRiskKpi.meta }}</div>
      </div>

      <div class="kpi-tile kpi-tile--weaning-high">
        <div class="kpi-head">
          <span class="kpi-label">脱机失败高风险占比</span>
          <span class="kpi-code">WEAN HIGH</span>
        </div>
        <div class="kpi-value">{{ weaningHighRiskKpi.rate }}</div>
        <div class="kpi-sub">{{ weaningHighRiskKpi.meta }}</div>
      </div>
    </section>

    <section class="analytics-grid">
      <a-card title="预警触发频率" :bordered="false" class="panel panel-wide">
        <div v-if="displayFreqSeries.length" class="chart-wrap chart-lg">
          <AnalyticsChart :option="frequencyOption" autoresize />
        </div>
        <div v-else class="empty">暂无频率数据</div>
      </a-card>

      <a-card title="规则类型热力图" :bordered="false" class="panel panel-wide panel-heatmap">
        <div v-if="displayHeatmapY.length" class="heatmap-summary">
          <div class="summary-chip">
            <span class="summary-k">规则数</span>
            <b class="summary-v">{{ heatmapSummary.ruleCount }}</b>
          </div>
          <div class="summary-chip">
            <span class="summary-k">时段数</span>
            <b class="summary-v">{{ heatmapSummary.slotCount }}</b>
          </div>
          <div class="summary-chip summary-chip--wide">
            <span class="summary-k">峰值时段</span>
            <b class="summary-v">{{ heatmapSummary.peakText }}</b>
          </div>
        </div>
        <div v-if="displayHeatmapY.length" class="chart-wrap chart-lg chart-heatmap">
          <AnalyticsChart :option="heatmapOption" autoresize />
        </div>
        <div v-else class="empty">暂无规则热力图数据</div>
      </a-card>

      <a-card title="科室预警排名" :bordered="false" class="panel">
        <div v-if="displayDeptRankings.length" class="chart-wrap chart-md">
          <AnalyticsChart :option="deptRankOption" autoresize />
        </div>
        <a-table
          class="rank-table"
          size="small"
          :columns="deptColumns"
          :data-source="displayDeptRankings"
          :pagination="false"
          row-key="dept"
        />
      </a-card>

      <a-card title="床位预警排名" :bordered="false" class="panel">
        <div v-if="displayBedRankings.length" class="chart-wrap chart-md">
          <AnalyticsChart :option="bedRankOption" autoresize />
        </div>
        <a-table
          class="rank-table"
          size="small"
          :columns="bedColumns"
          :data-source="displayBedRankings"
          :pagination="false"
          :scroll="{ x: 560 }"
          row-key="bedKey"
        />
      </a-card>

      <a-card title="月度脱机评估趋势" :bordered="false" class="panel panel-wide">
        <div v-if="weaningTrendRows.length" class="chart-wrap chart-lg">
          <AnalyticsChart :option="weaningTrendOption" autoresize />
        </div>
        <div v-else class="empty">暂无月度脱机评估趋势数据</div>
      </a-card>

      <a-card title="科室脱机 / 再插管风险对比" :bordered="false" class="panel">
        <div v-if="weaningDeptCompare.length" class="chart-wrap chart-md">
          <AnalyticsChart :option="weaningDeptCompareOption" autoresize />
        </div>
        <a-table
          class="rank-table"
          size="small"
          :columns="weaningDeptColumns"
          :data-source="weaningDeptCompare"
          :pagination="false"
          row-key="dept"
        />
      </a-card>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  Button as AButton,
  Card as ACard,
  InputNumber as AInputNumber,
  Segmented as ASegmented,
  Space as ASpace,
  Table as ATable,
} from 'ant-design-vue'
import {
  getAlertAnalyticsFrequency,
  getAlertAnalyticsHeatmap,
  getAlertAnalyticsRankings,
  getRecentAlerts,
  getSepsisBundleCompliance,
  getWeaningSummary,
} from '../api'
import {
  icuCategoryAxis,
  icuGrid,
  icuLegend,
  icuTooltip,
  icuValueAxis,
} from '../charts/icuTheme'

const AnalyticsChart = defineAsyncComponent(async () => {
  await import('../charts/analytics')
  const mod = await import('vue-echarts')
  return mod.default
})

const route = useRoute()
const loading = ref(false)
const windowRange = ref('7d')
const bucket = ref<'hour' | 'day'>('hour')
const topN = ref(10)
const rescueOnly = ref(false)

const windowOptions = [
  { label: '24h', value: '24h' },
  { label: '7d', value: '7d' },
  { label: '14d', value: '14d' },
  { label: '30d', value: '30d' },
]
const bucketOptions = [
  { label: '小时', value: 'hour' },
  { label: '天', value: 'day' },
]

const freqSeries = ref<any[]>([])
const heatmapX = ref<string[]>([])
const heatmapY = ref<string[]>([])
const heatmapData = ref<number[][]>([])
const deptRankings = ref<any[]>([])
const bedRankings = ref<any[]>([])
const sepsisBundleCompliance = ref<any>(null)
const weaningSummary = ref<any>(null)
const recentAlerts = ref<any[]>([])

const deptCode = computed(() => String(route.query.dept_code || route.query.deptCode || '').trim())
const deptName = computed(() => String(route.query.dept || '').trim())
const analyticsWindowLabel = computed(() => {
  const map: Record<string, string> = {
    '24h': '近24小时',
    '7d': '近7天',
    '14d': '近14天',
    '30d': '近30天',
  }
  return map[windowRange.value] || windowRange.value
})
const sepsisBundleMonth = computed(() => {
  const now = new Date()
  const y = now.getFullYear()
  const m = `${now.getMonth() + 1}`.padStart(2, '0')
  return `${y}-${m}`
})
const sepsisBundleMonthCode = computed(() => sepsisBundleMonth.value.replace('-', '.'))
const analyticsMonthCode = computed(() => sepsisBundleMonthCode.value)

function commonParams() {
  const params: Record<string, any> = { window: windowRange.value }
  if (deptCode.value) params.dept_code = deptCode.value
  else if (deptName.value) params.dept = deptName.value
  return params
}

function windowRangeMs() {
  const map: Record<string, number> = {
    '24h': 24 * 3600 * 1000,
    '7d': 7 * 24 * 3600 * 1000,
    '14d': 14 * 24 * 3600 * 1000,
    '30d': 30 * 24 * 3600 * 1000,
  }
  return map[windowRange.value] || 7 * 24 * 3600 * 1000
}

function alertTimeValue(alert: any) {
  const raw = alert?.created_at || alert?.source_time || alert?.time
  const val = new Date(raw).getTime()
  return Number.isFinite(val) ? val : 0
}

function isRescueRiskAlert(alert: any) {
  const sev = String(alert?.severity || '').toLowerCase()
  if (sev !== 'high' && sev !== 'critical') return false
  const alertType = String(alert?.alert_type || '').toLowerCase()
  const ruleId = String(alert?.rule_id || '').toLowerCase()
  const category = String(alert?.category || '').toLowerCase()
  if (alertType === 'ai_risk' || category === 'ai_analysis') return false
  const rescueKeywords = [
    'shock', 'sepsis', 'septic', 'cardiac_arrest', 'cardiac', 'pea',
    'pe_', 'embol', 'bleed', 'bleeding', 'resp', 'hypoxia', 'hypotension',
    'deterioration', 'multi_organ', 'post_extubation',
  ]
  const haystack = `${alertType} ${ruleId} ${category}`.toLowerCase()
  const extra = alert?.extra && typeof alert.extra === 'object' ? alert.extra : {}
  return rescueKeywords.some((key) => haystack.includes(key))
    || !!extra?.context_snapshot
    || !!extra?.clinical_chain
    || (Array.isArray(extra?.aggregated_groups) && extra.aggregated_groups.length > 0)
}

function bucketLabelByTime(ts: number) {
  const d = new Date(ts)
  const mm = `${d.getMonth() + 1}`.padStart(2, '0')
  const dd = `${d.getDate()}`.padStart(2, '0')
  if (bucket.value === 'day') return `${mm}-${dd}`
  const hh = `${d.getHours()}`.padStart(2, '0')
  return `${mm}-${dd} ${hh}:00`
}

function aggregateRescueFrequency(alertsInput: any[]) {
  const counter = new Map<string, { time: string; total: number; warning: number; high: number; critical: number }>()
  alertsInput.forEach((alert) => {
    const label = bucketLabelByTime(alertTimeValue(alert))
    const sev = String(alert?.severity || '').toLowerCase()
    if (!counter.has(label)) {
      counter.set(label, { time: label, total: 0, warning: 0, high: 0, critical: 0 })
    }
    const row = counter.get(label)!
    row.total += 1
    if (sev === 'critical') row.critical += 1
    else if (sev === 'high') row.high += 1
    else row.warning += 1
  })
  return Array.from(counter.values()).sort((a, b) => a.time.localeCompare(b.time))
}

function aggregateRescueHeatmap(alertsInput: any[]) {
  const bucketSet = new Set<string>()
  const ruleCounter = new Map<string, number>()
  const matrix = new Map<string, number>()
  alertsInput.forEach((alert) => {
    const bucketLabel = bucketLabelByTime(alertTimeValue(alert))
    const ruleLabel = String(alert?.name || alert?.rule_id || alert?.alert_type || '抢救期预警')
    bucketSet.add(bucketLabel)
    ruleCounter.set(ruleLabel, (ruleCounter.get(ruleLabel) || 0) + 1)
    const key = `${bucketLabel}__${ruleLabel}`
    matrix.set(key, (matrix.get(key) || 0) + 1)
  })
  const xLabels = Array.from(bucketSet).sort((a, b) => a.localeCompare(b))
  const yLabels = Array.from(ruleCounter.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, topN.value)
    .map(([name]) => name)
  const data: number[][] = []
  xLabels.forEach((x, xi) => {
    yLabels.forEach((y, yi) => {
      const count = matrix.get(`${x}__${y}`) || 0
      if (count > 0) data.push([xi, yi, count])
    })
  })
  return { xLabels, yLabels, data }
}

function aggregateRescueDeptRankings(alertsInput: any[]) {
  const counter = new Map<string, any>()
  alertsInput.forEach((alert) => {
    const key = String(alert?.dept || '未知科室')
    if (!counter.has(key)) {
      counter.set(key, { dept: key, count: 0, critical: 0, high: 0, warning: 0 })
    }
    const row = counter.get(key)
    const sev = String(alert?.severity || '').toLowerCase()
    row.count += 1
    if (sev === 'critical') row.critical += 1
    else if (sev === 'high') row.high += 1
    else row.warning += 1
  })
  return Array.from(counter.values()).sort((a, b) => b.count - a.count).slice(0, topN.value)
}

function aggregateRescueBedRankings(alertsInput: any[]) {
  const counter = new Map<string, any>()
  alertsInput.forEach((alert) => {
    const dept = String(alert?.dept || '未知科室')
    const bed = String(alert?.bed || alert?.hisBed || '—')
    const key = `${dept}-${bed}`
    if (!counter.has(key)) {
      counter.set(key, { dept, bed, count: 0, critical: 0, high: 0, warning: 0, bedKey: key })
    }
    const row = counter.get(key)
    const sev = String(alert?.severity || '').toLowerCase()
    row.count += 1
    if (sev === 'critical') row.critical += 1
    else if (sev === 'high') row.high += 1
    else row.warning += 1
  })
  return Array.from(counter.values()).sort((a, b) => b.count - a.count).slice(0, topN.value)
}

function toShortTime(v: string) {
  const s = String(v || '')
  if (bucket.value === 'day') return s.slice(5)
  return s.slice(5, 16)
}

function escapeHtml(v: any) {
  return String(v ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function tooltipShell(title: string, rows: string[], footer = '') {
  return `
    <div class="analytics-tooltip">
      <div class="analytics-tooltip__title">${escapeHtml(title)}</div>
      <div class="analytics-tooltip__body">${rows.join('')}</div>
      ${footer ? `<div class="analytics-tooltip__footer">${escapeHtml(footer)}</div>` : ''}
    </div>
  `
}

function tooltipRow(label: string, value: any, color = '#67e8f9') {
  return `
    <div class="analytics-tooltip__row">
      <span class="analytics-tooltip__label">
        <i class="analytics-tooltip__dot" style="background:${escapeHtml(color)}"></i>
        ${escapeHtml(label)}
      </span>
      <strong class="analytics-tooltip__value">${escapeHtml(value)}</strong>
    </div>
  `
}

const rescueWindowAlerts = computed(() => {
  const cutoff = Date.now() - windowRangeMs()
  return recentAlerts.value
    .filter((alert: any) => isRescueRiskAlert(alert))
    .filter((alert: any) => alertTimeValue(alert) >= cutoff)
})

const rescueFrequencySeries = computed(() => aggregateRescueFrequency(rescueWindowAlerts.value))
const rescueHeatmap = computed(() => aggregateRescueHeatmap(rescueWindowAlerts.value))
const displayFreqSeries = computed(() => rescueOnly.value ? rescueFrequencySeries.value : freqSeries.value)
const displayHeatmapX = computed(() => rescueOnly.value ? rescueHeatmap.value.xLabels : heatmapX.value)
const displayHeatmapY = computed(() => rescueOnly.value ? rescueHeatmap.value.yLabels : heatmapY.value)
const displayHeatmapData = computed(() => rescueOnly.value ? rescueHeatmap.value.data : heatmapData.value)
const displayDeptRankings = computed(() =>
  rescueOnly.value ? aggregateRescueDeptRankings(rescueWindowAlerts.value) : deptRankings.value
)
const displayBedRankings = computed(() =>
  rescueOnly.value ? aggregateRescueBedRankings(rescueWindowAlerts.value) : bedRankings.value
)

const frequencyOption = computed(() => {
  const source = displayFreqSeries.value
  const xs = source.map((p: any) => rescueOnly.value ? String(p.time || '') : toShortTime(p.time || ''))
  return {
    backgroundColor: 'transparent',
    tooltip: icuTooltip({
      trigger: 'axis',
      formatter: (params: any[]) => {
        const list = Array.isArray(params) ? params : [params]
        const title = list[0]?.axisValueLabel || list[0]?.name || '时间窗'
        const rows = list.map((item: any) => tooltipRow(item.seriesName || '指标', item.value ?? 0, item.color || '#67e8f9'))
        const total = list.find((item: any) => item.seriesName === '总量')?.value ?? 0
        return tooltipShell(title, rows, `总触发 ${total} 次`)
      },
    }),
    legend: icuLegend({ textStyle: { fontSize: 10 } }),
    grid: icuGrid({ left: 42, right: 18, top: 34, bottom: 34 }),
    xAxis: icuCategoryAxis(xs, { axisLabel: { fontSize: 10, margin: 10 } }),
    yAxis: icuValueAxis({ axisLabel: { fontSize: 10 } }),
    series: [
      {
        name: '总量',
        type: 'bar',
        data: source.map((p: any) => p.total || 0),
        itemStyle: {
          color: '#0ea5b7',
          borderRadius: [6, 6, 0, 0],
          shadowBlur: 10,
          shadowColor: 'rgba(14, 165, 183, 0.18)',
        },
        barMaxWidth: 16,
      },
      {
        name: 'Warning',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2, color: '#fbbf24' },
        itemStyle: { color: '#fbbf24' },
        data: source.map((p: any) => p.warning || 0),
      },
      {
        name: 'High',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2, color: '#fb923c' },
        itemStyle: { color: '#fb923c' },
        data: source.map((p: any) => p.high || 0),
      },
      {
        name: 'Critical',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2, color: '#fb5a7a' },
        itemStyle: { color: '#fb5a7a' },
        data: source.map((p: any) => p.critical || 0),
      },
    ],
  }
})

const heatmapOption = computed(() => {
  const sourceX = displayHeatmapX.value
  const sourceY = displayHeatmapY.value
  const sourceData = displayHeatmapData.value
  const maxVal = sourceData.reduce((m, cur) => Math.max(m, cur[2] || 0), 0)
  return {
    backgroundColor: 'transparent',
    tooltip: icuTooltip({
      extraCssText: 'box-shadow: 0 12px 28px rgba(0,0,0,.28); border-radius: 10px;',
      formatter: (params: any) => {
        const x = sourceX[params.value[0]]
        const y = sourceY[params.value[1]]
        return tooltipShell(
          `${y || '规则类型'}`,
          [
            tooltipRow('时段', x || '—', '#22d3ee'),
            tooltipRow('触发', `${params.value[2] || 0} 次`, '#fb5a7a'),
          ],
          '规则类型热区'
        )
      },
    }),
    grid: icuGrid({ left: 128, right: 22, top: 20, bottom: 62 }),
    xAxis: icuCategoryAxis(sourceX, {
      axisLine: { lineStyle: { color: 'rgba(79, 182, 219, 0.24)' } },
      axisLabel: { color: '#79d7ea', fontSize: 10, margin: 12 },
      splitArea: { show: false },
      splitLine: { show: true, lineStyle: { color: 'rgba(61, 118, 145, 0.12)' } },
    }),
    yAxis: icuCategoryAxis(sourceY, {
      axisLine: { lineStyle: { color: 'rgba(79, 182, 219, 0.24)' } },
      axisLabel: { color: '#b7ddec', fontSize: 10, margin: 14 },
      splitArea: { show: false },
      splitLine: { show: true, lineStyle: { color: 'rgba(61, 118, 145, 0.12)' } },
    }),
    visualMap: {
      min: 0,
      max: Math.max(1, maxVal),
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 8,
      itemWidth: 140,
      itemHeight: 10,
      text: ['高频', '低频'],
      textGap: 10,
      textStyle: { color: '#7fc7da', fontSize: 10 },
      inRange: {
        color: ['#0a2234', '#0e4c68', '#16b3c9', '#f59e0b', '#fb5a7a'],
      },
    },
    series: [
      {
        name: '触发频次',
        type: 'heatmap',
        data: sourceData,
        label: {
          show: true,
          formatter: ({ value }: any) => (value?.[2] ? value[2] : ''),
          color: '#effcff',
          fontSize: 10,
          fontWeight: 700,
        },
        itemStyle: {
          borderRadius: 8,
          borderColor: 'rgba(112, 226, 255, 0.1)',
          borderWidth: 1,
        },
        emphasis: {
          itemStyle: {
            borderColor: '#dffbff',
            borderWidth: 1,
            shadowBlur: 18,
            shadowColor: 'rgba(34, 211, 238, 0.22)',
          },
        },
      },
    ],
  }
})

const heatmapSummary = computed(() => {
  const sourceX = displayHeatmapX.value
  const sourceY = displayHeatmapY.value
  const sourceData = displayHeatmapData.value
  let peak = { val: 0, x: '', y: '' }
  for (const item of sourceData) {
    const xi = Number(item?.[0])
    const yi = Number(item?.[1])
    const v = item?.[2] || 0
    if (v >= peak.val) {
      peak = {
        val: v,
        x: sourceX[xi] || '',
        y: sourceY[yi] || '',
      }
    }
  }
  return {
    ruleCount: sourceY.length,
    slotCount: sourceX.length,
    peakText: peak.val ? `${peak.y} · ${peak.x} · ${peak.val}次` : '暂无峰值',
  }
})

const topRuleSummary = computed(() => {
  const totals = new Map<string, number>()
  for (const item of displayHeatmapData.value) {
    const yi = Number(item?.[1])
    const value = Number(item?.[2] || 0)
    const name = displayHeatmapY.value[yi] || ''
    if (!name) continue
    totals.set(name, (totals.get(name) || 0) + value)
  }
  const rows = Array.from(totals.entries()).sort((a, b) => b[1] - a[1])
  if (!rows.length) {
    return { name: '暂无数据', meta: '等待规则热力图数据' }
  }
  const topRow = rows[0] || ['', 0]
  const name = topRow[0]
  const count = topRow[1]
  const ratio = displayHeatmapData.value.length ? Math.round((count / Math.max(1, rows.reduce((s, [, v]) => s + v, 0))) * 100) : 0
  return {
    name,
    meta: `累计 ${count} 次 · 占规则触发 ${ratio}%`,
  }
})

const topRuleHeadline = computed(() => windowRange.value === '24h' ? '今日最高风险规则' : '当前窗口最高风险规则')

const peakSlotSummary = computed(() => {
  if (!heatmapSummary.value.peakText || heatmapSummary.value.peakText === '暂无峰值') {
    return { slot: '暂无峰值', meta: '等待热力图数据' }
  }
  return {
    slot: heatmapSummary.value.peakText.split(' · ').slice(1, 2)[0] || heatmapSummary.value.peakText,
    meta: heatmapSummary.value.peakText,
  }
})

const highRiskRatio = computed(() => {
  const source = displayFreqSeries.value
  const total = source.reduce((sum: number, item: any) => sum + Number(item?.total || 0), 0)
  const high = source.reduce((sum: number, item: any) => sum + Number(item?.high || 0), 0)
  const critical = source.reduce((sum: number, item: any) => sum + Number(item?.critical || 0), 0)
  const severe = high + critical
  const ratio = total > 0 ? `${Math.round((severe / total) * 100)}%` : '0%'
  return {
    ratio,
    meta: rescueOnly.value
      ? `${severe} / ${total} 次为抢救期 High / Critical`
      : `${severe} / ${total} 次为 High 或 Critical`,
  }
})

const sepsisBundleKpi = computed(() => {
  const summary = sepsisBundleCompliance.value || {}
  const total = Number(summary?.total_cases || 0)
  const met = Number(summary?.compliant_1h_cases || 0)
  const overdue1h = Number(summary?.overdue_1h_cases || 0)
  const overdue3h = Number(summary?.overdue_3h_cases || 0)
  const pending = Number(summary?.pending_active_cases || 0)
  const rateValue = Number(summary?.compliance_rate || 0)
  return {
    rate: total ? `${(rateValue * 100).toFixed(1)}%` : '0%',
    meta: total
      ? `${met} / ${total} 达标 · 超1h ${overdue1h} · 超3h ${overdue3h}${pending ? ` · 进行中 ${pending}` : ''}`
      : '本月暂无脓毒症 Bundle 病例',
  }
})

const reintubationRiskKpi = computed(() => {
  const summary = weaningSummary.value || {}
  const extubated = Number(summary?.extubated_patients || 0)
  const risk = Number(summary?.reintubation_risk_patients || 0)
  const critical = Number(summary?.critical_post_extubation_patients || 0)
  const rate = Number(summary?.reintubation_risk_ratio || 0)
  return {
    rate: extubated ? `${(rate * 100).toFixed(1)}%` : '0%',
    meta: extubated
      ? `${risk} / ${extubated} 例拔管后触发风险 · 危急 ${critical} 例`
      : '本月暂无拔管患者',
  }
})

const weaningHighRiskKpi = computed(() => {
  const summary = weaningSummary.value || {}
  const total = Number(summary?.weaning_assessed_patients || 0)
  const high = Number(summary?.high_risk_patients || 0)
  const rate = Number(summary?.high_risk_ratio || 0)
  return {
    rate: total ? `${(rate * 100).toFixed(1)}%` : '0%',
    meta: total
      ? `${high} / ${total} 例为 High/Critical`
      : '本月暂无脱机评估',
  }
})

const weaningTrendRows = computed(() =>
  Array.isArray(weaningSummary.value?.daily_trend) ? weaningSummary.value.daily_trend : []
)

const weaningDeptCompare = computed(() =>
  Array.isArray(weaningSummary.value?.dept_compare) ? weaningSummary.value.dept_compare : []
)

const deptRankOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: icuTooltip({
    trigger: 'axis',
    axisPointer: { type: 'shadow' },
    formatter: (params: any[]) => {
      const item = Array.isArray(params) ? params[0] : params
      return tooltipShell(
        item?.name || '科室',
        [tooltipRow('预警总量', `${item?.value ?? 0} 次`, item?.color || '#16b3c9')],
        'Department Ranking'
      )
    },
  }),
  grid: icuGrid({ left: 84, right: 18, top: 16, bottom: 24 }),
  xAxis: icuValueAxis({ axisLabel: { fontSize: 10 } }),
  yAxis: icuCategoryAxis(displayDeptRankings.value.map((d: any) => d.dept), {
    axisLine: { lineStyle: { color: 'rgba(79, 182, 219, 0.18)' } },
    axisLabel: { color: '#b7ddec', fontSize: 10 },
  }),
  series: [
    {
      type: 'bar',
      data: displayDeptRankings.value.map((d: any) => d.count || 0),
      itemStyle: {
        color: (params: any) => {
          const colors = ['#16b3c9', '#0ea5b7', '#0891b2', '#0369a1']
          return colors[params.dataIndex % colors.length]
        },
        borderRadius: [0, 8, 8, 0],
      },
      barMaxWidth: 18,
      label: {
        show: true,
        position: 'right',
        color: '#dffbff',
        fontSize: 10,
      },
    },
  ],
}))

const bedRankOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: icuTooltip({
    trigger: 'axis',
    axisPointer: { type: 'shadow' },
    formatter: (params: any[]) => {
      const item = Array.isArray(params) ? params[0] : params
      return tooltipShell(
        item?.name || '床位',
        [tooltipRow('预警总量', `${item?.value ?? 0} 次`, item?.color || '#fb923c')],
        'Bed Ranking'
      )
    },
  }),
  grid: icuGrid({ left: 102, right: 18, top: 16, bottom: 24 }),
  xAxis: icuValueAxis({ axisLabel: { fontSize: 10 } }),
  yAxis: icuCategoryAxis(displayBedRankings.value.map((d: any) => `${d.dept}-${d.bed}`), {
    axisLine: { lineStyle: { color: 'rgba(79, 182, 219, 0.18)' } },
    axisLabel: { color: '#b7ddec', fontSize: 10 },
  }),
  series: [
    {
      type: 'bar',
      data: displayBedRankings.value.map((d: any) => d.count || 0),
      itemStyle: {
        color: (params: any) => {
          const colors = ['#f59e0b', '#fb923c', '#fb7185', '#f43f5e']
          return colors[params.dataIndex % colors.length]
        },
        borderRadius: [0, 8, 8, 0],
      },
      barMaxWidth: 18,
      label: {
        show: true,
        position: 'right',
        color: '#dffbff',
        fontSize: 10,
      },
    },
  ],
}))

const weaningTrendOption = computed(() => {
  const xs = weaningTrendRows.value.map((row: any) => String(row.date || '').slice(5))
  return {
    backgroundColor: 'transparent',
    tooltip: icuTooltip({
      trigger: 'axis',
      formatter: (params: any[]) => {
        const list = Array.isArray(params) ? params : [params]
        const title = list[0]?.axisValueLabel || list[0]?.name || '日期'
        const rows = list.map((item: any) => tooltipRow(item.seriesName || '指标', item.value ?? 0, item.color || '#67e8f9'))
        return tooltipShell(title, rows, 'Weaning Monthly Trend')
      },
    }),
    legend: icuLegend({ textStyle: { fontSize: 10 } }),
    grid: icuGrid({ left: 42, right: 18, top: 34, bottom: 34 }),
    xAxis: icuCategoryAxis(xs, { axisLabel: { fontSize: 10, margin: 10 } }),
    yAxis: icuValueAxis({ axisLabel: { fontSize: 10 } }),
    series: [
      {
        name: '脱机评估',
        type: 'bar',
        data: weaningTrendRows.value.map((row: any) => Number(row.assessed || 0)),
        itemStyle: { color: '#0ea5b7', borderRadius: [6, 6, 0, 0] },
        barMaxWidth: 14,
      },
      {
        name: '高风险',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2, color: '#f59e0b' },
        itemStyle: { color: '#f59e0b' },
        data: weaningTrendRows.value.map((row: any) => Number(row.high_risk || 0)),
      },
      {
        name: '拔管后风险',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2, color: '#fb5a7a' },
        itemStyle: { color: '#fb5a7a' },
        data: weaningTrendRows.value.map((row: any) => Number(row.reintubation_risk || 0)),
      },
    ],
  }
})

const weaningDeptCompareOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: icuTooltip({
    trigger: 'axis',
    axisPointer: { type: 'shadow' },
    formatter: (params: any[]) => {
      const list = Array.isArray(params) ? params : [params]
      const title = list[0]?.name || '科室'
      const rows = list.map((item: any) => tooltipRow(item.seriesName || '指标', `${item.value ?? 0}%`, item.color || '#67e8f9'))
      return tooltipShell(title, rows, 'Department Compare')
    },
  }),
  legend: icuLegend({ textStyle: { fontSize: 10 } }),
  grid: icuGrid({ left: 52, right: 18, top: 28, bottom: 34 }),
  xAxis: icuCategoryAxis(weaningDeptCompare.value.map((row: any) => row.dept || '未知科室'), {
    axisLabel: { color: '#b7ddec', fontSize: 10, interval: 0, rotate: 18 },
  }),
  yAxis: icuValueAxis({
    axisLabel: {
      fontSize: 10,
      formatter: (value: number) => `${value}%`,
    },
  }),
  series: [
    {
      name: '脱机高风险占比',
      type: 'bar',
      data: weaningDeptCompare.value.map((row: any) => Math.round(Number(row.high_risk_ratio || 0) * 1000) / 10),
      itemStyle: { color: '#f59e0b', borderRadius: [6, 6, 0, 0] },
      barMaxWidth: 18,
    },
    {
      name: '再插管风险占比',
      type: 'bar',
      data: weaningDeptCompare.value.map((row: any) => Math.round(Number(row.reintubation_risk_ratio || 0) * 1000) / 10),
      itemStyle: { color: '#fb5a7a', borderRadius: [6, 6, 0, 0] },
      barMaxWidth: 18,
    },
  ],
}))

const deptColumns = [
  { title: '科室', dataIndex: 'dept', key: 'dept' },
  { title: '总量', dataIndex: 'count', key: 'count', width: 72 },
  { title: 'Critical', dataIndex: 'critical', key: 'critical', width: 80 },
  { title: 'High', dataIndex: 'high', key: 'high', width: 70 },
  { title: 'Warn', dataIndex: 'warning', key: 'warning', width: 70 },
]

const bedColumns = [
  { title: '科室', dataIndex: 'dept', key: 'dept', width: 120 },
  { title: '床位', dataIndex: 'bed', key: 'bed', width: 90 },
  { title: '总量', dataIndex: 'count', key: 'count', width: 72 },
  { title: 'Critical', dataIndex: 'critical', key: 'critical', width: 80 },
  { title: 'High', dataIndex: 'high', key: 'high', width: 70 },
  { title: 'Warn', dataIndex: 'warning', key: 'warning', width: 70 },
]

const weaningDeptColumns = [
  { title: '科室', dataIndex: 'dept', key: 'dept' },
  { title: '脱机评估', dataIndex: 'weaning_assessed_patients', key: 'weaning_assessed_patients', width: 84 },
  { title: '高风险', dataIndex: 'high_risk_patients', key: 'high_risk_patients', width: 76 },
  {
    title: '高风险占比',
    dataIndex: 'high_risk_ratio',
    key: 'high_risk_ratio',
    width: 92,
    customRender: ({ text }: any) => `${(Number(text || 0) * 100).toFixed(1)}%`,
  },
  { title: '拔管患者', dataIndex: 'extubated_patients', key: 'extubated_patients', width: 84 },
  { title: '再插管风险', dataIndex: 'reintubation_risk_patients', key: 'reintubation_risk_patients', width: 92 },
]

async function loadFrequency() {
  const res = await getAlertAnalyticsFrequency({
    ...commonParams(),
    bucket: bucket.value,
  })
  freqSeries.value = res.data.series || []
}

async function loadHeatmap() {
  const res = await getAlertAnalyticsHeatmap({
    ...commonParams(),
    top_n: topN.value,
  })
  heatmapX.value = res.data.x_labels || []
  heatmapY.value = res.data.y_labels || []
  heatmapData.value = res.data.data || []
}

async function loadRankings() {
  const res = await getAlertAnalyticsRankings({
    ...commonParams(),
    top_n: topN.value,
  })
  deptRankings.value = res.data.dept_rankings || []
  bedRankings.value = (res.data.bed_rankings || []).map((r: any, idx: number) => ({
    ...r,
    bedKey: `${r.dept || ''}-${r.bed || ''}-${idx}`,
  }))
}

async function loadSepsisBundleCompliance() {
  const res = await getSepsisBundleCompliance({
    month: sepsisBundleMonth.value,
    ...(deptCode.value ? { dept_code: deptCode.value } : {}),
    ...(!deptCode.value && deptName.value ? { dept: deptName.value } : {}),
  })
  sepsisBundleCompliance.value = res.data.summary || null
}

async function loadWeaningSummary() {
  const res = await getWeaningSummary({
    month: sepsisBundleMonth.value,
    ...(deptCode.value ? { dept_code: deptCode.value } : {}),
    ...(!deptCode.value && deptName.value ? { dept: deptName.value } : {}),
  })
  weaningSummary.value = res.data.summary || null
}

async function loadRecentRescueAlerts() {
  const res = await getRecentAlerts(200, {
    ...(deptCode.value ? { dept_code: deptCode.value } : {}),
    ...(!deptCode.value && deptName.value ? { dept: deptName.value } : {}),
  })
  recentAlerts.value = res.data.records || []
}

async function loadAll() {
  if (loading.value) return
  loading.value = true
  try {
    await Promise.all([
      loadFrequency(),
      loadHeatmap(),
      loadRankings(),
      loadSepsisBundleCompliance(),
      loadWeaningSummary(),
      loadRecentRescueAlerts(),
    ])
  } catch (e) {
    console.error('加载Analytics失败', e)
  } finally {
    loading.value = false
  }
}

watch([windowRange, bucket, topN], () => {
  void loadAll()
})

watch(
  () => route.query,
  () => {
    void loadAll()
  },
  { deep: true }
)

onMounted(() => {
  void loadAll()
})
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&display=swap');

.analytics-page {
  position: relative;
  isolation: isolate;
  padding: 16px 22px 24px;
  background:
    radial-gradient(circle at top, rgba(34, 211, 238, 0.1), rgba(34, 211, 238, 0) 28%),
    linear-gradient(180deg, #06111d 0%, #040b14 100%);
  min-height: 100%;
  font-family: 'Rajdhani', 'Noto Sans SC', sans-serif;
}

.analytics-page::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(rgba(73, 196, 255, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(73, 196, 255, 0.04) 1px, transparent 1px);
  background-size: 28px 28px;
  opacity: 0.26;
  z-index: -1;
}

.filter-card {
  background:
    linear-gradient(180deg, rgba(9, 22, 36, 0.94) 0%, rgba(6, 15, 27, 0.92) 100%);
  border: 1px solid rgba(80, 199, 255, 0.16);
  margin-bottom: 16px;
  border-radius: 12px;
  box-shadow: inset 0 1px 0 rgba(145, 228, 255, 0.06), 0 12px 28px rgba(0, 0, 0, 0.2);
}

.filter-card :deep(.ant-card-body) {
  padding: 12px 14px;
}

.filter-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.left-tools .label {
  font-size: 12px;
  color: #7ccfe4;
  margin-right: 4px;
  font-weight: 600;
  letter-spacing: 0.08em;
}

.filter-card :deep(.ant-segmented) {
  background: rgba(8, 28, 44, 0.78);
  border: 1px solid rgba(80, 199, 255, 0.14);
}

.filter-card :deep(.ant-segmented-item) {
  color: #8bcfe1;
  font-weight: 600;
}

.filter-card :deep(.ant-segmented-item-selected) {
  background: linear-gradient(180deg, rgba(11, 107, 137, 0.96) 0%, rgba(7, 63, 86, 0.98) 100%);
  color: #effcff;
  box-shadow: 0 0 12px rgba(34, 211, 238, 0.08);
}

.filter-card :deep(.ant-input-number) {
  background: rgba(8, 28, 44, 0.78);
  border-color: rgba(80, 199, 255, 0.14);
}

.filter-card :deep(.ant-input-number input) {
  color: #e8fbff;
}

.filter-card :deep(.ant-btn) {
  background: linear-gradient(180deg, rgba(11, 107, 137, 0.96) 0%, rgba(7, 63, 86, 0.98) 100%);
  border-color: rgba(110, 231, 249, 0.28);
  color: #effcff;
  font-weight: 600;
}
.rescue-toggle {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid rgba(251, 113, 133, 0.22);
  background: linear-gradient(180deg, rgba(51, 15, 27, 0.9) 0%, rgba(27, 11, 18, 0.92) 100%);
  color: #ffcad5;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: all .18s ease;
}
.rescue-toggle:hover,
.rescue-toggle.active {
  color: #fff1f4;
  border-color: rgba(251, 113, 133, 0.38);
  box-shadow: 0 0 18px rgba(251, 113, 133, 0.14);
}

.analytics-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.kpi-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.kpi-tile {
  position: relative;
  overflow: hidden;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(80, 199, 255, 0.14);
  background:
    radial-gradient(circle at top right, rgba(34, 211, 238, 0.08), rgba(34, 211, 238, 0) 32%),
    linear-gradient(180deg, rgba(7, 20, 34, 0.96) 0%, rgba(4, 12, 22, 0.98) 100%);
  box-shadow: inset 0 1px 0 rgba(145, 228, 255, 0.05), 0 12px 28px rgba(0, 0, 0, 0.18);
}

.kpi-tile::after {
  content: '';
  position: absolute;
  inset: auto 0 0 0;
  height: 2px;
  background: linear-gradient(90deg, rgba(34, 211, 238, 0.08), rgba(34, 211, 238, 0.5), rgba(34, 211, 238, 0.08));
}

.kpi-tile--risk::after {
  background: linear-gradient(90deg, rgba(251, 90, 122, 0.08), rgba(251, 90, 122, 0.56), rgba(251, 90, 122, 0.08));
}

.kpi-tile--bundle::after {
  background: linear-gradient(90deg, rgba(45, 212, 191, 0.08), rgba(45, 212, 191, 0.56), rgba(45, 212, 191, 0.08));
}

.kpi-tile--weaning::after {
  background: linear-gradient(90deg, rgba(59, 130, 246, 0.08), rgba(59, 130, 246, 0.58), rgba(59, 130, 246, 0.08));
}

.kpi-tile--weaning-high::after {
  background: linear-gradient(90deg, rgba(245, 158, 11, 0.08), rgba(245, 158, 11, 0.58), rgba(245, 158, 11, 0.08));
}

.kpi-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.kpi-label {
  color: #7ed6eb;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.kpi-code {
  color: #4ec6de;
  font-size: 10px;
  letter-spacing: 0.12em;
  font-family: 'SF Mono', 'Consolas', monospace;
}

.kpi-value {
  color: #effcff;
  font-size: 24px;
  line-height: 1.1;
  font-weight: 700;
  font-family: 'Rajdhani', 'SF Mono', 'Consolas', monospace;
  letter-spacing: 0.03em;
}

.kpi-value--rule {
  font-size: 20px;
}

.kpi-sub {
  margin-top: 6px;
  color: #8bbfd0;
  font-size: 11px;
  line-height: 1.45;
}

.panel {
  background:
    radial-gradient(circle at top, rgba(34, 211, 238, 0.07), rgba(34, 211, 238, 0) 30%),
    linear-gradient(180deg, rgba(7, 20, 34, 0.96) 0%, rgba(4, 12, 22, 0.98) 100%);
  border: 1px solid rgba(80, 199, 255, 0.14);
  min-height: 420px;
  border-radius: 12px;
  box-shadow: inset 0 1px 0 rgba(145, 228, 255, 0.04), 0 12px 28px rgba(0, 0, 0, 0.2);
}

.panel :deep(.ant-card-head) {
  min-height: 50px;
  border-bottom: 1px solid rgba(80, 199, 255, 0.1);
  background: linear-gradient(90deg, rgba(9, 31, 48, 0.5), rgba(9, 31, 48, 0));
}

.panel :deep(.ant-card-head-title) {
  color: #67e8f9;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.panel :deep(.ant-card-body) {
  padding: 12px 14px 14px;
}

.panel-wide {
  grid-column: span 2;
}

.chart-wrap {
  width: 100%;
  position: relative;
  border-radius: 12px;
}

.chart-lg {
  height: 360px;
}

.chart-heatmap {
  padding-top: 4px;
}

.chart-md {
  height: 280px;
}

.panel-heatmap {
  background:
    radial-gradient(circle at top, rgba(34, 211, 238, 0.08), rgba(34, 211, 238, 0) 35%),
    var(--card-bg);
}

.heatmap-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 8px;
}

.summary-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(8, 28, 44, 0.78);
  border: 1px solid rgba(79, 182, 219, 0.18);
}

.summary-chip--wide {
  max-width: 100%;
}

.summary-k {
  font-size: 11px;
  color: #77c9de;
  letter-spacing: 0.08em;
}

.summary-v {
  font-size: 12px;
  color: #e8fbff;
  font-weight: 700;
}

.rank-table {
  margin-top: 12px;
}

.empty {
  color: #7ccfe4;
  font-size: 12px;
  padding: 16px 8px;
}

.analytics-page :deep(.analytics-tooltip) {
  min-width: 180px;
  display: grid;
  gap: 8px;
}

.analytics-page :deep(.analytics-tooltip__title) {
  color: #ecfeff;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.analytics-page :deep(.analytics-tooltip__body) {
  display: grid;
  gap: 6px;
}

.analytics-page :deep(.analytics-tooltip__row) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.analytics-page :deep(.analytics-tooltip__label) {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #9eddef;
  font-size: 11px;
}

.analytics-page :deep(.analytics-tooltip__dot) {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  box-shadow: 0 0 10px rgba(103, 232, 249, 0.24);
}

.analytics-page :deep(.analytics-tooltip__value) {
  color: #effcff;
  font-size: 11px;
  font-weight: 700;
}

.analytics-page :deep(.analytics-tooltip__footer) {
  padding-top: 6px;
  border-top: 1px solid rgba(80, 199, 255, 0.12);
  color: #6fdcf2;
  font-size: 10px;
  letter-spacing: 0.08em;
}

.rank-table :deep(.ant-table) {
  background: transparent;
  color: #dff8ff;
}

.rank-table :deep(.ant-table-container) {
  border: 1px solid rgba(80, 199, 255, 0.08);
  border-radius: 10px;
  overflow: hidden;
}

.rank-table :deep(.ant-table-thead > tr > th) {
  background: rgba(8, 28, 44, 0.82);
  color: #7ccfe4;
  border-bottom-color: rgba(80, 199, 255, 0.1);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
}

.rank-table :deep(.ant-table-tbody > tr > td) {
  background: transparent;
  color: #e3fbff;
  border-bottom-color: rgba(80, 199, 255, 0.08);
  font-size: 12px;
}

.rank-table :deep(.ant-table-tbody > tr:hover > td) {
  background: rgba(11, 42, 63, 0.42) !important;
}

.rank-table :deep(.ant-table-placeholder) {
  background: transparent;
}

.rank-table :deep(.ant-empty-description) {
  color: #7ccfe4;
}

@media (max-width: 980px) {
  .analytics-page {
    padding: 10px;
  }

  .analytics-grid {
    grid-template-columns: 1fr;
  }

  .kpi-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .panel,
  .panel-wide {
    grid-column: auto;
    min-height: 0;
  }

  .chart-lg,
  .chart-md {
    height: 300px;
  }
}

@media (max-width: 680px) {
  .kpi-strip {
    grid-template-columns: 1fr;
  }

  .kpi-value {
    font-size: 20px;
  }

  .kpi-value--rule {
    font-size: 17px;
  }
}
</style>
```
