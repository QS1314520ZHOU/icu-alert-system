<template>
  <section class="primary-risk" :class="riskClass">
    <div class="risk-header">
      <div class="risk-badge" :class="badgeClass">{{ severityText }}</div>
      <div class="risk-title-row">
        <h2 class="risk-title">{{ title }}</h2>
        <span class="risk-domain">{{ domainLabel }}</span>
      </div>
      <div class="risk-actions">
        <a-button size="small" @click="$emit('acknowledge', alert)">确认</a-button>
        <a-button v-if="hasEvidence" size="small" type="link" @click="$emit('open-evidence', alert)">查看证据</a-button>
      </div>
    </div>

    <div class="risk-body">
      <p class="risk-description">{{ description }}</p>

      <!-- 关键数值 -->
      <div v-if="keyMetrics.length" class="risk-metrics">
        <div v-for="m in keyMetrics" :key="m.label" class="metric-item">
          <span class="metric-label">{{ m.label }}</span>
          <span class="metric-value" :class="m.tone ? `metric-${m.tone}` : ''">{{ m.value }}</span>
        </div>
      </div>

      <!-- AI置信度 -->
      <div v-if="confidence" class="risk-confidence">
        <span class="confidence-label">AI置信度：</span>
        <a-progress :percent="confidencePercent" :stroke-color="confidenceColor" size="small" style="width: 120px;" />
        <span class="confidence-text">{{ confidenceText }}</span>
      </div>

      <!-- 脓毒症Bundle提示 -->
      <div v-if="showBundleHint" class="bundle-hint">
        <span class="bundle-hint-icon">⏱</span>
        <span>{{ bundleHintText }}</span>
      </div>
    </div>

    <!-- 其他预警折叠 -->
    <div v-if="otherAlerts.length" class="other-alerts-toggle" @click="showOthers = !showOthers">
      <span>{{ showOthers ? '收起' : `查看其他 ${otherAlerts.length} 条预警` }}</span>
      <span class="toggle-arrow" :class="{ open: showOthers }">▼</span>
    </div>
    <div v-if="showOthers && otherAlerts.length" class="other-alerts">
      <div v-for="a in otherAlerts" :key="a._id" class="other-alert-item">
        <span class="other-badge" :class="otherBadgeClass(a)">{{ severityShort(a) }}</span>
        <span class="other-text">{{ alertTypeText(a.alert_type) }} · {{ formatAlertValue(a) }}</span>
        <span class="other-time">{{ fmtTime(a.created_at) }}</span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { usePatientDetail } from '../../../composables/usePatientDetail'

const props = defineProps<{
  alert: any
  patient: any
  sepsis: any
}>()

defineEmits<{
  (e: 'acknowledge', alert: any): void
  (e: 'open-evidence', alert: any): void
}>()

const {
  alerts, normalizeSeverity, alertSeverityText, alertDomainLabel,
  alertTypeText, formatAlertValue, fmtTime, isAiRiskAlert,
  aiRiskConfidenceLevel,
} = usePatientDetail()

const showOthers = ref(false)

const title = computed(() => {
  if (!props.alert) return '暂无预警'
  return alertTypeText(props.alert.alert_type) || props.alert.title || '预警'
})

const description = computed(() => {
  if (!props.alert) return '当前无活跃预警'
  return props.alert.description || props.alert.extra?.description || ''
})

const severityText = computed(() => {
  if (!props.alert) return '—'
  return alertSeverityText(props.alert.severity)
})

const domainLabel = computed(() => {
  if (!props.alert) return ''
  return alertDomainLabel(props.alert.domain)
})

const riskClass = computed(() => {
  if (!props.alert) return 'risk-none'
  const sev = normalizeSeverity(props.alert.severity)
  return `risk-${sev}`
})

const badgeClass = computed(() => {
  if (!props.alert) return 'badge-none'
  const sev = normalizeSeverity(props.alert.severity)
  return `badge-${sev}`
})

const hasEvidence = computed(() => {
  return props.alert?.evidence_chunks?.length > 0 || props.alert?.extra?.evidence
})

// 关键数值
const keyMetrics = computed(() => {
  if (!props.alert) return []
  const extra = props.alert.extra || {}
  const metrics: { label: string; value: string; tone?: string }[] = []

  if (props.alert.value != null) {
    metrics.push({ label: '当前值', value: String(props.alert.value) })
  }
  if (extra.threshold != null) {
    metrics.push({ label: '阈值', value: String(extra.threshold) })
  }
  if (extra.score != null) {
    metrics.push({ label: '评分', value: String(extra.score) })
  }
  if (extra.modi != null) {
    metrics.push({ label: 'MODI', value: String(extra.modi), tone: extra.modi >= 3 ? 'critical' : extra.modi >= 2 ? 'warning' : 'normal' })
  }
  if (extra.organ_count != null) {
    metrics.push({ label: '涉及系统', value: `${extra.organ_count}个` })
  }
  return metrics
})

// AI置信度
const confidence = computed(() => {
  if (!props.alert || !isAiRiskAlert(props.alert)) return null
  return aiRiskConfidenceLevel(props.alert)
})

const confidencePercent = computed(() => {
  const map: Record<string, number> = { high: 85, medium: 60, low: 35 }
  return map[confidence.value || ''] || 50
})

const confidenceColor = computed(() => {
  const map: Record<string, string> = { high: '#52c41a', medium: '#faad14', low: '#ff4d4f' }
  return map[confidence.value || ''] || '#d9d9d9'
})

const confidenceText = computed(() => {
  const map: Record<string, string> = { high: '高', medium: '中', low: '低' }
  return map[confidence.value || ''] || '—'
})

// 脓毒症Bundle
const showBundleHint = computed(() => {
  return props.sepsis?.status === 'pending' || props.sepsis?.status === 'overdue_1h'
})

const bundleHintText = computed(() => {
  if (!props.sepsis) return ''
  if (props.sepsis.status === 'overdue_1h') return '脓毒症1h Bundle已超时，请尽快完成'
  return `脓毒症Bundle计时中：${props.sepsis.label || ''}`
})

// 其他预警
const otherAlerts = computed(() => {
  if (!props.alert || !alerts.value?.length) return []
  return alerts.value.filter((a: any) => a._id !== props.alert._id).slice(0, 10)
})

function otherBadgeClass(a: any) {
  const sev = normalizeSeverity(a?.severity)
  return `badge-${sev}`
}

function severityShort(a: any) {
  const sev = normalizeSeverity(a?.severity)
  if (sev === 'critical') return '危'
  if (sev === 'high') return '高'
  return '预'
}
</script>

<style scoped>
.primary-risk {
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  padding: 16px 20px;
  border-left: 4px solid #d9d9d9;
}

.risk-critical { border-left-color: #ff4d4f; }
.risk-high { border-left-color: #fa8c16; }
.risk-warning { border-left-color: #faad14; }
.risk-none { border-left-color: #d9d9d9; }

.risk-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}

.risk-badge {
  flex-shrink: 0;
  padding: 2px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.badge-critical { background: #fff1f0; color: #ff4d4f; }
.badge-high { background: #fff7e6; color: #fa8c16; }
.badge-warning { background: #fffbe6; color: #faad14; }
.badge-none { background: #f5f5f5; color: #999; }

.risk-title-row {
  flex: 1;
  min-width: 0;
}

.risk-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #1a1a1a;
  line-height: 1.4;
}

.risk-domain {
  font-size: 12px;
  color: #999;
}

.risk-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.risk-body {
  padding-left: 0;
}

.risk-description {
  margin: 0 0 10px;
  font-size: 13px;
  color: #666;
  line-height: 1.6;
}

.risk-metrics {
  display: flex;
  gap: 20px;
  margin-bottom: 10px;
}

.metric-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.metric-label {
  font-size: 11px;
  color: #999;
}

.metric-value {
  font-size: 18px;
  font-weight: 700;
  color: #1a1a1a;
}

.metric-critical { color: #ff4d4f; }
.metric-warning { color: #faad14; }
.metric-normal { color: #52c41a; }

.risk-confidence {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 12px;
  color: #666;
}

.confidence-text {
  font-weight: 600;
}

.bundle-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #fff7e6;
  border-radius: 6px;
  font-size: 12px;
  color: #d48806;
}

.bundle-hint-icon {
  font-size: 14px;
}

.other-alerts-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 0;
  margin-top: 8px;
  font-size: 12px;
  color: #1890ff;
  cursor: pointer;
  border-top: 1px solid #f0f0f0;
}

.toggle-arrow {
  font-size: 10px;
  transition: transform 0.2s;
}

.toggle-arrow.open {
  transform: rotate(180deg);
}

.other-alerts {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-top: 8px;
}

.other-alert-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 4px;
  background: #fafafa;
  font-size: 12px;
}

.other-badge {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 700;
  color: #fff;
}

.badge-critical .other-badge, .other-badge.badge-critical { background: #ff4d4f; }
.badge-high .other-badge, .other-badge.badge-high { background: #fa8c16; }
.badge-warning .other-badge, .other-badge.badge-warning { background: #faad14; }

.other-text {
  flex: 1;
  color: #333;
}

.other-time {
  color: #999;
  font-size: 11px;
}
</style>
