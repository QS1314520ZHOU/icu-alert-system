<template>
  <div class="bedside-screen" :class="`level-${patient?.alertLevel || 'none'}`">
    <!-- 顶部状态栏 -->
    <header class="bedside-header">
      <div class="bedside-header__bed">
        <span class="bed-no">{{ patient?.hisBed || bedId || '--' }}</span>
        <span class="bed-label">床</span>
      </div>
      <div class="bedside-header__info">
        <div class="patient-name">{{ patient?.name || '加载中…' }}</div>
        <div class="patient-meta">
          {{ genderText(patient?.gender) }} / {{ patient?.age || '--' }}岁
        </div>
      </div>
      <div class="bedside-header__level">
        <span :class="['level-lamp', `lamp-${patient?.alertLevel || 'none'}`]"></span>
        <span class="level-text">{{ alertText(patient?.alertLevel) }}</span>
      </div>
      <div class="bedside-clock">{{ currentTime }}</div>
    </header>

    <!-- 生命体征 -->
    <section class="bedside-vitals">
      <div class="vital-card" :class="warnClass(vitals.hr, 60, 100)">
        <div class="vital-card__label">心率</div>
        <div class="vital-card__value">{{ vitals.hr ?? '--' }}</div>
        <div class="vital-card__unit">bpm</div>
      </div>
      <div class="vital-card" :class="warnClass(vitals.spo2, 95, 100)">
        <div class="vital-card__label">血氧</div>
        <div class="vital-card__value">{{ vitals.spo2 ?? '--' }}</div>
        <div class="vital-card__unit">%</div>
      </div>
      <div class="vital-card" :class="warnClass(vitals.rr, 12, 20)">
        <div class="vital-card__label">呼吸</div>
        <div class="vital-card__value">{{ vitals.rr ?? '--' }}</div>
        <div class="vital-card__unit">次/分</div>
      </div>
      <div class="vital-card vital-card--bp">
        <div class="vital-card__label">血压</div>
        <div class="vital-card__value bp-value">
          {{ vitals.sbp ?? '--' }}/{{ vitals.dbp ?? '--' }}
        </div>
        <div class="vital-card__unit">mmHg</div>
      </div>
      <div class="vital-card" :class="warnClass(vitals.temp, 36, 37.5)">
        <div class="vital-card__label">体温</div>
        <div class="vital-card__value">{{ vitals.temp ?? '--' }}</div>
        <div class="vital-card__unit">°C</div>
      </div>
    </section>

    <!-- 待办提醒 -->
    <section class="bedside-todos">
      <div class="section-title-row">
        <div>
          <span class="bedside-section-label">床旁待办</span>
          <strong>{{ bedsideTodos.length ? `${bedsideTodos.length} 项需处理` : '暂无待办' }}</strong>
        </div>
        <button class="voice-toggle" :class="{ active: speechEnabled }" @click="toggleSpeech">
          {{ speechEnabled ? '语音开启' : '语音关闭' }}
        </button>
      </div>
      <div v-if="bedsideTodos.length === 0" class="bedside-todos__empty">
        当前无活跃处置项，继续按班次复核管路、泵速、约束与皮肤。
      </div>
      <div
        v-for="todo in bedsideTodos"
        :key="todo.id"
        :class="['todo-item', `todo-item--${todo.priority || 'normal'}`]"
      >
        <span class="todo-item__dot"></span>
        <span class="todo-item__text">
          <strong>{{ todo.title }}</strong>
          <small>{{ todo.detail }}</small>
        </span>
        <span class="todo-item__time">{{ todo.time }}</span>
        <button class="done-btn" :disabled="closingAlertIds.has(todo.id)" @click="acknowledgeAlert(todo.id)">
          {{ closingAlertIds.has(todo.id) ? '处理中' : '确认' }}
        </button>
      </div>
    </section>

    <!-- 最近预警 -->
    <section class="bedside-alerts">
      <div class="section-title-row">
        <div>
          <span class="bedside-section-label">本床预警</span>
          <strong>{{ patientAlerts.length ? '优先看前 3 条' : '暂无活跃预警' }}</strong>
        </div>
        <button class="voice-toggle ghost" @click="testSpeech">试播</button>
      </div>
      <div v-if="patientAlerts.length === 0" class="bedside-alerts__empty">暂无活跃预警</div>
      <div
        v-for="alert in patientAlerts.slice(0, 3)"
        :key="alert._id || alert.rule_id"
        :class="['alert-row', `alert-row--${alert.severity || 'warning'}`]"
      >
        <span class="alert-row__name">
          <strong>{{ alert.name }}</strong>
          <small>{{ alertSuggestion(alert) }}</small>
        </span>
        <span class="alert-row__severity">{{ severityText(alert.severity) }}</span>
      </div>
    </section>

    <!-- 语音播报状态角标 -->
    <div class="speech-badge" :class="{ active: speechActive }">
      <span class="speech-badge__icon">声</span>
      <span class="speech-badge__label">{{ speechActive ? '播报中' : '语音就绪' }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import dayjs from 'dayjs'
import { getPatientDetail, getPatientVitals, getRecentAlerts, postAlertAcknowledge } from '../api'
import { onAlertMessage } from '../services/alertSocket'

const route = useRoute()
const patientId = computed(() => String(route.params.patientId || ''))
const bedId = computed(() => String(route.query.bedId || route.query.bed || ''))
const routeDeptCode = computed(() => String(route.query.dept_code || route.query.deptCode || '').trim())
const routeDeptName = computed(() => String(route.query.dept || route.query.department || '').trim())

// ── 时钟 ──────────────────────────────────────────────────────
const currentTime = ref(dayjs().format('HH:mm:ss'))
let clockTimer: number

// ── 数据 ──────────────────────────────────────────────────────
const patient = ref<any>(null)
const vitals = ref<any>({})
const allAlerts = ref<any[]>([])
const speechActive = ref(false)
const speechEnabled = ref(true)
const closingAlertIds = ref<Set<string>>(new Set())

// 只保留本床预警
const patientAlerts = computed(() =>
  allAlerts.value.filter(
    (a: any) =>
      String(a.patient_id) === patientId.value ||
      String(a.bed) === (patient.value?.hisBed || bedId.value)
  ).slice(0, 6)
)
const bedsideTodos = computed(() =>
  patientAlerts.value.slice(0, 4).map((alert: any) => {
    const id = String(alert._id || alert.record_id || alert.rule_id || '')
    return {
      id,
      priority: String(alert.severity || 'normal').toLowerCase(),
      title: alert.name || '床旁预警待确认',
      detail: alertSuggestion(alert),
      time: formatAlertTime(alert.created_at || alert.time),
    }
  }).filter((item) => item.id)
)

// ── 工具函数 ──────────────────────────────────────────────────
function alertText(level?: string) {
  const map: Record<string, string> = {
    critical: '危急',
    high: '高危',
    warning: '警告',
    info: '关注',
    none: '正常',
  }
  return map[level || 'none'] || '正常'
}

function severityText(level?: string) {
  const map: Record<string, string> = {
    critical: '危急',
    high: '高危',
    warning: '警告',
    info: '关注',
  }
  return map[String(level || '').toLowerCase()] || '关注'
}

function alertSuggestion(alert: any) {
  const severity = String(alert?.severity || '').toLowerCase()
  const text = String(alert?.name || alert?.rule_id || '').toLowerCase()
  if (severity === 'critical') return '立即复核患者、设备与医嘱，必要时呼叫医生到床旁。'
  if (text.includes('spo2') || text.includes('氧') || text.includes('呼吸')) return '先看氧疗连接、气道通畅、体位和监护探头。'
  if (text.includes('血压') || text.includes('shock') || text.includes('乳酸')) return '复测血压灌注，核对升压药、液体和乳酸趋势。'
  return '完成床旁复核后点击确认，交班时追踪是否复发。'
}

function formatAlertTime(value: any) {
  if (!value) return '刚刚'
  const parsed = dayjs(value)
  if (!parsed.isValid()) return '刚刚'
  return parsed.format('HH:mm')
}

function genderText(g?: string | number) {
  if (g === 'M' || g === 1 || g === '1') return '男'
  if (g === 'F' || g === 2 || g === '2') return '女'
  return '未知'
}

function warnClass(val: any, low: number, high: number) {
  if (val == null) return ''
  const n = Number(val)
  if (n < low || n > high) return 'vital-card--warn'
  return ''
}

// ── 语音播报（Web Speech API） ────────────────────────────────
const SPEECH_ENABLED_KEY = 'icu_bedside_speech_enabled'

function isSpeechEnabled() {
  return speechEnabled.value
}

function toggleSpeech() {
  speechEnabled.value = !speechEnabled.value
  localStorage.setItem(SPEECH_ENABLED_KEY, speechEnabled.value ? '1' : '0')
}

function speakText(text: string) {
  if (!isSpeechEnabled()) return
  if (!('speechSynthesis' in window)) return
  const utter = new SpeechSynthesisUtterance(text)
  utter.lang = 'zh-CN'
  utter.rate = 0.92
  utter.volume = 1
  speechActive.value = true
  utter.onend = () => { speechActive.value = false }
  utter.onerror = () => { speechActive.value = false }
  window.speechSynthesis.cancel()
  window.speechSynthesis.speak(utter)
}

function testSpeech() {
  speakText(`${patient.value?.hisBed || bedId.value || '本'}床，语音播报正常。`)
}

function speakAlert(msg: { type: string; data: any }) {
  if (msg.type !== 'alert') return
  const alert = msg.data || {}

  // 只播报与本床相关的 critical 级别预警
  const alertBed = String(alert.bed || '')
  const myBed = patient.value?.hisBed || bedId.value
  const alertPatientId = String(alert.patient_id || '')

  const isThisBed =
    alertBed === String(myBed) || alertPatientId === patientId.value

  if (!isThisBed) return
  if (String(alert.severity || '').toLowerCase() !== 'critical') return
  const text = `危急预警：${alert.name || '未知预警'}，${alert.patient_name || '患者'}，请立即处置`
  speakText(text)
}

// ── 加载数据 ──────────────────────────────────────────────────
async function loadPatient() {
  try {
    const res = await getPatientDetail(patientId.value)
    patient.value = res?.data?.patient || null
  } catch {
    patient.value = null
  }
}

async function loadVitals() {
  try {
    const res = await getPatientVitals(patientId.value)
    vitals.value = res?.data?.vitals || {}
  } catch {
    vitals.value = {}
  }
}

async function loadAlerts() {
  try {
    const params: { patient_id?: string; bed?: string; dept?: string; dept_code?: string } = {}
    if (patientId.value) params.patient_id = patientId.value
    const currentBed = String(patient.value?.hisBed || bedId.value || '').trim()
    if (currentBed) params.bed = currentBed
    const currentDeptCode = String(patient.value?.deptCode || routeDeptCode.value || '').trim()
    const currentDept = String(patient.value?.hisDept || patient.value?.dept || routeDeptName.value || '').trim()
    if (currentDeptCode) params.dept_code = currentDeptCode
    else if (currentDept) params.dept = currentDept
    const res = await getRecentAlerts(30, params)
    allAlerts.value = res?.data?.records || []
  } catch {
    allAlerts.value = []
  }
}

async function acknowledgeAlert(alertId: string) {
  if (!alertId || closingAlertIds.value.has(alertId)) return
  closingAlertIds.value = new Set([...closingAlertIds.value, alertId])
  try {
    await postAlertAcknowledge(alertId, { actor: 'bedside-screen', note: '床旁屏确认处理', disposition: 'bedside_confirmed' })
    allAlerts.value = allAlerts.value.filter((item: any) => String(item._id || item.record_id || item.rule_id || '') !== alertId)
    speakText('已确认，待办已关闭。')
  } finally {
    const next = new Set(closingAlertIds.value)
    next.delete(alertId)
    closingAlertIds.value = next
  }
}

let offAlert: (() => void) | null = null
let refreshTimer: number

onMounted(async () => {
  speechEnabled.value = localStorage.getItem(SPEECH_ENABLED_KEY) !== '0'
  await Promise.all([loadPatient(), loadVitals()])
  await loadAlerts()

  // 时钟
  clockTimer = window.setInterval(() => {
    currentTime.value = dayjs().format('HH:mm:ss')
  }, 1000)

  // 定时刷新体征 & 预警（每30秒）
  refreshTimer = window.setInterval(async () => {
    await Promise.all([loadVitals(), loadAlerts()])
  }, 30_000)

  // WebSocket 实时预警 → 语音播报
  offAlert = onAlertMessage((msg) => {
    speakAlert(msg)
    // 同步更新预警列表
    if (msg.type === 'alert' && msg.data) {
      const exists = allAlerts.value.some(
        (a: any) => a._id && a._id === msg.data._id
      )
      if (!exists) {
        allAlerts.value = [msg.data, ...allAlerts.value].slice(0, 50)
      }
    }
  })
})

onUnmounted(() => {
  clearInterval(clockTimer)
  clearInterval(refreshTimer)
  offAlert?.()
  window.speechSynthesis?.cancel()
})

watch(patientId, async (nextId, prevId) => {
  if (!nextId || nextId === prevId) return
  await Promise.all([loadPatient(), loadVitals()])
  await loadAlerts()
})
</script>

<style scoped>
/* ── 根容器 ────────────────────────────── */
.bedside-screen {
  min-height: 100vh;
  background:
    radial-gradient(circle at 0 0, rgba(14,165,233,.16), transparent 34%),
    linear-gradient(145deg, #07111f, #0a1324 58%, #071018);
  color: #e8eaf0;
  font-family: var(--app-display-font);
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: 0;
  transition: background 0.4s;
}
.bedside-screen.level-critical { background: #150a0a; }
.bedside-screen.level-warning  { background: #0f0e0a; }

/* ── header ────────────────────────────── */
.bedside-header {
  display: flex;
  align-items: center;
  gap: 28px;
  padding: 22px 34px;
  background: rgba(255,255,255,0.04);
  border-bottom: 1px solid rgba(255,255,255,0.08);
}
.bedside-header__bed {
  display: flex;
  align-items: baseline;
  gap: 4px;
}
.bed-no {
  font-size: clamp(4rem, 7vw, 7.5rem);
  font-weight: 800;
  line-height: 1;
  color: #a8d8ff;
}
.bed-label { font-size: 1.35rem; color: #8090a8; }

.bedside-header__info { flex: 1; }
.patient-name { font-size: clamp(2rem, 3.4vw, 3.4rem); font-weight: 800; }
.patient-meta { font-size: 1.2rem; color: #9fb3c8; margin-top: 6px; }

.bedside-header__level {
  display: flex;
  align-items: center;
  gap: 8px;
}
.level-lamp {
  width: 14px; height: 14px;
  border-radius: 50%;
  display: inline-block;
}
.lamp-critical { background: #ff3d3d; box-shadow: 0 0 10px #ff3d3d; animation: blink 0.8s infinite; }
.lamp-warning  { background: #ffb800; box-shadow: 0 0 8px #ffb800; }
.lamp-info     { background: #00c8ff; }
.lamp-none     { background: #3a5a3a; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.2} }

.level-text { font-size: 1.4rem; font-weight: 800; }
.bedside-clock { font-size: 1.6rem; font-variant-numeric: tabular-nums; color: #9fb3c8; }

/* ── 诊断 ───────────────────────────────── */
.bedside-diag {
  padding: 12px 28px;
  display: flex;
  align-items: baseline;
  gap: 12px;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}
.bedside-section-label {
  font-size: 0.72rem;
  color: #506070;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  white-space: nowrap;
}
.bedside-diag__text { font-size: 0.95rem; color: #c0ccd8; }

/* ── 生命体征 ───────────────────────────── */
.bedside-vitals {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 16px;
  padding: 26px 34px;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}
.vital-card {
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 22px;
  padding: 22px 14px;
  text-align: center;
  transition: border-color 0.3s;
}
.vital-card--warn {
  border-color: #ffb800;
  background: rgba(255,184,0,0.07);
}
.vital-card--bp { grid-column: span 1; }
.vital-card__label { font-size: 1rem; color: #7f94aa; margin-bottom: 12px; }
.vital-card__value { font-size: clamp(3rem, 5.2vw, 5.4rem); font-weight: 800; line-height: 1; color: #e0eeff; }
.bp-value { font-size: clamp(2rem, 3.5vw, 3.6rem); }
.vital-card__unit  { font-size: 0.95rem; color: #6d8196; margin-top: 8px; }

/* ── 待办 ───────────────────────────────── */
.bedside-todos {
  padding: 20px 34px;
  border-bottom: 1px solid rgba(255,255,255,0.05);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.bedside-todos__empty,
.bedside-alerts__empty { color: #66788c; font-size: 1.35rem; padding: 12px 0; }
.section-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.section-title-row > div {
  display: grid;
  gap: 4px;
}
.section-title-row strong {
  color: #e6f4ff;
  font-size: 1.65rem;
}
.todo-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(255,255,255,.045);
  border: 1px solid rgba(255,255,255,.08);
  font-size: 1.25rem;
}
.todo-item__dot {
  width: 14px; height: 14px;
  border-radius: 50%;
  background: #4080c0;
  flex-shrink: 0;
}
.todo-item--urgent .todo-item__dot { background: #ff4040; }
.todo-item--high   .todo-item__dot { background: #ffb800; }
.todo-item__text { flex: 1; display: grid; gap: 4px; }
.todo-item__text strong { color: #f1f7ff; }
.todo-item__text small { color: #9fb3c8; font-size: 1rem; }
.todo-item__time { font-size: 1rem; color: #76899e; white-space: nowrap; }
.done-btn,
.voice-toggle {
  border: 0;
  border-radius: 999px;
  padding: 10px 18px;
  color: #06202f;
  background: #7dd3fc;
  font-weight: 800;
  cursor: pointer;
}
.done-btn:disabled {
  cursor: wait;
  opacity: .72;
}
.voice-toggle {
  background: rgba(255,255,255,.08);
  border: 1px solid rgba(255,255,255,.14);
  color: #cfe8ff;
}
.voice-toggle.active {
  background: rgba(34,197,94,.16);
  border-color: rgba(74,222,128,.4);
  color: #bbf7d0;
}
.voice-toggle.ghost {
  background: rgba(14,165,233,.12);
  color: #bae6fd;
}

/* ── 预警 ───────────────────────────────── */
.bedside-alerts {
  padding: 20px 34px 34px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
}
.alert-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 16px 18px;
  border-radius: 18px;
  background: rgba(255,255,255,0.03);
  font-size: 1.2rem;
}
.alert-row--critical { background: rgba(255,40,40,0.12); }
.alert-row--warning  { background: rgba(255,184,0,0.10); }
.alert-row__name { color: #c8d8e8; display: grid; gap: 5px; }
.alert-row__name strong { color: #f5f9ff; font-size: 1.35rem; }
.alert-row__name small { color: #9fb3c8; font-size: 1rem; }
.alert-row__severity {
  font-size: 1.15rem;
  font-weight: 800;
  color: #8090a8;
  white-space: nowrap;
}
.alert-row--critical .alert-row__severity { color: #ff6060; }
.alert-row--warning  .alert-row__severity { color: #ffb800; }

/* ── 语音角标 ───────────────────────────── */
.speech-badge {
  position: fixed;
  bottom: 20px;
  right: 24px;
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(0,0,0,0.6);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 20px;
  padding: 8px 16px;
  font-size: 1rem;
  color: #607080;
  transition: all 0.3s;
}
.speech-badge.active {
  border-color: #00c8ff;
  color: #00c8ff;
  box-shadow: 0 0 12px rgba(0,200,255,0.3);
}
.speech-badge__icon { font-size: 1rem; font-weight: 800; }
html[data-theme='light'] .bedside-screen {
  background:
    radial-gradient(circle at 0 0, rgba(14,165,233,.12), transparent 34%),
    linear-gradient(145deg, #f5fbff, #eef7fb 58%, #f8fcff);
  color: #1f3852;
}
html[data-theme='light'] .bedside-screen.level-critical { background: #fff5f5; }
html[data-theme='light'] .bedside-screen.level-warning { background: #fffbeb; }
html[data-theme='light'] .bedside-header {
  background: rgba(255,255,255,.92);
  border-bottom-color: rgba(187,204,220,.72);
}
html[data-theme='light'] .bed-no { color: #1d4ed8; }
html[data-theme='light'] .bed-label,
html[data-theme='light'] .patient-meta,
html[data-theme='light'] .bedside-clock,
html[data-theme='light'] .bedside-section-label,
html[data-theme='light'] .vital-card__label,
html[data-theme='light'] .vital-card__unit,
html[data-theme='light'] .todo-item__time,
html[data-theme='light'] .bedside-todos__empty,
html[data-theme='light'] .bedside-alerts__empty {
  color: #6f8399;
}
html[data-theme='light'] .patient-name,
html[data-theme='light'] .vital-card__value,
html[data-theme='light'] .section-title-row strong,
html[data-theme='light'] .todo-item__text strong,
html[data-theme='light'] .alert-row__name,
html[data-theme='light'] .alert-row__name strong { color: #16324f; }
html[data-theme='light'] .todo-item__text small,
html[data-theme='light'] .alert-row__name small {
  color: #5b7188;
}
html[data-theme='light'] .bedside-diag,
html[data-theme='light'] .bedside-vitals,
html[data-theme='light'] .bedside-todos {
  border-bottom-color: rgba(187,204,220,.56);
}
html[data-theme='light'] .bedside-diag__text { color: #47627e; }
html[data-theme='light'] .vital-card,
html[data-theme='light'] .todo-item,
html[data-theme='light'] .alert-row {
  background: rgba(241,246,251,.96);
  border-color: rgba(187,204,220,.72);
}
html[data-theme='light'] .vital-card--warn {
  border-color: rgba(245,158,11,.3);
  background: rgba(254,243,199,.96);
}
html[data-theme='light'] .alert-row--critical { background: rgba(255,241,242,.98); }
html[data-theme='light'] .alert-row--warning { background: rgba(254,243,199,.98); }
html[data-theme='light'] .alert-row__severity { color: #6f8399; }
html[data-theme='light'] .alert-row--critical .alert-row__severity { color: #be123c; }
html[data-theme='light'] .alert-row--warning .alert-row__severity { color: #b45309; }
html[data-theme='light'] .speech-badge {
  background: rgba(255,255,255,.95);
  border-color: rgba(187,204,220,.72);
  color: #6f8399;
}
html[data-theme='light'] .speech-badge.active {
  border-color: rgba(59,130,246,.34);
  color: #1d4ed8;
  box-shadow: 0 0 12px rgba(37,99,235,.18);
}
html[data-theme='light'] .voice-toggle {
  background: #eef6ff;
  border-color: rgba(148,163,184,.42);
  color: #2563eb;
}
html[data-theme='light'] .voice-toggle.active {
  background: #ecfdf5;
  border-color: rgba(34,197,94,.32);
  color: #047857;
}
html[data-theme='light'] .voice-toggle.ghost {
  background: #e0f2fe;
  color: #0369a1;
}
html[data-theme='light'] .done-btn {
  background: #2563eb;
  color: white;
}

@media (max-width: 1100px) {
  .bedside-header {
    flex-wrap: wrap;
  }
  .bedside-vitals {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
