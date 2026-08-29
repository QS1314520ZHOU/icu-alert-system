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
        <span class="context-bar__risk" :class="`risk-${primaryRiskLevel}`" @click="openEvidenceDrawer('risk', { title: '风险证据链' })" style="cursor: pointer;">
          {{ primaryRiskLabel }}
        </span>
        <span class="context-bar__time">数据 {{ heroMonitorUpdatedAt }}</span>
        <button class="context-bar__btn" @click="refreshData" title="刷新">↻</button>
      </div>
    </header>

    <!-- 安全条 -->
    <div v-if="safetyItems.length" class="safety-strip">
      <span v-for="item in safetyItems" :key="item.key" :class="['safety-tag', `safety-${item.level}`]">
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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, provide } from 'vue'
import { usePatientDetail } from '../../composables/usePatientDetail'
import { useAppNavigation } from '../../navigation/useAppNavigation'
import ClinicalEvidenceDrawer from '../../components/evidence/ClinicalEvidenceDrawer.vue'
import type { ContextType, OrganSystem } from '../../api/clinicalEvidence'

const { navigateBack } = useAppNavigation()
const {
  patient, alerts,
  displayName, displayBed, displayDept, displayGenderAge,
  heroMonitorUpdatedAt,
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

// ── 风险等级 ─────────────────────────────────────

const primaryRiskLevel = computed(() => {
  const a = alerts.value
  if (!a?.length) return 'stable'
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
    critical: '危急', high: '高风险', warning: '预警', stable: '稳定',
  }
  return labels[primaryRiskLevel.value] || '稳定'
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
  background: var(--page-bg, #F4F7FB);
}

/* ── 顶部上下文条 ────────────────────────────── */

.layout-context-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 20px;
  background: #fff;
  border-bottom: 1px solid var(--border, #DCE3EC);
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
  border: 1px solid var(--border, #DCE3EC);
  border-radius: 4px;
  background: #fff;
  font-size: 12px;
  color: var(--text-secondary, #52606D);
  cursor: pointer;
}

.context-bar__back:hover {
  background: var(--hover-bg, #F0F6FF);
}

.context-bar__identity {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.context-bar__name {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary, #182230);
}

.context-bar__meta {
  font-size: 11px;
  color: var(--text-secondary, #52606D);
  display: flex;
  gap: 4px;
}

.context-bar__bed {
  font-weight: 600;
  color: var(--primary, #2563EB);
}

.context-bar__sep {
  color: var(--border, #DCE3EC);
}

.context-bar__right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.context-bar__risk {
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.risk-critical { background: #FEF2F2; color: #991B1B; }
.risk-high { background: #FEF2F2; color: #DC2626; }
.risk-warning { background: #FFFBEB; color: #92400E; }
.risk-stable { background: #F0FDF4; color: #16A34A; }

.context-bar__time {
  font-size: 11px;
  color: var(--text-tertiary, #94A3B8);
}

.context-bar__btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border, #DCE3EC);
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  font-size: 14px;
  color: var(--text-secondary, #52606D);
}

.context-bar__btn:hover {
  background: var(--hover-bg, #F0F6FF);
}

/* ── 安全条 ──────────────────────────────────── */

.safety-strip {
  display: flex;
  gap: 8px;
  padding: 4px 20px;
  background: #FFFBEB;
  border-bottom: 1px solid #FDE68A;
  flex-wrap: wrap;
}

.safety-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 3px;
  font-weight: 500;
}

.safety-danger { background: #FEF2F2; color: #991B1B; }
.safety-warning { background: #FFFBEB; color: #92400E; }
.safety-info { background: #EFF6FF; color: #1E40AF; }

/* ── 主内容区 ────────────────────────────────── */

.layout-main {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
</style>
