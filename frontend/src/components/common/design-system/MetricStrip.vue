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
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 14px;
}

.metric-strip__item {
  position: relative;
  padding: 14px 16px;
  background: var(--color-bg-surface, #FFFFFF);
  border: 1px solid var(--color-border, #E5E7EB);
  border-radius: var(--radius-lg, 10px);
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow: hidden;
}

/* 状态色条（有 variant 时） */
.metric-strip__item--danger::before,
.metric-strip__item--warning::before,
.metric-strip__item--success::before,
.metric-strip__item--info::before {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
}
.metric-strip__item--danger::before { background: var(--color-danger, #DC2626); }
.metric-strip__item--warning::before { background: var(--color-warning, #D97706); }
.metric-strip__item--success::before { background: var(--color-success, #16A34A); }
.metric-strip__item--info::before { background: var(--color-primary, #2563EB); }

.metric-strip__label {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #4B5563);
  font-weight: var(--weight-medium, 500);
}

.metric-strip__value {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.metric-strip__number {
  font-family: var(--font-digit, 'Rajdhani', sans-serif);
  font-size: var(--text-metric-key, 26px);
  font-weight: 700;
  line-height: 1.15;
  color: var(--color-text-primary, #111827);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em;
}

.metric-strip__unit {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #4B5563);
}

.metric-strip__trend {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--text-caption, 12px);
  font-weight: var(--weight-medium, 500);
}

.metric-strip__trend--up {
  color: var(--color-success, #16A34A);
}

.metric-strip__trend--down {
  color: var(--color-danger, #DC2626);
}

.metric-strip__trend--stable {
  color: var(--color-text-tertiary, #9CA3AF);
}

.metric-strip__trend-value {
  font-size: var(--text-caption, 12px);
}

/* 变体样式 */
.metric-strip__item--danger .metric-strip__number {
  color: var(--color-danger, #DC2626);
}

.metric-strip__item--warning .metric-strip__number {
  color: var(--color-warning, #D97706);
}

.metric-strip__item--success .metric-strip__number {
  color: var(--color-success, #16A34A);
}

.metric-strip__item--info .metric-strip__number {
  color: var(--color-primary, #2563EB);
}

@media (max-width: 768px) {
  .metric-strip {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
