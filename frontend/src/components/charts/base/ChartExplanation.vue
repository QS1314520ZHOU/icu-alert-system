<template>
  <div class="chart-explanation" v-if="description">
    <div class="chart-explanation__content">
      <span class="chart-explanation__icon">
        <InfoCircleOutlined />
      </span>
      <div class="chart-explanation__text">
        <p class="chart-explanation__desc">{{ description }}</p>
        <p v-if="keyFinding" class="chart-explanation__finding">
          <AlertOutlined /> {{ keyFinding }}
        </p>
      </div>
    </div>
    <div class="chart-explanation__meta">
      <span v-if="source" class="chart-explanation__source">来源: {{ source }}</span>
      <span v-if="dataTime" class="chart-explanation__time">更新: {{ dataTime }}</span>
      <router-link
        v-if="rawDataRoute"
        :to="rawDataRoute"
        class="chart-explanation__link"
      >
        查看原始数据 →
      </router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { InfoCircleOutlined, AlertOutlined } from '@ant-design/icons-vue'

defineProps<{
  /** 图表说明 */
  description: string
  /** 当前关键发现 */
  keyFinding?: string
  /** 数据来源 */
  source?: string
  /** 数据时间 */
  dataTime?: string
  /** 查看原始数据路由 */
  rawDataRoute?: string
}>()
</script>

<style scoped>
.chart-explanation {
  padding: 8px 12px;
  margin-top: 8px;
  border-radius: 6px;
  background: var(--color-bg-surface-secondary, #F1F3F5);
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text-secondary, #667085);
}

.chart-explanation__content {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.chart-explanation__icon {
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--color-text-tertiary, #8A94A6);
}

.chart-explanation__text {
  flex: 1;
  min-width: 0;
}

.chart-explanation__desc {
  margin: 0;
  /* 限制2-4行 */
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.chart-explanation__finding {
  margin: 4px 0 0;
  color: var(--color-warning, #E5B700);
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 4px;
}

.chart-explanation__meta {
  display: flex;
  gap: 12px;
  margin-top: 6px;
  font-size: 11px;
  color: var(--color-text-tertiary, #8A94A6);
  flex-wrap: wrap;
}

.chart-explanation__link {
  color: var(--color-primary, #1677FF);
  text-decoration: none;
}

.chart-explanation__link:hover {
  text-decoration: underline;
}
</style>
