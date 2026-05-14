<template>
  <div class="mobile-page">
    <section class="mobile-hero compact">
      <span>{{ bedOf(patient) }}</span>
      <h1>{{ patientNameOf(patient) }}</h1>
      <p>{{ patientDiagnosisOf(patient, '患者移动详情') }}</p>
    </section>

    <div class="mobile-segment">
      <button v-for="item in tabs" :key="item.key" type="button" :class="{ active: tab === item.key }" @click="tab = item.key">
        {{ item.label }}
      </button>
    </div>

    <section v-if="tab === 'overview'" class="mobile-card">
      <div class="mobile-section-head"><h2>概览</h2><button type="button" @click="loadAll">刷新</button></div>
      <div class="mobile-grid two">
        <div class="mobile-stat"><span>年龄</span><strong>{{ ageLabel(firstText(patient, ['age'], '--')) }}</strong></div>
        <div class="mobile-stat"><span>风险</span><strong>{{ labelText(firstText(patient, ['risk_level', 'level'], '关注')) }}</strong></div>
      </div>
      <div class="mobile-info-list readonly">
        <p><b>科室</b><span>{{ firstText(patient, ['hisDept', 'deptName', 'dept', 'department'], '--') }}</span></p>
        <p><b>性别</b><span>{{ genderLabel(firstText(patient, ['hisSex', 'sex', 'gender'], '--')) }}</span></p>
        <p><b>住院号</b><span>{{ firstText(patient, ['hisPid', 'admission_no', 'patient_id'], '--') }}</span></p>
        <p><b>最新摘要</b><span>{{ patientDiagnosisOf(patient, '暂无') }}</span></p>
      </div>
    </section>

    <section v-if="tab === 'alerts'" class="mobile-card">
      <div class="mobile-section-head"><h2>告警</h2><button type="button" @click="loadAlerts">刷新</button></div>
      <article v-for="alert in alerts" :key="alertIdOf(alert)" class="mobile-list-row" @click="selectedAlert = alert">
        <i :class="`tone-${toneOf(alert)}`"></i>
        <div>
          <strong>{{ alertTitleOf(alert) }}</strong>
          <p>{{ alertSummaryOf(alert) }}</p>
          <div class="mobile-chip-row"><span>{{ levelLabel(alert) }}</span></div>
        </div>
        <span>{{ formatTime(firstText(alert, ['created_at', 'time', 'timestamp'])) }}</span>
      </article>
      <div v-if="!alerts.length" class="mobile-empty">暂无告警</div>
    </section>

    <section v-if="tab === 'trend'" class="mobile-card">
      <div class="mobile-section-head"><h2>24h趋势</h2><button type="button" @click="loadTrend">刷新</button></div>
      <div class="mobile-vital-grid">
        <div v-for="metric in vitalMetrics" :key="metric.key" class="mobile-vital">
          <span>{{ metric.label }}</span>
          <strong>{{ metric.value }}</strong>
        </div>
      </div>
    </section>

    <section v-if="tab === 'handoff'" class="mobile-card">
      <div class="mobile-section-head"><h2>交班/查房</h2><button type="button" @click="loadHandoff">刷新</button></div>
      <div class="mobile-note">{{ handoffText || '暂无交班摘要' }}</div>
    </section>

    <section v-if="tab === 'orders'" class="mobile-card">
      <div class="mobile-section-head"><h2>检验与用药</h2><button type="button" @click="loadOrders">刷新</button></div>
      <h3 class="mobile-subtitle">异常检验</h3>
      <article v-for="lab in labs.slice(0, 8)" :key="JSON.stringify(lab)" class="mobile-mini-row">
        <strong>{{ firstText(lab, ['itemName', 'itemCnName', 'item_name', 'name', 'label'], '检验') }}</strong>
        <span>{{ firstText(lab, ['result', 'resultValue', 'value'], '--') }} {{ firstText(lab, ['unit', 'resultUnit'], '') }}</span>
      </article>
      <div v-if="!labs.length" class="mobile-empty">暂无检验记录</div>
      <h3 class="mobile-subtitle">用药</h3>
      <article v-for="drug in drugs.slice(0, 8)" :key="JSON.stringify(drug)" class="mobile-mini-row">
        <strong>{{ firstText(drug, ['drugName', 'drug_name', 'name', 'orderName', 'order_name'], '用药') }}</strong>
        <span>{{ firstText(drug, ['dose', 'drugSpec'], '') }} {{ firstText(drug, ['frequency', 'route', 'status'], '') }}</span>
      </article>
      <div v-if="!drugs.length" class="mobile-empty">暂无用药记录</div>
    </section>

    <div v-if="selectedAlert" class="mobile-drawer-mask" @click.self="selectedAlert = null">
      <section class="mobile-drawer">
        <h2>{{ alertTitleOf(selectedAlert) }}</h2>
        <p>{{ alertSummaryOf(selectedAlert) }}</p>
        <textarea v-model="actionNote" placeholder="处置备注，可选"></textarea>
        <div class="mobile-action-grid">
          <button type="button" @click="ackSelected('acknowledged')">确认</button>
          <button type="button" @click="ackSelected('handoff_doctor')">转医生</button>
          <button type="button" @click="ackSelected('handoff_nurse')">转护士</button>
          <button type="button" @click="disposeSelected('review_later')">稍后复评</button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getClinicalPatientHandoff, getPatientAlerts, getPatientDetail, getPatientDrugs, getPatientLabs, getPatientVitalsTrend, postAlertAcknowledge, postAlertDisposition, postPatientAlertsViewed } from '../api'
import { useMobileShell } from '../composables/useMobileShell'
import { onAlertMessage } from '../services/alertSocket'
import { MOBILE_ACTION_SOURCE } from './types'
import { ageLabel, alertIdOf, alertSummaryOf, alertTitleOf, arrayFromResponse, bedOf, firstText, formatTime, genderLabel, labelText, levelLabel, patientDiagnosisOf, patientNameOf, toneOf } from './mobileData'
import { alertMatchesPatient, mergeMobileAlert } from './mobileRealtime'

const route = useRoute()
const shell = useMobileShell()
const patient = ref<any>({})
const alerts = ref<any[]>([])
const trend = ref<any>({})
const labs = ref<any[]>([])
const drugs = ref<any[]>([])
const handoffText = ref('')
const selectedAlert = ref<any | null>(null)
const actionNote = ref('')
const tab = ref('overview')
let offAlert: (() => void) | null = null
const tabs = [
  { key: 'overview', label: '概览' },
  { key: 'alerts', label: '告警' },
  { key: 'trend', label: '趋势' },
  { key: 'handoff', label: '交班' },
  { key: 'orders', label: '医嘱' },
]
const patientId = computed(() => String(route.params.id || ''))
const latestTrendPoint = computed(() => {
  const rows = arrayFromResponse(trend.value, ['points', 'series', 'vitals'])
  return rows[rows.length - 1] || trend.value || {}
})
const vitalMetrics = computed(() => [
  { key: 'hr', label: 'HR', value: firstText(latestTrendPoint.value, ['hr', 'HR'], '--') },
  { key: 'map', label: 'MAP', value: firstText(latestTrendPoint.value, ['ibp_map', 'nibp_map', 'map', 'MAP'], '--') },
  { key: 'spo2', label: 'SpO2', value: firstText(latestTrendPoint.value, ['spo2', 'SpO2'], '--') },
  { key: 'rr', label: 'RR', value: firstText(latestTrendPoint.value, ['rr', 'RR'], '--') },
])

function readableText(value: any): string {
  if (value == null) return ''
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value).trim()
  if (Array.isArray(value)) return value.map(readableText).filter(Boolean).join('\n')
  if (typeof value === 'object') {
    for (const key of ['summary', 'handoff', 'content', 'markdown', 'text', 'narrative', 'brief', 'note']) {
      const text = readableText(value[key])
      if (text) return text
    }
    const rows = Object.entries(value)
      .filter(([, item]) => item != null && typeof item !== 'function')
      .map(([key, item]) => {
        const text = readableText(item)
        return text ? `${key}: ${text}` : ''
      })
      .filter(Boolean)
    return rows.join('\n')
  }
  return ''
}

async function loadPatient() {
  try {
    const cached = sessionStorage.getItem(`mobile_patient:${patientId.value}`)
    if (cached && !Object.keys(patient.value || {}).length) patient.value = JSON.parse(cached)
  } catch {
    // Ignore malformed cache.
  }
  const res = await getPatientDetail(patientId.value)
  patient.value = { ...(patient.value || {}), ...(res.data?.patient || res.data || {}) }
}
async function loadAlerts() {
  const res = await getPatientAlerts(patientId.value)
  alerts.value = arrayFromResponse(res.data, ['alerts', 'records'])
  const ids = alerts.value.map(alertIdOf).filter(Boolean)
  if (ids.length) void postPatientAlertsViewed(patientId.value, { alert_ids: ids, actor: shell.actor.value, source: MOBILE_ACTION_SOURCE })
}
async function loadTrend() {
  const res = await getPatientVitalsTrend(patientId.value, '24h')
  trend.value = res.data || {}
}
async function loadOrders() {
  const [labRes, drugRes] = await Promise.allSettled([getPatientLabs(patientId.value), getPatientDrugs(patientId.value)])
  if (labRes.status === 'fulfilled') labs.value = normalizeLabs(labRes.value.data)
  if (drugRes.status === 'fulfilled') drugs.value = arrayFromResponse(drugRes.value.data, ['records', 'drugs', 'orders'])
}
async function loadHandoff() {
  const res = await getClinicalPatientHandoff(patientId.value, { role: shell.role.value, hours: 24 })
  handoffText.value = readableText(res.data)
}
async function loadAll() {
  try {
    const cached = sessionStorage.getItem(`mobile_patient:${patientId.value}`)
    if (cached) patient.value = JSON.parse(cached)
  } catch {
    // Ignore malformed cache.
  }
  await Promise.allSettled([loadPatient(), loadAlerts(), loadTrend(), loadOrders(), loadHandoff()])
}

function normalizeLabs(data: any) {
  const rows = arrayFromResponse(data, ['labs', 'items', 'records'])
  if (rows.length) return rows
  const exams = arrayFromResponse(data, ['exams'])
  return exams.flatMap((exam: any) => {
    const items = arrayFromResponse(exam, ['items'])
    return items.map((item: any) => ({
      ...item,
      examName: firstText(exam, ['examName', 'name'], ''),
      requestTime: firstText(exam, ['requestTime', 'time'], ''),
    }))
  })
}
async function ackSelected(disposition: string) {
  if (!selectedAlert.value) return
  const id = alertIdOf(selectedAlert.value)
  if (!id) return
  await postAlertAcknowledge(id, { actor: shell.actor.value, note: actionNote.value, disposition, override_reason_text: actionNote.value, source: MOBILE_ACTION_SOURCE } as any)
  selectedAlert.value = null
  actionNote.value = ''
  await loadAlerts()
}
async function disposeSelected(action: string) {
  if (!selectedAlert.value) return
  const id = alertIdOf(selectedAlert.value)
  if (!id) return
  await postAlertDisposition(id, { action, reason: actionNote.value, actor: shell.actor.value, review_after_minutes: 60, source: MOBILE_ACTION_SOURCE } as any)
  selectedAlert.value = null
  actionNote.value = ''
  await loadAlerts()
}

function applyRealtimeAlert(message: any) {
  if (message?.type !== 'alert' || !message.data) return
  const alertPatientId = firstText(message.data, ['patient_id', 'patientId'])
  if (alertPatientId !== patientId.value && !alertMatchesPatient(message.data, patient.value)) return
  alerts.value = mergeMobileAlert(alerts.value, message.data, 60)
}

watch(patientId, loadAll)
onMounted(() => {
  void loadAll()
  offAlert = onAlertMessage(applyRealtimeAlert)
})

onUnmounted(() => {
  offAlert?.()
})
</script>
