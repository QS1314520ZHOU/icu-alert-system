<template>
  <div class="handover-layout">
    <nav v-if="!isPatientPage" class="handover-tabs" aria-label="交接班子页面">
      <router-link
        v-for="tab in tabs"
        :key="tab.name"
        :to="{ name: tab.name, query: route.query }"
        class="handover-tab"
        :class="{ 'handover-tab--active': route.name === tab.name }"
      >
        {{ tab.label }}
      </router-link>
    </nav>
    <router-view />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const tabs = [
  { name: 'handover-overview', label: '交班总览' },
  { name: 'handover-patients', label: '患者交班' },
  { name: 'handover-tasks', label: '待办与未闭环' },
  { name: 'handover-history', label: '交班历史' },
  { name: 'handover-settings', label: '班次与诊断' },
]
const isPatientPage = computed(() => route.name === 'handover-patient')
</script>

<style scoped>
.handover-layout {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-bg-page);
}
.handover-tabs {
  display: flex;
  gap: 4px;
  padding: 0 var(--page-padding, 24px);
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-surface);
}
.handover-tab {
  padding: 10px 14px;
  font-size: var(--text-body, 13px);
  color: var(--color-text-secondary);
  border-bottom: 2px solid transparent;
  text-decoration: none;
}
.handover-tab:hover { color: var(--color-text-primary); }
.handover-tab--active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
  font-weight: 600;
}
</style>
