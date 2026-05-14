<template>
  <div class="mobile-page">
    <section class="mobile-filter">
      <input v-model.trim="keyword" placeholder="搜索床号 / 姓名 / 住院号" />
      <select v-model="risk">
        <option value="">全部风险</option>
        <option value="critical">危急</option>
        <option value="warning">高危</option>
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
            <span>{{ genderLabel(firstText(patient, ['sex', 'gender'], '--')) }}</span>
            <span>{{ ageLabel(firstText(patient, ['age'], '--')) }}</span>
            <span>{{ firstText(patient, ['risk_level', 'level'], '关注') }}</span>
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
import { getPatients, getRecentAlerts } from '../api'
import { useMobileShell } from '../composables/useMobileShell'
import { onAlertMessage } from '../services/alertSocket'
import { ageLabel, arrayFromResponse, bedOf, firstText, genderLabel, patientDiagnosisOf, patientIdOf, patientNameOf, patientRouteIdOf, toneOf } from './mobileData'
import { alertBelongsToMobileScope, alertMatchesPatient } from './mobileRealtime'

const router = useRouter()
const shell = useMobileShell()
const patients = ref<any[]>([])
const loading = ref(false)
const keyword = ref('')
const risk = ref('')
let offAlert: (() => void) | null = null

const filteredPatients = computed(() => {
  const key = keyword.value.toLowerCase()
  return patients.value.filter((patient) => {
    const hay = [bedOf(patient), patientNameOf(patient), patientIdOf(patient), firstText(patient, ['hisPid', 'admission_no'])].join(' ').toLowerCase()
    const tone = toneOf(patient)
    return (!key || hay.includes(key)) && (!risk.value || tone === risk.value)
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
  return rows.map((patient) => {
    const match = alerts.find((alert) => alertMatchesPatient(alert, patient))
    if (!match) return patient
    const level = firstText(match, ['severity', 'level'], patient.alertLevel || patient.risk_level || 'warning')
    return { ...patient, latest_alert: match, alertLevel: level, risk_level: level }
  })
}

async function loadPatients() {
  loading.value = true
  try {
    const scope = params()
    const [patientRes, alertRes] = await Promise.allSettled([
      getPatients({ ...scope, patient_scope: 'in_dept' }),
      getRecentAlerts(120, { ...scope, fast: true, pending: true }),
    ])
    let rows = patients.value
    if (patientRes.status === 'fulfilled' && patientRes.value?.data) {
      rows = arrayFromResponse(patientRes.value.data, ['patients'])
    }
    if (alertRes.status === 'fulfilled' && alertRes.value?.data) {
      rows = mergePatientAlerts(rows, arrayFromResponse(alertRes.value.data, ['records', 'alerts']))
    }
    patients.value = rows
  } finally {
    loading.value = false
  }
}

function openPatient(patient: any) {
  const id = patientRouteIdOf(patient)
  if (!id) return
  sessionStorage.setItem(`mobile_patient:${id}`, JSON.stringify(patient))
  router.push({ path: `/m/patient/${id}`, query: shell.identityQuery() })
}

function refreshFromShell() {
  void loadPatients()
}

function applyRealtimeAlert(message: any) {
  if (message?.type !== 'alert' || !message.data) return
  if (!alertBelongsToMobileScope(message.data, shell.deptCode.value, shell.deptLabel.value)) return
  const alert = message.data
  patients.value = patients.value.map((patient) => {
    if (!alertMatchesPatient(alert, patient)) return patient
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

