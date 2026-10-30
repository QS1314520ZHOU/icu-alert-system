<template>
  <div class="saki-layout">
    <header class="layout-header">
      <div class="header-top">
        <div class="header-left">
          <h1 class="header-title">🔬 S-AKI 单病种科研中心</h1>
          <p class="header-subtitle">脓毒症相关急性肾损伤 — 脓毒症电子表型 + KDIGO AKI + 时间关联识别 + 科研队列 + 统计分析</p>
        </div>
        <div class="header-right">
          <div class="version-tags">
            <span class="version-tag">表型引擎 v1.0</span>
            <span class="version-tag version-tag--info">KDIGO 2012</span>
            <span class="version-tag version-tag--info">Sepsis-3</span>
          </div>
        </div>
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
        </router-link>
      </nav>
    </header>
    <main class="layout-main">
      <router-view v-slot="{ Component }">
        <keep-alive :include="cachedViews">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </main>
    <footer class="layout-footer">
      <p class="disclaimer-text">仅用于科研分析与临床决策支持，不替代医生诊断和治疗决策。</p>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const cachedViews = ref(['SAKIOverview'])

const navTabs = computed(() => [
  { key: 'overview', icon: '📊', label: '总览', to: '/disease-center/saki/overview' },
  { key: 'cases', icon: '📋', label: '病例库', to: '/disease-center/saki/cases' },
  { key: 'cohorts', icon: '👥', label: '队列构建', to: '/disease-center/saki/cohorts' },
  { key: 'analysis', icon: '📈', label: '统计分析', to: '/disease-center/saki/analysis' },
  { key: 'charts', icon: '📉', label: '图表', to: '/disease-center/saki/charts' },
  { key: 'quality', icon: '✅', label: '数据质量', to: '/disease-center/saki/quality' },
  { key: 'field-mapping', icon: '🗺️', label: '字段映射', to: '/disease-center/saki/field-mapping' },
])
</script>

<style scoped>
.saki-layout { display: flex; flex-direction: column; min-height: 100%; background: var(--color-bg-page); }
.layout-header { background: var(--color-bg-surface); border-bottom: 1px solid var(--color-border); padding: 16px 24px 0; position: sticky; top: 0; z-index: 100; }
.header-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
.header-title { font-size: var(--text-page-title); font-weight: var(--text-page-title-weight); margin: 0 0 4px; color: var(--color-text-primary); }
.header-subtitle { font-size: var(--text-page-subtitle); color: var(--color-text-secondary); margin: 0; }
.version-tags { display: flex; gap: 8px; }
.version-tag { font-size: var(--text-caption); padding: 2px 8px; border-radius: var(--radius-tag); background: var(--color-bg-surface-secondary); color: var(--color-text-secondary); }
.version-tag--info { background: var(--color-primary-bg); color: var(--color-primary); }
.layout-nav { display: flex; gap: 4px; overflow-x: auto; }
.nav-item { display: flex; align-items: center; gap: 4px; padding: 8px 14px; border-radius: 6px 6px 0 0; text-decoration: none; color: var(--color-text-secondary); font-size: var(--text-body); white-space: nowrap; transition: all 0.2s; }
.nav-item:hover { background: var(--color-bg-inset); color: var(--color-primary); }
.nav-item--active { background: var(--color-primary-bg); color: var(--color-primary); font-weight: var(--weight-medium); border-bottom: 2px solid var(--color-primary); }
.layout-main { flex: 1; padding: 20px 24px; }
.layout-footer { padding: 12px 24px; text-align: center; border-top: 1px solid var(--color-divider); }
.disclaimer-text { font-size: var(--text-caption); color: var(--color-warning); margin: 0; }
</style>
