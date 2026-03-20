<template>
  <div class="bigscreen">
    <header class="screen-header">
      <div class="header-main">
        <div class="title">
          <span class="title-tag">ICU Command</span>
          ICU 主任 / 护士长指挥大屏
        </div>
        <div class="header-sub">抢救、流程、人力与装置风险统一驾驶舱</div>
        <div class="header-context-row">
          <span class="header-context-chip">当前范围 {{ scopeLabel }}</span>
          <span class="header-context-chip">High / Critical {{ severeAlertCount }}</span>
          <span class="header-context-chip">抢救期床位 {{ rescuePatientCount }}</span>
        </div>
        <div class="header-filters">
          <button
            :class="['header-filter-chip', { active: rescueOnly }]"
            @click="rescueOnly = !rescueOnly"
          >
            抢救期快筛
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
          <span class="kpi-label">危急床位</span>
          <strong>{{ filteredCriticalPatientCount }}</strong>
        </div>
        <div class="kpi-chip">
          <span class="kpi-label">导管高风险</span>
          <strong>{{ highDeviceRiskCount }}</strong>
        </div>
        <div class="kpi-chip">
          <span class="kpi-label">{{ rescueOnly ? '抢救期告警' : '实时告警' }}</span>
          <strong>{{ filteredAlerts.length }}</strong>
        </div>
      </div>
      <div class="clock">{{ currentTime }}</div>
    </header>

    <section class="command-strip">
      <article v-for="item in commandKpis" :key="item.label" :class="['command-card', item.tone ? `command-card--${item.tone}` : '']">
        <span class="command-card__label">{{ item.label }}</span>
        <strong class="command-card__value">{{ item.value }}</strong>
        <span class="command-card__meta">{{ item.meta }}</span>
      </article>
    </section>

    <section class="ops-board">
      <article class="ops-lane">
        <div class="ops-lane__head">
          <div>
            <div class="ops-lane__kicker">Director Focus</div>
            <div class="ops-lane__title">ICU 主任关注</div>
          </div>
          <span class="ops-lane__badge">流程 / 风险 / 负荷</span>
        </div>
        <div class="ops-lane__list">
          <div v-for="item in directorFocusRows" :key="item.label" class="ops-item">
            <div class="ops-item__label">{{ item.label }}</div>
            <div class="ops-item__value">{{ item.value }}</div>
            <div class="ops-item__meta">{{ item.meta }}</div>
          </div>
        </div>
      </article>

      <article class="ops-lane ops-lane--nurse">
        <div class="ops-lane__head">
          <div>
            <div class="ops-lane__kicker">Head Nurse Focus</div>
            <div class="ops-lane__title">护士长关注</div>
          </div>
          <span class="ops-lane__badge">交班 / 装置 / 床旁执行</span>
        </div>
        <div class="ops-lane__list">
          <div v-for="item in nurseFocusRows" :key="item.label" class="ops-item">
            <div class="ops-item__label">{{ item.label }}</div>
            <div class="ops-item__value">{{ item.value }}</div>
            <div class="ops-item__meta">{{ item.meta }}</div>
          </div>
        </div>
      </article>
    </section>

    <section class="screen-body">
      <aside class="panel panel-left">
        <div class="panel-head">
          <div class="panel-title">{{ rescueOnly ? '抢救期预警' : '实时预警' }}</div>
          <div class="panel-meta">滚动展示 {{ showAlerts.length }} 条重点事件</div>
        </div>
        <BigScreenAlertFeed :alerts="showAlerts" />
      </aside>

      <main class="panel panel-center">
        <div class="panel-head">
          <div class="panel-title">{{ rescueOnly ? '抢救期床位监控' : '床位监控' }}</div>
          <div class="panel-meta">当前纳管 {{ filteredPatients.length }} 床</div>
        </div>
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

const scopeLabel = computed(() => routeDeptName.value || routeDeptCode.value || '全院 ICU')
const severeAlertCount = computed(() =>
  filteredAlerts.value.filter((a: any) => ['high', 'critical'].includes(String(a?.severity || '').toLowerCase())).length
)
const highDeviceRiskCount = computed(() =>
  deviceHeatRows.value.filter((row: any) => {
    const risk = String(row?.risk || '').toLowerCase()
    const score = Number(row?.risk_score || 0)
    return risk === 'high' || risk === 'critical' || score >= 2
  }).length
)
const postExtubationRiskCount = computed(() =>
  filteredPatients.value.filter((p: any) => p?.postExtubationRisk?.has_alert).length
)
const bundleWatchCount = computed(() => Number(bundleCounts.value?.yellow || 0) + Number(bundleCounts.value?.red || 0))
const topAlertLabel = computed(() => {
  const map = new Map<string, number>()
  filteredAlerts.value.forEach((row: any) => {
    const key = String(row?.name || row?.alert_type || row?.rule_id || '未知事件').trim()
    if (!key) return
    map.set(key, (map.get(key) || 0) + 1)
  })
  const top = [...map.entries()].sort((a, b) => b[1] - a[1])[0]
  return top ? `${top[0]} · ${top[1]} 次` : '暂无高频事件'
})
const deptPressureLabel = computed(() => {
  const map = new Map<string, number>()
  filteredPatients.value.forEach((row: any) => {
    const key = String(row?.hisDept || row?.dept || '未知科室').trim()
    map.set(key, (map.get(key) || 0) + 1)
  })
  const top = [...map.entries()].sort((a, b) => b[1] - a[1])[0]
  return top ? `${top[0]} · ${top[1]} 床` : '暂无科室压力数据'
})
const commandKpis = computed(() => [
  {
    label: '危急床位',
    value: `${filteredCriticalPatientCount.value}`,
    meta: rescueOnly.value ? '当前抢救期视图内的危急床位' : '全视图内 alertLevel = critical 的床位',
    tone: 'risk',
  },
  {
    label: 'Bundle 待跟进',
    value: `${bundleWatchCount.value}`,
    meta: `${Number(bundleCounts.value?.red || 0)} 床高风险，${Number(bundleCounts.value?.yellow || 0)} 床待闭环`,
    tone: 'bundle',
  },
  {
    label: '装置高风险',
    value: `${highDeviceRiskCount.value}`,
    meta: '导管风险热力图中高风险床位数',
    tone: 'amber',
  },
  {
    label: '拔管后高风险',
    value: `${postExtubationRiskCount.value}`,
    meta: '需要护士长交班重点盯防的床位',
    tone: 'cyan',
  },
])
const directorFocusRows = computed(() => [
  {
    label: '流程压点',
    value: topAlertLabel.value,
    meta: '先看最近高频规则，决定今日质控与值班抽查重点。',
  },
  {
    label: '科室压力',
    value: deptPressureLabel.value,
    meta: '当前床位最密集的科室，可联动护理和装置风险下钻。',
  },
  {
    label: '抢救负荷',
    value: `${rescuePatientCount.value} 床 / ${severeAlertCount.value} 条高危告警`,
    meta: rescueOnly.value ? '已锁定抢救期视图，可直接做床位调度。' : '建议结合抢救期快筛判断是否需要切换到高风险模式。',
  },
])
const nurseFocusRows = computed(() => [
  {
    label: '交班盯防',
    value: `${postExtubationRiskCount.value} 床拔管后高风险`,
    meta: '优先安排连续观察、氧疗升级与呼吸功复评。',
  },
  {
    label: '装置巡视',
    value: `${highDeviceRiskCount.value} 处导管高风险`,
    meta: '建议优先查在位天数长、风险评分高的床位。',
  },
  {
    label: '实时队列',
    value: `${showAlerts.value.length} 条滚动事件`,
    meta: '左侧事件流可直接配合床位网格进行处置追踪。',
  },
])

const showAlerts = computed(() => {
  const n = 8
  const list = filteredAlerts.value
  if (list.length <= n) return list
  const start = alertIndex.value % list.length
  return [...list.slice(start, start + n), ...list.slice(0, Math.max(0, n - (list.length - start)))]
})

const deptOption = computed(() => {
  const data = depts.value.map((d, idx) => ({
    name: d.dept,
    value: d.patientCount,
    itemStyle: {
      color: ['#3dd9f5', '#34d399', '#fbbf24', '#fb923c', '#fb7185', '#818cf8'][idx % 6],
    },
  }))
  const total = data.reduce((sum, item) => sum + Number(item.value || 0), 0)
  const hasData = data.length > 0
  return {
    backgroundColor: 'transparent',
    tooltip: icuTooltip({
      trigger: 'item',
      formatter: (params: any) => `${params.name}<br/>当前床位 <b>${params.value || 0}</b> 床`,
    }),
    graphic: hasData ? [
      {
        type: 'group',
        left: 'center',
        top: '40%',
        children: [
          {
            type: 'text',
            left: 'center',
            top: 0,
            style: {
              text: String(total),
              fill: '#effcff',
              fontSize: 22,
              fontWeight: 700,
              textAlign: 'center',
            },
          },
          {
            type: 'text',
            left: 'center',
            top: 26,
            style: {
              text: '在院床位',
              fill: '#7ccfe4',
              fontSize: 10,
              textAlign: 'center',
            },
          },
        ],
      },
    ] : [
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
        radius: ['48%', '72%'],
        center: ['50%', '46%'],
        data,
        label: {
          color: '#dffbff',
          fontSize: 10,
          formatter: '{b}\n{c}床',
        },
        labelLine: { lineStyle: { color: 'rgba(79,182,219,.7)' }, length: 8, length2: 6 },
        itemStyle: { borderColor: '#04111b', borderWidth: 2, shadowBlur: 12, shadowColor: 'rgba(0,0,0,.18)' },
      }
    ],
  }
})
const alertTrendOption = computed(() => {
  const xs = trendSeries.value.map(s => s.time)
  return {
    backgroundColor: 'transparent',
    tooltip: icuTooltip({
      trigger: 'axis',
      formatter: (params: any[]) => {
        const lines = (params || []).map((item) => `${item.marker}${item.seriesName} <b>${item.value || 0}</b> 次`)
        return [`<div style="margin-bottom:4px;color:#9edff0;">${params?.[0]?.axisValue || '--'}</div>`, ...lines].join('<br/>')
      },
    }),
    legend: icuLegend({ top: 2 }),
    grid: icuGrid({ left: 36, right: 12, top: 36, bottom: 30 }),
    xAxis: icuCategoryAxis(xs),
    yAxis: icuValueAxis(),
    series: [
      { name: '预警', type: 'line', smooth: true, symbol: 'circle', symbolSize: 6, lineStyle: { width: 2, color: '#fbbf24' }, areaStyle: { color: 'rgba(251,191,36,.12)' }, itemStyle: { color: '#fbbf24' }, data: trendSeries.value.map(s => s.warning || 0) },
      { name: '高危', type: 'line', smooth: true, symbol: 'circle', symbolSize: 6, lineStyle: { width: 2, color: '#fb923c' }, areaStyle: { color: 'rgba(251,146,60,.1)' }, itemStyle: { color: '#fb923c' }, data: trendSeries.value.map(s => s.high || 0) },
      { name: '危急', type: 'line', smooth: true, symbol: 'circle', symbolSize: 6, lineStyle: { width: 2, color: '#fb5a7a' }, areaStyle: { color: 'rgba(251,90,122,.1)' }, itemStyle: { color: '#fb5a7a' }, data: trendSeries.value.map(s => s.critical || 0) },
    ],
  }
})

const bundleOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: icuTooltip({
    trigger: 'item',
    formatter: (params: any) => `${params.name}状态<br/>当前占比 <b>${params.value || 0}</b>`,
  }),
  series: [
    {
      type: 'pie',
      radius: ['46%', '70%'],
      center: ['50%', '46%'],
      data: [
        { name: '达标', value: bundleCounts.value.green || 0, itemStyle: { color: '#22c55e' } },
        { name: '待跟进', value: bundleCounts.value.yellow || 0, itemStyle: { color: '#f59e0b' } },
        { name: '高风险', value: bundleCounts.value.red || 0, itemStyle: { color: '#ef4444' } },
      ],
      label: { color: '#dffbff', fontSize: 10, formatter: '{b}\n{c}' },
      labelLine: { lineStyle: { color: 'rgba(79,182,219,.7)' }, length: 8, length2: 6 },
      itemStyle: { borderColor: '#04111b', borderWidth: 2, shadowBlur: 12, shadowColor: 'rgba(0,0,0,.18)' },
    },
  ],
}))

const deviceHeatmapOption = computed(() => {
  const beds = Array.from(new Set(deviceHeatRows.value.map((x: any) => String(x.bed || '--'))))
  const devices = ['中心静脉导管', '导尿管', '气管导管']
  const deviceKeyMap: Record<string, string> = {
    cvc: '中心静脉导管',
    foley: '导尿管',
    ett: '气管导管',
  }
  const data = deviceHeatRows.value.map((row: any) => [
    devices.indexOf(deviceKeyMap[String(row.device_type || '')] || ''),
    beds.indexOf(String(row.bed || '--')),
    row.risk_score || 0,
  ]).filter((x: any) => x[0] >= 0 && x[1] >= 0)

  return {
    tooltip: icuTooltip({
      position: 'top',
      formatter: (params: any) => {
        const row = deviceHeatRows.value.find((x: any) =>
          devices.indexOf(deviceKeyMap[String(x.device_type || '')] || '') === params.data?.[0] &&
          beds.indexOf(String(x.bed || '--')) === params.data?.[1]
        )
        if (!row) return ''
        const deviceLabel = deviceKeyMap[String(row.device_type || '')] || String(row.device_type || '装置')
        return `<div style="margin-bottom:4px;color:#9edff0;">${row.bed}床 · ${deviceLabel}</div>风险等级 <b>${row.risk}</b><br/>在位天数 <b>${row.line_days || 0}</b> 天`
      },
    }),
    grid: icuGrid({ left: 54, right: 14, top: 20, bottom: 42 }),
    xAxis: icuCategoryAxis(devices, { axisLabel: { color: '#8fd4e6', fontSize: 10 } }),
    yAxis: icuCategoryAxis(beds, { axisLabel: { color: '#8fd4e6', fontSize: 10 } }),
    visualMap: {
      min: 0,
      max: 3,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      calculable: false,
      text: ['高风险', '低风险'],
      inRange: { color: ['#0b2538', '#0e7490', '#34d399', '#f59e0b', '#fb5a7a'] },
      textStyle: { color: '#8fd4e6', fontSize: 10 },
    },
    series: [{ type: 'heatmap', data, itemStyle: { borderRadius: 8, borderColor: 'rgba(88,225,255,.08)', borderWidth: 1 } }],
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
  gap: 18px;
  padding: 18px 22px;
  background: linear-gradient(90deg, rgba(8,26,43,0.96), rgba(6,16,29,0.96));
  border-bottom: 1px solid rgba(80,199,255,.2);
  box-shadow: 0 10px 28px rgba(0,0,0,.22);
  position: sticky;
  top: 0;
  z-index: 5;
}
.header-main { display: flex; flex-direction: column; gap: 6px; }
.title {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 24px;
  letter-spacing: 0.06em;
  font-weight: 700;
  line-height: 1;
  color: #effcff;
}
.title-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 34px;
  padding: 0 14px;
  border-radius: 999px;
  background: linear-gradient(180deg, #0b6b89 0%, #07465a 100%);
  border: 1px solid rgba(110, 231, 249, 0.24);
  font-size: 13px;
  font-weight: 700;
  color: #ecfeff;
  box-shadow: inset 0 1px 0 rgba(210, 248, 255, 0.18);
}
.header-sub {
  position: relative;
  display: inline-flex;
  align-items: center;
  width: fit-content;
  min-height: 20px;
  padding-left: 46px;
  color: #9ae8f7;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.14em;
  line-height: 1.15;
  text-shadow: 0 0 14px rgba(56, 189, 248, 0.18);
}
.header-sub::before {
  content: "";
  position: absolute;
  left: 0;
  top: 50%;
  width: 34px;
  height: 1px;
  background: linear-gradient(90deg, rgba(154, 232, 247, 0.9), rgba(154, 232, 247, 0.08));
  transform: translateY(-50%);
}
.header-filters {
  margin-top: 10px;
}
.header-filter-chip:hover,
.header-filter-chip.active {
  border-color: rgba(251, 113, 133, .38);
  box-shadow: 0 0 18px rgba(251, 113, 133, .16);
  color: #fff0f4;
}
.screen-kpis { display: flex; gap: 12px; margin-left: auto; }
.kpi-chip {
  min-width: 112px;
  padding: 10px 13px;
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(9,31,48,.88) 0%, rgba(6,21,34,.92) 100%);
  border: 1px solid rgba(80,199,255,.14);
  display: flex;
  flex-direction: column;
  gap: 4px;
  box-shadow: inset 0 1px 0 rgba(145,228,255,.04);
}
.kpi-label { font-size: 11px; color: #7ecce1; letter-spacing: .08em; }
.kpi-chip strong { font-size: 22px; color: #e8fbff; }
.clock {
  font-size: 16px;
  color: #8de3f3;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: .08em;
  padding: 10px 14px;
  border-radius: 14px;
  background: rgba(6, 21, 34, 0.76);
  border: 1px solid rgba(80, 199, 255, 0.12);
}
.header-context-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 2px;
}
.header-context-chip,
.header-filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid rgba(80,199,255,.14);
  background: rgba(8, 28, 44, 0.78);
  color: #dffbff;
  font-size: 11px;
  font-weight: 700;
}
.header-filter-chip {
  cursor: pointer;
  transition: all .18s ease;
}
.command-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  padding: 14px 16px 0;
}
.command-card {
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(80,199,255,.14);
  background:
    radial-gradient(circle at top right, rgba(34,211,238,.08), rgba(34,211,238,0) 34%),
    linear-gradient(180deg, rgba(7,20,34,.96) 0%, rgba(4,12,22,.98) 100%);
  box-shadow: inset 0 1px 0 rgba(145,228,255,.05), 0 12px 28px rgba(0,0,0,.2);
}
.command-card--risk { border-color: rgba(251,113,133,.18); }
.command-card--bundle { border-color: rgba(74,222,128,.18); }
.command-card--amber { border-color: rgba(251,191,36,.18); }
.command-card--cyan { border-color: rgba(56,189,248,.18); }
.command-card__label {
  color: #7ecce1;
  font-size: 11px;
  letter-spacing: .12em;
  text-transform: uppercase;
}
.command-card__value {
  color: #effcff;
  font-size: 28px;
  line-height: 1;
}
.command-card__meta {
  color: #8fb8ca;
  font-size: 11px;
  line-height: 1.5;
}
.ops-board {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 12px 16px 0;
}
.ops-lane {
  display: grid;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(80,199,255,.14);
  background: linear-gradient(180deg, rgba(7,20,34,.96) 0%, rgba(4,12,22,.98) 100%);
  box-shadow: inset 0 1px 0 rgba(145,228,255,.04), 0 12px 28px rgba(0,0,0,.18);
}
.ops-lane--nurse { border-color: rgba(74,222,128,.16); }
.ops-lane__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.ops-lane__kicker {
  color: #6ea9bc;
  font-size: 10px;
  letter-spacing: .12em;
  text-transform: uppercase;
}
.ops-lane__title {
  color: #effcff;
  font-size: 18px;
  font-weight: 700;
}
.ops-lane__badge {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba(80,199,255,.12);
  background: rgba(8,28,44,.8);
  color: #9ae8f7;
  font-size: 10px;
}
.ops-lane__list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.ops-item {
  display: grid;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(8, 28, 44, 0.78);
  border: 1px solid rgba(80,199,255,.12);
}
.ops-item__label {
  color: #7ecce1;
  font-size: 11px;
  letter-spacing: .08em;
}
.ops-item__value {
  color: #effcff;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.4;
}
.ops-item__meta {
  color: #8fb8ca;
  font-size: 11px;
  line-height: 1.5;
}
.screen-body {
  display: grid;
  grid-template-columns: 1.45fr 2.85fr 1.25fr;
  gap: 16px;
  padding: 16px;
  position: relative;
  z-index: 1;
}
.panel {
  background: linear-gradient(180deg, rgba(7,20,34,.94) 0%, rgba(4,12,22,.96) 100%);
  border: 1px solid rgba(80,199,255,.14);
  border-radius: 16px;
  padding: 12px;
  box-shadow: inset 0 1px 0 rgba(145,228,255,.04), 0 10px 30px rgba(0,0,0,0.35);
}
.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: baseline;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(80,199,255,.08);
}
.panel-title {
  font-size: 12px;
  color: #67e8f9;
  letter-spacing: .06em;
  font-weight: 700;
}
.panel-meta {
  color: #6faec1;
  font-size: 10px;
  letter-spacing: .08em;
}
.panel-left,
.panel-center {
  min-width: 0;
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
  .header-context-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 2px;
}
.header-context-chip,
.header-filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid rgba(80,199,255,.14);
  background: rgba(8, 28, 44, 0.78);
  color: #dffbff;
  font-size: 11px;
  font-weight: 700;
}
.header-filter-chip {
  cursor: pointer;
  transition: all .18s ease;
}
.command-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  padding: 14px 16px 0;
}
.command-card {
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(80,199,255,.14);
  background:
    radial-gradient(circle at top right, rgba(34,211,238,.08), rgba(34,211,238,0) 34%),
    linear-gradient(180deg, rgba(7,20,34,.96) 0%, rgba(4,12,22,.98) 100%);
  box-shadow: inset 0 1px 0 rgba(145,228,255,.05), 0 12px 28px rgba(0,0,0,.2);
}
.command-card--risk { border-color: rgba(251,113,133,.18); }
.command-card--bundle { border-color: rgba(74,222,128,.18); }
.command-card--amber { border-color: rgba(251,191,36,.18); }
.command-card--cyan { border-color: rgba(56,189,248,.18); }
.command-card__label {
  color: #7ecce1;
  font-size: 11px;
  letter-spacing: .12em;
  text-transform: uppercase;
}
.command-card__value {
  color: #effcff;
  font-size: 28px;
  line-height: 1;
}
.command-card__meta {
  color: #8fb8ca;
  font-size: 11px;
  line-height: 1.5;
}
.ops-board {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 12px 16px 0;
}
.ops-lane {
  display: grid;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(80,199,255,.14);
  background: linear-gradient(180deg, rgba(7,20,34,.96) 0%, rgba(4,12,22,.98) 100%);
  box-shadow: inset 0 1px 0 rgba(145,228,255,.04), 0 12px 28px rgba(0,0,0,.18);
}
.ops-lane--nurse { border-color: rgba(74,222,128,.16); }
.ops-lane__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.ops-lane__kicker {
  color: #6ea9bc;
  font-size: 10px;
  letter-spacing: .12em;
  text-transform: uppercase;
}
.ops-lane__title {
  color: #effcff;
  font-size: 18px;
  font-weight: 700;
}
.ops-lane__badge {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba(80,199,255,.12);
  background: rgba(8,28,44,.8);
  color: #9ae8f7;
  font-size: 10px;
}
.ops-lane__list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.ops-item {
  display: grid;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(8, 28, 44, 0.78);
  border: 1px solid rgba(80,199,255,.12);
}
.ops-item__label {
  color: #7ecce1;
  font-size: 11px;
  letter-spacing: .08em;
}
.ops-item__value {
  color: #effcff;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.4;
}
.ops-item__meta {
  color: #8fb8ca;
  font-size: 11px;
  line-height: 1.5;
}
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
  .command-strip {
    padding-top: 10px;
  }
  .header-filters {
    margin-top: 6px;
  }
}
</style>






