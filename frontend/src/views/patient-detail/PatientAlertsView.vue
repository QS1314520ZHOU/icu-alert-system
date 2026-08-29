<template>
  <div class="alerts-layout">
    <aside class="alerts-sidebar">
      <section class="alerts-section">
        <div class="section-header">
          <h3>活跃预警</h3>
          <div class="alert-filters">
            <a-select v-model:value="severityFilter" size="small" style="width: 100px;" allow-clear placeholder="严重程度">
              <a-select-option value="critical">危急</a-select-option>
              <a-select-option value="high">高风险</a-select-option>
              <a-select-option value="warning">预警</a-select-option>
            </a-select>
            <a-select v-model:value="domainFilter" size="small" style="width: 120px;" allow-clear placeholder="领域">
              <a-select-option v-for="d in domains" :key="d.value" :value="d.value">{{ d.label }}</a-select-option>
            </a-select>
            <a-button size="small" @click="loadAlerts">刷新</a-button>
          </div>
        </div>
        <div v-if="filteredAlerts.length" class="alerts-list">
          <div v-for="alert in filteredAlerts" :key="alert._id" class="alert-card" :class="alertCardClass(alert)">
            <div class="alert-header">
              <span class="alert-severity-badge" :class="severityBadgeClass(alert)">{{ severityShort(alert) }}</span>
              <span class="alert-type">{{ alertTypeText(alert.alert_type) }}</span>
              <span class="alert-domain">{{ alertDomainLabel(alert.domain) }}</span>
              <span class="alert-time">{{ fmtTime(alert.created_at) }}</span>
            </div>
            <div class="alert-body">
              <p class="alert-description">{{ alert.description || alert.extra?.description || '' }}</p>
              <div class="alert-value">
                <span class="value-label">当前值：</span>
                <span class="value-text">{{ formatAlertValue(alert) }}</span>
              </div>
              <div v-if="alert.extra?.evidence" class="alert-evidence">
                <span class="evidence-label">证据：</span>
                <span>{{ alert.extra.evidence }}</span>
              </div>
            </div>
            <div class="alert-actions">
              <a-button size="small" @click="acknowledgeAlert(alert)">确认</a-button>
              <a-button size="small" @click="acknowledgeAlert(alert, 'resolved')">标记解决</a-button>
              <a-button v-if="alert.evidence_chunks?.length" size="small" type="link" @click="openEvidence(alert)">查看证据</a-button>
            </div>
          </div>
        </div>
        <a-empty v-else description="暂无活跃预警" :image-style="{ height: '40px' }" />
      </section>
    </aside>
    <main class="alerts-main">
      <CollapseSection>
        <template #title><h3 style="margin:0;font-size:15px;font-weight:600">AI风险预测</h3></template>
        <template #extra><a-button size="small" @click="loadAiRisk" :loading="aiRiskLoading">刷新</a-button></template>
        <div v-if="aiRiskForecast" class="ai-risk-detail">
          <div class="risk-summary"><p>{{ aiRiskText || '暂无风险摘要' }}</p></div>
          <div v-if="aiRiskOrganRows(aiRiskForecast).length" class="organ-assessment">
            <h4>器官评估</h4>
            <div class="organ-grid">
              <div v-for="organ in aiRiskOrganRows(aiRiskForecast)" :key="organ.key" class="organ-item">
                <span class="organ-name">{{ organ.label }}</span>
                <span class="organ-status" :class="organStatusClass(organ)">{{ organ.status_text }}</span>
                <p v-if="organ.evidence" class="organ-evidence">{{ organ.evidence }}</p>
              </div>
            </div>
          </div>
        </div>
        <a-empty v-else-if="!aiRiskLoading" description="暂无AI风险预测" :image-style="{ height: '40px' }" />
      </CollapseSection>
      <CollapseSection>
        <template #title><h3 style="margin:0;font-size:15px;font-weight:600">综合风险报告</h3></template>
        <template #extra><a-button size="small" @click="loadIntegratedRisk(true)" :loading="integratedRiskLoading">刷新</a-button></template>
        <div v-if="integratedRiskReport" class="integrated-risk">
          <div class="risk-report-summary">
            <p v-if="integratedRiskReport.summary">{{ integratedRiskReport.summary }}</p>
            <p v-if="integratedRiskReport.causal_chain" class="causal-chain">因果链：{{ integratedRiskReport.causal_chain }}</p>
            <p v-if="integratedRiskReport.deterioration_forecast" class="deterioration-forecast">恶化预判：{{ integratedRiskReport.deterioration_forecast }}</p>
          </div>
        </div>
        <a-empty v-else-if="!integratedRiskLoading" description="暂无综合风险报告" :image-style="{ height: '40px' }" />
      </CollapseSection>
      <CollapseSection v-if="personalizedThresholdRecord">
        <template #title><h3 style="margin:0;font-size:15px;font-weight:600">个性化阈值</h3></template>
        <template #extra><a-tag :color="personalizedThresholdRecord.status === 'approved' ? 'success' : 'warning'">{{ personalizedThresholdRecord.status === 'approved' ? '已审核' : '待审核' }}</a-tag></template>
        <div class="threshold-detail">
          <p v-if="personalizedThresholdRecord.summary">{{ personalizedThresholdRecord.summary }}</p>
          <div v-if="personalizedThresholdRecord.parameters?.length" class="threshold-params">
            <div v-for="param in personalizedThresholdRecord.parameters" :key="param.name || param.parameter" class="threshold-param">
              <span class="param-name">{{ param.name || param.parameter }}</span>
              <span class="param-range">{{ param.lower }} ~ {{ param.upper }}</span>
            </div>
          </div>
        </div>
      </CollapseSection>
      <section class="alerts-section">
        <div class="section-header"><h3>数字孪生诊疗推理</h3></div>
        <Suspense>
          <DigitalTwinTab :patient-id="patientId" :patient="patient" />
          <template #fallback><div class="loading-placeholder"><a-spin /></div></template>
        </Suspense>
      </section>
    </main>
  </div>
</template>
<script setup lang="ts">
import { ref, computed, defineAsyncComponent } from 'vue'
import CollapseSection from '../../components/common/CollapseSection.vue'
import { usePatientDetail } from '../../composables/usePatientDetail'

const DigitalTwinTab = defineAsyncComponent(() => import('../../components/patient-detail/DigitalTwinTab.vue'))

const {
  patient, alerts, aiRiskForecast, aiRiskText, aiRiskLoading,
  integratedRiskReport, integratedRiskLoading,
  loadAlerts, loadAiRisk, loadIntegratedRisk,
  acknowledgeAlert, openEvidence,
  normalizeSeverity, alertDomainLabel,
  alertTypeText, formatAlertValue, fmtTime,
  aiRiskOrganRows, route,
  personalizedThresholdRecord,
} = usePatientDetail()

const patientId = computed(() => String(route.params.id || ''))

const severityFilter = ref<string | undefined>(undefined)
const domainFilter = ref<string | undefined>(undefined)

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
    const severityOrder: Record<string, number> = { critical: 0, high: 1, warning: 2 }
    const sa = severityOrder[normalizeSeverity(a.severity)] ?? 3
    const sb = severityOrder[normalizeSeverity(b.severity)] ?? 3
    if (sa !== sb) return sa - sb
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  })
})

function alertCardClass(alert: any) {
  const sev = normalizeSeverity(alert.severity)
  return `alert-${sev}`
}

function severityBadgeClass(alert: any) {
  const sev = normalizeSeverity(alert.severity)
  return `badge-${sev}`
}

function severityShort(alert: any) {
  const sev = normalizeSeverity(alert.severity)
  if (sev === 'critical') return '危急'
  if (sev === 'high') return '高'
  return '预'
}

function organStatusClass(organ: any) {
  const status = String(organ.status_text || '').toLowerCase()
  if (status.includes('衰竭') || status.includes('failure')) return 'organ-critical'
  if (status.includes('受损') || status.includes('impaired')) return 'organ-warning'
  return 'organ-normal'
}
</script>

<style scoped>
.alerts-layout {
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 16px;
  align-items: start;
}

.alerts-sidebar {
  position: sticky;
  top: 120px;
  max-height: calc(100vh - 140px);
  overflow-y: auto;
}

.alerts-main {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.alerts-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

@media (max-width: 960px) {
  .alerts-layout {
    grid-template-columns: 1fr;
  }
  .alerts-sidebar {
    position: static;
    max-height: none;
  }
}

.alerts-section {
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  padding: 16px 20px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #1a1a1a;
}

.alert-filters {
  display: flex;
  gap: 8px;
}

.alerts-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: calc(100vh - 280px);
  overflow-y: auto;
}

.alert-card {
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 12px;
  border-left: 3px solid #d9d9d9;
}

.alert-critical { border-left-color: #ff4d4f; }
.alert-high { border-left-color: #fa8c16; }
.alert-warning { border-left-color: #faad14; }

.alert-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.alert-severity-badge {
  flex-shrink: 0;
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
}

.badge-critical { background: #ff4d4f; }
.badge-high { background: #fa8c16; }
.badge-warning { background: #faad14; }

.alert-type {
  font-size: 13px;
  font-weight: 600;
  color: #333;
}

.alert-domain {
  font-size: 11px;
  color: #999;
  padding: 1px 6px;
  background: #f5f5f5;
  border-radius: 4px;
}

.alert-time {
  margin-left: auto;
  font-size: 11px;
  color: #999;
}

.alert-body {
  margin-bottom: 8px;
}

.alert-description {
  margin: 0 0 6px;
  font-size: 13px;
  color: #666;
  line-height: 1.5;
}

.alert-value {
  font-size: 12px;
  color: #333;
}

.value-label {
  color: #999;
}

.value-text {
  font-weight: 600;
}

.alert-evidence {
  margin-top: 4px;
  font-size: 12px;
  color: #666;
}

.evidence-label {
  font-weight: 600;
}

.alert-actions {
  display: flex;
  gap: 8px;
}

/* AI Risk */
.ai-risk-detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.risk-summary p {
  margin: 0;
  font-size: 13px;
  color: #333;
  line-height: 1.6;
}

.organ-assessment h4 {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: #333;
}

.organ-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
}

.organ-item {
  padding: 10px;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  background: #fafbfc;
}

.organ-name {
  font-size: 12px;
  color: #666;
  font-weight: 500;
}

.organ-status {
  display: block;
  font-size: 14px;
  font-weight: 700;
  margin: 4px 0;
}

.organ-critical { color: #ff4d4f; }
.organ-warning { color: #fa8c16; }
.organ-normal { color: #52c41a; }

.organ-evidence {
  margin: 0;
  font-size: 11px;
  color: #999;
  line-height: 1.4;
}

.integrated-risk {
  max-height: 400px;
  overflow: auto;
}

.risk-report-data {
  font-size: 11px;
  color: #666;
  background: #fafafa;
  padding: 8px;
  border-radius: 4px;
  white-space: pre-wrap;
}
</style>







