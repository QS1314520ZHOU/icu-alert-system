<template>
  <div class="ai-pulse-root">
    <transition name="pulse-slide">
      <div
        v-if="activePulse"
        :class="['pulse-card', `tone-${activePulse.tone}`]"
        @mouseenter="paused = true"
        @mouseleave="paused = false"
      >
        <div class="pulse-card__bar"></div>
        <div class="pulse-card__head">
          <span class="pulse-source">{{ sourceLabel(activePulse.source) }}</span>
          <button class="pulse-icon-btn" type="button" @click="dismiss(activePulse)">×</button>
        </div>
        <div class="pulse-card__headline">{{ activePulse.headline }}</div>
        <div class="pulse-card__action">{{ activePulse.action_hint }}</div>
        <div class="pulse-card__cta">
          <button class="pulse-primary" type="button" @click="openDeepLink(activePulse)">去处理</button>
        </div>
      </div>
    </transition>

    <button class="pulse-fab" type="button" @click="toggleHistory">
      <span class="fab-icon">AI</span>
      <span v-if="unreadCount" class="fab-badge">{{ unreadCount }}</span>
    </button>

    <transition name="pulse-history-pop">
      <div v-if="showHistory" class="pulse-history">
        <div class="pulse-history__head">
          <strong>AI提醒</strong>
          <span>24小时内</span>
        </div>
        <div v-if="!history.length" class="pulse-history__empty">暂无主动提醒</div>
        <button
          v-for="item in history"
          :key="item.candidate_id"
          type="button"
          :class="['pulse-history__item', `tone-${item.tone}`]"
          @click="openDeepLink(item)"
        >
          <span>{{ sourceLabel(item.source) }}</span>
          <strong>{{ item.headline }}</strong>
          <em>{{ item.action_hint }}</em>
        </button>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { usePulseStore, type PulseNarration } from '../stores/pulse'

const route = useRoute()
const router = useRouter()
const store = usePulseStore()
const { activePulse, history, unreadCount } = storeToRefs(store)
const showHistory = ref(false)
const paused = ref(false)
let hideTimer: number | null = null
let contextTimer: number | null = null
let lastContextKey = ''

const currentPatientId = computed(() => {
  if (route.name === 'patient-detail') return String(route.params.id || '')
  return String(route.query.patient_id || route.query.patientId || '')
})

const currentDeptCode = computed(() => String(route.query.dept_code || route.query.deptCode || '').trim())

function sourceLabel(source: string) {
  const labels: Record<string, string> = {
    alert: '预警',
    reasoning: 'AI结论',
    lab_drug_mismatch: '药敏',
    mdt_overdue: 'MDT',
    mdt: 'MDT',
  }
  return labels[source] || 'AI'
}

function dismiss(item: PulseNarration) {
  store.dismiss(item.candidate_id)
}

function openDeepLink(item: PulseNarration) {
  store.click(item.candidate_id)
  store.activePulse = null
  showHistory.value = false
  router.push(item.deep_link)
}

function toggleHistory() {
  showHistory.value = !showHistory.value
  if (showHistory.value) store.markHistoryRead()
}

function scheduleContextReport() {
  if (contextTimer) window.clearTimeout(contextTimer)
  contextTimer = window.setTimeout(() => {
    const contextKey = [
      route.path,
      currentPatientId.value || '',
      currentDeptCode.value,
      String(route.query.role || 'doctor'),
      String(route.query.userName || ''),
    ].join('|')
    if (contextKey === lastContextKey) return
    lastContextKey = contextKey
    store.reportViewerContext(route.fullPath, currentPatientId.value || null, {
      dept_code: currentDeptCode.value,
      role: route.query.role || 'doctor',
      actor: route.query.userName || '',
    })
  }, 800)
}

function armAutoHide() {
  if (hideTimer) window.clearInterval(hideTimer)
  hideTimer = window.setInterval(() => {
    if (!activePulse.value || paused.value) return
    store.activePulse = null
    if (hideTimer) window.clearInterval(hideTimer)
    hideTimer = null
  }, 12000)
}

watch(currentDeptCode, (value) => store.setCurrentDeptCode(value), { immediate: true })
watch(() => route.fullPath, scheduleContextReport, { immediate: true })
watch(activePulse, (value) => {
  if (value) armAutoHide()
})

onMounted(() => {
  store.connect()
  scheduleContextReport()
})

onUnmounted(() => {
  if (hideTimer) window.clearInterval(hideTimer)
  if (contextTimer) window.clearTimeout(contextTimer)
})
</script>

<style scoped>
.ai-pulse-root {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 3000;
  display: grid;
  justify-items: end;
  gap: 12px;
  pointer-events: none;
}
.pulse-card,
.pulse-fab,
.pulse-history {
  pointer-events: auto;
}
.pulse-card {
  position: relative;
  width: 320px;
  overflow: hidden;
  border-radius: var(--card-radius);
  border: 1px solid rgba(103, 232, 249, 0.18);
  background: var(--bg-surface), var(--bg-surface));
  box-shadow: var(--card-shadow);
  padding: 14px 14px 13px 18px;
  color: var(--text-primary);
}
.pulse-card__bar {
  position: absolute;
  inset: 0 auto 0 0;
  width: 4px;
  background: var(--brand);
}
.pulse-card.tone-warn .pulse-card__bar { background: var(--warning); }
.pulse-card.tone-critical .pulse-card__bar { background: var(--danger); }
.pulse-card__head,
.pulse-card__cta,
.pulse-history__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.pulse-source {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 9px;
  border-radius: var(--card-radius);
  border: 1px solid rgba(103, 232, 249, 0.16);
  background: var(--bg-surface), 0.88);
  color: var(--accent);
  font-size: 11px;
  font-weight: 800;
}
.pulse-icon-btn {
  width: 26px;
  height: 26px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: var(--card-radius);
  background: var(--bg-surface), 0.58);
  color: #b8d5e1;
  cursor: pointer;
}
.pulse-card__headline {
  margin-top: 12px;
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 800;
  line-height: 1.45;
}
.pulse-card__action {
  margin-top: 7px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}
.pulse-card__cta {
  margin-top: 12px;
  justify-content: flex-end;
}
.pulse-primary {
  min-height: 30px;
  border: 1px solid rgba(34, 211, 238, 0.32);
  border-radius: var(--card-radius);
  background: var(--bg-surface);
  color: var(--text-primary);
  padding: 0 14px;
  cursor: pointer;
  font-weight: 800;
}
.pulse-fab {
  position: relative;
  width: 52px;
  height: 52px;
  border-radius: var(--card-radius);
  border: 1px solid rgba(103, 232, 249, 0.24);
  background: var(--bg-surface);
  color: var(--text-primary);
  cursor: pointer;
  box-shadow: var(--card-shadow);
  font-weight: 900;
}
.fab-badge {
  position: absolute;
  right: -5px;
  top: -6px;
  min-width: 20px;
  height: 20px;
  padding: 0 5px;
  border-radius: var(--card-radius);
  background: var(--danger);
  color: var(--text-primary);
  font-size: 11px;
  line-height: 20px;
}
.pulse-history {
  width: 320px;
  max-height: 420px;
  overflow: auto;
  border-radius: var(--card-radius);
  border: 1px solid rgba(103, 232, 249, 0.16);
  background: var(--bg-surface), 0.98);
  box-shadow: var(--card-shadow);
  padding: 12px;
}
.pulse-history__head strong {
  color: var(--text-primary);
}
.pulse-history__head span,
.pulse-history__empty {
  color: var(--accent);
  font-size: 12px;
}
.pulse-history__item {
  width: 100%;
  display: grid;
  gap: 5px;
  text-align: left;
  margin-top: 8px;
  padding: 10px;
  border-radius: var(--card-radius);
  border: 1px solid rgba(103, 232, 249, 0.12);
  background: var(--bg-surface), 0.82);
  cursor: pointer;
}
.pulse-history__item span { color: var(--accent); font-size: 10px; }
.pulse-history__item strong { color: var(--text-primary); font-size: 12px; line-height: 1.45; }
.pulse-history__item em { color: var(--text-secondary); font-size: 11px; font-style: normal; }
html[data-theme='light'] .pulse-card {
  border-color: rgba(59, 130, 246, 0.2);
  background:
    var(--bg-surface), transparent 38%),
    var(--bg-surface), rgba(248, 251, 255, 0.98));
  box-shadow: var(--card-shadow);
  color: var(--text-primary);
}
html[data-theme='light'] .pulse-source {
  border-color: rgba(59, 130, 246, 0.18);
  background: rgba(239, 246, 255, 0.98);
  color: var(--brand);
}
html[data-theme='light'] .pulse-icon-btn {
  border-color: rgba(148, 163, 184, 0.26);
  background: rgba(255, 255, 255, 0.9);
  color: var(--text-secondary);
}
html[data-theme='light'] .pulse-card__headline,
html[data-theme='light'] .pulse-history__head strong,
html[data-theme='light'] .pulse-history__item strong {
  color: var(--text-primary);
}
html[data-theme='light'] .pulse-card__action,
html[data-theme='light'] .pulse-history__item em {
  color: var(--text-secondary);
}
html[data-theme='light'] .pulse-primary {
  border-color: rgba(37, 99, 235, 0.32);
  background: var(--bg-surface);
  color: var(--text-primary);
}
html[data-theme='light'] .pulse-fab {
  border-color: rgba(37, 99, 235, 0.22);
  background: var(--bg-surface);
  box-shadow: var(--card-shadow);
}
html[data-theme='light'] .pulse-history {
  border-color: rgba(148, 163, 184, 0.24);
  background: rgba(255, 255, 255, 0.98);
  box-shadow: var(--card-shadow);
}
html[data-theme='light'] .pulse-history__head span,
html[data-theme='light'] .pulse-history__empty {
  color: var(--text-secondary);
}
html[data-theme='light'] .pulse-history__item {
  border-color: rgba(148, 163, 184, 0.22);
  background: rgba(248, 251, 255, 0.98);
}
html[data-theme='light'] .pulse-history__item span {
  color: var(--brand);
}
.pulse-slide-enter-active,
.pulse-slide-leave-active,
.pulse-history-pop-enter-active,
.pulse-history-pop-leave-active {
  transition: all 0.22s ease;
}
.pulse-slide-enter-from,
.pulse-slide-leave-to {
  opacity: 0;
  transform: translateX(34px);
}
.pulse-history-pop-enter-from,
.pulse-history-pop-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
@media (max-width: 640px) {
  .ai-pulse-root { right: 12px; bottom: 12px; }
  .pulse-card,
  .pulse-history { width: min(320px, calc(100vw - 24px)); }
}
</style>
