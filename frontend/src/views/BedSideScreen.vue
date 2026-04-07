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

    <!-- 诊断 -->
    <section class="bedside-diag">
      <span class="bedside-section-label">当前诊断</span>
      <span class="bedside-diag__text">
        {{ patient?.clinicalDiagnosis || patient?.admissionDiagnosis || '暂无' }}
      </span>
    </section>

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
      <div class="bedside-section-label">床旁待办</div>
      <div v-if="todos.length === 0" class="bedside-todos__empty">暂无待办事项</div>
      <div
        v-for="todo in todos"
        :key="todo.id"
        :class="['todo-item', `todo-item--${todo.priority || 'normal'}`]"
      >
        <span class="todo-item__dot"></span>
        <span class="todo-item__text">{{ todo.content }}</span>
        <span class="todo-item__time">{{ todo.time }}</span>
      </div>
    </section>

    <!-- 最近预警 -->
    <section class="bedside-alerts">
      <div class="bedside-section-label">本床预警</div>
      <div v-if="patientAlerts.length === 0" class="bedside-alerts__empty">暂无活跃预警</div>
      <div
        v-for="alert in patientAlerts"
        :key="alert._id || alert.rule_id"
        :class="['alert-row', `alert-row--${alert.severity || 'warning'}`]"
      >
        <span class="alert-row__name">{{ alert.name }}</span>
        <span class="alert-row__severity">{{ alert.severity?.toUpperCase() }}</span>
      </div>
    </section>

    <!-- 语音播报状态角标 -->
    <div class="speech-badge" :class="{ active: speechActive }">
      <span class="speech-badge__icon">🔊</span>
      <span class="speech-badge__label">{{ speechActive ? '播报中' : '语音就绪' }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import dayjs from 'dayjs'
import { getPatientDetail, getPatientVitals, getRecentAlerts } from '../api'
import { onAlertMessage } from '../services/alertSocket'

const route = useRoute()
const patientId = computed(() => String(route.params.patientId || ''))
const bedId = computed(() => String(route.query.bedId || route.query.bed || ''))

// ── 时钟 ──────────────────────────────────────────────────────
const currentTime = ref(dayjs().format('HH:mm:ss'))
let clockTimer: number

// ── 数据 ──────────────────────────────────────────────────────
const patient = ref<any>(null)
const vitals = ref<any>({})
const allAlerts = ref<any[]>([])
const todos = ref<any[]>([])
const speechActive = ref(false)

// 只保留本床预警
const patientAlerts = computed(() =>
  allAlerts.value.filter(
    (a: any) =>
      String(a.patient_id) === patientId.value ||
      String(a.bed) === (patient.value?.hisBed || bedId.value)
  ).slice(0, 6)
)

// ── 工具函数 ──────────────────────────────────────────────────
function alertText(level?: string) {
  const map: Record<string, string> = {
    critical: '危急',
    warning: '警告',
    info: '关注',
    none: '正常',
  }
  return map[level || 'none'] || '正常'
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
  return localStorage.getItem(SPEECH_ENABLED_KEY) !== '0'
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
  if (!isSpeechEnabled()) return
  if (!('speechSynthesis' in window)) return

  const text = `危急预警：${alert.name || '未知预警'}，${alert.patient_name || '患者'}，请立即处置`
  const utter = new SpeechSynthesisUtterance(text)
  utter.lang = 'zh-CN'
  utter.rate = 0.95
  utter.volume = 1

  speechActive.value = true
  utter.onend = () => { speechActive.value = false }
  utter.onerror = () => { speechActive.value = false }

  window.speechSynthesis.cancel() // 中断上一条
  window.speechSynthesis.speak(utter)
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
    const res = await getRecentAlerts(30)
    allAlerts.value = res?.data?.records || []
  } catch {
    allAlerts.value = []
  }
}

let offAlert: (() => void) | null = null
let refreshTimer: number

onMounted(async () => {
  await Promise.all([loadPatient(), loadVitals(), loadAlerts()])

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
  await Promise.all([loadPatient(), loadVitals(), loadAlerts()])
})
</script>

<style scoped>
/* ── 根容器 ────────────────────────────── */
.bedside-screen {
  min-height: 100vh;
  background: #0a0e1a;
  color: #e8eaf0;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
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
  gap: 20px;
  padding: 16px 28px;
  background: rgba(255,255,255,0.04);
  border-bottom: 1px solid rgba(255,255,255,0.08);
}
.bedside-header__bed {
  display: flex;
  align-items: baseline;
  gap: 4px;
}
.bed-no {
  font-size: 3rem;
  font-weight: 800;
  line-height: 1;
  color: #a8d8ff;
}
.bed-label { font-size: 1rem; color: #8090a8; }

.bedside-header__info { flex: 1; }
.patient-name { font-size: 1.5rem; font-weight: 700; }
.patient-meta { font-size: 0.85rem; color: #8090a8; margin-top: 2px; }

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

.level-text { font-size: 1rem; font-weight: 600; }
.bedside-clock { font-size: 1.2rem; font-variant-numeric: tabular-nums; color: #8090a8; }

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
  display: flex;
  gap: 12px;
  padding: 20px 28px;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}
.vital-card {
  flex: 1;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px;
  padding: 16px 12px;
  text-align: center;
  transition: border-color 0.3s;
}
.vital-card--warn {
  border-color: #ffb800;
  background: rgba(255,184,0,0.07);
}
.vital-card--bp { flex: 1.4; }
.vital-card__label { font-size: 0.72rem; color: #607080; margin-bottom: 8px; }
.vital-card__value { font-size: 2rem; font-weight: 700; line-height: 1; color: #e0eeff; }
.bp-value { font-size: 1.5rem; }
.vital-card__unit  { font-size: 0.7rem; color: #506070; margin-top: 4px; }

/* ── 待办 ───────────────────────────────── */
.bedside-todos {
  padding: 16px 28px;
  border-bottom: 1px solid rgba(255,255,255,0.05);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.bedside-todos__empty,
.bedside-alerts__empty { color: #405060; font-size: 0.85rem; }
.todo-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.9rem;
}
.todo-item__dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: #4080c0;
  flex-shrink: 0;
}
.todo-item--urgent .todo-item__dot { background: #ff4040; }
.todo-item--high   .todo-item__dot { background: #ffb800; }
.todo-item__text { flex: 1; }
.todo-item__time { font-size: 0.75rem; color: #506070; white-space: nowrap; }

/* ── 预警 ───────────────────────────────── */
.bedside-alerts {
  padding: 16px 28px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
}
.alert-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba(255,255,255,0.03);
  font-size: 0.88rem;
}
.alert-row--critical { background: rgba(255,40,40,0.12); }
.alert-row--warning  { background: rgba(255,184,0,0.10); }
.alert-row__name { color: #c8d8e8; }
.alert-row__severity {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: #8090a8;
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
  padding: 6px 14px;
  font-size: 0.78rem;
  color: #607080;
  transition: all 0.3s;
}
.speech-badge.active {
  border-color: #00c8ff;
  color: #00c8ff;
  box-shadow: 0 0 12px rgba(0,200,255,0.3);
}
.speech-badge__icon { font-size: 1rem; }
</style>
