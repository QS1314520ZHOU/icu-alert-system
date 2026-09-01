<template>
  <div class="alerts-page">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <h2 class="page-title">
          <span class="title-dot"></span>
          临床预警
        </h2>
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
  background: #fff;
  border: 1px solid #E3E7EC;
  border-radius: 8px;
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
  font-size: 15px;
  font-weight: 700;
  color: #18212B;
}

.title-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-danger, #D92D20);
}

.alert-count {
  font-size: 12px;
  color: #667085;
  padding: 2px 8px;
  background: #F1F3F5;
  border-radius: 4px;
  font-weight: 500;
}

.alert-count--ok {
  background: var(--color-normal-bg, #E8F7F0);
  color: var(--color-normal, #12A66A);
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* ── 分段筛选 ──────────────────────────────── */
.seg-filter {
  display: flex;
  border: 1px solid #E3E7EC;
  border-radius: 6px;
  overflow: hidden;
}

.seg-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: none;
  background: #fff;
  font-size: 12px;
  font-weight: 500;
  color: #667085;
  cursor: pointer;
  transition: all 0.15s;
  border-right: 1px solid #E3E7EC;
}

.seg-btn:last-child {
  border-right: none;
}

.seg-btn:hover {
  background: #F1F3F5;
}

.seg-btn.active {
  background: #18212B;
  color: #fff;
}

.seg-btn.active .seg-dot {
  background: #fff;
}

.seg-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.seg-dot--critical { background: #D92D20; }
.seg-dot--high { background: #F79009; }
.seg-dot--warning { background: #E5B700; }

/* ── 领域选择 ──────────────────────────────── */
.field-select {
  padding: 4px 8px;
  border: 1px solid #E3E7EC;
  border-radius: 6px;
  font-size: 12px;
  color: #18212B;
  background: #fff;
  cursor: pointer;
  outline: none;
}

.field-select:focus {
  border-color: var(--color-primary, #2563EB);
}

/* ── 刷新按钮 ──────────────────────────────── */
.icon-btn {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #E3E7EC;
  border-radius: 6px;
  background: #fff;
  font-size: 14px;
  color: #667085;
  cursor: pointer;
  transition: all 0.15s;
}

.icon-btn:hover:not(:disabled) {
  background: #F1F3F5;
  color: #18212B;
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
  background: #fff;
  border: 1px solid #E3E7EC;
  border-radius: 6px;
  overflow: hidden;
  transition: border-color 0.15s;
}

.alert-row:hover {
  border-color: #CBD5E1;
}

.alert-row--critical {
  border-left: 3px solid #D92D20;
}

.alert-row--high {
  border-left: 3px solid #F79009;
}

.alert-row--warning {
  border-left: 3px solid #E5B700;
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
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
}

.sev-critical { background: #D92D20; }
.sev-high { background: #F79009; }
.sev-warning { background: #E5B700; color: #713F12; }

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
  font-size: 13px;
  font-weight: 600;
  color: #18212B;
}

.row-domain {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
  font-weight: 500;
}

.dom-physiologic_alarm { background: #FEF2F2; color: #991B1B; }
.dom-clinical_risk { background: #FFFBEB; color: #92400E; }
.dom-workflow_reminder { background: #EFF6FF; color: #1E40AF; }
.dom-quality_gap { background: #F5F3FF; color: #5B21B6; }
.dom-ai_advisory { background: #F0FDF4; color: #166534; }

.row-time {
  margin-left: auto;
  font-size: 11px;
  color: #94A3B8;
  font-family: 'Rajdhani', monospace;
  white-space: nowrap;
}

.row-desc {
  margin: 0;
  font-size: 12px;
  color: #667085;
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
  font-size: 12px;
  color: #475569;
}

.row-val strong {
  font-family: 'Rajdhani', monospace;
  font-size: 14px;
  font-weight: 700;
  color: #18212B;
}

.row-val--dim {
  color: #94A3B8;
}

.row-evidence {
  font-size: 11px;
  color: #94A3B8;
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
  border-radius: 4px;
  border: 1px solid #E3E7EC;
  background: #fff;
  font-size: 11px;
  font-weight: 600;
  color: #18212B;
  cursor: pointer;
  transition: all 0.15s;
}

.action-btn:hover {
  background: #F1F3F5;
  border-color: #CBD5E1;
}

.action-btn--ghost {
  border: none;
  color: #667085;
}

.action-btn--ghost:hover {
  color: #18212B;
}

.action-btn--link {
  border: none;
  color: var(--color-primary, #2563EB);
  padding: 0 6px;
}

.action-btn--link:hover {
  background: var(--color-primary-bg, rgba(37, 99, 235, 0.06));
}

/* ── 空状态 ────────────────────────────────── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 48px 16px;
  background: #fff;
  border: 1px dashed #E3E7EC;
  border-radius: 8px;
}

.empty-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--color-normal-bg, #E8F7F0);
  color: var(--color-normal, #12A66A);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 10px;
}

.empty-text {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 600;
  color: #18212B;
}

.empty-hint {
  margin: 0;
  font-size: 12px;
  color: #94A3B8;
}

/* ── 底部提示 ──────────────────────────────── */
.footer-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  font-size: 12px;
  color: #94A3B8;
  background: #F8FAFC;
  border-radius: 6px;
  border: 1px solid #F1F3F5;
}

.footer-tip a {
  color: var(--color-primary, #2563EB);
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