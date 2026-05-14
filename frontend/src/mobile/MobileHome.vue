<template>
  <div class="mobile-page">
    <section class="mobile-hero">
      <span>{{ roleLabel }}工作台</span>
      <h1>{{ shell.deptLabel.value }}</h1>
      <p>床旁查看、告警处置、任务闭环</p>
    </section>

    <section class="mobile-grid two">
      <button class="mobile-stat" type="button" @click="go('/m/patients')">
        <span>在科患者</span>
        <strong>{{ patientCount }}</strong>
      </button>
      <button class="mobile-stat tone-warning" type="button" @click="go('/m/alerts')">
        <span>待看告警</span>
        <strong>{{ alertCountText }}</strong>
      </button>
    </section>

    <section class="mobile-card">
      <div class="mobile-section-head">
        <h2>今日重点</h2>
        <button type="button" @click="manualRefresh">刷新</button>
      </div>
      <article v-for="item in focusItems" :key="item.id" class="mobile-list-row" @click="openPatient(item.patientId)">
        <i :class="`tone-${item.tone}`"></i>
        <div>
          <strong>{{ item.title }}</strong>
          <p>{{ item.desc }}</p>
        </div>
        <span>{{ item.meta }}</span>
      </article>
      <div v-if="loading && !focusItems.length" class="mobile-skeleton-list"><i></i><i></i><i></i></div>
      <div v-else-if="!focusItems.length" class="mobile-empty">暂无重点事项</div>
    </section>

    <section class="mobile-card">
      <div class="mobile-section-head"><h2>快速入口</h2></div>
      <div class="mobile-action-grid">
        <button type="button" @click="go('/m/patients')">患者</button>
        <button type="button" @click="go('/m/alerts')">告警</button>
        <button type="button" @click="go('/m/tasks')">任务</button>
        <button type="button" @click="go('/m/consult')">AI问诊</button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getClinicalRoleHome, getDoctorHome, getMobileHomeLite, getNurseHome, getPatientPriority } from '../api'
import { useMobileShell } from '../composables/useMobileShell'
import { onAlertMessage } from '../services/alertSocket'
import { mobileAlertCacheKey, mobileScopeKey, readMobileCache, writeMobileCache } from './mobileCache'
import { alertSummaryOf, alertTitleOf, arrayFromResponse, bedOf, firstText, labelText, patientIdOf, patientNameOf, patientRouteIdOf, toneOf } from './mobileData'
import { alertBelongsToMobileScope, mergeMobileAlert } from './mobileRealtime'

const router = useRouter()
const shell = useMobileShell()
const loading = ref(false)
const patients = ref<any[]>([])
const patientTotal = ref<number | null>(null)
const priorityPatients = ref<any[]>([])
const alerts = ref<any[]>([])
const alertsLoaded = ref(false)
let offAlert: (() => void) | null = null

const roleLabelMap: Record<string, string> = {
  doctor: '医生',
  nurse: '护士',
  head_nurse: '护士长',
  director: '主任',
  respiratory: '呼吸治疗',
  nutrition: '营养支持',
  admin: '管理',
  unknown: '临床',
}
const roleLabel = computed(() => roleLabelMap[shell.role.value] || '临床')
const patientCount = computed(() => patientTotal.value ?? (patients.value.length ? patients.value.length : '...'))
const alertCountText = computed(() => (alertsLoaded.value ? String(alerts.value.length) : '...'))
const scopeKey = computed(() => mobileScopeKey(shell.deptCode.value, shell.deptLabel.value))
const alertsCacheKey = computed(() => mobileAlertCacheKey(scopeKey.value))
const patientsCacheKey = computed(() => `mobile_home_patients:${scopeKey.value}`)

const focusItems = computed(() => {
  const rows: Array<{ id: string; patientId: string; title: string; desc: string; meta: string; tone: string }> = []
  for (const alert of alerts.value.slice(0, 4)) {
    rows.push({
      id: `a-${firstText(alert, ['alert_id', '_id', 'id'], Math.random().toString(36))}`,
      patientId: firstText(alert, ['patient_id', 'patientId']),
      title: alertTitleOf(alert),
      desc: alertSummaryOf(alert) || `${patientNameOf(alert)} ${bedOf(alert)}`,
      meta: bedOf(alert),
      tone: toneOf(alert),
    })
  }
  for (const patient of priorityPatients.value.slice(0, 4)) {
    rows.push({
      id: `p-${patientIdOf(patient)}`,
      patientId: patientRouteIdOf(patient),
      title: `${bedOf(patient)} ${patientNameOf(patient)}`,
      desc: firstText(patient, ['reason', 'summary', 'diagnosis'], '重点关注患者'),
      meta: labelText(firstText(patient, ['risk_level', 'level'], '关注')),
      tone: toneOf(patient),
    })
  }
  return rows.slice(0, 6)
})

function params() {
  const value: Record<string, any> = {}
  if (shell.deptCode.value) value.dept_code = shell.deptCode.value
  else if (shell.deptLabel.value && shell.deptLabel.value !== '全院') value.dept = shell.deptLabel.value
  return value
}

async function loadAll(options: { showLoading?: boolean } = {}) {
  if (options.showLoading) loading.value = true
  const user = shell.actor.value
  const scope = params()
  restoreCachedPatients()
  restoreCachedAlerts()
  await loadHomeLite(scope)
  void loadPriorityInBackground(scope, user)
  loading.value = false
}

async function loadPriorityInBackground(scope = params(), user = shell.actor.value) {
  try {
    const requests: Array<Promise<any>> = [
      getPatientPriority({ ...scope, limit: 20 }),
      getClinicalRoleHome({ userName: user, role: shell.role.value, ...scope }),
    ]
    if (shell.role.value === 'doctor' || shell.role.value === 'director') requests.push(getDoctorHome({ user_id: user, ...scope }))
    if (shell.role.value === 'nurse' || shell.role.value === 'head_nurse') requests.push(getNurseHome({ user_id: user, ...scope }))
    const [priorityRes] = await Promise.allSettled(requests)
    if (priorityRes?.status === 'fulfilled') priorityPatients.value = arrayFromResponse(priorityRes.value.data, ['patients', 'priority', 'data'])
  } catch {
    // Role-specific summaries are secondary; keep the home page responsive.
  }
}

function restoreCachedPatients() {
  const rows = readMobileCache<any[]>(patientsCacheKey.value, [])
  if (Array.isArray(rows) && rows.length && !patients.value.length) patients.value = rows
}

async function loadPatientsFast(scope = params()) {
  try {
    const patientRes = await getMobileHomeLite({ ...scope, actor: shell.actor.value, userName: shell.actor.value })
    if (patientRes?.data) {
      const rows = arrayFromResponse(patientRes.data, ['patients_preview', 'patients'])
      if (rows.length || !patients.value.length) {
        patients.value = rows
        if (rows.length) writeMobileCache(patientsCacheKey.value, rows.slice(0, 80))
      }
      const count = Number(patientRes.data.patient_count ?? patientRes.data.count)
      if (Number.isFinite(count)) patientTotal.value = count
    }
  } catch {
    // Keep the last valid cached count; never clear to 0 on request failure.
  }
}

async function loadHomeLite(scope = params()) {
  const fallbackTimer = window.setTimeout(() => {
    alertsLoaded.value = true
  }, 1000)
  try {
    const res = await getMobileHomeLite({ ...scope, actor: shell.actor.value, userName: shell.actor.value })
    const rows = arrayFromResponse(res.data, ['patients_preview', 'patients'])
    const count = Number(res.data?.patient_count ?? res.data?.count)
    if (rows.length || !patients.value.length) patients.value = rows
    if (Number.isFinite(count)) patientTotal.value = count
    if (rows.length) writeMobileCache(patientsCacheKey.value, rows.slice(0, 80))
    syncResolvedDepartment(res.data)
    const nextAlerts = arrayFromResponse(res.data, ['alerts', 'records'])
    alerts.value = nextAlerts
    alertsLoaded.value = true
    writeMobileCache(alertsCacheKey.value, nextAlerts.slice(0, 80))
  } catch {
    void loadPatientsFast(scope)
  } finally {
    window.clearTimeout(fallbackTimer)
    alertsLoaded.value = true
  }
}

function syncResolvedDepartment(data: any) {
  const code = firstText(data, ['dept_code', 'deptCode'])
  const dept = firstText(data, ['dept'])
  if (!code && !dept) return
  if (code === shell.deptCode.value && (!dept || dept === shell.deptLabel.value)) return
  shell.setDepartment({ deptCode: code || shell.deptCode.value, dept: dept || shell.deptLabel.value })
}

function restoreCachedAlerts() {
  const rows = readMobileCache<any[]>(alertsCacheKey.value, [])
  if (Array.isArray(rows) && rows.length && !alerts.value.length) alerts.value = rows
  alertsLoaded.value = true
}

function manualRefresh() {
  void loadAll({ showLoading: true })
}

function go(path: string) {
  router.push({ path, query: shell.identityQuery() })
}

function openPatient(id: string) {
  if (!id) return
  router.push({ path: `/m/patient/${id}`, query: shell.identityQuery() })
}

function refreshFromShell() {
  void loadAll({ showLoading: true })
}

function applyRealtimeAlert(message: any) {
  if (message?.type !== 'alert' || !message.data) return
  if (!alertBelongsToMobileScope(message.data, shell.deptCode.value, shell.deptLabel.value)) return
  alerts.value = mergeMobileAlert(alerts.value, message.data, 80)
  alertsLoaded.value = true
  writeMobileCache(alertsCacheKey.value, alerts.value.slice(0, 80))
}

watch(() => [shell.deptCode.value, shell.deptLabel.value], () => {
  patients.value = []
  patientTotal.value = null
  priorityPatients.value = []
  alerts.value = []
  alertsLoaded.value = false
  void loadAll({ showLoading: true })
})

onMounted(() => {
  void shell.resolveIdentity().finally(() => loadAll({ showLoading: true }))
  offAlert = onAlertMessage(applyRealtimeAlert)
  window.addEventListener('mobile:refresh', refreshFromShell)
})

onUnmounted(() => {
  offAlert?.()
  window.removeEventListener('mobile:refresh', refreshFromShell)
})
</script>
