<template>
  <div
    class="metric-card"
    :class="[
      status && `metric-card--${status}`,
      { 'metric-card--clickable': !!to }
    ]"
    @click="handleClick"
  >
    <div class="metric-card__header">
      <span class="metric-card__label">{{ label }}</span>
      <span v-if="statusIcon" class="metric-card__status-icon">
        <component :is="statusIcon" />
      </span>
    </div>

    <div class="metric-card__value-row">
      <span class="metric-card__value" :style="valueStyle">{{ displayValue }}</span>
      <span v-if="unit" class="metric-card__unit">{{ unit }}</span>
    </div>

    <div v-if="trend !== undefined || changeText" class="metric-card__footer">
      <span v-if="trend !== undefined" class="metric-card__trend" :class="trendClass">
        <RiseOutlined v-if="trend > 0" />
        <FallOutlined v-if="trend < 0" />
        <MinusOutlined v-if="trend === 0" />
      </span>
      <span v-if="changeText" class="metric-card__change">{{ changeText }}</span>
    </div>

    <div v-if="dataTime" class="metric-card__time">{{ dataTime }}</div>

    <!-- 迷你趋势线插槽 -->
    <div v-if="$slots.sparkline" class="metric-card__sparkline">
      <slot name="sparkline" />
    </div>

    <!-- 空状态 -->
    <ClinicalEmptyState
      v-if="loading || error || empty"
      :type="loading ? 'loading' : error ? 'error' : 'no-data'"
      :message="loading ? '加载中' : error || '暂无数据'"
      size="small"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { RiseOutlined, FallOutlined, MinusOutlined } from '@ant-design/icons-vue'
import {
  CloseCircleFilled, ExclamationCircleFilled,
  WarningFilled, CheckCircleFilled,
} from '@ant-design/icons-vue'
import { type ClinicalStatus } from '../../../styles/tokens/colors'
import ClinicalEmptyState from './ClinicalEmptyState.vue'

const props = defineProps<{
  /** 指标名称 */
  label: string
  /** 当前值 */
  value?: string | number
  /** 单位 */
  unit?: string
  /** 临床状态 */
  status?: ClinicalStatus
  /** 趋势方向（正数上升，负数下降，0持平） */
  trend?: number
  /** 变化说明 */
  changeText?: string
  /** 数据时间 */
  dataTime?: string
  /** 点击跳转路由 */
  to?: string
  /** 大数字字号 */
  valueSize?: 'normal' | 'key' | 'monitor'
  /** 加载中 */
  loading?: boolean
  /** 错误信息 */
  error?: string
  /** 是否为空 */
  empty?: boolean
}>()

const emit = defineEmits<{ click: [] }>()
const router = useRouter()

const displayValue = computed(() => {
  if (props.value === undefined || props.value === null) return '--'
  return props.value
})

const valueStyle = computed(() => {
  const sizes = { normal: '20px', key: '24px', monitor: '28px' }
  return { fontSize: sizes[props.valueSize ?? 'key'] }
})

const statusIcon = computed(() => {
  if (!props.status) return null
  const map: Record<string, any> = {
    'critical': CloseCircleFilled,
    'high-risk': ExclamationCircleFilled,
    'warning': WarningFilled,
    'normal': CheckCircleFilled,
  }
  return map[props.status] ?? null
})

const trendClass = computed(() => {
  if (!props.trend) return 'metric-card__trend--flat'
  return props.trend > 0 ? 'metric-card__trend--up' : 'metric-card__trend--down'
})

function handleClick() {
  if (props.to) router.push(props.to)
  else emit('click')
}
</script>

<style scoped>
.metric-card {
  position: relative;
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg, 10px);
  padding: 14px 16px;
  min-height: 116px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.metric-card--clickable { cursor: pointer; }
.metric-card--clickable:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-sm);
}

/* 状态色左侧条 */
.metric-card--critical  { border-left: 3px solid var(--color-critical); }
.metric-card--high-risk { border-left: 3px solid var(--color-danger); }
.metric-card--warning   { border-left: 3px solid var(--color-warning); }
.metric-card--normal    { border-left: 3px solid var(--color-success, var(--color-normal)); }
.metric-card--info      { border-left: 3px solid var(--color-primary); }

.metric-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.metric-card__label {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-secondary);
}

.metric-card__status-icon {
  font-size: 16px;
}
.metric-card--critical .metric-card__status-icon { color: var(--color-critical); }
.metric-card--high-risk .metric-card__status-icon { color: var(--color-danger); }
.metric-card--warning .metric-card__status-icon { color: var(--color-warning); }
.metric-card--normal .metric-card__status-icon { color: var(--color-success, var(--color-normal)); }

.metric-card__value-row {
  display: flex;
  align-items: baseline;
  gap: 4px;
  margin-top: auto;
}

.metric-card__value {
  font-family: 'Rajdhani', 'Microsoft YaHei', sans-serif;
  font-weight: 700;
  line-height: 1.15;
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em;
}

.metric-card__unit {
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.metric-card__footer {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.metric-card__trend--up { color: var(--color-danger); }
.metric-card__trend--down { color: var(--color-normal); }
.metric-card__trend--flat { color: var(--color-unknown); }

.metric-card__change {
  color: var(--color-text-tertiary);
}

.metric-card__time {
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-top: 2px;
}

.metric-card__sparkline {
  margin-top: 6px;
  height: 32px;
}
</style>
