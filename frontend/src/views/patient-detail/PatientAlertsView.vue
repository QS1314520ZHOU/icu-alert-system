<template>
  <div class="alerts-page">
    <PageHeader title="临床预警" subtitle="活跃预警列表，可按严重程度与领域快速筛选" />

    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <span class="alert-count" v-if="filteredAlerts.length">{{ filteredAlerts.length }} 条活跃</span>
        <span class="alert-count alert-count--ok" v-else>暂无活跃预警</span>
      </div>

      <div class="toolbar-right">
        <!-- 严重程度筛选 -->
        <div class="seg-filter">
          <button
            v-for="s in severityOptions"
            :key="s.value"
            :class="['seg-btn', { active: severityFilter === s.value }]"
            @click="severityFilter = severityFilter === s.value ? undefined : s.value"
          >
            <span class="seg-dot" :class="`seg-dot--${s.value}`"></span>
            {{ s.label }}
          </button>
        </div>

        <!-- 领域筛选 -->
        <select v-model="domainFilter" class="field-select">
          <option value="">全部领域</option>
          <option v-for="d in domains" :key="d.value" :value="d.value">{{ d.label }}</option>
        </select>

        <!-- 刷新 -->
        <button class="icon-btn" @click="handleRefresh" :disabled="alertsLoading" title="刷新数据">
          <span :class="{ spinning: alertsLoading }">↻</span>
        </button>
      </div>
    </div>

    <!-- 预警列表 -->
    <div class="alerts-content">
      <template v-if="filteredAlerts.length">
        <div
          v-for="alert in filteredAlerts"
          :key="alert._id"
          :class="['alert-row', `alert-row--${normalizeSeverity(alert.severity)}`]"
        >
          <!-- 左侧：严重等级标记 -->
          <div class="row-severity">
            <span class="sev-badge" :class="`sev-${normalizeSeverity(alert.severity)}`">
              {{ severityShort(alert) }}
            </span>
          </div>

          <!-- 中间：核心信息 -->
          <div class="row-body">
            <div class="row-top">
              <span class="row-type">{{ alertTypeText(alert) }}</span>
              <span class="row-domain" :class="`dom-${alert.domain}`">{{ alertDomainLabel(alert.domain) }}</span>
              <span class="row-time">{{ fmtTime(alert.created_at) }}</span>
            </div>
            <p class="row-desc">{{ alert.description || alert.extra?.description || '—' }}</p>
            <div class="row-values">
              <span v-if="formatAlertValue(alert)" class="row-val">
                当前 <strong>{{ formatAlertValue(alert) }}</strong>
              </span>
              <span v-if="alert.extra?.threshold" class="row-val row-val--dim">
                阈值 {{ alert.extra.threshold }}
              </span>
              <span v-if="alert.extra?.evidence" class="row-evidence">{{ alert.extra.evidence }}</span>
            </div>
          </div>

          <!-- 右侧：操作 -->
          <div class="row-actions">
            <button class="action-btn" @click="handleAcknowledge(alert)">确认</button>
            <button class="action-btn action-btn--ghost" @click="handleAcknowledge(alert, 'resolved')">解决</button>
            <button v-if="alert.evidence_chunks?.length" class="action-btn action-btn--link" @click="openEvidenceDrawer && openEvidenceDrawer({ title: alertTypeText(alert) })">证据</button>
          </div>
        </div>
      </template>

      <!-- 空状态 -->
      <div v-else class="empty-state">
        <div class="empty-icon">✓</div>
        <p class="empty-text">所有预警已处理</p>
        <p class="empty-hint">当前无活跃风险指标</p>
      </div>
    </div>

    <!-- 底部提示 -->
    <div class="footer-tip">
      <span>需要更深入的风险分析？</span>
      <router-link :to="`/patient/${patientId}/tool/risk-prediction`">风险预测</router-link>
      <span>·</span>
      <router-link :to="`/patient/${patientId}/tool/integrated-risk`">综合风险</router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { PageHeader } from '../../components/common/design-system'
import { ref, computed } from 'vue'
import { usePatientDetail } from '../../composables/usePatientDetail'

const {
  alerts,
  loadAlerts, acknowledgeAlert,
  normalizeSeverity, alertDomainLabel,
  alertTypeText, formatAlertValue, fmtTime,
  route,
} = usePatientDetail()

const patientId = computed(() => String(route.params.patientId || route.params.id || ''))

// 证据抽屉（由父布局注入）
import { inject } from 'vue'
const openEvidenceDrawer = inject<(opts: { title: string }) => void>('openEvidenceDrawer')
const alertsLoading = ref(false)

async function handleRefresh() {
  alertsLoading.value = true
  try {
    await loadAlerts()
  } finally {
    alertsLoading.value = false
  }
}

async function handleAcknowledge(alert: any, status?: string) {
  await acknowledgeAlert(alert, status)
}

// ── 筛选 ──
const severityFilter = ref<string | undefined>(undefined)
const domainFilter = ref('')

const severityOptions = [
  { value: 'critical', label: '危急' },
  { value: 'high', label: '高风险' },
  { value: 'warning', label: '预警' },
]

const domains = [
  { value: 'physiologic_alarm', label: '生理危急' },
  { value: 'clinical_risk', label: '临床风险' },
  { value: 'workflow_reminder', label: '流程提醒' },
  { value: 'quality_gap', label: '质控缺项' },
  { value: 'ai_advisory', label: 'AI建议' },
]

const filteredAlerts = computed(() => {
  let result = [...(alerts.value || [])]
  if (severityFilter.value) {
    result = result.filter((a: any) => normalizeSeverity(a.severity) === severityFilter.value)
  }
  if (domainFilter.value) {
    result = result.filter((a: any) => String(a.domain || '') === domainFilter.value)
  }
  return result.sort((a: any, b: any) => {
    const order: Record<string, number> = { critical: 0, high: 1, warning: 2 }
    const sa = order[normalizeSeverity(a.severity)] ?? 3
    const sb = order[normalizeSeverity(b.severity)] ?? 3
    if (sa !== sb) return sa - sb
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  })
})

function severityShort(alert: any) {
  const sev = normalizeSeverity(alert.severity)
  if (sev === 'critical') return '危'
  if (sev === 'high') return '高'
  return '预'
}
</script>

<style scoped>
/* ── 页面 ──────────────────────────────────── */
.alerts-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ── 工具栏 ────────────────────────────────── */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: var(--text-section-title);
  font-weight: 700;
  color: var(--color-text-primary);
}

.title-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-danger);
}

.alert-count {
  font-size: var(--text-label);
  font-variant-numeric: tabular-nums;
  color: var(--color-text-secondary);
  padding: 2px 8px;
  background: var(--color-bg-surface-secondary);
  border-radius: var(--radius-tag);
  font-weight: 500;
}

.alert-count--ok {
  background: var(--color-normal-bg);
  font-variant-numeric: tabular-nums;
  color: var(--color-normal);
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* ── 分段筛选 ──────────────────────────────── */
.seg-filter {
  display: flex;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.seg-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: none;
  background: var(--color-bg-surface);
  font-size: var(--text-label);
  font-weight: 500;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.15s;
  border-right: 1px solid var(--color-border);
}

.seg-btn:last-child {
  border-right: none;
}

.seg-btn:hover {
  background: var(--color-bg-surface-secondary);
}

.seg-btn.active {
  background: var(--color-primary);
  color: var(--color-text-inverse);
}

.seg-btn.active .seg-dot {
  background: var(--color-bg-surface);
}

.seg-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.seg-dot--critical { background: var(--color-danger); }
.seg-dot--high { background: var(--color-high-risk); }
.seg-dot--warning { background: var(--color-warning-soft); }

/* ── 领域选择 ──────────────────────────────── */
.field-select {
  padding: 4px 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--text-label);
  color: var(--color-text-primary);
  background: var(--color-bg-surface);
  cursor: pointer;
  outline: none;
}

.field-select:focus {
  border-color: var(--color-primary);
}

/* ── 刷新按钮 ──────────────────────────────── */
.icon-btn {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-surface);
  font-size: var(--text-body);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}

.icon-btn:hover:not(:disabled) {
  background: var(--color-bg-surface-secondary);
  color: var(--color-text-primary);
}

.icon-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spinning {
  display: inline-block;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ── 预警行 ────────────────────────────────── */
.alerts-content {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.alert-row {
  display: flex;
  align-items: stretch;
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
  transition: border-color 0.15s;
}

.alert-row:hover {
  border-color: var(--color-border-strong);
}

.alert-row--critical {
  border-left: 3px solid var(--color-danger);
}

.alert-row--high {
  border-left: 3px solid var(--color-high-risk);
}

.alert-row--warning {
  border-left: 3px solid var(--color-warning-soft);
}

/* 严重等级标记 */
.row-severity {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 40px;
  padding: 8px 0;
}

.sev-badge {
  width: 26px;
  height: 26px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-label);
  font-weight: 700;
  color: var(--color-text-inverse);
}

.sev-critical { background: var(--color-danger); }
.sev-high { background: var(--color-high-risk); }
.sev-warning { background: var(--color-warning-soft); color: var(--color-warning); }

/* 核心信息 */
.row-body {
  flex: 1;
  min-width: 0;
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.row-top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.row-type {
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--color-text-primary);
}

.row-domain {
  font-size: var(--text-caption);
  padding: 1px 6px;
  border-radius: var(--radius-tag);
  font-weight: 500;
}

.dom-physiologic_alarm { background: var(--color-critical-bg); color: var(--color-critical); }
.dom-clinical_risk { background: var(--color-warning-soft-bg); color: var(--color-warning); }
.dom-workflow_reminder { background: var(--color-primary-bg); color: var(--color-primary); }
.dom-quality_gap { background: var(--color-ai-light); color: var(--color-ai); }
.dom-ai_advisory { background: var(--color-normal-bg); color: var(--color-success); }

.row-time {
  margin-left: auto;
  font-size: var(--text-caption);
  color: var(--color-text-tertiary);
  font-family: 'Rajdhani', monospace;
  white-space: nowrap;
}

.row-desc {
  margin: 0;
  font-size: var(--text-label);
  color: var(--color-text-secondary);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-values {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 2px;
}

.row-val {
  font-size: var(--text-label);
  color: var(--color-text-secondary);
}

.row-val strong {
  font-family: 'Rajdhani', monospace;
  font-size: var(--text-body);
  font-weight: 700;
  color: var(--color-text-primary);
}

.row-val--dim {
  color: var(--color-text-tertiary);
}

.row-evidence {
  font-size: var(--text-caption);
  color: var(--color-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 操作按钮 */
.row-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 10px;
  flex-shrink: 0;
}

.action-btn {
  height: 26px;
  padding: 0 10px;
  border-radius: var(--radius-tag);
  border: 1px solid var(--color-border);
  background: var(--color-bg-surface);
  font-size: var(--text-caption);
  font-weight: 600;
  color: var(--color-text-primary);
  cursor: pointer;
  transition: all 0.15s;
}

.action-btn:hover {
  background: var(--color-bg-surface-secondary);
  border-color: var(--color-border-strong);
}

.action-btn--ghost {
  border: none;
  color: var(--color-text-secondary);
}

.action-btn--ghost:hover {
  color: var(--color-text-primary);
}

.action-btn--link {
  border: none;
  color: var(--color-primary);
  padding: 0 6px;
}

.action-btn--link:hover {
  background: var(--color-primary-bg);
}

/* ── 空状态 ────────────────────────────────── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 48px 16px;
  background: var(--color-bg-surface);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-lg);
}

.empty-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--color-normal-bg);
  color: var(--color-normal);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 10px;
}

.empty-text {
  margin: 0 0 4px;
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--color-text-primary);
}

.empty-hint {
  margin: 0;
  font-size: var(--text-label);
  color: var(--color-text-tertiary);
}

/* ── 底部提示 ──────────────────────────────── */
.footer-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  font-size: var(--text-label);
  color: var(--color-text-tertiary);
  background: var(--color-bg-surface-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-divider);
}

.footer-tip a {
  color: var(--color-primary);
  text-decoration: none;
  font-weight: 500;
}

.footer-tip a:hover {
  text-decoration: underline;
}

/* ── 响应式 ────────────────────────────────── */
@media (max-width: 768px) {
  .toolbar {
    flex-wrap: wrap;
    gap: 10px;
  }

  .toolbar-right {
    flex-wrap: wrap;
  }

  .row-actions {
    flex-direction: column;
    padding: 4px 8px;
  }
}
</style>