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
                <span v-if="a.category"> · {{ labelCategory(a.category) }}</span>
                <span v-if="a.alert_type"> · {{ labelType(a.alert_type) }}</span>
              </div>
            </div>
            <div class="alert-val">{{ formatAlertValue(a) }}</div>
          </div>
        </div>
      </aside>

      <main class="panel panel-center">
        <div class="panel-title">床位监控</div>
        <BigScreenBedGrid :patients="patients" />
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
import { getBundleOverview, getDepartments, getDeviceRiskHeatmap, getPatients, getPatientVitals, getRecentAlerts, getAlertStats } from '../api'
import { onAlertMessage } from '../services/alertSocket'

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

const deptOption = computed(() => {
  const data = depts.value.map(d => ({ name: d.dept, value: d.patientCount }))
  const hasData = data.length > 0
  return {
    tooltip: { trigger: 'item' },
    graphic: hasData ? [] : [
      {
        type: 'text',
        left: 'center',
        top: 'middle',
        style: {
          text: '暂无科室数据',
          fill: '#6b7280',
          fontSize: 12,
        },
      },
    ],
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        data,
        label: {
          color: '#cbd5f5',
          fontSize: 10,
          formatter: '{b} {c}',
        },
        labelLine: { length: 8, length2: 6 },
      }
    ],
  }
})

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

const bundleOption = computed(() => ({
  tooltip: { trigger: 'item' },
  series: [
    {
      type: 'pie',
      radius: ['40%', '68%'],
      data: [
        { name: '绿色', value: bundleCounts.value.green || 0, itemStyle: { color: '#22c55e' } },
        { name: '黄色', value: bundleCounts.value.yellow || 0, itemStyle: { color: '#f59e0b' } },
        { name: '红色', value: bundleCounts.value.red || 0, itemStyle: { color: '#ef4444' } },
      ],
      label: { color: '#cbd5f5', fontSize: 10, formatter: '{b} {c}' },
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
    tooltip: {
      position: 'top',
      formatter: (params: any) => {
        const row = deviceHeatRows.value.find((x: any) =>
          devices.indexOf(String(x.device_type || '')) === params.data?.[0] &&
          beds.indexOf(String(x.bed || '--')) === params.data?.[1]
        )
        if (!row) return ''
        return `${row.bed}床 ${row.device_type}<br/>风险 ${row.risk}<br/>在位 ${row.line_days || 0} 天`
      },
    },
    grid: { left: 48, right: 10, top: 20, bottom: 34 },
    xAxis: { type: 'category', data: devices, axisLabel: { color: '#9aa4b2', fontSize: 10 } },
    yAxis: { type: 'category', data: beds, axisLabel: { color: '#9aa4b2', fontSize: 10 } },
    visualMap: {
      min: 0,
      max: 3,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      calculable: false,
      inRange: { color: ['#0f172a', '#22c55e', '#f59e0b', '#ef4444'] },
      textStyle: { color: '#9aa4b2', fontSize: 10 },
    },
    series: [{ type: 'heatmap', data }],
  }
})

function fmtTime(t: any) {
  if (!t) return ''
  try { return dayjs(t).format('HH:mm') } catch { return '' }
}

function labelCategory(v: any) {
  const k = String(v || '')
  const map: Record<string, string> = {
    vital_signs: '生命体征',
    lab_results: '检验',
    trend: '趋势',
    syndrome: '综合征',
    tbi: '颅脑',
    ventilator: '呼吸机',
    drug_safety: '药物安全',
    assessments: '护理评估',
    ai_analysis: 'AI',
    fluid_balance: '液体平衡',
    glycemic_control: '血糖管理',
    antibiotic_stewardship: '抗菌药管理',
    vte_prophylaxis: 'VTE预防',
    nutrition_monitor: '营养监测',
    composite_deterioration: '复合恶化',
    device_management: '装置管理',
    bundle: 'Bundle',
    hemodynamic: '血流动力学',
    crrt: 'CRRT',
    dose_adjustment: '剂量调整',
  }
  return map[k] || k
}

function labelType(v: any) {
  const k = String(v || '')
  const map: Record<string, string> = {
    pupil: '瞳孔异常',
    dic: 'DIC',
    ards: 'ARDS',
    aki: 'AKI',
    qsofa: 'qSOFA',
    sofa: 'SOFA',
    septic_shock: '脓毒性休克',
    icp: 'ICP',
    cpp: 'CPP',
    gi_bleeding: '消化道出血',
    weaning: '撤机筛查',
    hit: 'HIT',
    nephrotoxicity: '肾毒性',
    sedation: '过度镇静',
    qt_risk: 'QT风险',
    af_afl_new_onset: '新发房颤/房扑',
    brady_hypotension: '心动过缓合并低压',
    qtc_prolonged: 'QTc明显延长',
    opioid_high_dose_resp_risk: '阿片高剂量风险',
    opioid_respiratory_depression: '阿片呼吸抑制',
    opioid_withdrawal_risk: '阿片戒断风险',
    nurse_reminder: '评估超时',
    lab_threshold: '检验阈值',
    threshold: '阈值',
    trend_analysis: '趋势',
    ai_risk: 'AI风险',
    fluid_balance: '液体平衡',
    delirium_risk: '谵妄风险',
    sedation_delirium_conversion: '镇静转谵妄',
    glucose_variability: '血糖波动',
    hypoglycemia: '低血糖',
    glucose_drop_fast: '血糖快速下降',
    glucose_recheck_reminder: '血糖复查提醒',
    hyperglycemia_no_insulin: '高血糖未启胰岛素',
    abx_timeout: '抗生素time-out',
    abx_stop_recommendation: 'PCT停药评估',
    abx_tdm_reminder: '抗生素TDM提醒',
    abx_duration_exceeded: '抗生素疗程超限',
    vte_prophylaxis_omission: 'VTE预防遗漏',
    vte_bleeding_linkage: 'VTE出血风险联动',
    vte_immobility_no_prophylaxis: '制动无VTE预防',
    nutrition_start_delay: '营养启动延迟',
    nutrition_calorie_not_reached: '热卡未达标',
    nutrition_feeding_intolerance: '喂养不耐受',
    nutrition_refeeding_risk: '再喂养风险',
    multi_organ_deterioration_trend: '多器官恶化趋势',
    cvc_review: 'CVC评估',
    foley_review: '导尿管评估',
    ett_extubation_delay: '拔管延迟',
    liberation_bundle: 'ABCDEF Bundle',
    fluid_responsiveness: '容量反应性',
    crrt_filter_clotting: '滤器凝堵',
    crrt_citrate_ica: '枸橼酸iCa',
    crrt_heparin_act: '肝素ACT',
    crrt_dose_low: 'CRRT剂量不足',
    renal_dose_adjustment: '肾功能剂量调整',
    driving_pressure: '驱动压',
    pplat_high: '平台压',
    lung_protective_ventilation: '肺保护通气',
    mechanical_power: '机械功率',
    steroid_taper_after_vaso: '激素减停',
    steroid_long_term_taper: '长程激素减停',
    steroid_hyperglycemia: '激素相关高血糖',
  }
  return map[k] || k
}

function formatAlertValue(a: any) {
  if (!a) return '—'
  const t = String(a.alert_type || '')
  const p = String(a.parameter || '')
  const v = a.value
  const extra = a.extra || {}

  if (t === 'dic') {
    const score = extra?.score ?? v
    return score != null ? `DIC=${score}` : '—'
  }
  if (t === 'ards') {
    const pf = v ?? extra?.pf_ratio
    return pf != null ? `P/F=${Math.round(Number(pf))}` : '—'
  }
  if (t === 'aki') {
    return v != null ? `AKI=${v}期` : '—'
  }
  if (t === 'qsofa') {
    return v != null ? `qSOFA=${v}` : '—'
  }
  if (t === 'sofa' || t === 'septic_shock') {
    return v != null ? `SOFA=${v}` : '—'
  }
  if (t === 'nurse_reminder') {
    return '—'
  }

  if (t === 'fluid_balance') {
    const net = v ?? extra?.windows?.['24h']?.net_ml
    const pct = extra?.max_positive_pct_body_weight
    if (net != null && pct != null) return `Net=${net}mL(${pct}%)`
    if (net != null) return `Net=${net}mL`
    return '—'
  }

  if (t === 'delirium_risk') {
    return v != null ? `Delirium=${v}` : '—'
  }

  if (t === 'sedation_delirium_conversion') {
    const h = extra?.deep_sedation_hours
    return h != null ? `RASS<-3 ${h}h` : '—'
  }

  if (t === 'glucose_variability') {
    const cv = extra?.cv_percent ?? v
    return cv != null ? `CV=${cv}%` : '—'
  }

  if (t === 'hypoglycemia') {
    return v != null ? `Glu=${v}` : '—'
  }

  if (t === 'glucose_drop_fast') {
    const r = extra?.drop_rate_mmol_per_h ?? v
    return r != null ? `dGlu=${r}/h` : '—'
  }

  if (t === 'glucose_recheck_reminder') {
    const h = extra?.hours_since_last_check ?? v
    return h != null ? `Recheck ${h}h` : '—'
  }

  if (t === 'hyperglycemia_no_insulin') {
    const c = extra?.consecutive_high_count
    const lv = extra?.latest_glucose ?? v
    if (c != null && lv != null) return `${c}x>${extra?.high_threshold_mmol || 10},${lv}`
    return lv != null ? `Glu=${lv}` : '—'
  }

  if (t === 'abx_timeout') {
    const h = extra?.broad_duration_hours ?? v
    return h != null ? `Broad ${h}h` : '—'
  }

  if (t === 'abx_stop_recommendation') {
    const pct = extra?.pct_latest ?? v
    return pct != null ? `PCT=${pct}` : '—'
  }

  if (t === 'abx_tdm_reminder') {
    const g = extra?.drug_group || p
    return g ? `${g} TDM` : 'TDM'
  }

  if (t === 'abx_duration_exceeded') {
    const d = extra?.course_duration_days ?? v
    return d != null ? `${d}d no culture` : '—'
  }

  if (t === 'af_afl_new_onset') {
    const hr = extra?.hr_peak_in_segment ?? v
    return hr != null ? `AF/AFL HR${hr}` : 'AF/AFL'
  }

  if (t === 'brady_hypotension') {
    const hr = extra?.latest_hr ?? v
    const d = extra?.drop_sbp
    if (hr != null && d != null) return `HR${hr},SBP↓${d}`
    return hr != null ? `HR${hr}` : 'Brady+BP'
  }

  if (t === 'qtc_prolonged') {
    const qtc = extra?.qtc_ms ?? v
    return qtc != null ? `QTc${qtc}` : 'QTc high'
  }

  if (t === 'opioid_high_dose_resp_risk') {
    const med = extra?.opioid_med_24h_mg ?? v
    return med != null ? `MED=${med}mg` : 'High opioid'
  }

  if (t === 'opioid_respiratory_depression') {
    const rr = extra?.rr
    const spo2 = extra?.latest_spo2
    if (rr != null && spo2 != null) return `RR${rr}/SpO₂${spo2}`
    if (rr != null) return `RR${rr}`
    if (spo2 != null) return `SpO₂${spo2}`
    return 'Resp risk'
  }

  if (t === 'opioid_withdrawal_risk') {
    const h = extra?.since_last_opioid_hours ?? v
    return h != null ? `Stop ${h}h` : 'Withdrawal'
  }

  if (t === 'vte_prophylaxis_omission') {
    const score = extra?.padua_score ?? v
    return score != null ? `Padua=${score}` : '—'
  }

  if (t === 'vte_bleeding_linkage') {
    const score = extra?.padua_score ?? v
    return score != null ? `Padua=${score}, mech` : 'mech only'
  }

  if (t === 'vte_immobility_no_prophylaxis') {
    const h = extra?.immobility_hours ?? v
    return h != null ? `Bedrest ${h}h` : '—'
  }

  if (t === 'nutrition_start_delay') {
    const h = extra?.icu_stay_hours ?? v
    return h != null ? `ICU ${h}h no EN/PN` : 'No EN/PN'
  }

  if (t === 'nutrition_calorie_not_reached') {
    const pct = extra?.coverage_percent ?? v
    return pct != null ? `Calorie ${pct}%` : 'Calorie low'
  }

  if (t === 'nutrition_feeding_intolerance') {
    const grv = extra?.latest_grv_ml ?? v
    if (grv != null) return `GRV=${grv}mL`
    return 'Intolerance'
  }

  if (t === 'nutrition_refeeding_risk') {
    const items = extra?.triggered_electrolytes
    if (Array.isArray(items) && items.length > 0) return `Drop:${items.join('/')}`
    const pct = v
    return pct != null ? `Drop=${pct}%` : 'Refeeding risk'
  }

  if (t === 'multi_organ_deterioration_trend') {
    const modi = extra?.modi ?? v
    const n = extra?.organ_count
    if (modi != null && n != null) return `MODI=${modi}/${n}sys`
    if (modi != null) return `MODI=${modi}`
    return 'MODI trend'
  }

  if (t === 'lab_threshold') {
    const unit = extra?.unit || ''
    const labelMap: Record<string, string> = {
      k: 'K⁺',
      na: 'Na⁺',
      ica: 'iCa',
      ca: 'Ca',
      lac: 'Lac',
      glu: 'Glu',
      hb: 'Hb',
      plt: 'PLT',
      cr: 'Cr',
      pct: 'PCT',
      inr: 'INR',
      pt: 'PT',
      fib: 'Fib',
      ddimer: 'D-Dimer',
      trop: 'TnI/TnT',
      bnp: 'BNP',
      bil: 'TBil',
      pao2: 'PaO₂',
    }
    const label = labelMap[p] || extra?.raw_name || ''
    if (v == null) return '—'
    return label ? `${label}=${v}${unit}` : `${v}${unit}`
  }

  const unitMap: Record<string, string> = {
    param_HR: ' bpm',
    param_PR: ' bpm',
    param_resp: ' 次/分',
    param_spo2: ' %',
    param_T: ' ℃',
    param_nibp_s: ' mmHg',
    param_nibp_d: ' mmHg',
    param_nibp_m: ' mmHg',
    param_ibp_s: ' mmHg',
    param_ibp_d: ' mmHg',
    param_ibp_m: ' mmHg',
    param_cvp: ' cmH2O',
    param_ETCO2: ' mmHg',
    icp: ' mmHg',
    cpp: ' mmHg',
  }
  if (p && unitMap[p]) {
    return v != null ? `${v}${unitMap[p]}` : '—'
  }

  return v ?? '—'
}

const routeDeptCode = computed(() => String(route.query.dept_code || ''))
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
  const res = await getRecentAlerts(50, buildPatientParams())
  alerts.value = res.data.records || []
}

async function loadTrend() {
  const res = await getAlertStats('24h')
  trendSeries.value = res.data.series || []
}

async function loadBundle() {
  const res = await getBundleOverview(buildPatientParams())
  bundleCounts.value = res.data?.counts || { green: 0, yellow: 0, red: 0 }
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
}
</style>
