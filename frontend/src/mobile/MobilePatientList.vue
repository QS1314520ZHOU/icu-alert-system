<template>
  <div class="mobile-page">
    <section class="mobile-filter">
      <input v-model.trim="keyword" placeholder="搜索床号 / 姓名 / 住院号" />
      <select v-model="risk">
        <option value="">全部风险</option>
        <option value="critical">危急</option>
        <option value="warning">高危</option>
        <option value="watch">关注</option>
        <option value="stable">平稳</option>
      </select>
    </section>

    <section class="mobile-card">
      <div class="mobile-section-head">
        <h2>患者列表</h2>
        <button type="button" @click="loadPatients">刷新</button>
      </div>
      <div v-if="loading && !patients.length" class="mobile-skeleton-list">
        <i></i><i></i><i></i><i></i>
      </div>
      <article v-for="patient in filteredPatients" :key="patientIdOf(patient)" class="mobile-patient-card" @click="openPatient(patient)">
        <div :class="['mobile-bed', `tone-${toneOf(patient)}`]">{{ bedOf(patient) }}</div>
        <div>
          <strong>{{ patientNameOf(patient) }}</strong>
          <p>{{ patientDiagnosisOf(patient) }}</p>
          <div class="mobile-chip-row">
            <span v-if="visibleText(genderLabel(firstText(patient, ['sex', 'gender'])))">{{ genderLabel(firstText(patient, ['sex', 'gender'])) }}</span>
            <span v-if="visibleText(ageLabel(firstText(patient, ['age'])))">{{ ageLabel(firstText(patient, ['age'])) }}</span>
            <span :class="`chip-${toneOf(patient)}`">{{ levelLabel(patient) }}</span>
          </div>
          <div :class="['mobile-patient-alert', `tone-${toneOf(patient)}`, { 'is-risk-only': !patient.latest_alert }]">
            <b>{{ levelLabel(patient.latest_alert || patient) }}</b>
            <span>{{ patientAlertText(patient) }}</span>
          </div>
        </div>
      </article>
      <div v-if="!loading && !filteredPatients.length" class="mobile-empty">暂无匹配患者</div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getMobilePatients, getRecentAlerts } from '../api'
import { useMobileShell } from '../composables/useMobileShell'
import { onAlertMessage } from '../services/alertSocket'
import { ageLabel, alertTitleOf, arrayFromResponse, bedOf, firstText, genderLabel, levelLabel, patientDiagnosisOf, patientIdOf, patientNameOf, patientRouteIdOf, toneOf } from './mobileData'
import { alertBelongsToMobileScope, alertMatchesPatient } from './mobileRealtime'
import { mobileScopeKey, readMobileCache, writeMobileCache } from './mobileCache'

const router = useRouter()
const shell = useMobileShell()
const patients = ref<any[]>([])
const loading = ref(false)
const keyword = ref('')
const risk = ref('')
let offAlert: (() => void) | null = null

const cacheKey = computed(() => `mobile_patients:${mobileScopeKey(shell.deptCode.value, shell.deptLabel.value)}`)

const filteredPatients = computed(() => {
  const key = keyword.value.toLowerCase()
  return patients.value.filter((patient) => {
    const hay = [bedOf(patient), patientNameOf(patient), patientIdOf(patient), firstText(patient, ['hisPid', 'admission_no'])].join(' ').toLowerCase()
    const tone = toneOf(patient)
    return (!key || hay.includes(key)) && (!risk.value || riskMatches(tone, risk.value))
  })
})

function params() {
  const value: Record<string, any> = {}
  if (shell.deptCode.value) value.dept_code = shell.deptCode.value
  else if (shell.deptLabel.value && shell.deptLabel.value !== '全院') value.dept = shell.deptLabel.value
  return value
}

function mergePatientAlerts(rows: any[], alerts: any[]) {
  if (!alerts.length) return rows
  const alertIndex = buildAlertIndex(alerts)
  return rows.map((patient) => {
    const match = findPatientAlert(patient, alertIndex)
    if (!match) return patient
    const level = firstText(match, ['severity', 'level'], patient.alertLevel || patient.risk_level || 'warning')
    return { ...patient, latest_alert: match, alertLevel: level, risk_level: level }
  })
}

function norm(value: any) {
  return String(value ?? '').trim().toLowerCase()
}

function patientKeys(patient: any) {
  return [
    patientIdOf(patient),
    firstText(patient, ['_id', 'id']),
    firstText(patient, ['patient_id', 'patientId']),
    firstText(patient, ['hisPid']),
    firstText(patient, ['hisBed', 'bed', 'bed_no', 'bedNo']),
  ].map(norm).filter(Boolean)
}

function buildAlertIndex(alerts: any[]) {
  const index = new Map<string, any>()
  for (const alert of alerts) {
    const keys = [
      firstText(alert, ['patient_id', 'patientId']),
      firstText(alert, ['hisPid']),
      firstText(alert, ['bed', 'hisBed', 'bed_no', 'bedNo']),
    ].map(norm).filter(Boolean)
    for (const key of keys) if (!index.has(key)) index.set(key, alert)
  }
  return index
}

function findPatientAlert(patient: any, index: Map<string, any>) {
  for (const key of patientKeys(patient)) {
    const hit = index.get(key)
    if (hit) return hit
  }
  return null
}

function riskMatches(tone: string, selected: string) {
  if (selected === 'warning') return tone === 'warning' || tone === 'critical'
  if (selected === 'watch') return tone === 'watch'
  return tone === selected
}

async function loadPatients() {
  loading.value = true
  try {
    const scope = params()
    const cached = readMobileCache<any[]>(cacheKey.value, [])
    if (cached.length && !patients.value.length) {
      patients.value = cached
      loading.value = false
    }
    const patientRes = await getMobilePatients({ ...scope, patient_scope: 'in_dept' })
    const rows = arrayFromResponse(patientRes.data, ['patients']).map(ensurePatientRisk)
    if (rows.length || !patients.value.length) {
      patients.value = rows
      if (rows.length) writeMobileCache(cacheKey.value, rows.slice(0, 300))
    }
    loading.value = false
    void loadPatientAlerts(scope)
  } finally {
    loading.value = false
  }
}

function ensurePatientRisk(patient: any) {
  const latest = patient.latest_alert
  const level = latest
    ? firstText(latest, ['severity', 'level'], patient.alertLevel || patient.risk_level || 'warning')
    : firstText(patient, ['alertLevel', 'risk_level', 'level', 'severity'], 'watch')
  return { ...patient, alertLevel: level, risk_level: level }
}

function patientAlertText(patient: any) {
  if (patient.latest_alert) return alertTitleOf(patient.latest_alert)
  const tone = toneOf(patient)
  if (tone === 'critical') return '存在危急风险，请优先查看'
  if (tone === 'warning') return '存在高危风险，请持续关注'
  if (tone === 'stable') return '当前风险平稳'
  return '暂无未处理告警'
}

async function loadPatientAlerts(scope = params()) {
  try {
    const alertRes = await getRecentAlerts(120, { ...scope, fast: true, pending: true })
    if (alertRes?.data) {
      patients.value = mergePatientAlerts(patients.value, arrayFromResponse(alertRes.data, ['records', 'alerts']))
      writeMobileCache(cacheKey.value, patients.value.slice(0, 300))
    }
  } catch {
    // Patients should stay visible even when alerts are slow.
  }
}

function openPatient(patient: any) {
  const id = patientRouteIdOf(patient)
  if (!id) return
  sessionStorage.setItem(`mobile_patient:${id}`, JSON.stringify(patient))
  router.push({ path: `/m/patient/${id}`, query: shell.identityQuery() })
}

function visibleText(value: any) {
  const text = String(value ?? '').trim()
  return Boolean(text && text !== '--')
}

function refreshFromShell() {
  void loadPatients()
}

function applyRealtimeAlert(message: any) {
  if (message?.type !== 'alert' || !message.data) return
  if (!alertBelongsToMobileScope(message.data, shell.deptCode.value, shell.deptLabel.value)) return
  const alert = message.data
  const index = buildAlertIndex([alert])
  patients.value = patients.value.map((patient) => {
    if (!findPatientAlert(patient, index) && !alertMatchesPatient(alert, patient)) return patient
    return {
      ...patient,
      latest_alert: alert,
      alertLevel: firstText(alert, ['severity', 'level'], patient.alertLevel || patient.risk_level || 'warning'),
      risk_level: firstText(alert, ['severity', 'level'], patient.risk_level || 'warning'),
    }
  })
}

watch(() => [shell.deptCode.value, shell.deptLabel.value], () => {
  patients.value = []
  void loadPatients()
})

onMounted(() => {
  void shell.resolveIdentity().finally(() => loadPatients())
  offAlert = onAlertMessage(applyRealtimeAlert)
  window.addEventListener('mobile:refresh', refreshFromShell)
})

onUnmounted(() => {
  offAlert?.()
  window.removeEventListener('mobile:refresh', refreshFromShell)
})
</script>

