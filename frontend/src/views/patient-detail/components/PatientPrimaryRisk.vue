<template>
  <section class="alert-card" :class="riskClass">
    <!-- 左侧色条 + 严重等级 -->
    <div class="card-rail">
      <span class="rail-badge" :class="`rail-${riskLevel}`">{{ severityText }}</span>
    </div>

    <!-- 主内容 -->
    <div class="card-body">
      <div class="card-row">
        <!-- 标题 + 领域 -->
        <div class="card-info">
          <h2 class="card-title">{{ title }}</h2>
          <span class="card-domain">{{ domainLabel }}</span>
        </div>

        <!-- 关键数值 -->
        <div v-if="keyMetrics.length" class="card-metrics">
          <span v-for="m in keyMetrics" :key="m.label" :class="['metric-chip', m.tone ? `mc--${m.tone}` : '']">
            <span class="mc-label">{{ m.label }}</span>
            <span class="mc-value">{{ m.value }}</span>
          </span>
        </div>

        <!-- AI -->
        <span v-if="confidence" class="ai-badge" :style="{ color: confidenceColor }">AI {{ confidenceText }}</span>

        <!-- 操作 -->
        <div class="card-actions">
          <button v-if="hasEvidence" class="abtn abtn--link" @click="$emit('open-evidence', alert)">证据</button>
          <button class="abtn abtn--primary" @click="$emit('acknowledge', alert)">确认</button>
        </div>
      </div>

      <!-- 描述 -->
      <p v-if="description" class="card-desc">{{ description }}</p>

      <!-- Bundle -->
      <div v-if="showBundleHint" class="card-bundle">⏱ {{ bundleHintText }}</div>
    </div>

    <!-- 其他预警 -->
    <div v-if="otherAlerts.length" class="card-expand" @click="showOthers = !showOthers">
      <span>{{ showOthers ? '收起' : `${otherAlerts.length} 条其他预警` }}</span>
      <span class="expand-chevron" :class="{ open: showOthers }">›</span>
    </div>
    <div v-if="showOthers && otherAlerts.length" class="card-others">
      <div v-for="a in otherAlerts" :key="a._id" class="other-item">
        <span class="other-dot" :class="`dot-${normalizeSeverity(a?.severity)}`"></span>
        <span>{{ alertTypeText(a) }}</span>
        <span class="other-val">{{ formatAlertValue(a) }}</span>
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
  return alertTypeText(props.alert) || props.alert.title || '预警'
})

const description = computed(() => {
  if (!props.alert) return ''
  return props.alert.description || props.alert.extra?.description || ''
})

const severityText = computed(() => {
  if (!props.alert) return '—'
  return alertSeverityText(props.alert.severity)
})

const riskLevel = computed(() => {
  if (!props.alert) return 'none'
  return normalizeSeverity(props.alert.severity)
})

const domainLabel = computed(() => {
  if (!props.alert) return ''
  return alertDomainLabel(props.alert.domain)
})

const riskClass = computed(() => `risk-${riskLevel.value}`)

const hasEvidence = computed(() => {
  return props.alert?.evidence_chunks?.length > 0 || props.alert?.extra?.evidence
})

const keyMetrics = computed(() => {
  if (!props.alert) return []
  const extra = props.alert.extra || {}
  const m: { label: string; value: string; tone?: string }[] = []
  if (props.alert.value != null) m.push({ label: '当前值', value: String(props.alert.value) })
  if (extra.threshold != null) m.push({ label: '阈值', value: String(extra.threshold) })
  if (extra.score != null) m.push({ label: '评分', value: String(extra.score) })
  if (extra.modi != null) m.push({ label: 'MODI', value: String(extra.modi), tone: extra.modi >= 3 ? 'critical' : extra.modi >= 2 ? 'warning' : 'normal' })
  if (extra.organ_count != null) m.push({ label: '涉及系统', value: `${extra.organ_count}个` })
  return m
})

const confidence = computed(() => {
  if (!props.alert || !isAiRiskAlert(props.alert)) return null
  return aiRiskConfidenceLevel(props.alert)
})

const confidenceColor = computed(() => {
  const map: Record<string, string> = { high: '#16A34A', medium: '#F59E0B', low: '#D92D20' }
  return map[confidence.value || ''] || '#94A3B8'
})

const confidenceText = computed(() => {
  const map: Record<string, string> = { high: '高', medium: '中', low: '低' }
  return map[confidence.value || ''] || '—'
})

const showBundleHint = computed(() => props.sepsis?.status === 'pending' || props.sepsis?.status === 'overdue_1h')

const bundleHintText = computed(() => {
  if (!props.sepsis) return ''
  if (props.sepsis.status === 'overdue_1h') return '脓毒症1h Bundle已超时，请尽快完成'
  return `脓毒症Bundle计时中：${props.sepsis.label || ''}`
})

const otherAlerts = computed(() => {
  if (!props.alert || !alerts.value?.length) return []
  return alerts.value.filter((a: any) => a._id !== props.alert._id).slice(0, 10)
})
</script>

<style scoped>
.alert-card {
  display: flex;
  flex-direction: column;
  background: #fff;
  border: 1px solid #E3E7EC;
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 12px;
}

.alert-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

/* ── 左侧色条 ──────────────────────────────── */
.card-rail {
  padding: 10px 14px;
  display: flex;
  align-items: center;
}

.risk-critical .card-rail { background: #FEF2F2; }
.risk-high .card-rail { background: #FFF7ED; }
.risk-warning .card-rail { background: #FFFBEB; }
.risk-none .card-rail { background: #F8FAFC; }

.rail-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 700;
}

.rail-critical { background: #D92D20; color: #fff; }
.rail-high { background: #F79009; color: #fff; }
.rail-warning { background: #E5B700; color: #713F12; }
.rail-none { background: #E2E8F0; color: #64748B; }

/* ── 主体 ──────────────────────────────────── */
.card-body {
  padding: 10px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.card-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.card-info {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.card-title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: #18212B;
}

.card-domain {
  font-size: 12px;
  color: #94A3B8;
}

/* 数值 chip */
.card-metrics {
  display: flex;
  gap: 8px;
}

.metric-chip {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 4px;
  background: #F1F3F5;
}

.mc-label {
  font-size: 11px;
  color: #94A3B8;
}

.mc-value {
  font-family: 'Rajdhani', monospace;
  font-size: 15px;
  font-weight: 700;
  color: #18212B;
}

.mc--critical { background: #FEF2F2; }
.mc--critical .mc-value { color: #D92D20; }
.mc--warning { background: #FFFBEB; }
.mc--warning .mc-value { color: #B8860B; }
.mc--normal { background: #F0FDF4; }
.mc--normal .mc-value { color: #12A66A; }

/* AI badge */
.ai-badge {
  font-size: 11px;
  font-weight: 600;
}

/* 按钮 */
.card-actions {
  display: flex;
  gap: 6px;
  margin-left: auto;
}

.abtn {
  height: 28px;
  padding: 0 12px;
  border-radius: 5px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.15s;
}

.abtn--primary {
  background: var(--color-danger, #D92D20);
  color: #fff;
}

.abtn--primary:hover {
  background: var(--color-danger-hover, #B42318);
}

.risk-high .abtn--primary {
  background: var(--color-high-risk, #F79009);
}

.abtn--link {
  background: transparent;
  color: #667085;
  border-color: #E3E7EC;
}

.abtn--link:hover {
  background: #F1F3F5;
}

/* 描述 */
.card-desc {
  margin: 0;
  font-size: 12px;
  color: #667085;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Bundle */
.card-bundle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 4px;
  background: #FFFBEB;
  font-size: 11px;
  color: #92400E;
  width: fit-content;
}

/* ── 折叠其他 ──────────────────────────────── */
.card-expand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 6px 16px;
  font-size: 12px;
  color: var(--color-primary, #2563EB);
  cursor: pointer;
  border-top: 1px solid #E3E7EC;
}

.card-expand:hover {
  background: rgba(37, 99, 235, 0.03);
}

.expand-chevron {
  font-weight: 700;
  transition: transform 0.2s;
  display: inline-block;
}

.expand-chevron.open {
  transform: rotate(90deg);
}

/* ── 其他预警 ──────────────────────────────── */
.card-others {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px 16px 10px;
}

.other-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 4px;
  background: #F8FAFC;
  font-size: 12px;
}

.other-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot-critical { background: #D92D20; }
.dot-high { background: #F79009; }
.dot-warning { background: #E5B700; }
.dot-low, .dot-stable { background: #12A66A; }

.other-val {
  font-family: 'Rajdhani', monospace;
  font-weight: 700;
  font-size: 13px;
  color: #18212B;
}

.other-time {
  margin-left: auto;
  color: #94A3B8;
  font-size: 11px;
}

/* ── 响应式 ────────────────────────────────── */
@media (max-width: 768px) {
  .card-row {
    gap: 8px;
  }
  .card-metrics {
    width: 100%;
  }
  .card-actions {
    margin-left: 0;
  }
}
</style>