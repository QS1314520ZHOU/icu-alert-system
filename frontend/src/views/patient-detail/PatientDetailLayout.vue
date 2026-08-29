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
        <span class="context-bar__risk" :class="`risk-${primaryRiskLevel}`">
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

    <!-- 主体：侧边栏 + 内容 -->
    <div class="layout-body">
      <!-- 左侧分组菜单 -->
      <aside class="layout-sidebar" :class="{ 'layout-sidebar--collapsed': sidebarCollapsed }">
        <button class="sidebar-toggle" @click="sidebarCollapsed = !sidebarCollapsed">
          {{ sidebarCollapsed ? '→' : '←' }}
        </button>
        <nav class="sidebar-nav">
          <div v-for="group in menuGroups" :key="group.key" class="sidebar-group">
            <div v-if="!sidebarCollapsed" class="sidebar-group__label" @click="toggleGroup(group.key)">
              <span class="sidebar-group__icon">{{ group.icon }}</span>
              <span class="sidebar-group__text">{{ group.label }}</span>
              <span class="sidebar-group__arrow" :class="{ 'sidebar-group__arrow--open': expandedGroups.has(group.key) }">▾</span>
            </div>
            <div v-if="sidebarCollapsed || expandedGroups.has(group.key)" class="sidebar-group__items">
              <router-link
                v-for="item in group.items"
                :key="item.key"
                :to="item.route"
                class="sidebar-item"
                :class="{ 'sidebar-item--active': isActiveRoute(item.key), 'sidebar-item--risk': item.badge === 'risk' }"
                :title="sidebarCollapsed ? item.title : undefined"
              >
                <span class="sidebar-item__icon">{{ item.icon }}</span>
                <span v-if="!sidebarCollapsed" class="sidebar-item__text">{{ item.title }}</span>
                <span v-if="item.badge === 'risk' && !sidebarCollapsed" class="sidebar-item__badge sidebar-item__badge--risk">!</span>
                <span v-if="item.badge === 'ai' && !sidebarCollapsed" class="sidebar-item__badge sidebar-item__badge--ai">AI</span>
              </router-link>
            </div>
          </div>
        </nav>
      </aside>

      <!-- 主内容区 -->
      <main class="layout-main">
        <router-view v-slot="{ Component }">
          <keep-alive :include="cachedViews">
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </main>
    </div>

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
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { usePatientDetail } from '../../composables/usePatientDetail'
import { MODULE_GROUPS, getModuleByKey } from '../../config/patientModuleRegistry'

const router = useRouter()
const route = useRoute()
const {
  patient, vitals, bedcard, alerts,
  displayName, displayBed, displayDept, displayGenderAge,
  heroMonitorUpdatedAt, clinicalSummaryLoading, loadClinicalSummary,
  evidenceModalOpen, evidenceModal,
  initLifecycle, cleanupLifecycle,
} = usePatientDetail()

const densityMode = ref<'compact' | 'full'>('full')
const sidebarCollapsed = ref(false)
const cachedViews = ref(['PatientOverviewView', 'PatientMonitoringView'])
const expandedGroups = ref(new Set(['patient-detail', 'alert-decision']))

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

// ── 菜单 ─────────────────────────────────────────

interface MenuItem {
  key: string
  title: string
  icon: string
  route: string
  badge?: 'risk' | 'ai' | 'new'
}

interface MenuGroup {
  key: string
  label: string
  icon: string
  items: MenuItem[]
}

const menuGroups = computed<MenuGroup[]>(() => {
  const pid = patient.value?._id || patient.value?.id || ''
  if (!pid) return []

  return MODULE_GROUPS.map(group => ({
    key: group.key,
    label: group.label,
    icon: group.icon,
    items: group.modules.map(mod => ({
      key: mod.moduleKey,
      title: mod.title,
      icon: mod.icon,
      route: mod.route.replace(':patientId', pid),
      badge: mod.badge,
    })),
  }))
})

function toggleGroup(key: string) {
  if (expandedGroups.value.has(key)) {
    expandedGroups.value.delete(key)
  } else {
    expandedGroups.value.add(key)
  }
}

function isActiveRoute(moduleKey: string): boolean {
  const currentPath = route.path
  const pid = patient.value?._id || patient.value?.id || ''

  // 原生页面
  if (moduleKey === 'overview' && currentPath.includes('/overview')) return true
  if (moduleKey === 'monitoring' && currentPath.includes('/monitoring')) return true
  if (moduleKey === 'treatment' && currentPath.includes('/treatment')) return true
  if (moduleKey === 'alerts' && currentPath.includes('/alerts')) return true

  // 工具模块
  if (currentPath.includes(`/tool/${moduleKey}`)) return true

  return false
}

function goBack() {
  router.push('/')
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

/* ── 主体布局 ────────────────────────────────── */

.layout-body {
  display: flex;
  flex: 1;
  min-height: 0;
}

/* ── 侧边栏 ──────────────────────────────────── */

.layout-sidebar {
  width: 220px;
  min-width: 220px;
  background: var(--nav-bg, #0F1F33);
  border-right: 1px solid rgba(255,255,255,0.06);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  transition: width 0.2s, min-width 0.2s;
}

.layout-sidebar--collapsed {
  width: 52px;
  min-width: 52px;
}

.sidebar-toggle {
  padding: 8px;
  background: transparent;
  border: none;
  color: var(--nav-text, #94A3B8);
  cursor: pointer;
  text-align: center;
  font-size: 14px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}

.sidebar-toggle:hover {
  background: rgba(255,255,255,0.06);
}

.sidebar-nav {
  flex: 1;
  padding: 8px 0;
}

.sidebar-group {
  margin-bottom: 4px;
}

.sidebar-group__label {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  font-size: 11px;
  font-weight: 600;
  color: var(--nav-text, #94A3B8);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  cursor: pointer;
  user-select: none;
}

.sidebar-group__label:hover {
  color: #fff;
}

.sidebar-group__icon {
  font-size: 14px;
}

.sidebar-group__text {
  flex: 1;
}

.sidebar-group__arrow {
  font-size: 10px;
  transition: transform 0.2s;
}

.sidebar-group__arrow--open {
  transform: rotate(180deg);
}

.sidebar-group__items {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.sidebar-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 14px 7px 28px;
  font-size: 13px;
  color: var(--nav-text, #94A3B8);
  text-decoration: none;
  transition: all 0.15s;
  position: relative;
}

.sidebar-item:hover {
  background: rgba(255,255,255,0.06);
  color: #fff;
}

.sidebar-item--active {
  background: rgba(37,99,235,0.15);
  color: #fff;
  font-weight: 500;
}

.sidebar-item--active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 4px;
  bottom: 4px;
  width: 3px;
  background: var(--primary, #2563EB);
  border-radius: 0 2px 2px 0;
}

.sidebar-item--risk {
  color: #FCA5A5;
}

.sidebar-item--risk:hover {
  color: #FCA5A5;
}

.sidebar-item__icon {
  font-size: 15px;
  width: 20px;
  text-align: center;
}

.sidebar-item__text {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar-item__badge {
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 8px;
  font-weight: 700;
}

.sidebar-item__badge--risk {
  background: #DC2626;
  color: #fff;
}

.sidebar-item__badge--ai {
  background: #7C3AED;
  color: #fff;
}

/* ── 主内容 ──────────────────────────────────── */

.layout-main {
  flex: 1;
  padding: 16px 24px 32px;
  overflow-x: hidden;
  overflow-y: auto;
}

.layout-compact .layout-main {
  padding: 8px 16px 24px;
}

/* ── 证据弹窗 ────────────────────────────────── */

.evidence-modal-body {
  max-height: 60vh;
  overflow-y: auto;
}

.evidence-source {
  font-size: 12px;
  color: var(--text-tertiary, #94A3B8);
  margin-bottom: 12px;
}

.evidence-content {
  font-size: 14px;
  line-height: 1.8;
  color: var(--text-primary, #182230);
}

/* ── 响应式 ──────────────────────────────────── */

@media (max-width: 1024px) {
  .layout-sidebar {
    width: 52px;
    min-width: 52px;
  }
  .sidebar-group__label {
    display: none;
  }
  .sidebar-item__text {
    display: none;
  }
  .sidebar-item__badge {
    display: none;
  }
}
</style>
