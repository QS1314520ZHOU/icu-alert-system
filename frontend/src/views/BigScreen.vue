<template>
  <div class="bigscreen">
    <header class="screen-header">
      <div class="header-main">
        <div class="title">
          <span class="title-tag">ICU</span>
          护士站监控大屏
        </div>
        <div class="header-sub">Central Monitoring Command Center</div>
        <div class="header-filters">
          <button
            :class="['header-filter-chip', { active: rescueOnly }]"
            @click="rescueOnly = !rescueOnly"
          >
            🚨 仅看抢救期风险
            <b>{{ rescuePatientCount }}</b>
          </button>
        </div>
      </div>
      <div class="screen-kpis">
        <div class="kpi-chip">
          <span class="kpi-label">{{ rescueOnly ? '抢救期床位' : '在院床位' }}</span>
          <strong>{{ filteredPatients.length }}</strong>
        </div>
        <div class="kpi-chip">
          <span class="kpi-label">危急预警</span>
          <strong>{{ filteredCriticalPatientCount }}</strong>
        </div>
        <div class="kpi-chip">
          <span class="kpi-label">{{ rescueOnly ? '抢救期告警' : '实时告警' }}</span>
          <strong>{{ filteredAlerts.length }}</strong>
        </div>
      </div>
      <div class="clock">{{ currentTime }}</div>
    </header>

    <section class="screen-body">
      <aside class="panel panel-left">
        <div class="panel-title">{{ rescueOnly ? '抢救期预警' : '实时预警' }}</div>
        <BigScreenAlertFeed :alerts="showAlerts" />
      </aside>

      <main class="panel panel-center">
        <div class="panel-title">{{ rescueOnly ? '抢救期床位监控' : '床位监控' }}</div>
        <BigScreenBedGrid :patients="filteredPatients" />
      </main>

      <BigScreenStatsPanel
        :dept-option="deptOption"
        :bundle-option="bundleOption"
        :alert-trend-option="alertTrendOption"
        :device-heatmap-option="deviceHeatmapOption"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent, onMounted, onUnmounted, watch } from 'vue'
import dayjs from 'dayjs'
import { useRoute } from 'vue-router'
import {
  getAlertStats,
  getBundleOverview,
  getDepartments,
  getDeviceRiskHeatmap,
  getPatients,
  getPatientVitals,
  getPatientWeaningStatus,
  getRecentAlerts,
} from '../api'
import { onAlertMessage } from '../services/alertSocket'
import {
  icuCategoryAxis,
  icuGrid,
  icuLegend,
  icuTooltip,
  icuValueAxis,
} from '../charts/icuTheme'

const BigScreenAlertFeed = defineAsyncComponent(() => import('../components/bigscreen/BigScreenAlertFeed.vue'))
const BigScreenBedGrid = defineAsyncComponent(() => import('../components/bigscreen/BigScreenBedGrid.vue'))
const BigScreenStatsPanel = defineAsyncComponent(() => import('../components/bigscreen/BigScreenStatsPanel.vue'))

const route = useRoute()
const currentTime = ref(dayjs().format('YYYY-MM-DD HH:mm:ss'))
const alerts = ref<any[]>([])
const alertIndex = ref(0)
const patients = ref<any[]>([])
const depts = ref<any[]>([])
const trendSeries = ref<any[]>([])
const bundleCounts = ref<any>({ green: 0, yellow: 0, red: 0 })
const deviceHeatRows = ref<any[]>([])
const rescueOnly = ref(false)

let timer: number
let refreshTimer: number
let alertTimer: number
let offAlert: any = null

const rescuePatientCount = computed(() =>
  patients.value.filter((p: any) => hasPatientRescueRisk(p)).length
)

const filteredPatients = computed(() =>
  rescueOnly.value ? patients.value.filter((p: any) => hasPatientRescueRisk(p)) : patients.value
)

const filteredAlerts = computed(() =>
  rescueOnly.value ? alerts.value.filter((a: any) => isRescueRiskAlert(a)) : alerts.value
)

const filteredCriticalPatientCount = computed(() =>
  filteredPatients.value.filter((p: any) => p.alertLevel === 'critical').length
)

const showAlerts = computed(() => {
  const n = 8
  const list = filteredAlerts.value
  if (list.length <= n) return list
  const start = alertIndex.value % list.length
  return [...list.slice(start, start + n), ...list.slice(0, Math.max(0, n - (list.length - start)))]
})

const deptOption = computed(() => {
  const data = depts.value.map(d => ({ name: d.dept, value: d.patientCount }))
  const hasData = data.length > 0
  return {
    backgroundColor: 'transparent',
    tooltip: icuTooltip({ trigger: 'item' }),
    graphic: hasData ? [] : [
      {
        type: 'text',
        left: 'center',
        top: 'middle',
        style: {
          text: '暂无科室数据',
          fill: '#7ccfe4',
          fontSize: 11,
        },
      },
    ],
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        data,
        label: {
          color: '#dffbff',
          fontSize: 10,
          formatter: '{b} {c}',
        },
        labelLine: { lineStyle: { color: '#4fb6db' }, length: 8, length2: 6 },
        itemStyle: { borderColor: '#04111b', borderWidth: 2 },
      }
    ],
  }
})

const alertTrendOption = computed(() => {
  const xs = trendSeries.value.map(s => s.time)
  return {
    backgroundColor: 'transparent',
    tooltip: icuTooltip({ trigger: 'axis' }),
    legend: icuLegend(),
    grid: icuGrid({ left: 36, right: 12, top: 28, bottom: 30 }),
    xAxis: icuCategoryAxis(xs),
    yAxis: icuValueAxis(),
    series: [
      { name: 'Warning', type: 'line', smooth: true, symbol: 'circle', symbolSize: 6, lineStyle: { width: 2, color: '#fbbf24' }, itemStyle: { color: '#fbbf24' }, data: trendSeries.value.map(s => s.warning || 0) },
      { name: 'High', type: 'line', smooth: true, symbol: 'circle', symbolSize: 6, lineStyle: { width: 2, color: '#fb923c' }, itemStyle: { color: '#fb923c' }, data: trendSeries.value.map(s => s.high || 0) },
      { name: 'Critical', type: 'line', smooth: true, symbol: 'circle', symbolSize: 6, lineStyle: { width: 2, color: '#fb5a7a' }, itemStyle: { color: '#fb5a7a' }, data: trendSeries.value.map(s => s.critical || 0) },
    ],
  }
})

const bundleOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: icuTooltip({ trigger: 'item' }),
  series: [
    {
      type: 'pie',
      radius: ['40%', '68%'],
      data: [
        { name: '绿色', value: bundleCounts.value.green || 0, itemStyle: { color: '#22c55e' } },
        { name: '黄色', value: bundleCounts.value.yellow || 0, itemStyle: { color: '#f59e0b' } },
        { name: '红色', value: bundleCounts.value.red || 0, itemStyle: { color: '#ef4444' } },
      ],
      label: { color: '#dffbff', fontSize: 10, formatter: '{b} {c}' },
      itemStyle: { borderColor: '#04111b', borderWidth: 2 },
    },
  ],
}))

const deviceHeatmapOption = computed(() => {
  const beds = Array.from(new Set(deviceHeatRows.value.map((x: any) => String(x.bed || '--'))))
  const devices = ['cvc', 'foley', 'ett']
  const data = deviceHeatRows.value.map((row: any) => [
    devices.indexOf(String(row.device_type || '')),
    beds.indexOf(String(row.bed || '--')),
    row.risk_score || 0,
  ]).filter((x: any) => x[0] >= 0 && x[1] >= 0)

  return {
    tooltip: icuTooltip({
      position: 'top',
      formatter: (params: any) => {
        const row = deviceHeatRows.value.find((x: any) =>
          devices.indexOf(String(x.device_type || '')) === params.data?.[0] &&
          beds.indexOf(String(x.bed || '--')) === params.data?.[1]
        )
        if (!row) return ''
        return `${row.bed}床 ${row.device_type}<br/>风险 ${row.risk}<br/>在位 ${row.line_days || 0} 天`
      },
    }),
    grid: icuGrid({ left: 54, right: 14, top: 20, bottom: 38 }),
    xAxis: icuCategoryAxis(devices, { axisLabel: { color: '#8fd4e6', fontSize: 10 } }),
    yAxis: icuCategoryAxis(beds, { axisLabel: { color: '#8fd4e6', fontSize: 10 } }),
    visualMap: {
      min: 0,
      max: 3,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      calculable: false,
      inRange: { color: ['#0a2234', '#0e8ca1', '#3ee7c0', '#f59e0b', '#fb5a7a'] },
      textStyle: { color: '#8fd4e6', fontSize: 10 },
    },
    series: [{ type: 'heatmap', data, itemStyle: { borderRadius: 6, borderColor: 'rgba(88,225,255,.08)', borderWidth: 1 } }],
  }
})

const routeDeptCode = computed(() => String(route.query.dept_code || route.query.deptCode || '').trim())
const routeDeptName = computed(() => String(route.query.dept || ''))

function buildPatientParams() {
  const deptCode = routeDeptCode.value
  const deptName = routeDeptName.value
  if (deptCode) return { dept_code: deptCode }
  if (deptName) return { dept: deptName }
  return undefined
}

function severityPriority(level: string) {
  const p: Record<string, number> = { none: 0, normal: 1, warning: 2, high: 3, critical: 4 }
  return p[level] ?? 0
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

function hasPatientRescueRisk(patient: any) {
  if (patient?.postExtubationRisk?.has_alert) return true
  const level = String(patient?.alertLevel || '').toLowerCase()
  return (level === 'high' || level === 'critical') && !!patient?.hasRescueRisk
}

function buildAlertMap() {
  const map = new Map<string, { severity: string; rescue: boolean }>()
  alerts.value.forEach(a => {
    const pid = String(a.patient_id || '')
    if (!pid) return
    const sev = String(a.severity || 'warning')
    const cur = map.get(pid) || { severity: 'none', rescue: false }
    if (severityPriority(sev) >= severityPriority(cur.severity)) {
      map.set(pid, { severity: sev, rescue: cur.rescue || isRescueRiskAlert(a) })
    } else if (isRescueRiskAlert(a) && !cur.rescue) {
      map.set(pid, { ...cur, rescue: true })
    }
  })
  return map
}

function applyAlert(alert: any) {
  if (!alert) return
  alerts.value.unshift(alert)
  alerts.value = alerts.value.slice(0, 50)
  const pid = String(alert.patient_id || '')
  const target = patients.value.find(p => String(p._id) === pid)
  if (target) {
    const sev = String(alert.severity || 'warning')
    if (severityPriority(sev) >= severityPriority(target.alertLevel || 'none')) {
      target.alertLevel = sev
    }
    if (isRescueRiskAlert(alert)) {
      target.hasRescueRisk = true
    }
    target.alertHoldUntil = Date.now() + 30 * 60 * 1000
    target.alertFlash = true
    window.setTimeout(() => { target.alertFlash = false }, 15000)
  }
}

async function loadAlerts() {
  const res = await getRecentAlerts(50, buildPatientParams())
  alerts.value = res.data.records || []
}

async function loadTrend() {
  const res = await getAlertStats('24h')
  trendSeries.value = res.data.series || []
}

async function loadBundle() {
  try {
    const res = await getBundleOverview(buildPatientParams())
    bundleCounts.value = res.data?.counts || { green: 0, yellow: 0, red: 0 }
  } catch {
    bundleCounts.value = { green: 0, yellow: 0, red: 0 }
  }
}

async function loadDeviceHeatmap() {
  const res = await getDeviceRiskHeatmap(buildPatientParams())
  deviceHeatRows.value = res.data?.rows || []
}

async function loadDepts() {
  // 若带科室参数，直接基于患者列表统计，避免“切换页面参数丢失”
  if (routeDeptCode.value || routeDeptName.value) {
    const map = new Map<string, number>()
    patients.value.forEach((p: any) => {
      const name = p.hisDept || p.dept || '未知'
      map.set(name, (map.get(name) || 0) + 1)
    })
    depts.value = Array.from(map.entries()).map(([dept, patientCount]) => ({ dept, patientCount }))
    return
  }
  const res = await getDepartments()
  depts.value = res.data.departments || []
}

async function loadPatients() {
  const res = await getPatients(buildPatientParams())
  const list = res.data.patients || []
  const head = list.slice(0, 60)
  const tail = list.slice(60).map((p: any) => ({
    ...p,
    vitals: {},
    alertLevel: 'none',
    postExtubationRisk: null,
    hasRescueRisk: false,
  }))

  const done = await Promise.all(head.map(async (p: any) => {
    try { p.vitals = (await getPatientVitals(p._id)).data.vitals || {} }
    catch { p.vitals = {} }
    try {
      const status = (await getPatientWeaningStatus(p._id)).data?.status || {}
      p.postExtubationRisk = status?.post_extubation_risk || null
      const riskSeverity = String(p.postExtubationRisk?.severity || '').toLowerCase()
      if (p.postExtubationRisk?.has_alert && severityPriority(riskSeverity) > severityPriority(p.alertLevel || 'none')) {
        p.alertLevel = riskSeverity
      }
      p.hasRescueRisk = !!p.postExtubationRisk?.has_alert
    } catch {
      p.postExtubationRisk = null
      p.hasRescueRisk = false
    }
    p.alertLevel = p.alertLevel || 'none'
    return p
  }))

  const map = buildAlertMap()
  patients.value = [...done, ...tail].map(p => {
    const holdUntil = p.alertHoldUntil || 0
    const linked = map.get(String(p._id))
    if (linked?.severity) p.alertLevel = linked.severity
    if (linked?.rescue) p.hasRescueRisk = true
    if (holdUntil > Date.now()) return p
    return p
  })
}

onMounted(() => {
  timer = window.setInterval(() => {
    currentTime.value = dayjs().format('YYYY-MM-DD HH:mm:ss')
  }, 1000)
  refreshTimer = window.setInterval(() => {
    loadAlerts()
    loadPatients()
    loadTrend()
    loadDepts()
    loadBundle()
    loadDeviceHeatmap()
  }, 60000)
  alertTimer = window.setInterval(() => {
    alertIndex.value += 1
  }, 3000)

  loadAlerts()
  loadPatients()
  loadDepts()
  loadTrend()
  loadBundle()
  loadDeviceHeatmap()

  offAlert = onAlertMessage(msg => {
    if (msg?.type === 'alert') applyAlert(msg.data)
  })
})

onUnmounted(() => {
  clearInterval(timer)
  clearInterval(refreshTimer)
  clearInterval(alertTimer)
  if (offAlert) offAlert()
})

watch(() => route.query, () => {
  loadPatients()
  loadDepts()
  loadAlerts()
  loadTrend()
  loadBundle()
  loadDeviceHeatmap()
}, { deep: true })
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;600;700&display=swap');

.bigscreen {
  min-height: 100vh;
  position: relative;
  isolation: isolate;
  background: radial-gradient(circle at 20% 0%, #0c1f36 0%, #050b16 45%, #04070d 100%);
  color: #e2e8f0;
  font-family: 'Rajdhani', 'Noto Sans SC', sans-serif;
}
.bigscreen::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(rgba(73, 196, 255, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(73, 196, 255, 0.04) 1px, transparent 1px);
  background-size: 32px 32px;
  opacity: 0.24;
}
.screen-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  background: linear-gradient(90deg, rgba(8,26,43,0.96), rgba(6,16,29,0.96));
  border-bottom: 1px solid rgba(80,199,255,.2);
  box-shadow: 0 10px 28px rgba(0,0,0,.22);
  position: sticky;
  top: 0;
  z-index: 5;
}
.header-main { display: flex; flex-direction: column; gap: 4px; }
.title {
  font-size: 22px;
  letter-spacing: 2px;
  font-weight: 700;
  color: #effcff;
}
.title-tag {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  background: linear-gradient(180deg, #0b6b89 0%, #07465a 100%);
  border: 1px solid rgba(110, 231, 249, 0.24);
  margin-right: 8px;
  font-size: 12px;
  color: #ecfeff;
}
.header-sub {
  color: #7ed6e8;
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}
.header-filters {
  margin-top: 8px;
}
.header-filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid rgba(251, 113, 133, .18);
  background: linear-gradient(180deg, rgba(49, 15, 25, .9) 0%, rgba(24, 10, 16, .92) 100%);
  color: #ffcad5;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: all .18s ease;
}
.header-filter-chip b {
  color: #fff1f4;
  font-size: 13px;
}
.header-filter-chip:hover,
.header-filter-chip.active {
  border-color: rgba(251, 113, 133, .38);
  box-shadow: 0 0 18px rgba(251, 113, 133, .16);
  color: #fff0f4;
}
.screen-kpis { display: flex; gap: 10px; margin-left: auto; }
.kpi-chip {
  min-width: 104px;
  padding: 8px 12px;
  border-radius: 12px;
  background: rgba(7,29,45,.82);
  border: 1px solid rgba(80,199,255,.14);
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.kpi-label { font-size: 11px; color: #7ecce1; letter-spacing: .08em; }
.kpi-chip strong { font-size: 20px; color: #e8fbff; }
.clock {
  font-size: 16px;
  color: #8de3f3;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: .08em;
}
.screen-body {
  display: grid;
  grid-template-columns: 1.2fr 3fr 1.3fr;
  gap: 14px;
  padding: 14px;
  position: relative;
  z-index: 1;
}
.panel {
  background: linear-gradient(180deg, rgba(7,20,34,.94) 0%, rgba(4,12,22,.96) 100%);
  border: 1px solid rgba(80,199,255,.14);
  border-radius: 12px;
  padding: 10px;
  box-shadow: inset 0 1px 0 rgba(145,228,255,.04), 0 10px 30px rgba(0,0,0,0.35);
}
.panel-title {
  font-size: 12px;
  color: #67e8f9;
  margin-bottom: 8px;
  letter-spacing: .12em;
  text-transform: uppercase;
  border-bottom: 1px solid rgba(80,199,255,.08);
  padding-bottom: 8px;
}

.chart-wrap {
  height: 240px;
  margin-bottom: 12px;
}
.chart-wrap-heatmap {
  height: 300px;
}

@keyframes flash-border {
  0%, 100% { box-shadow: 0 0 0 rgba(239,68,68,0); }
  50% { box-shadow: 0 0 18px rgba(239,68,68,0.35); }
}

@media (max-width: 1100px) {
  .screen-body {
    grid-template-columns: 1fr;
  }
  .screen-header {
    flex-wrap: wrap;
  }
  .screen-kpis {
    order: 3;
    width: 100%;
  }
  .header-filters {
    margin-top: 6px;
  }
}
</style>
