<template>
  <div class="mobile-page">
    <section class="mobile-hero">
      <span>{{ roleLabel }}工作台</span>
      <h1>{{ greeting }}</h1>
      <p>{{ summaryText }}</p>
    </section>

    <section class="mobile-grid two">
      <button class="mobile-stat" type="button" @click="go('/m/patients')">
        <span>重点患者</span>
        <strong>{{ priorityPatients.length || patientCount }}</strong>
      </button>
      <button class="mobile-stat tone-warning" type="button" @click="go('/m/alerts')">
        <span>待看告警</span>
        <strong :class="{ pending: !alertsLoaded }">{{ alertCountText }}</strong>
      </button>
    </section>

    <section class="mobile-card">
      <div class="mobile-section-head">
        <h2>今日重点</h2>
        <button type="button" @click="loadAll">刷新</button>
      </div>
      <template>
        <article v-for="item in focusItems" :key="item.id" class="mobile-list-row" @click="openPatient(item.patientId)">
          <i :class="`tone-${item.tone}`"></i>
          <div>
            <strong>{{ item.title }}</strong>
            <p>{{ item.desc }}</p>
          </div>
          <span>{{ item.meta }}</span>
        </article>
        <div v-if="loading && !focusItems.length" class="mobile-skeleton-list">
          <i></i><i></i><i></i>
        </div>
        <div v-else-if="!focusItems.length" class="mobile-empty">暂无重点事项</div>
      </template>
    </section>

    <section class="mobile-card">
      <div class="mobile-section-head">
        <h2>快速入口</h2>
      </div>
      <div class="mobile-action-grid">
        <button type="button" @click="go('/m/patients')">患者总览</button>
        <button type="button" @click="go('/m/alerts')">告警处置</button>
        <button type="button" @click="go('/m/tasks')">任务闭环</button>
        <button type="button" @click="go('/m/consult')">AI问诊</button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getClinicalRoleHome, getDoctorHome, getNurseHome, getPatientPriority, getPatients, getRecentAlerts } from '../api'
import { useMobileShell } from '../composables/useMobileShell'
import { onAlertMessage } from '../services/alertSocket'
import { mobileAlertCacheKey, mobileScopeKey, readMobileCache, writeMobileCache } from './mobileCache'
import { alertSummaryOf, alertTitleOf, arrayFromResponse, bedOf, firstText, labelText, patientIdOf, patientNameOf, patientRouteIdOf, toneOf } from './mobileData'
import { alertBelongsToMobileScope, mergeMobileAlert } from './mobileRealtime'

const router = useRouter()
const shell = useMobileShell()
const loading = ref(false)
const roleHome = ref<any>({})
const patients = ref<any[]>([])
const priorityPatients = ref<any[]>([])
const alerts = ref<any[]>([])
const alertsLoaded = ref(false)
const pendingAlertTotal = ref<number | null>(null)
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
const greeting = computed(() => `${roleLabel.value}移动工作台`)
const patientCount = computed(() => patients.value.length)
const summaryText = computed(() => shell.deptLabel.value)
const alertCountText = computed(() => {
  if (!alertsLoaded.value) return '加载中'
  return String(pendingAlertTotal.value ?? alerts.value.length)
})
const alertsCacheKey = computed(() => mobileAlertCacheKey(mobileScopeKey(shell.deptCode.value, shell.deptLabel.value)))

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

async function loadAll() {
  loading.value = true
  try {
    const user = shell.actor.value
    const scope = params()
    restoreCachedAlerts()
    void loadAlertsFast(scope)
    const patientRes = await Promise.race([
      getPatients({ ...scope, patient_scope: 'in_dept' }),
      new Promise<any>((resolve) => setTimeout(() => resolve(null), 1500)),
    ])
    if (patientRes?.data) patients.value = arrayFromResponse(patientRes.data, ['patients'])
    loading.value = false

    const requests: Array<Promise<any>> = [
      getPatientPriority({ ...scope, limit: 20 }),
      getClinicalRoleHome({ userName: user, role: shell.role.value, ...scope }),
    ]
    if (shell.role.value === 'doctor' || shell.role.value === 'director') requests.push(getDoctorHome({ user_id: user, ...scope }))
    if (shell.role.value === 'nurse' || shell.role.value === 'head_nurse') requests.push(getNurseHome({ user_id: user, ...scope }))
    const [priorityRes, roleRes] = await Promise.allSettled(requests)
    if (priorityRes?.status === 'fulfilled') priorityPatients.value = arrayFromResponse(priorityRes.value.data, ['patients', 'priority', 'data'])
    if (roleRes?.status === 'fulfilled') roleHome.value = roleRes.value.data || {}
  } finally {
    loading.value = false
  }
}

function restoreCachedAlerts() {
      const rows = readMobileCache<any[]>(alertsCacheKey.value, [])
      if (Array.isArray(rows) && rows.length) {
        alerts.value = rows
        pendingAlertTotal.value = rows.length
        alertsLoaded.value = true
      }
}

async function loadAlertsFast(scope = params()) {
  try {
    const res = await Promise.race([
      getRecentAlerts(8, { ...scope, fast: true, pending: true }),
      new Promise<any>((resolve) => setTimeout(() => resolve(null), 2500)),
    ])
    if (res?.data) {
      const rows = arrayFromResponse(res.data, ['records', 'alerts'])
      alerts.value = rows
      pendingAlertTotal.value = Number.isFinite(Number(res.data.pending_count ?? res.data.total))
        ? Number(res.data.pending_count ?? res.data.total)
        : rows.length
      alertsLoaded.value = true
      writeMobileCache(alertsCacheKey.value, rows.slice(0, 80))
    }
  } finally {
    if (alerts.value.length || pendingAlertTotal.value !== null) alertsLoaded.value = true
  }
}

function go(path: string) {
  router.push({ path, query: shell.identityQuery() })
}

function openPatient(id: string) {
  if (!id) return
  router.push({ path: `/m/patient/${id}`, query: shell.identityQuery() })
}

function refreshFromShell() {
  void loadAll()
}

function applyRealtimeAlert(message: any) {
  if (message?.type !== 'alert' || !message.data) return
  if (!alertBelongsToMobileScope(message.data, shell.deptCode.value, shell.deptLabel.value)) return
  alerts.value = mergeMobileAlert(alerts.value, message.data, 80)
  pendingAlertTotal.value = (pendingAlertTotal.value ?? alerts.value.length - 1) + 1
  alertsLoaded.value = true
  writeMobileCache(alertsCacheKey.value, alerts.value.slice(0, 80))
}

watch(() => [shell.deptCode.value, shell.deptLabel.value], () => {
  patients.value = []
  priorityPatients.value = []
  alerts.value = []
  pendingAlertTotal.value = null
  alertsLoaded.value = false
  void loadAll()
})

onMounted(() => {
  void shell.resolveIdentity().finally(() => loadAll())
  offAlert = onAlertMessage(applyRealtimeAlert)
  window.addEventListener('mobile:refresh', refreshFromShell)
})

onUnmounted(() => {
  offAlert?.()
  window.removeEventListener('mobile:refresh', refreshFromShell)
})
</script>
