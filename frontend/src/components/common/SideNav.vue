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
      <div v-for="group in navGroups" :key="group.key" class="side-nav__group">
        <div v-if="!collapsed" class="side-nav__group-label">{{ group.label }}</div>
        <router-link
          v-for="item in group.items"
          :key="item.key"
          :to="item.path"
          :class="['side-nav__item', { 'side-nav__item--active': isActive(item.path) }]"
          :title="item.label"
        >
          <span class="side-nav__icon" v-html="iconSvg(item.icon)"></span>
          <span v-if="!collapsed" class="side-nav__label">{{ item.label }}</span>
        </router-link>
      </div>
    </nav>
  </aside>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { navGroups } from '../../config/roleHomeConfig'

const route = useRoute()
const STORAGE_KEY = 'side-nav-collapsed'
const collapsed = ref(localStorage.getItem(STORAGE_KEY) === 'true')

function toggleCollapse() {
  collapsed.value = !collapsed.value
  localStorage.setItem(STORAGE_KEY, String(collapsed.value))
}

function isActive(path: string) {
  return route.path === path || route.path.startsWith(path + '/')
}

function iconSvg(icon: string) {
  const svgs: Record<string, string> = {
    stethoscope: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.8 2.3A.3.3 0 1 0 5 2H4a2 2 0 0 0-2 2v5a6 6 0 0 0 6 6v0a6 6 0 0 0 6-6V4a2 2 0 0 0-2-2h-1a.2.2 0 1 0 .3.3"/><path d="M8 15v1a6 6 0 0 0 6 6v0a6 6 0 0 0 6-6v-4"/><circle cx="20" cy="10" r="2"/></svg>',
    nurse: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a4 4 0 0 0-4 4v2a4 4 0 0 0 8 0V6a4 4 0 0 0-4-4Z"/><path d="M6 14h12l-1 8H7l-1-8Z"/></svg>',
    shield: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/></svg>',
    crown: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 4l3 12h14l3-12-5 4-5-4-5 4-5-4z"/><path d="M5 16h14v2H5z"/></svg>',
    users: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    activity: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
    exchange: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 1l4 4-4 4"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><path d="M7 23l-4-4 4-4"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>',
    monitor: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/></svg>',
    sparkles: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.9 5.8a2 2 0 0 0 1.3 1.3L21 12l-5.8 1.9a2 2 0 0 0-1.3 1.3L12 21l-1.9-5.8a2 2 0 0 0-1.3-1.3L3 12l5.8-1.9a2 2 0 0 0 1.3-1.3z"/></svg>',
    clipboard: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/></svg>',
    file: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
    network: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="2" width="6" height="6" rx="1"/><rect x="2" y="16" width="6" height="6" rx="1"/><rect x="16" y="16" width="6" height="6" rx="1"/><path d="M12 8v8"/></svg>',
    chart: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-6"/></svg>',
    pulse: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>',
    lungs: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v8"/><path d="M8 10c-2 0-4 1-4 4s2 6 4 6c1 0 2-1 2-3v-7"/><path d="M16 10c2 0 4 1 4 4s-2 6-4 6c-1 0-2-1-2-3v-7"/></svg>',
    apple: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2c-1.7 0-3 1.3-3 3v1c-1.7 0-3 1.3-3 3 0 3.5 3 7 6 8.5 1.2.6 2.4.6 3.6 0 3-1.5 6-5 6-8.5 0-1.7-1.3-3-3-3V5c0-1.7-1.3-3-3-3z"/></svg>',
    cpu: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/></svg>',
    settings: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
    flask: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h6"/><path d="M10 9V3"/><path d="M14 9V3"/><path d="M7 9l-3 8h16l-3-8"/></svg>',
    download: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
    beaker: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 3h15"/><path d="M6 3v16a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V3"/><path d="M6 14h12"/></svg>',
    book: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>',
  }
  return svgs[icon] || '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="2"/></svg>'
}
</script>

<style scoped>
.side-nav {
  display: flex; flex-direction: column; width: 220px; min-height: 100vh;
  background: var(--sidebar-bg); border-right: 1px solid var(--sidebar-border);
  transition: width 0.2s ease; flex-shrink: 0; overflow: hidden;
  position: sticky; top: 0; z-index: 100;
}
.side-nav--collapsed { width: 60px; }
.side-nav__header {
  display: flex; align-items: center; justify-content: space-between;
  height: 48px; padding: 0 12px; border-bottom: 1px solid var(--sidebar-border);
}
.side-nav__brand {
  display: flex; align-items: center; gap: 10px; text-decoration: none; color: inherit; overflow: hidden;
}
.side-nav__logo { width: 28px; height: 28px; border-radius: 6px; flex-shrink: 0; }
.side-nav__title { font-size: 14px; font-weight: 700; color: var(--sidebar-text-active); white-space: nowrap; }
.side-nav__toggle {
  background: transparent; border: none; color: var(--sidebar-text);
  cursor: pointer; padding: 6px; border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  transition: background 0.15s; flex-shrink: 0;
}
.side-nav__toggle:hover { background: var(--sidebar-item-hover); color: var(--sidebar-text-active); }
.side-nav__menu {
  flex: 1; overflow-y: auto; overflow-x: hidden; padding: 8px 0;
  scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;
}
.side-nav__group { margin-bottom: 4px; }
.side-nav__group-label {
  padding: 12px 16px 4px; font-size: 10px; text-transform: uppercase;
  letter-spacing: 0.08em; color: var(--sidebar-group-label); font-weight: 600; white-space: nowrap;
}
.side-nav__item {
  display: flex; align-items: center; gap: 12px; padding: 8px 16px;
  color: var(--sidebar-text); text-decoration: none; font-size: 13px; font-weight: 500;
  border-left: 3px solid transparent;
  transition: background 0.15s, color 0.15s, border-color 0.15s; white-space: nowrap;
}
.side-nav__item:hover { background: var(--sidebar-item-hover); color: var(--sidebar-text-active); }
.side-nav__item--active {
  background: var(--sidebar-item-active-bg); border-left-color: var(--sidebar-item-active-border);
  color: var(--sidebar-text-active); font-weight: 600;
}
.side-nav__icon { width: 20px; height: 20px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.side-nav__icon :deep(svg) { display: block; }
.side-nav--collapsed .side-nav__label { display: none; }
.side-nav--collapsed .side-nav__group-label { display: none; }
.side-nav--collapsed .side-nav__item { justify-content: center; padding: 10px 0; }
.side-nav--collapsed .side-nav__header { justify-content: center; padding: 0; }
.side-nav--collapsed .side-nav__brand { justify-content: center; }
</style>
