<template>
  <div class="forbidden-page">
    <div class="forbidden-card">
      <div class="forbidden-icon">🔒</div>
      <h1 class="forbidden-title">403 — 权限不足</h1>
      <p class="forbidden-desc">您没有权限访问此页面或模块。</p>
      <p class="forbidden-hint">
        如需访问，请联系管理员开通相应权限。
      </p>
      <div class="forbidden-actions">
        <button class="forbidden-btn forbidden-btn--primary" @click="goBack">
          返回上一页
        </button>
        <router-link to="/patients" class="forbidden-btn">
          返回患者列表
        </router-link>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAppNavigation } from '../navigation/useAppNavigation'

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
  padding: 24px;
}

.forbidden-card {
  text-align: center;
  max-width: 420px;
  padding: 48px 32px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
}

.forbidden-icon {
  font-size: 64px;
  margin-bottom: 16px;
}

.forbidden-title {
  margin: 0 0 12px;
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text-primary, #18212B);
}

.forbidden-desc {
  margin: 0 0 8px;
  font-size: 14px;
  color: var(--color-text-secondary, #52606D);
}

.forbidden-hint {
  margin: 0 0 24px;
  font-size: 13px;
  color: var(--color-text-tertiary, #94A3B8);
}

.forbidden-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.forbidden-btn {
  display: inline-flex;
  align-items: center;
  padding: 8px 20px;
  font-size: 14px;
  font-weight: 500;
  border-radius: 8px;
  border: 1px solid var(--color-border, #DCE3EC);
  background: #fff;
  color: var(--color-text-primary, #18212B);
  text-decoration: none;
  cursor: pointer;
  transition: all 0.15s;
}

.forbidden-btn:hover {
  background: var(--color-bg-hover, #F0F6FF);
}

.forbidden-btn--primary {
  background: var(--color-primary, #2563EB);
  color: #fff;
  border-color: var(--color-primary, #2563EB);
}

.forbidden-btn--primary:hover {
  background: var(--color-primary-hover, #3B82F6);
}
</style>
