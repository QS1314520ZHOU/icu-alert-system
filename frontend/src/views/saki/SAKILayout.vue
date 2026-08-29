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
      <p class="disclaimer-text">⚠️ 仅用于科研分析与临床决策支持，不替代医生诊断和治疗决策。</p>
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
.saki-layout { display: flex; flex-direction: column; min-height: 100%; background: var(--bg-base, #F6F7F9); }
.layout-header { background: #fff; border-bottom: 1px solid #e8e8e8; padding: 16px 24px 0; position: sticky; top: 0; z-index: 100; }
.header-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
.header-title { font-size: 20px; font-weight: 600; margin: 0 0 4px; color: #1a1a2e; }
.header-subtitle { font-size: 13px; color: #8c8c8c; margin: 0; }
.version-tags { display: flex; gap: 8px; }
.version-tag { font-size: 11px; padding: 2px 8px; border-radius: 4px; background: #f0f0f0; color: #666; }
.version-tag--info { background: #e6f7ff; color: #1890ff; }
.layout-nav { display: flex; gap: 4px; overflow-x: auto; }
.nav-item { display: flex; align-items: center; gap: 4px; padding: 8px 14px; border-radius: 6px 6px 0 0; text-decoration: none; color: #666; font-size: 13px; white-space: nowrap; transition: all 0.2s; }
.nav-item:hover { background: #f5f5f5; color: #1890ff; }
.nav-item--active { background: #e6f7ff; color: #1890ff; font-weight: 500; border-bottom: 2px solid #1890ff; }
.layout-main { flex: 1; padding: 20px 24px; }
.layout-footer { padding: 12px 24px; text-align: center; border-top: 1px solid #f0f0f0; }
.disclaimer-text { font-size: 12px; color: #faad14; margin: 0; }
</style>
