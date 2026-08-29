<template>
  <div class="patient-detail-layout" :class="{ 'layout-compact': densityMode === 'compact' }">
    <!-- 顶部：患者身份 + 安全条 + 导航 -->
    <header class="layout-header">
      <PatientHeaderBar
        :patient="patient"
        :vitals="vitals"
        :bedcard="bedcard"
        :alerts="alerts"
        :loading="!patient"
        @density-change="densityMode = $event as 'compact' | 'full'"
        @back="goBack"
      />
      <!-- 安全条：过敏、隔离、机械通气、CRRT -->
      <div v-if="safetyItems.length" class="safety-strip">
        <span v-for="item in safetyItems" :key="item.key" :class="['safety-tag', `safety-${item.level}`]">
          {{ item.text }}
        </span>
      </div>
      <nav class="layout-nav">
        <router-link
          v-for="tab in navTabs"
          :key="tab.key"
          :to="tab.to"
          class="nav-item"
          active-class="nav-item--active"
        >
          <span class="nav-icon">{{ tab.icon }}</span>
          <span class="nav-label">{{ tab.label }}</span>
          <span v-if="tab.badge" class="nav-badge">{{ tab.badge }}</span>
        </router-link>
        <a-button size="small" class="nav-summary-btn" @click="loadClinicalSummary" :loading="clinicalSummaryLoading">
          生成查房摘要
        </a-button>
      </nav>
    </header>

    <!-- 主体：子路由渲染区 -->
    <main class="layout-main">
      <router-view v-slot="{ Component }">
        <keep-alive :include="cachedViews">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </main>

    <!-- 证据弹窗 -->
    <a-modal
      :open="evidenceModalOpen"
      :title="evidenceModal?.title || '证据详情'"
      @cancel="evidenceModalOpen = false"
      :footer="null"
      width="640px"
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
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { usePatientDetail } from '../../composables/usePatientDetail'
import PatientHeaderBar from './components/PatientHeaderBar.vue'

const router = useRouter()
const {
  patient, vitals, bedcard, alerts,
  clinicalSummaryLoading, loadClinicalSummary,
  evidenceModalOpen, evidenceModal,
  initLifecycle, cleanupLifecycle,
} = usePatientDetail()

const densityMode = ref<'compact' | 'full'>('full')
const cachedViews = ref(['PatientOverviewView', 'PatientMonitoringView'])

// 安全条：过敏、隔离、机械通气、CRRT
const safetyItems = computed(() => {
  const items: Array<{ key: string; text: string; level: 'danger' | 'warning' | 'info' }> = []
  const p = patient.value || {}
  if (p.allergies || p.allergyText) items.push({ key: 'allergy', text: `过敏：${p.allergies || p.allergyText}`, level: 'danger' })
  if (p.isolation || p.isolationType) items.push({ key: 'isolation', text: `隔离：${p.isolation || p.isolationType}`, level: 'warning' })
  if (p.ventilator || p.mechanicalVentilation) items.push({ key: 'vent', text: '机械通气', level: 'info' })
  if (p.crrt || p.crrtActive) items.push({ key: 'crrt', text: 'CRRT', level: 'info' })
  return items
})

const navTabs = computed(() => {
  const id = patient.value?._id || patient.value?.id || ''
  const base = id ? `/patient/${id}` : ''
  const alertCount = alerts.value?.length || 0
  return [
    { key: 'overview', icon: '📋', label: '总览', to: `${base}/overview` },
    { key: 'monitoring', icon: '📈', label: '监测', to: `${base}/monitoring` },
    { key: 'treatment', icon: '💊', label: '治疗与护理', to: `${base}/treatment` },
    { key: 'alerts', icon: '🚨', label: '预警与决策', to: `${base}/alerts`, badge: alertCount > 0 ? alertCount : undefined },
    { key: 'documents', icon: '📑', label: '文书与AI', to: `${base}/documents` },
    { key: 'intelligence', icon: '🤖', label: 'AI分析', to: `${base}/intelligence` },
    { key: 'followup', icon: '📋', label: '随访管理', to: `${base}/followup` },
  ]
})

function goBack() {
  router.push('/')
}

onMounted(() => { initLifecycle() })
onBeforeUnmount(() => { cleanupLifecycle() })
</script>

<style scoped>
.patient-detail-layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: #f5f6fa;
}

.layout-header {
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  position: sticky;
  top: 0;
  z-index: 100;
}

.layout-nav {
  display: flex;
  gap: 2px;
  padding: 0 24px;
  border-top: 1px solid #f0f0f0;
  background: #fafbfc;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  font-size: 13px;
  color: #666;
  text-decoration: none;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
  position: relative;
}

.nav-item:hover {
  color: #1890ff;
  background: #f0f7ff;
}

.nav-item--active {
  color: #1890ff;
  border-bottom-color: #1890ff;
  font-weight: 600;
}

.nav-icon {
  font-size: 15px;
}

.nav-badge {
  background: #ff4d4f;
  color: #fff;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 10px;
  min-width: 18px;
  text-align: center;
}

.layout-main {
  flex: 1;
  padding: 16px 24px 32px;
  max-width: 1400px;
  width: 100%;
  margin: 0 auto;
}

.layout-compact .layout-main {
  padding: 8px 16px 24px;
}

/* Safety strip */
.safety-strip {
  display: flex;
  gap: 8px;
  padding: 4px 24px;
  background: #fffbe6;
  border-top: 1px solid #f0f0f0;
  flex-wrap: wrap;
}

.safety-tag {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
}

.safety-danger { background: #fff1f0; color: #ff4d4f; border: 1px solid #ffa39e; }
.safety-warning { background: #fffbe6; color: #faad14; border: 1px solid #ffe58f; }
.safety-info { background: #e6f7ff; color: #1890ff; border: 1px solid #91d5ff; }

/* Nav summary button */
.nav-summary-btn {
  margin-left: auto;
  align-self: center;
  position: relative;
  z-index: 10;
  pointer-events: auto;
}

/* Evidence modal */
.evidence-modal-body {
  max-height: 60vh;
  overflow-y: auto;
}

.evidence-source {
  font-size: 12px;
  color: #999;
  margin-bottom: 12px;
}

.evidence-content {
  font-size: 14px;
  line-height: 1.8;
  color: #333;
}

.evidence-tags {
  margin-top: 12px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
</style>

