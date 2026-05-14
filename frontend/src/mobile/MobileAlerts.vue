<template>
  <div class="mobile-page">
    <section class="mobile-filter">
      <input v-model.trim="keyword" placeholder="搜索患者 / 告警 / 床号" />
      <select v-model="level">
        <option value="">全部</option>
        <option value="critical">危急</option>
        <option value="warning">高危</option>
        <option value="watch">关注</option>
      </select>
    </section>
    <section class="mobile-card">
      <div class="mobile-section-head"><h2>告警中心</h2><button type="button" @click="refreshAlerts">刷新</button></div>
      <article v-for="alert in filteredAlerts" :key="alertIdOf(alert)" class="mobile-alert-card" @click="selected = alert">
        <i :class="`tone-${toneOf(alert)}`"></i>
        <div>
          <strong>{{ alertTitleOf(alert) }}</strong>
          <p>{{ alertSummaryOf(alert) }}</p>
          <div class="mobile-chip-row">
            <span>{{ bedOf(alert) }}</span>
            <span>{{ patientNameOf(alert) }}</span>
            <span>{{ levelLabel(alert) }}</span>
            <span>{{ formatTime(firstText(alert, ['created_at', 'time', 'timestamp'])) }}</span>
          </div>
        </div>
      </article>
      <div v-if="loading && !alerts.length" class="mobile-skeleton-list">
        <i></i><i></i><i></i>
      </div>
      <div v-if="!loading && !filteredAlerts.length" class="mobile-empty">{{ emptyText }}</div>
    </section>

    <div v-if="selected" class="mobile-drawer-mask" @click.self="selected = null">
      <section class="mobile-drawer">
        <h2>{{ alertTitleOf(selected) }}</h2>
        <p>{{ alertSummaryOf(selected) }}</p>
        <textarea v-model="note" placeholder="填写处置备注"></textarea>
        <div class="mobile-action-grid">
          <button type="button" @click="ack('acknowledged')">确认</button>
          <button type="button" @click="ack('false_positive')">误报</button>
          <button type="button" @click="ack('handoff_doctor')">转医生</button>
          <button type="button" @click="dispose('review_later')">1小时复评</button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { getRecentAlerts, postAlertAcknowledge, postAlertDisposition } from '../api'
import { useMobileShell } from '../composables/useMobileShell'
import { onAlertMessage } from '../services/alertSocket'
import { mobileAlertCacheKey, mobileScopeKey, readMobileCache, writeMobileCache } from './mobileCache'
import { alertIdOf, alertSummaryOf, alertTitleOf, arrayFromResponse, bedOf, firstText, formatTime, levelLabel, patientNameOf, toneOf } from './mobileData'
import { alertBelongsToMobileScope, mergeMobileAlert } from './mobileRealtime'
import { MOBILE_ACTION_SOURCE } from './types'

const shell = useMobileShell()
const alerts = ref<any[]>([])
const selected = ref<any | null>(null)
const loading = ref(false)
const loaded = ref(false)
const keyword = ref('')
const level = ref('')
const note = ref('')
let offAlert: (() => void) | null = null
const emptyText = computed(() => loaded.value ? '暂无告警' : '正在加载告警...')
const filteredAlerts = computed(() => {
  const key = keyword.value.toLowerCase()
  return alerts.value.filter((alert) => {
    const hay = [patientNameOf(alert), bedOf(alert), alertTitleOf(alert), alertSummaryOf(alert), firstText(alert, ['title', 'message', 'summary', 'alert_type'])].join(' ').toLowerCase()
    const tone = toneOf(alert)
    return (!key || hay.includes(key)) && (!level.value || tone === level.value)
  })
})

const cacheKey = computed(() => mobileAlertCacheKey(mobileScopeKey(shell.deptCode.value, shell.deptLabel.value)))

function params() {
  const value: Record<string, any> = {}
  if (shell.deptCode.value) value.dept_code = shell.deptCode.value
  else if (shell.deptLabel.value && shell.deptLabel.value !== '全院') value.dept = shell.deptLabel.value
  return value
}

function restoreCachedAlerts() {
  const parsed = readMobileCache<any[]>(cacheKey.value, [])
  if (Array.isArray(parsed) && parsed.length) {
    alerts.value = parsed
    loaded.value = true
  }
}

async function loadAlerts(options: { fast?: boolean } = {}) {
  loading.value = true
  try {
    if (options.fast) restoreCachedAlerts()
    const res = await Promise.race([
      getRecentAlerts(60, { ...params(), fast: Boolean(options.fast), pending: true }),
      new Promise<any>((resolve) => setTimeout(() => resolve(null), options.fast ? 900 : 1800)),
    ])
    if (res?.data) {
      const rows = arrayFromResponse(res.data, ['records', 'alerts'])
      alerts.value = rows
      loaded.value = true
      writeMobileCache(cacheKey.value, rows.slice(0, 80))
    }
  } finally {
    loading.value = false
    loaded.value = true
  }
}
async function ack(disposition: string) {
  const id = alertIdOf(selected.value)
  if (!id) return
  await postAlertAcknowledge(id, { actor: shell.actor.value, note: note.value, disposition, override_reason_text: note.value, source: MOBILE_ACTION_SOURCE } as any)
  selected.value = null
  note.value = ''
  await loadAlerts()
}
async function dispose(action: string) {
  const id = alertIdOf(selected.value)
  if (!id) return
  await postAlertDisposition(id, { action, reason: note.value, actor: shell.actor.value, review_after_minutes: 60, source: MOBILE_ACTION_SOURCE } as any)
  selected.value = null
  note.value = ''
  await loadAlerts()
}

function refreshFromShell() {
  void loadAlerts({ fast: true })
}

function refreshAlerts() {
  void loadAlerts()
}

function applyRealtimeAlert(message: any) {
  if (message?.type !== 'alert' || !message.data) return
  if (!alertBelongsToMobileScope(message.data, shell.deptCode.value, shell.deptLabel.value)) return
  alerts.value = mergeMobileAlert(alerts.value, message.data, 80)
  loaded.value = true
  writeMobileCache(cacheKey.value, alerts.value.slice(0, 80))
}

watch(() => [shell.deptCode.value, shell.deptLabel.value], () => {
  alerts.value = []
  loaded.value = false
  void loadAlerts({ fast: true })
})

onMounted(() => {
  void shell.resolveIdentity().finally(() => loadAlerts({ fast: true }))
  offAlert = onAlertMessage(applyRealtimeAlert)
  window.addEventListener('mobile:refresh', refreshFromShell)
})

onUnmounted(() => {
  offAlert?.()
  window.removeEventListener('mobile:refresh', refreshFromShell)
})
</script>
