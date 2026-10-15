<template>
  <div class="evidence-metrics">
    <div v-if="!metrics.length" class="metrics-empty">暂无指标数据</div>
    <div v-else class="metrics-grid">
      <div
        v-for="m in metrics"
        :key="m.code"
        :class="['metric-card', `flag-${m.abnormal_flag}`]"
      >
        <div class="metric-header">
          <span class="metric-name">{{ m.name }}</span>
          <span :class="['metric-flag', `flag-${m.abnormal_flag}`]">{{ flagLabel(m.abnormal_flag) }}</span>
        </div>
        <div class="metric-value-row">
          <strong class="metric-value">{{ formatValue(m.value) }}</strong>
          <span class="metric-unit">{{ m.unit }}</span>
        </div>
        <div class="metric-meta">
          <span v-if="m.reference_range" class="metric-range">参考：{{ m.reference_range }}</span>
          <span v-if="m.min != null && m.max != null" class="metric-minmax">{{ m.min }} - {{ m.max }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { EvidenceMetric } from '../../api/clinicalEvidence'

defineProps<{
  metrics: EvidenceMetric[]
}>()

function flagLabel(flag: string): string {
  const map: Record<string, string> = { critical: '危急', high: '偏高', low: '偏低', normal: '正常', missing: '缺失' }
  return map[flag] || flag
}

function formatValue(v: number | string | null | undefined): string {
  if (v == null) return '不可计算'
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(1)
  return String(v)
}
</script>

<style scoped>
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}
.metric-card {
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid var(--color-border, #E5E7EB);
  background: var(--bg-surface, #fff);
}
.metric-card.flag-critical { border-color: var(--color-danger); background: var(--color-critical-bg); }
.metric-card.flag-high { border-color: var(--color-high-risk); background: var(--color-warning-soft-bg); }
.metric-card.flag-low { border-color: var(--color-warning); background: var(--color-warning-soft-bg); }
.metric-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.metric-name { font-size: 12px; color: var(--text-secondary, #6B7280); }
.metric-flag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 600;
}
.metric-flag.flag-critical { background: var(--color-danger); color: var(--color-text-inverse); }
.metric-flag.flag-high { background: var(--color-high-risk); color: var(--color-text-inverse); }
.metric-flag.flag-low { background: var(--color-warning); color: var(--color-text-inverse); }
.metric-flag.flag-normal { background: var(--color-normal-bg); color: var(--color-success); }
.metric-flag.flag-missing { background: var(--color-bg-inset); color: var(--color-text-secondary); }
.metric-value-row {
  display: flex;
  align-items: baseline;
  gap: 4px;
  margin-bottom: 4px;
}
.metric-value { font-size: 20px; font-weight: 700; color: var(--text-primary, #182230); }
.metric-unit { font-size: 12px; color: var(--text-tertiary, #9CA3AF); }
.metric-meta {
  display: flex;
  gap: 8px;
  font-size: 11px;
  color: var(--text-tertiary, #9CA3AF);
}
.metrics-empty {
  text-align: center;
  padding: 20px;
  color: var(--text-tertiary, #9CA3AF);
  font-size: 13px;
}
</style>
