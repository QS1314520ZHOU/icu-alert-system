<template>
  <div class="forbidden-page">
    <div class="forbidden-card">
      <ErrorState title="权限不足" description="您没有权限访问此页面或模块。">
        <template #icon>
          <span class="forbidden-icon" aria-hidden="true">🔒</span>
        </template>
        <template #action>
          <p class="forbidden-hint">
            如需访问，请联系管理员开通相应权限。
          </p>
          <div class="forbidden-actions">
            <a-button type="primary" @click="goBack">
              返回上一页
            </a-button>
            <router-link to="/patients" class="forbidden-link">
              返回患者列表
            </router-link>
          </div>
        </template>
      </ErrorState>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Button as AButton } from 'ant-design-vue'
import { useAppNavigation } from '../navigation/useAppNavigation'
import { ErrorState } from '../components/common/design-system'

const { navigateBack } = useAppNavigation()

function goBack() {
  navigateBack()
}
</script>

<style scoped>
.forbidden-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  padding: var(--space-6, 24px);
  background: var(--color-bg-page);
}

.forbidden-card {
  text-align: center;
  max-width: 420px;
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.forbidden-card :deep(.error-state__title) {
  font-size: var(--text-page-title);
  font-weight: var(--text-page-title-weight);
}

.forbidden-icon {
  font-size: 40px;
  line-height: 1;
}

.forbidden-hint {
  margin: 0 0 var(--space-4, 16px);
  font-size: var(--text-body);
  color: var(--color-text-secondary);
}

.forbidden-actions {
  display: flex;
  gap: var(--element-gap-lg, 12px);
  justify-content: center;
  align-items: center;
}

.forbidden-link {
  font-size: var(--text-body);
  font-weight: var(--weight-medium);
  color: var(--color-primary);
  text-decoration: none;
}

.forbidden-link:hover {
  color: var(--color-primary-hover);
}
</style>
