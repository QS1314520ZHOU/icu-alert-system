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
      <section class="mobile-drawer mobile-action-panel">
        <h2>{{ alertTitleOf(selected) }}</h2>
        <p>{{ alertSummaryOf(selected) }}</p>
        <div class="mobile-chip-row">
          <span>{{ bedOf(selected) }}</span>
          <span>{{ patientNameOf(selected) }}</span>
          <span>{{ levelLabel(selected) }}</span>
        </div>
        <textarea v-model="note" placeholder="填写处置备注"></textarea>

        <template v-if="confirmAction">
          <div class="mobile-confirm-box">
            <strong>{{ confirmAction === 'false_positive' ? '确认标记误报？' : '确认已完成床旁核对？' }}</strong>
            <p>危急告警需要二次确认，提交后会写入审计记录。</p>
            <select v-if="confirmAction === 'false_positive'" v-model="falseReason">
              <option value="">选择误报原因</option>
              <option v-for="item in falseReasons" :key="item.code" :value="item.code">{{ item.label }}</option>
            </select>
            <div class="mobile-action-grid">
              <button type="button" @click="confirmAction = ''">取消</button>
              <button type="button" :disabled="actionBusy || (confirmAction === 'false_positive' && !falseReason)" @click="submitConfirmedAction">提交</button>
            </div>
          </div>
        </template>

        <template v-else-if="sbarDraft">
          <div class="mobile-confirm-box">
            <strong>SBAR 草稿</strong>
            <textarea v-model="sbarText" rows="6"></textarea>
            <div class="mobile-action-grid">
              <button type="button" @click="sbarDraft = null">取消</button>
              <button type="button" :disabled="actionBusy" @click="sendSbar">发送给二线</button>
            </div>
          </div>
        </template>

        <template v-else-if="orderItems.length">
          <div class="mobile-confirm-box">
            <strong>医嘱草稿清单</strong>
            <label v-for="item in orderItems" :key="item.key" class="mobile-check-row">
              <input v-model="item.checked" type="checkbox" />
              <span>{{ item.label }}</span>
            </label>
            <div class="mobile-action-grid">
              <button type="button" @click="orderItems = []">取消</button>
              <button type="button" :disabled="actionBusy || !orderItems.some((item) => item.checked)" @click="submitOrderStubs">生成草稿</button>
            </div>
          </div>
        </template>

        <template v-else>
          <div class="mobile-action-grid">
            <button type="button" :disabled="actionBusy" @click="startAck('acknowledged')">确认</button>
            <button type="button" :disabled="actionBusy" @click="startAck('false_positive')">误报</button>
            <button type="button" :disabled="actionBusy" @click="prepareSbar">SBAR移交</button>
            <button type="button" :disabled="actionBusy" @click="prepareOrderStubs">医嘱草稿</button>
            <button type="button" :disabled="actionBusy" @click="createReviewReminder">1小时复评</button>
          </div>
        </template>
        <div v-if="actionMessage" class="mobile-inline-status">{{ actionMessage }}</div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { getMobileOrderStubDefaults, getRecentAlerts, postAlertAcknowledge, postMobileAlertSbar, postMobileOrderStubs, postMobileReviewReminder } from '../api'
import { useMobileShell } from '../composables/useMobileShell'
import { onAlertMessage } from '../services/alertSocket'
import { mobileAlertCacheKey, mobileScopeKey, readMobileCache, writeMobileCache } from './mobileCache'
import { alertIdOf, alertSummaryOf, alertTitleOf, arrayFromResponse, bedOf, firstText, formatTime, levelLabel, patientNameOf, toneOf } from './mobileData'
import { alertBelongsToMobileScope, mergeMobileAlert } from './mobileRealtime'
import { enqueueMobileAction, makeIdempotencyKey, registerMobileNotifications, scheduleMobileNotification } from './mobileOfflineQueue'
import { MOBILE_ACTION_SOURCE } from './types'

const shell = useMobileShell()
const alerts = ref<any[]>([])
const selected = ref<any | null>(null)
const loading = ref(false)
const loaded = ref(false)
const keyword = ref('')
const level = ref('')
const note = ref('')
const falseReason = ref('')
const confirmAction = ref('')
const actionBusy = ref(false)
const actionMessage = ref('')
const sbarDraft = ref<any | null>(null)
const sbarText = ref('')
const orderItems = ref<Array<{ key: string; label: string; category?: string; checked: boolean }>>([])
let offAlert: (() => void) | null = null
const falseReasons = [
  { code: 'threshold_mismatch', label: '阈值不合理' },
  { code: 'measurement_error', label: '测量错误' },
  { code: 'device_detached', label: '设备脱落' },
  { code: 'duplicate_alert', label: '重复告警' },
  { code: 'other', label: '其他' },
]
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
  value.actor = shell.actor.value
  value.userName = shell.actor.value
  if (shell.deptCode.value) {
    value.dept_code = shell.deptCode.value
    value.deptCode = shell.deptCode.value
  }
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

function isCritical(alert: any) {
  return toneOf(alert) === 'critical'
}

function updateSelectedAlert(patch: Record<string, any>) {
  if (!selected.value) return
  const id = alertIdOf(selected.value)
  selected.value = { ...selected.value, ...patch }
  alerts.value = alerts.value.map((item) => alertIdOf(item) === id ? { ...item, ...patch } : item)
  writeMobileCache(cacheKey.value, alerts.value.slice(0, 80))
}

function resetActionState() {
  confirmAction.value = ''
  falseReason.value = ''
  sbarDraft.value = null
  sbarText.value = ''
  orderItems.value = []
}

function startAck(disposition: string) {
  actionMessage.value = ''
  if (isCritical(selected.value) || disposition === 'false_positive') {
    confirmAction.value = disposition
    return
  }
  void ack(disposition)
}

async function submitConfirmedAction() {
  if (!confirmAction.value) return
  await ack(confirmAction.value)
}

async function ack(disposition: string) {
  const id = alertIdOf(selected.value)
  if (!id) return
  const reason = falseReasons.find((item) => item.code === falseReason.value)
  const payload = {
    actor: shell.actor.value,
    note: note.value,
    disposition,
    override_reason_code: falseReason.value,
    override_reason_text: reason?.label || note.value,
    reason_code: falseReason.value,
    reason_text: reason?.label || note.value,
    confirm_required: isCritical(selected.value) || disposition === 'false_positive',
    source: MOBILE_ACTION_SOURCE,
    idempotency_key: makeIdempotencyKey(`ack:${id}`),
  }
  actionBusy.value = true
  try {
    await postAlertAcknowledge(id, payload as any)
    updateSelectedAlert({ acknowledged_at: new Date().toISOString(), ack_disposition: disposition, ack_note: note.value })
    actionMessage.value = '已记录处置'
    note.value = ''
    resetActionState()
  } catch {
    enqueueMobileAction('alert_ack', { alertId: id, body: payload })
    actionMessage.value = '网络异常，已加入离线队列'
  } finally {
    actionBusy.value = false
  }
}

async function prepareSbar() {
  const id = alertIdOf(selected.value)
  if (!id) return
  actionBusy.value = true
  actionMessage.value = ''
  try {
    const res = await postMobileAlertSbar(id, { actor: shell.actor.value, note: note.value, target_type: 'second_line', source: MOBILE_ACTION_SOURCE, idempotency_key: makeIdempotencyKey(`sbar:${id}`) })
    sbarDraft.value = res.data
    sbarText.value = String(res.data?.sbar_text || '')
    actionMessage.value = 'SBAR 草稿已生成'
  } catch {
    actionMessage.value = 'SBAR 生成失败，请稍后重试'
  } finally {
    actionBusy.value = false
  }
}

async function sendSbar() {
  if (!sbarDraft.value) return
  actionMessage.value = 'SBAR 已发送并生成闭环任务'
  updateSelectedAlert({ ack_disposition: 'sbar_handoff', acknowledged_at: new Date().toISOString() })
  resetActionState()
}

async function prepareOrderStubs() {
  const id = alertIdOf(selected.value)
  if (!id) return
  actionBusy.value = true
  actionMessage.value = ''
  try {
    const res = await getMobileOrderStubDefaults(id)
    orderItems.value = arrayFromResponse(res.data, ['items']).map((item: any) => ({ ...item, checked: item.checked !== false }))
  } finally {
    actionBusy.value = false
  }
}

async function submitOrderStubs() {
  const id = alertIdOf(selected.value)
  if (!id) return
  const payload = { actor: shell.actor.value, note: note.value, source: MOBILE_ACTION_SOURCE, idempotency_key: makeIdempotencyKey(`order:${id}`), items: orderItems.value }
  actionBusy.value = true
  try {
    await postMobileOrderStubs(id, payload)
    actionMessage.value = '已生成待执行医嘱草稿'
    resetActionState()
  } catch {
    enqueueMobileAction('order_stub', { alertId: id, body: payload })
    actionMessage.value = '网络异常，医嘱草稿已加入离线队列'
  } finally {
    actionBusy.value = false
  }
}

async function createReviewReminder() {
  const id = alertIdOf(selected.value)
  if (!id) return
  const payload = { actor: shell.actor.value, note: note.value, source: MOBILE_ACTION_SOURCE, review_after_minutes: 60, idempotency_key: makeIdempotencyKey(`review:${id}`) }
  actionBusy.value = true
  try {
    const res = await postMobileReviewReminder(id, payload)
    const dueAt = res.data?.reminder?.due_at
    if (dueAt) scheduleMobileNotification('告警复评提醒', `${bedOf(selected.value)} ${alertTitleOf(selected.value)}`, dueAt)
    updateSelectedAlert({ review_status: 'pending', ack_disposition: 'review_later' })
    actionMessage.value = '已设置1小时复评'
    resetActionState()
  } catch {
    enqueueMobileAction('review_reminder', { alertId: id, body: payload })
    actionMessage.value = '网络异常，复评提醒已加入离线队列'
  } finally {
    actionBusy.value = false
  }
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
  registerMobileNotifications()
  offAlert = onAlertMessage(applyRealtimeAlert)
  window.addEventListener('mobile:refresh', refreshFromShell)
})

onUnmounted(() => {
  offAlert?.()
  window.removeEventListener('mobile:refresh', refreshFromShell)
})
</script>
