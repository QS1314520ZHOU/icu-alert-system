<template>
  <aside class="side-nav" :class="{ 'side-nav--collapsed': collapsed }">
    <div class="side-nav__header">
      <router-link to="/" class="side-nav__brand">
        <img src="../../favicon.ico" alt="" class="side-nav__logo" />
        <span v-if="!collapsed" class="side-nav__title">SmartCare AI</span>
      </router-link>
      <button class="side-nav__toggle" type="button" @click="toggleCollapse">
        <svg v-if="collapsed" width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M6 4l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <svg v-else width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M10 4l-4 4 4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>
    </div>

    <nav class="side-nav__menu">
      <!-- ═══ 患者模式：返回按钮 + 患者模块 ═══ -->
      <template v-if="isPatientMode">
        <!-- 返回患者列表 -->
        <div class="side-nav__group">
          <button
            class="side-nav__item side-nav__back-btn"
            @click="handleBackToPatients"
            title="返回患者列表"
          >
            <span class="side-nav__icon" v-html="iconSvg('arrow-left')"></span>
            <span v-if="!collapsed" class="side-nav__label">返回患者列表</span>
          </button>
        </div>

        <!-- 患者模块分组 -->
        <div v-for="group in patientNavGroups" :key="group.key" class="side-nav__group">
          <div v-if="!collapsed" class="side-nav__group-label">{{ group.label }}</div>
          <template v-for="item in group.items" :key="item.key">
            <!-- 可展开的子组（如"患者智能分析"） -->
            <template v-if="item.children && item.children.length > 0">
              <button
                :class="['side-nav__item', 'side-nav__expandable', { 'side-nav__item--expanded': expandedGroups.has(item.key) }]"
                @click="toggleExpandGroup(item.key)"
                :title="item.label"
              >
                <span class="side-nav__icon" v-html="iconSvg(item.icon)"></span>
                <span v-if="!collapsed" class="side-nav__label">{{ item.label }}</span>
                <span v-if="!collapsed" class="side-nav__expand-arrow">
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                    <path d="M4 4.5L6 6.5L8 4.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                </span>
              </button>
              <template v-if="expandedGroups.has(item.key) && !collapsed">
                <router-link
                  v-for="child in item.children"
                  :key="child.key"
                  :to="getPatientItemPath(child)"
                  :class="['side-nav__item', 'side-nav__item--sub', { 'side-nav__item--active': isActiveRoute(getPatientItemPath(child)) }]"
                  :title="child.label"
                >
                  <span class="side-nav__icon" v-html="iconSvg(child.icon)"></span>
                  <span class="side-nav__label">{{ child.label }}</span>
                </router-link>
              </template>
            </template>
            <!-- 普通菜单项 -->
            <router-link
              v-else
              :to="getPatientItemPath(item)"
              :class="['side-nav__item', { 'side-nav__item--active': isActiveRoute(getPatientItemPath(item)) }]"
              :title="item.label"
            >
              <span class="side-nav__icon" v-html="iconSvg(item.icon)"></span>
              <span v-if="!collapsed" class="side-nav__label">{{ item.label }}</span>
            </router-link>
          </template>
        </div>
      </template>

      <!-- ═══ 全局模式：统一由 resolveNavigation 生成，所有分组可折叠 ═══ -->
      <template v-else>
        <template v-for="group in globalNavGroups" :key="group.key">
          <div class="side-nav__group">
            <!-- 分组标题：点击折叠/展开 -->
            <button
              v-if="!collapsed"
              class="side-nav__group-label side-nav__group-label--toggle"
              @click="toggleGroupCollapse(group.key)"
            >
              {{ group.label }}
              <span class="side-nav__toggle-arrow" :class="{ 'side-nav__toggle-arrow--open': isGroupExpanded(group.key) }">▸</span>
            </button>
            <!-- 收起态：点击展开该组 -->
            <button
              v-else
              class="side-nav__item"
              :title="group.label"
              @click="toggleGroupCollapse(group.key)"
            >
              <span class="side-nav__icon" v-html="iconSvg(groupIcon(group.key))"></span>
            </button>

            <!-- 组内菜单项 -->
            <div v-show="isGroupExpanded(group.key)">
              <!-- AI 智能分析组：点击需要选患者 -->
              <template v-if="group.key === 'ai-intelligence'">
                <button
                  v-for="item in group.items"
                  :key="item.key"
                  class="side-nav__item"
                  :title="item.label"
                  @click="onGlobalAiClick(item.key)"
                >
                  <span class="side-nav__icon" v-html="iconSvg(item.icon)"></span>
                  <span v-if="!collapsed" class="side-nav__label">{{ item.label }}</span>
                </button>
              </template>

              <!-- 更多组：折叠态侧边栏用 dropdown -->
              <template v-else-if="group.key === 'more' && collapsed">
                <a-dropdown
                  :trigger="['click']"
                  placement="bottomRight"
                  overlay-class-name="side-nav__more-dropdown"
                >
                  <button class="side-nav__item side-nav__more-trigger" title="更多">
                    <span class="side-nav__icon" v-html="iconSvg('more')"></span>
                  </button>
                  <template #overlay>
                    <a-menu>
                      <a-menu-item v-for="item in group.items" :key="item.key">
                        <router-link :to="item.path" class="side-nav__more-item">
                          <span v-html="iconSvg(item.icon)"></span>
                          <span>{{ item.label }}</span>
                        </router-link>
                      </a-menu-item>
                    </a-menu>
                  </template>
                </a-dropdown>
              </template>

              <!-- 普通组 / 更多组展开态 -->
              <template v-else>
                <router-link
                  v-for="item in group.items"
                  :key="item.key"
                  :to="item.path"
                  :class="['side-nav__item', { 'side-nav__item--active': isActiveRoute(item.path) }]"
                  :title="item.label"
                >
                  <span class="side-nav__icon" v-html="iconSvg(item.icon)"></span>
                  <span v-if="!collapsed" class="side-nav__label">{{ item.label }}</span>
                </router-link>
              </template>
            </div>
          </div>
        </template>
      </template>
    </nav>
  </aside>

  <!-- Patient Selector Modal (global mode AI click) — teleported to body -->
  <Teleport to="body">
    <PatientSelectorModal
      :open="showPatientSelector"
      @select="onPatientSelected"
      @cancel="onCancelPatientSelector"
    />
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { usePatientContext } from '../../stores/patientContext'
import { useAuthStore } from '../../stores/auth'
import { resolveNavigation } from '../../navigation/navigationResolver'
import { useAppNavigation } from '../../navigation/useAppNavigation'
import PatientSelectorModal from '../PatientSelectorModal.vue'
import type { NavItem } from '../../navigation/navigationTypes'

const route = useRoute()
const patientCtx = usePatientContext()
const auth = useAuthStore()
const {
  navigateBack,
  navigateToModule: navToModule,
  onPatientSelected,
  onCancelPatientSelector,
  showPatientSelector,
} = useAppNavigation()

const STORAGE_KEY = 'side-nav-collapsed'
const GROUP_STORAGE_KEY = 'side-nav-collapsed-groups'
const collapsed = ref(localStorage.getItem(STORAGE_KEY) === 'true')
const expandedGroups = ref(new Set<string>())

// ── 全局分组折叠状态（默认全部收起） ──
function loadCollapsedGroups(): Set<string> {
  try {
    const saved = localStorage.getItem(GROUP_STORAGE_KEY)
    if (saved) return new Set(JSON.parse(saved))
  } catch {}
  // 默认全部收起
  return new Set(['today', 'patients', 'alerts', 'clinical-knowledge', 'research', 'more', 'ai-intelligence'])
}
const collapsedGlobalGroups = ref(loadCollapsedGroups())
function toggleGroupCollapse(key: string) {
  const set = new Set(collapsedGlobalGroups.value)
  if (set.has(key)) set.delete(key)
  else set.add(key)
  collapsedGlobalGroups.value = set
  localStorage.setItem(GROUP_STORAGE_KEY, JSON.stringify([...set]))
}
function isGroupExpanded(key: string) {
  return !collapsedGlobalGroups.value.has(key)
}

// ── Navigation mode ──
const navigationMode = computed(() => (route.meta?.navigationMode as string) || 'global')
const isPatientMode = computed(() => navigationMode.value === 'patient')

// ── Patient navigation (unified via resolveNavigation) ──
const patientNav = computed(() => {
  return resolveNavigation({
    mode: 'patient',
    role: auth.role,
  })
})

// Convert flat patient nav groups into structured groups with expandable children
const patientNavGroups = computed(() => {
  return patientNav.value.groups.map(group => ({
    key: group.key,
    label: group.label,
    items: group.items.map(item => ({
      ...item,
      children: item.children || [],
    })),
  }))
})

function getPatientItemPath(item: NavItem): string {
  const patientId = patientCtx.activePatientId
  if (!patientId) return '/patients'

  // If the item has a path template, substitute patientId
  if (item.path) {
    return item.path.replace(':patientId', patientId)
  }
  // Default to tool route
  return `/patient/${patientId}/tool/${item.key}`
}

// ── Global navigation (unified via resolveNavigation) ──
const globalResolved = computed(() => {
  return resolveNavigation({
    mode: 'global',
    role: auth.role,
  })
})

// All global groups — each group is collapsible via toggleGroupCollapse
const globalNavGroups = computed(() => globalResolved.value.groups)

// ── AI Intelligence in global mode ──
function onGlobalAiClick(moduleKey: string) {
  navToModule(moduleKey)
}

// ── 分组图标映射（收起态显示） ──
function groupIcon(key: string): string {
  const map: Record<string, string> = {
    today: 'stethoscope',
    patients: 'users',
    alerts: 'alert',
    'clinical-knowledge': 'database',
    research: 'flask',
    more: 'more',
    'ai-intelligence': 'brain',
  }
  return map[key] || 'more'
}

// ── Actions ──
function toggleCollapse() {
  collapsed.value = !collapsed.value
  localStorage.setItem(STORAGE_KEY, String(collapsed.value))
}

function toggleExpandGroup(groupKey: string) {
  const set = new Set(expandedGroups.value)
  if (set.has(groupKey)) {
    set.delete(groupKey)
  } else {
    set.add(groupKey)
  }
  expandedGroups.value = set
}

function handleBackToPatients() {
  navigateBack()
}

function isActiveRoute(path: string): boolean {
  return route.path === path || route.path.startsWith(path + '/')
}

// ── SVG icons ──
function iconSvg(icon: string) {
  const svgs: Record<string, string> = {
    stethoscope: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.8 2.3A.3.3 0 1 0 5 2H4a2 2 0 0 0-2 2v5a6 6 0 0 0 6 6v0a6 6 0 0 0 6-6V4a2 2 0 0 0-2-2h-1a.2.2 0 1 0 .3.3"/><path d="M8 15v1a6 6 0 0 0 6 6v0a6 6 0 0 0 6-6v-4"/><circle cx="20" cy="10" r="2"/></svg>',
    nurse: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a4 4 0 0 0-4 4v2a4 4 0 0 0 8 0V6a4 4 0 0 0-4-4Z"/><path d="M6 14h12l-1 8H7l-1-8Z"/></svg>',
    shield: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/></svg>',
    crown: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 4l3 12h14l3-12-5 4-5-4-5 4-5-4z"/><path d="M5 16h14v2H5z"/></svg>',
    users: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    activity: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
    exchange: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 1l4 4-4 4"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><path d="M7 23l-4-4 4-4"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>',
    sparkles: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.9 5.8a2 2 0 0 0 1.3 1.3L21 12l-5.8 1.9a2 2 0 0 0-1.3 1.3L12 21l-1.9-5.8a2 2 0 0 0-1.3-1.3L3 12l5.8-1.9a2 2 0 0 0 1.3-1.3z"/></svg>',
    clipboard: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/></svg>',
    network: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="2" width="6" height="6" rx="1"/><rect x="2" y="16" width="6" height="6" rx="1"/><rect x="16" y="16" width="6" height="6" rx="1"/><path d="M12 8v8"/></svg>',
    lungs: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v8"/><path d="M8 10c-2 0-4 1-4 4s2 6 4 6c1 0 2-1 2-3v-7"/><path d="M16 10c2 0 4 1 4 4s-2 6-4 6c-1 0-2-1-2-3v-7"/></svg>',
    apple: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2c-1.7 0-3 1.3-3 3v1c-1.7 0-3 1.3-3 3 0 3.5 3 7 6 8.5 1.2.6 2.4.6 3.6 0 3-1.5 6-5 6-8.5 0-1.7-1.3-3-3-3V5c0-1.7-1.3-3-3-3z"/></svg>',
    chart: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-6"/></svg>',
    flask: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h6"/><path d="M10 9V3"/><path d="M14 9V3"/><path d="M7 9l-3 8h16l-3-8"/></svg>',
    cpu: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/></svg>',
    settings: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
    database: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>',
    more: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></svg>',
    'chevron-down': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>',
    'chevron-up': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 15l-6-6-6 6"/></svg>',
    'arrow-left': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5"/><path d="M12 19l-7-7 7-7"/></svg>',
    brain: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a4 4 0 0 0-4 4v1a3 3 0 0 0-3 3 3 3 0 0 0 1 2.24V14a4 4 0 0 0 2.8 3.82L10 22h4l1.2-4.18A4 4 0 0 0 18 14v-1.76A3 3 0 0 0 19 10a3 3 0 0 0-3-3V6a4 4 0 0 0-4-4z"/></svg>',
    alert: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    'trending-up': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>',
    search: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
    book: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>',
    calendar: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
    grid: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>',
    lightbulb: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z"/></svg>',
  }
  return svgs[icon] || '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="2"/></svg>'
}
</script>

<style scoped>
.side-nav {
  display: flex;
  flex-direction: column;
  width: 208px;
  min-height: 100vh;
  background: var(--sidebar-bg, #FFFFFF);
  border-right: 1px solid var(--sidebar-border, #E3E7EC);
  transition: width 0.2s ease;
  flex-shrink: 0;
  overflow: hidden;
  position: sticky;
  top: 0;
  z-index: 100;
}

.side-nav--collapsed {
  width: 64px;
}

.side-nav__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 48px;
  padding: 0 12px;
  border-bottom: 1px solid var(--sidebar-border, #E3E7EC);
}

.side-nav__brand {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
  color: inherit;
  overflow: hidden;
}

.side-nav__logo {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  flex-shrink: 0;
}

.side-nav__title {
  font-size: 14px;
  font-weight: 700;
  color: var(--sidebar-text-active, #18212B);
  white-space: nowrap;
}

.side-nav__toggle {
  background: transparent;
  border: none;
  color: var(--sidebar-text, #667085);
  cursor: pointer;
  padding: 6px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, color 0.15s;
  flex-shrink: 0;
}

.side-nav__toggle:hover {
  background: var(--sidebar-item-hover, #F1F3F5);
  color: var(--sidebar-text-active, #18212B);
}

.side-nav__menu {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 8px 0;
  scrollbar-width: thin;
  scrollbar-color: rgba(0, 0, 0, 0.1) transparent;
}

.side-nav__group {
  margin-bottom: 4px;
}

.side-nav__group-label {
  padding: 12px 16px 4px;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--sidebar-group-label, #667085);
  font-weight: 600;
  white-space: nowrap;
}

.side-nav__group-label--toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  background: none;
  border: none;
  cursor: pointer;
  font-family: inherit;
}

.side-nav__group-label--toggle:hover {
  color: var(--sidebar-active, #1677ff);
}

.side-nav__toggle-arrow {
  font-size: 11px;
  transition: transform 0.2s;
}

.side-nav__toggle-arrow--open {
  transform: rotate(90deg);
}

.side-nav__item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  color: var(--sidebar-text, #667085);
  text-decoration: none;
  font-size: 13px;
  font-weight: 500;
  border-left: 3px solid transparent;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
  white-space: nowrap;
  cursor: pointer;
  background: transparent;
  border: none;
  border-left: 3px solid transparent;
  width: 100%;
  text-align: left;
}

.side-nav__item:hover {
  background: var(--sidebar-item-hover, #F1F3F5);
  color: var(--sidebar-text-active, #18212B);
}

.side-nav__item--active {
  background: var(--sidebar-item-active-bg, rgba(37, 99, 235, 0.08));
  border-left-color: var(--sidebar-item-active-border, #2563EB);
  color: var(--sidebar-text-active, #18212B);
  font-weight: 600;
}

.side-nav__item--sub {
  padding-left: 48px;
  font-size: 12px;
}

.side-nav__expandable {
  position: relative;
}

.side-nav__expand-arrow {
  margin-left: auto;
  opacity: 0.5;
  transition: transform 0.2s;
}

.side-nav__item--expanded .side-nav__expand-arrow {
  transform: rotate(180deg);
}

.side-nav__back-btn {
  color: var(--color-primary, #2563EB);
  font-weight: 500;
}

.side-nav__back-btn:hover {
  background: rgba(37, 99, 235, 0.06);
}

.side-nav__icon {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.side-nav__icon :deep(svg) {
  display: block;
}

.side-nav__label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}

.side-nav__more-trigger {
  border-left: 3px solid transparent;
}

.side-nav__more-item {
  display: flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  color: inherit;
}

/* 收起状态 */
.side-nav--collapsed .side-nav__label {
  display: none;
}

.side-nav--collapsed .side-nav__group-label {
  display: none;
}

.side-nav--collapsed .side-nav__item {
  justify-content: center;
  padding: 10px 0;
}

.side-nav--collapsed .side-nav__header {
  justify-content: center;
  padding: 0;
}

.side-nav--collapsed .side-nav__brand {
  justify-content: center;
}

.side-nav--collapsed .side-nav__expand-arrow {
  display: none;
}

.side-nav--collapsed .side-nav__item--sub {
  padding-left: 0;
}

/* 更多下拉菜单样式 */
:deep(.side-nav__more-dropdown .ant-dropdown-menu) {
  background: var(--color-bg-surface, #FFFFFF) !important;
  border: 1px solid var(--color-border, #E3E7EC) !important;
  border-radius: var(--radius-lg, 8px) !important;
  box-shadow: var(--shadow-lg, 0 10px 15px -3px rgba(0, 0, 0, 0.1)) !important;
  padding: 4px !important;
}

:deep(.side-nav__more-dropdown .ant-dropdown-menu-item) {
  border-radius: var(--radius-md, 6px) !important;
  padding: 8px 12px !important;
}

:deep(.side-nav__more-dropdown .ant-dropdown-menu-item:hover) {
  background: var(--color-bg-surface-secondary, #F1F3F5) !important;
}
</style>
