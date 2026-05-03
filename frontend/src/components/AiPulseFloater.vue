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
          <button class="pulse-icon-btn" type="button" @click="dismiss(activePulse)">x</button>
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
          <strong>AI Pulse</strong>
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

const currentPatientId = computed(() => {
  if (route.name === 'patient-detail') return String(route.params.id || '')
  return String(route.query.patient_id || route.query.patientId || '')
})

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
    store.reportViewerContext(route.fullPath, currentPatientId.value || null, {
      dept_code: route.query.dept_code || route.query.deptCode || '',
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
  border-radius: 12px;
  border: 1px solid rgba(103, 232, 249, 0.18);
  background: linear-gradient(180deg, rgba(8, 26, 43, 0.98), rgba(5, 16, 28, 0.98));
  box-shadow: 0 18px 42px rgba(0, 0, 0, 0.34);
  padding: 14px 14px 13px 18px;
  color: #dffbff;
}
.pulse-card__bar {
  position: absolute;
  inset: 0 auto 0 0;
  width: 4px;
  background: #22d3ee;
}
.pulse-card.tone-warn .pulse-card__bar { background: #f59e0b; }
.pulse-card.tone-critical .pulse-card__bar { background: #fb5a7a; }
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
  border-radius: 999px;
  border: 1px solid rgba(103, 232, 249, 0.16);
  background: rgba(8, 40, 58, 0.88);
  color: #67e8f9;
  font-size: 11px;
  font-weight: 800;
}
.pulse-icon-btn {
  width: 26px;
  height: 26px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.58);
  color: #b8d5e1;
  cursor: pointer;
}
.pulse-card__headline {
  margin-top: 12px;
  color: #effcff;
  font-size: 15px;
  font-weight: 800;
  line-height: 1.45;
}
.pulse-card__action {
  margin-top: 7px;
  color: #9cc9d8;
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
  border-radius: 8px;
  background: linear-gradient(180deg, #0891b2, #0e7490);
  color: #ecfeff;
  padding: 0 14px;
  cursor: pointer;
  font-weight: 800;
}
.pulse-fab {
  position: relative;
  width: 52px;
  height: 52px;
  border-radius: 16px;
  border: 1px solid rgba(103, 232, 249, 0.24);
  background: linear-gradient(180deg, #0b6b89 0%, #07465a 100%);
  color: #ecfeff;
  cursor: pointer;
  box-shadow: 0 14px 28px rgba(0, 0, 0, 0.28);
  font-weight: 900;
}
.fab-badge {
  position: absolute;
  right: -5px;
  top: -6px;
  min-width: 20px;
  height: 20px;
  padding: 0 5px;
  border-radius: 999px;
  background: #fb5a7a;
  color: #fff;
  font-size: 11px;
  line-height: 20px;
}
.pulse-history {
  width: 320px;
  max-height: 420px;
  overflow: auto;
  border-radius: 12px;
  border: 1px solid rgba(103, 232, 249, 0.16);
  background: rgba(5, 16, 28, 0.98);
  box-shadow: 0 18px 42px rgba(0, 0, 0, 0.34);
  padding: 12px;
}
.pulse-history__head strong {
  color: #effcff;
}
.pulse-history__head span,
.pulse-history__empty {
  color: #7ecce1;
  font-size: 12px;
}
.pulse-history__item {
  width: 100%;
  display: grid;
  gap: 5px;
  text-align: left;
  margin-top: 8px;
  padding: 10px;
  border-radius: 10px;
  border: 1px solid rgba(103, 232, 249, 0.12);
  background: rgba(8, 31, 47, 0.82);
  cursor: pointer;
}
.pulse-history__item span { color: #67e8f9; font-size: 10px; }
.pulse-history__item strong { color: #effcff; font-size: 12px; line-height: 1.45; }
.pulse-history__item em { color: #9cc9d8; font-size: 11px; font-style: normal; }
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
