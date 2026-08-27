<template>
  <div class="metric-strip">
    <div
      v-for="(metric, index) in metrics"
      :key="index"
      :class="['metric-strip__item', `metric-strip__item--${metric.variant || 'default'}`]"
    >
      <div class="metric-strip__label">{{ metric.label }}</div>
      <div class="metric-strip__value">
        <span class="metric-strip__number">{{ metric.value }}</span>
        <span v-if="metric.unit" class="metric-strip__unit">{{ metric.unit }}</span>
      </div>
      <div v-if="metric.trend" :class="['metric-strip__trend', `metric-strip__trend--${metric.trend}`]">
        <svg v-if="metric.trend === 'up'" width="12" height="12" viewBox="0 0 12 12" fill="none">
          <path d="M6 2L10 7H2L6 2Z" fill="currentColor"/>
        </svg>
        <svg v-else-if="metric.trend === 'down'" width="12" height="12" viewBox="0 0 12 12" fill="none">
          <path d="M6 10L2 5H10L6 10Z" fill="currentColor"/>
        </svg>
        <span v-if="metric.trendValue" class="metric-strip__trend-value">{{ metric.trendValue }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Metric {
  label: string
  value: string | number
  unit?: string
  variant?: 'danger' | 'warning' | 'success' | 'info' | 'default'
  trend?: 'up' | 'down' | 'stable'
  trendValue?: string
}

interface Props {
  metrics: Metric[]
}

defineProps<Props>()
</script>

<style scoped>
.metric-strip {
  display: flex;
  gap: 1px;
  background: var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px);
  overflow: hidden;
}

.metric-strip__item {
  flex: 1;
  padding: 16px;
  background: var(--color-bg-surface, #FFFFFF);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.metric-strip__label {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
  font-weight: var(--weight-medium, 500);
}

.metric-strip__value {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.metric-strip__number {
  font-family: var(--font-digit, 'Rajdhani', sans-serif);
  font-size: var(--text-metric-normal, 20px);
  font-weight: 700;
  line-height: 1.2;
  color: var(--color-text-primary, #18212B);
}

.metric-strip__unit {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}

.metric-strip__trend {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--text-caption, 12px);
  font-weight: var(--weight-medium, 500);
}

.metric-strip__trend--up {
  color: var(--color-success, #16845B);
}

.metric-strip__trend--down {
  color: var(--color-danger, #D92D20);
}

.metric-strip__trend--stable {
  color: var(--color-text-secondary, #667085);
}

.metric-strip__trend-value {
  font-size: var(--text-caption, 12px);
}

/* 变体样式 */
.metric-strip__item--danger .metric-strip__number {
  color: var(--color-danger, #D92D20);
}

.metric-strip__item--warning .metric-strip__number {
  color: var(--color-warning, #B54708);
}

.metric-strip__item--success .metric-strip__number {
  color: var(--color-success, #16845B);
}

.metric-strip__item--info .metric-strip__number {
  color: var(--color-primary, #2563EB);
}

@media (max-width: 768px) {
  .metric-strip {
    flex-direction: column;
  }

  .metric-strip__item {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
  }

  .metric-strip__value {
    align-items: center;
  }
}
</style>
