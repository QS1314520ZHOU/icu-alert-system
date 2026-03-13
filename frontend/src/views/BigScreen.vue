<template>
  <div class="bigscreen">
    <header class="screen-header">
      <div class="title">
        <span class="title-tag">ICU</span>
        护士站监控大屏
      </div>
      <div class="clock">{{ currentTime }}</div>
    </header>

    <section class="screen-body">
      <aside class="panel panel-left">
        <div class="panel-title">实时预警</div>
        <div class="alert-list">
          <div v-for="a in showAlerts" :key="a._id" class="alert-row">
            <span :class="['sev-dot', `sev-${a.severity || 'warning'}`]"></span>
            <div class="alert-main">
              <div class="alert-name">{{ a.name || a.rule_id || '预警' }}</div>
              <div class="alert-meta">
                {{ a.bed || '--' }}床 · {{ a.patient_name || '未知' }} · {{ fmtTime(a.created_at) }}
              </div>
            </div>
            <div class="alert-val">{{ a.value ?? '—' }}</div>
          </div>
        </div>
      </aside>

      <main class="panel panel-center">
        <div class="panel-title">床位监控</div>
        <div class="bed-grid">
          <div v-for="p in patients" :key="p._id"
               :class="['bed-card', `bed-${p.alertLevel || 'none'}`, { flash: p.alertFlash }]">
            <div class="bed-head">
              <div class="bed-no">{{ p.hisBed || '--' }}床</div>
              <span :class="['lamp', `lamp-${p.alertLevel || 'none'}`]"></span>
            </div>
            <div class="bed-name">{{ p.name || '—' }}</div>
            <div class="bed-vitals">
              <div>HR <b>{{ p.vitals?.hr ?? '—' }}</b></div>
              <div>SpO₂ <b>{{ p.vitals?.spo2 ?? '—' }}</b></div>
              <div>RR <b>{{ p.vitals?.rr ?? '—' }}</b></div>
            </div>
          </div>
        </div>
      </main>

      <aside class="panel panel-right">
        <div class="panel-title">科室统计</div>
        <div class="chart-wrap">
          <VChart :option="deptOption" autoresize />
        </div>
        <div class="panel-title">近24小时预警趋势</div>
        <div class="chart-wrap">
          <VChart :option="alertTrendOption" autoresize />
        </div>
      </aside>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import dayjs from 'dayjs'
import { getDepartments, getPatients, getPatientVitals, getRecentAlerts, getAlertStats } from '../api'
import { onAlertMessage } from '../services/alertSocket'

const currentTime = ref(dayjs().format('YYYY-MM-DD HH:mm:ss'))
const alerts = ref<any[]>([])
const alertIndex = ref(0)
const patients = ref<any[]>([])
const depts = ref<any[]>([])
const trendSeries = ref<any[]>([])

let timer: number
let refreshTimer: number
let alertTimer: number
let offAlert: any = null

const showAlerts = computed(() => {
  const n = 8
  const list = alerts.value
  if (list.length <= n) return list
  const start = alertIndex.value % list.length
  return [...list.slice(start, start + n), ...list.slice(0, Math.max(0, n - (list.length - start)))]
})

const deptOption = computed(() => ({
  tooltip: { trigger: 'item' },
  series: [
    {
      type: 'pie',
      radius: ['40%', '70%'],
      data: depts.value.map(d => ({ name: d.dept, value: d.patientCount })),
      label: { color: '#cbd5f5', fontSize: 10 },
    }
  ],
}))

const alertTrendOption = computed(() => {
  const xs = trendSeries.value.map(s => s.time)
  return {
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#9aa4b2' } },
    grid: { left: 30, right: 10, top: 20, bottom: 30 },
    xAxis: { type: 'category', data: xs, axisLabel: { color: '#6b7280', fontSize: 10 } },
    yAxis: { type: 'value', axisLabel: { color: '#6b7280', fontSize: 10 }, splitLine: { lineStyle: { color: '#132237' } } },
    series: [
      { name: 'Warning', type: 'line', smooth: true, data: trendSeries.value.map(s => s.warning || 0) },
      { name: 'High', type: 'line', smooth: true, data: trendSeries.value.map(s => s.high || 0) },
      { name: 'Critical', type: 'line', smooth: true, data: trendSeries.value.map(s => s.critical || 0) },
    ],
  }
})

function fmtTime(t: any) {
  if (!t) return ''
  try { return dayjs(t).format('HH:mm') } catch { return '' }
}

function severityPriority(level: string) {
  const p: Record<string, number> = { none: 0, normal: 1, warning: 2, high: 3, critical: 4 }
  return p[level] ?? 0
}

function buildAlertMap() {
  const map = new Map<string, string>()
  alerts.value.forEach(a => {
    const pid = String(a.patient_id || '')
    if (!pid) return
    const sev = String(a.severity || 'warning')
    const cur = map.get(pid) || 'none'
    if (severityPriority(sev) >= severityPriority(cur)) {
      map.set(pid, sev)
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
    target.alertHoldUntil = Date.now() + 30 * 60 * 1000
    target.alertFlash = true
    window.setTimeout(() => { target.alertFlash = false }, 15000)
  }
}

async function loadAlerts() {
  const res = await getRecentAlerts(50)
  alerts.value = res.data.records || []
}

async function loadTrend() {
  const res = await getAlertStats('24h')
  trendSeries.value = res.data.series || []
}

async function loadDepts() {
  const res = await getDepartments()
  depts.value = res.data.departments || []
}

async function loadPatients() {
  const res = await getPatients()
  const list = res.data.patients || []
  const head = list.slice(0, 60)
  const tail = list.slice(60).map((p: any) => ({ ...p, vitals: {}, alertLevel: 'none' }))

  const done = await Promise.all(head.map(async (p: any) => {
    try { p.vitals = (await getPatientVitals(p._id)).data.vitals || {} }
    catch { p.vitals = {} }
    p.alertLevel = p.alertLevel || 'none'
    return p
  }))

  const map = buildAlertMap()
  patients.value = [...done, ...tail].map(p => {
    const holdUntil = p.alertHoldUntil || 0
    const sev = map.get(String(p._id))
    if (sev) p.alertLevel = sev
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
  }, 60000)
  alertTimer = window.setInterval(() => {
    alertIndex.value += 1
  }, 3000)

  loadAlerts()
  loadPatients()
  loadDepts()
  loadTrend()

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
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;600;700&display=swap');

.bigscreen {
  min-height: 100vh;
  background: radial-gradient(circle at 20% 0%, #0c1f36 0%, #050b16 45%, #04070d 100%);
  color: #e2e8f0;
  font-family: 'Rajdhani', 'Noto Sans SC', sans-serif;
}
.screen-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 18px 32px;
  background: linear-gradient(90deg, rgba(12,35,61,0.9), rgba(10,18,34,0.9));
  border-bottom: 2px solid #1e3a8a;
}
.title {
  font-size: 24px;
  letter-spacing: 2px;
  font-weight: 700;
}
.title-tag {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  background: #1e40af;
  margin-right: 8px;
  font-size: 12px;
}
.clock {
  font-size: 18px;
  color: #94a3b8;
  font-family: 'JetBrains Mono', monospace;
}
.screen-body {
  display: grid;
  grid-template-columns: 1.2fr 3fr 1.3fr;
  gap: 16px;
  padding: 16px;
}
.panel {
  background: rgba(6, 12, 22, 0.85);
  border: 1px solid #14233b;
  border-radius: 12px;
  padding: 12px;
  box-shadow: 0 10px 30px rgba(0,0,0,0.35);
}
.panel-title {
  font-size: 14px;
  color: #93c5fd;
  margin-bottom: 10px;
  letter-spacing: 1px;
}
.alert-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.alert-row {
  display: grid;
  grid-template-columns: 10px 1fr 60px;
  gap: 8px;
  padding: 8px;
  border-radius: 8px;
  background: #0b1320;
  border: 1px solid #14243b;
}
.alert-main { min-width: 0; }
.alert-name { font-size: 13px; color: #e5e7eb; }
.alert-meta { font-size: 11px; color: #64748b; margin-top: 2px; }
.alert-val { text-align: right; font-weight: 700; color: #cbd5f5; }
.sev-dot { width: 8px; height: 8px; border-radius: 50%; margin-top: 6px; }
.sev-warning { background: #f59e0b; box-shadow: 0 0 6px #f59e0b88; }
.sev-high { background: #f97316; box-shadow: 0 0 6px #f9731688; }
.sev-critical { background: #d946ef; box-shadow: 0 0 6px #d946ef88; }

.bed-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}
.bed-card {
  background: #0a111d;
  border: 1px solid #14243b;
  border-radius: 12px;
  padding: 10px;
}
.bed-card.flash { animation: flash-border 1.2s ease-in-out infinite; }
.bed-critical { border-color: #ef444433; }
.bed-warning { border-color: #f59e0b28; }
.bed-high { border-color: #f9731628; }
.bed-normal { border-color: #22c55e18; }
.bed-head { display: flex; justify-content: space-between; align-items: center; }
.bed-no { font-size: 20px; font-weight: 700; color: #60a5fa; }
.bed-name { font-size: 14px; margin: 6px 0; }
.bed-vitals {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  font-size: 11px;
  color: #94a3b8;
}
.bed-vitals b { color: #e2e8f0; }
.lamp { width: 8px; height: 8px; border-radius: 50%; }
.lamp-critical { background: #ef4444; box-shadow: 0 0 6px #ef4444; }
.lamp-warning { background: #f59e0b; box-shadow: 0 0 6px #f59e0b; }
.lamp-high { background: #f97316; box-shadow: 0 0 6px #f97316; }
.lamp-normal { background: #22c55e; }
.lamp-none { background: #334155; }

.chart-wrap {
  height: 240px;
  margin-bottom: 12px;
}

@keyframes flash-border {
  0%, 100% { box-shadow: 0 0 0 rgba(239,68,68,0); }
  50% { box-shadow: 0 0 18px rgba(239,68,68,0.35); }
}

@media (max-width: 1100px) {
  .screen-body {
    grid-template-columns: 1fr;
  }
}
</style>
