<template>
  <div class="patient-detail-layout" :class="{ 'layout-compact': densityMode === 'compact' }">
    <!-- 顶部患者上下文条 -->
    <header class="layout-context-bar">
      <div class="context-bar__left">
        <button class="context-bar__back" @click="goBack">← 返回</button>
        <div class="context-bar__identity">
          <span class="context-bar__name">{{ displayName }}</span>
          <span class="context-bar__meta">
            <span class="context-bar__bed">{{ displayBed }}床</span>
            <span class="context-bar__sep">·</span>
            <span>{{ displayDept }}</span>
            <span class="context-bar__sep">·</span>
            <span>{{ displayGenderAge }}</span>
          </span>
        </div>
      </div>
      <div class="context-bar__right">
        <!-- 体征快览（恢复自 PatientHeaderBar 拆分前的 header 体征展示） -->
        <div class="context-bar__vitals">
          <span v-for="v in quickVitals" :key="v.label" class="vital-chip" :class="`vital-${v.tone}`">
            <span class="vital-label">{{ v.label }}</span>
            <span class="vital-value">{{ v.value }}</span>
          </span>
        </div>
        <!-- 床旁卡：器械 / 管路概览 -->
        <span v-if="bedcardSummary" class="context-bar__bedcard" title="床旁器械与管路">
          器械 {{ bedcardSummary.devices }} · 管路 {{ bedcardSummary.tubes }}
        </span>
        <span class="context-bar__risk" :class="`risk-${primaryRiskLevel}`" @click="openEvidenceDrawer('risk', { title: '风险证据链' })" style="cursor: pointer;">
          {{ primaryRiskLabel }}
        </span>
        <span class="context-bar__time">数据 {{ heroMonitorUpdatedAt }}</span>
        <a-button
          size="small"
          class="context-bar__summary-btn"
          :loading="clinicalSummaryLoading"
          @click="loadClinicalSummary"
        >
          生成查房摘要
        </a-button>
        <button
          class="context-bar__btn context-bar__btn--density"
          :title="densityMode === 'compact' ? '切换为完整密度' : '切换为紧凑密度'"
          @click="toggleDensity"
        >
          {{ densityMode === 'compact' ? '标准' : '紧凑' }}
        </button>
        <button class="context-bar__btn" @click="refreshData" title="刷新" aria-label="刷新">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg>
        </button>
      </div>
    </header>

    <!-- 安全条 -->
    <div v-if="safetyItems.length" class="safety-strip">
      <span v-for="item in safetyItems" :key="item.key" :class="['safety-tag', `safety-${item.level}`]">
        <span class="safety-icon">{{ item.level === 'danger' ? '✕' : item.level === 'warning' ? '⚠' : 'ℹ' }}</span>
        {{ item.text }}
      </span>
    </div>

    <!-- 主内容区（侧边栏已移至全局 SideNav） -->
    <main class="layout-main">
      <router-view v-slot="{ Component }">
        <keep-alive :include="cachedViews">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </main>

    <!-- 证据抽屉 -->
    <ClinicalEvidenceDrawer
      :open="evidenceDrawerOpen"
      :patient-id="evidenceDrawerPatientId"
      :context-type="evidenceDrawerContextType"
      :context-id="evidenceDrawerContextId"
      :organ-system="evidenceDrawerOrganSystem"
      :title="evidenceDrawerTitle"
      include-ai
      @close="evidenceDrawerOpen = false"
    />

    <!-- 证据弹窗（知识库 chunk，含 tags；子视图 openEvidence 写入此状态） -->
    <a-modal
      :open="evidenceModalOpen"
      :title="evidenceModal?.title || '证据详情'"
      :footer="null"
      width="640px"
      @cancel="evidenceModalOpen = false"
    >
      <div v-if="evidenceModal" class="evidence-modal-body">
        <p v-if="evidenceModal.source" class="evidence-source">来源：{{ evidenceModal.source }}</p>
        <div class="evidence-content" v-html="evidenceModal.content"></div>
        <div v-if="evidenceModal.tags?.length" class="evidence-tags">
          <a-tag v-for="tag in evidenceModal.tags" :key="tag">{{ tag }}</a-tag>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, provide } from 'vue'
import { Button as AButton, Modal as AModal, Tag as ATag } from 'ant-design-vue'
import { usePatientDetail } from '../../composables/usePatientDetail'
import { useAppNavigation } from '../../navigation/useAppNavigation'
import ClinicalEvidenceDrawer from '../../components/evidence/ClinicalEvidenceDrawer.vue'
import type { ContextType, OrganSystem } from '../../api/clinicalEvidence'

const { navigateBack } = useAppNavigation()
const {
  patient, alerts, vitals, bedcard,
  displayName, displayBed, displayDept, displayGenderAge,
  heroMonitorUpdatedAt,
  clinicalSummaryLoading, loadClinicalSummary,
  evidenceModalOpen, evidenceModal,
  initLifecycle, cleanupLifecycle,
} = usePatientDetail()

// 证据抽屉状态
const evidenceDrawerOpen = ref(false)
const evidenceDrawerPatientId = ref('')
const evidenceDrawerContextType = ref<ContextType>('risk')
const evidenceDrawerContextId = ref('')
const evidenceDrawerOrganSystem = ref<OrganSystem | undefined>(undefined)
const evidenceDrawerTitle = ref('')

function openEvidenceDrawer(contextType: ContextType, opts?: { contextId?: string; organSystem?: OrganSystem; title?: string }) {
  const pid = patient.value?._id || patient.value?.id || ''
  if (!pid) return
  evidenceDrawerPatientId.value = pid
  evidenceDrawerContextType.value = contextType
  evidenceDrawerContextId.value = opts?.contextId || ''
  evidenceDrawerOrganSystem.value = opts?.organSystem
  evidenceDrawerTitle.value = opts?.title || '临床证据'
  evidenceDrawerOpen.value = true
}

// 向子组件提供证据抽屉方法
provide('openEvidenceDrawer', openEvidenceDrawer)

const densityMode = ref<'compact' | 'full'>('full')
const cachedViews = ref(['PatientOverviewView', 'PatientMonitoringView'])

function toggleDensity() {
  densityMode.value = densityMode.value === 'compact' ? 'full' : 'compact'
}

// ── header 体征快览 / 床旁卡 ─────────────────────

const quickVitals = computed(() => {
  const v: any = vitals.value || {}
  return [
    { label: 'HR', value: v.hr ?? '—', tone: hrTone(v.hr) },
    { label: 'MAP', value: v.ibp_map ?? v.nibp_map ?? '—', tone: mapTone(v.ibp_map ?? v.nibp_map) },
    { label: 'SpO₂', value: v.spo2 != null ? `${v.spo2}%` : '—', tone: spo2Tone(v.spo2) },
  ]
})

function hrTone(v: any) { if (v == null) return 'default'; return v > 120 || v < 50 ? 'critical' : v > 100 || v < 60 ? 'warning' : 'normal' }
function mapTone(v: any) { if (v == null) return 'default'; return v < 55 ? 'critical' : v < 65 ? 'warning' : 'normal' }
function spo2Tone(v: any) { if (v == null) return 'default'; return v < 88 ? 'critical' : v < 92 ? 'warning' : 'normal' }

const bedcardSummary = computed(() => {
  const b: any = bedcard.value
  if (!b) return null
  const devices = Array.isArray(b.devices) ? b.devices.length : 0
  const tubes = Array.isArray(b.tubes) ? b.tubes.length : 0
  if (!devices && !tubes) return null
  return { devices, tubes }
})

// ── 风险等级 ─────────────────────────────────────

const primaryRiskLevel = computed(() => {
  const a = alerts.value
  if (!a?.length) {
    const lv = String((patient.value as any)?.alertLevel || '').toLowerCase()
    return ['critical', 'high', 'warning'].includes(lv) ? lv : 'stable'
  }
  const hasCritical = a.some((x: any) => x.severity === 'critical')
  if (hasCritical) return 'critical'
  const hasHigh = a.some((x: any) => x.severity === 'high')
  if (hasHigh) return 'high'
  const hasWarning = a.some((x: any) => x.severity === 'warning')
  if (hasWarning) return 'warning'
  return 'stable'
})

const primaryRiskLabel = computed(() => {
  const labels: Record<string, string> = {
    critical: '危急', high: '高风险', warning: '预警', stable: '无预警',
  }
  return labels[primaryRiskLevel.value] || '无预警'
})

// ── 安全条 ───────────────────────────────────────

const safetyItems = computed(() => {
  const items: Array<{ key: string; text: string; level: 'danger' | 'warning' | 'info' }> = []
  const p = patient.value || {}
  if (p.allergies || p.allergyText) items.push({ key: 'allergy', text: `过敏：${p.allergies || p.allergyText}`, level: 'danger' })
  if (p.isolation || p.isolationType) items.push({ key: 'isolation', text: `隔离：${p.isolation || p.isolationType}`, level: 'warning' })
  if (p.ventilator || p.mechanicalVentilation) items.push({ key: 'vent', text: '机械通气', level: 'info' })
  if (p.crrt || p.crrtActive) items.push({ key: 'crrt', text: 'CRRT', level: 'info' })
  return items
})

// ── 导航 ─────────────────────────────────────────

function goBack() {
  navigateBack()
}

function refreshData() {
  window.location.reload()
}

onMounted(() => { initLifecycle() })
onBeforeUnmount(() => { cleanupLifecycle() })
</script>

<style scoped>
.patient-detail-layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: var(--color-bg-page);
}

/* ── 顶部上下文条 ────────────────────────────── */

.layout-context-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 24px;
  background: var(--color-bg-surface);
  border-bottom: 1px solid var(--color-border);
  position: sticky;
  top: 0;
  z-index: 100;
}

.context-bar__left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.context-bar__back {
  padding: 4px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-surface);
  font-size: var(--text-label);
  font-weight: var(--weight-medium);
  color: var(--color-text-secondary);
  cursor: pointer;
}

.context-bar__back:hover {
  background: var(--color-bg-inset);
}

.context-bar__identity {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.context-bar__name {
  font-size: var(--text-section-title);
  font-weight: var(--weight-bold);
  color: var(--color-text-primary);
}

.context-bar__meta {
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
  display: flex;
  gap: 4px;
}

.context-bar__bed {
  font-weight: var(--weight-semibold);
  color: var(--color-primary);
}

.context-bar__sep {
  color: var(--color-border-strong);
}

.context-bar__right {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* ── 体征快览 ──────────────────────────────────── */

.context-bar__vitals {
  display: flex;
  gap: 8px;
}

.vital-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 2px 8px;
  border-radius: var(--radius-md);
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  line-height: 1.3;
}

.vital-label {
  font-size: var(--text-label);
  color: var(--color-text-tertiary);
  font-weight: var(--weight-medium);
}

.vital-value {
  font-size: var(--text-card-title);
  font-variant-numeric: tabular-nums;
  font-weight: var(--weight-bold);
  color: var(--color-text-primary);
}

.vital-critical .vital-value { color: var(--color-critical); }
.vital-warning .vital-value { color: var(--color-warning); }
.vital-normal .vital-value { color: var(--color-normal); }

.context-bar__bedcard {
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
  padding: 3px 8px;
  border-radius: var(--radius-tag);
  background: var(--color-bg-surface-secondary);
  border: 1px solid var(--color-border);
  white-space: nowrap;
}

.context-bar__summary-btn {
  font-size: var(--text-label);
}

.context-bar__btn.context-bar__btn--density {
  width: auto;
  white-space: nowrap;
  padding: 0 8px;
  font-size: var(--text-label);
}

.context-bar__risk {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: var(--radius-tag);
  font-size: var(--text-label);
  font-weight: var(--weight-semibold);
  border: 1px solid transparent;
}

.risk-critical { background: var(--color-critical-bg); color: var(--color-critical); border-color: var(--color-critical-border); }
.risk-high { background: var(--color-high-risk-bg); color: var(--color-high-risk); border-color: var(--color-high-risk-border); }
.risk-warning { background: var(--color-warning-soft-bg); color: var(--color-warning); border-color: var(--color-warning-soft-border); }
.risk-stable { background: var(--color-normal-bg); color: var(--color-normal); border-color: var(--color-normal-border); }

.context-bar__time {
  font-size: var(--text-caption);
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
}

.context-bar__btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-surface);
  cursor: pointer;
  font-size: var(--text-body);
  color: var(--color-text-secondary);
}

.context-bar__btn:hover {
  background: var(--color-bg-inset);
}

/* ── 安全条 ──────────────────────────────────── */

.safety-strip {
  display: flex;
  gap: 10px;
  padding: 6px 24px;
  background: var(--color-bg-surface-secondary);
  border-bottom: 1px solid var(--color-border);
  flex-wrap: wrap;
  align-items: center;
}

.safety-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--text-label);
  padding: 3px 10px;
  border-radius: 999px;
  font-weight: var(--weight-medium);
  line-height: 1.4;
  border: 1px solid transparent;
}

.safety-icon {
  font-size: var(--text-caption);
  line-height: 1;
}

.safety-danger {
  background: var(--color-critical-bg);
  color: var(--color-critical);
  border-color: var(--color-critical-border);
}

.safety-warning {
  background: var(--color-warning-soft-bg);
  color: var(--color-warning);
  border-color: var(--color-warning-soft-border);
}

.safety-info {
  background: var(--color-info-bg);
  color: var(--color-info);
  border-color: var(--color-info-border);
}

/* ── 主内容区 ────────────────────────────────── */

.layout-main {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px 16px 24px;
  box-sizing: border-box;
}

/* ── 紧凑密度 ──────────────────────────────────── */

.layout-compact .layout-context-bar {
  padding: 6px 24px;
}

.layout-compact .safety-strip {
  padding: 3px 24px;
}

/* ── 证据弹窗 ──────────────────────────────────── */

.evidence-modal-body {
  max-height: 60vh;
  overflow-y: auto;
}

.evidence-source {
  font-size: var(--text-caption);
  color: var(--color-text-tertiary);
  margin-bottom: 12px;
}

.evidence-content {
  font-size: var(--text-body);
  line-height: 1.8;
  color: var(--color-text-primary);
}

.evidence-tags {
  margin-top: 12px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
</style>