<template>
  <div class="disease-center-layout">
    <!-- 顶部标题区 -->
    <header class="layout-header">
      <div class="header-top">
        <div class="header-left">
          <h1 class="header-title">病种中心</h1>
          <p class="header-subtitle">统一管理标准编码、临床病种、评分规则、AI知识与发布版本</p>
        </div>
        <div class="header-right">
          <div class="version-tags">
            <span class="version-tag">病种库 v1.0.0</span>
            <span class="version-tag">规则包 v1.0.0</span>
            <span class="version-tag">知识包 v1.0.0</span>
            <span class="version-tag version-tag--success">本地AI 在线</span>
          </div>
          <div class="header-actions">
            <button class="btn btn--outline">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
              导入离线包
            </button>
            <button class="btn btn--primary">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              新建病种
            </button>
          </div>
        </div>
      </div>

      <!-- 二级导航 Tabs -->
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

    <!-- 主体：子路由渲染区 -->
    <main class="layout-main">
      <router-view v-slot="{ Component }">
        <keep-alive :include="cachedViews">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const cachedViews = ref(['DiseaseCenterOverview'])

const navTabs = computed(() => [
  { key: 'overview', icon: '📊', label: '总览', to: '/disease-center/overview' },
  { key: 'cases', icon: '🩺', label: '病例中心', to: '/disease-center/cases' },
  { key: 'diseases', icon: '📁', label: '病种目录', to: '/disease-center/diseases' },
  { key: 'terminology', icon: '🔤', label: '术语编码', to: '/disease-center/terminology' },
  { key: 'scores', icon: '📈', label: '评分规则', to: '/disease-center/scores' },
  { key: 'phenotypes', icon: '🧬', label: '表型规则', to: '/disease-center/phenotypes' },
  { key: 'offline', icon: '📦', label: '离线知识包', to: '/disease-center/offline-packages' },
  { key: 'reviews', icon: '✅', label: '审核发布', to: '/disease-center/reviews' },
  { key: 'ai', icon: '🤖', label: 'AI助手', to: '/disease-center/ai' },
  { key: 'quality', icon: '🔍', label: '质量监控', to: '/disease-center/quality' },
])
</script>

<style scoped>
.disease-center-layout {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  background: var(--bg-base, #F6F7F9);
}

.layout-header {
  background: #fff;
  border-bottom: 1px solid var(--color-border, #E3E7EC);
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 24px 16px;
}

.header-left {
  flex: 1;
  min-width: 0;
}

.header-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text-primary, #18212B);
  margin: 0;
  line-height: 1.3;
}

.header-subtitle {
  font-size: 13px;
  color: var(--color-text-secondary, #667085);
  margin: 4px 0 0;
  line-height: 1.5;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-shrink: 0;
}

.version-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.version-tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  color: var(--color-text-secondary, #667085);
  background: var(--color-bg-surface-secondary, #F1F3F5);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: 4px;
  white-space: nowrap;
}

.version-tag--success {
  color: var(--color-success, #16845B);
  background: rgba(22, 132, 91, 0.08);
  border-color: rgba(22, 132, 91, 0.2);
}

.header-actions {
  display: flex;
  gap: 8px;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 500;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
  border: 1px solid transparent;
}

.btn--primary {
  background: var(--color-primary, #1D6F63);
  color: #fff;
  border-color: var(--color-primary, #1D6F63);
}

.btn--primary:hover {
  background: var(--color-primary-hover, #195C52);
}

.btn--outline {
  background: #fff;
  color: var(--color-text-primary, #18212B);
  border-color: var(--color-border, #D0D5DD);
}

.btn--outline:hover {
  background: var(--color-bg-surface-secondary, #F9FAFB);
  border-color: #B0B8C4;
}

.layout-nav {
  display: flex;
  gap: 2px;
  padding: 0 24px;
  border-top: 1px solid #f0f0f0;
  background: #fafbfc;
  overflow-x: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.layout-nav::-webkit-scrollbar {
  display: none;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 14px;
  font-size: 13px;
  color: #666;
  text-decoration: none;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
  white-space: nowrap;
  flex-shrink: 0;
}

.nav-item:hover {
  color: var(--color-primary, #1D6F63);
  background: rgba(29, 111, 99, 0.06);
}

.nav-item--active {
  color: var(--color-primary, #1D6F63);
  border-bottom-color: var(--color-primary, #1D6F63);
  font-weight: 600;
}

.nav-icon {
  font-size: 14px;
}

.layout-main {
  flex: 1;
  padding: 16px 24px 32px;
  max-width: 1400px;
  width: 100%;
  margin: 0 auto;
}

@media (max-width: 768px) {
  .header-top {
    flex-direction: column;
    padding: 16px;
  }

  .header-right {
    flex-direction: column;
    align-items: flex-start;
    width: 100%;
  }

  .version-tags {
    width: 100%;
  }

  .header-actions {
    width: 100%;
  }

  .btn {
    flex: 1;
    justify-content: center;
  }

  .layout-nav {
    padding: 0 16px;
  }

  .nav-item {
    padding: 10px 12px;
  }

  .layout-main {
    padding: 12px 16px 24px;
  }
}
</style>
