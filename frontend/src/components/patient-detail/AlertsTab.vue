<template>
  <div>
    <div v-if="latestCompositeAlert" class="modi-panel">
      <div class="modi-head">
        <div>
          <div class="modi-title">多器官恶化指数 (MODI)</div>
          <div class="modi-sub">
            {{ fmtTime(latestCompositeAlert.created_at) || '时间未知' }} · 最近{{ latestCompositeWindowHours }}h
          </div>
        </div>
        <div class="modi-kpi-group">
          <div class="modi-kpi">
            <span>MODI</span>
            <strong>{{ latestCompositeModi ?? '—' }}</strong>
          </div>
          <div class="modi-kpi">
            <span>器官系统</span>
            <strong>{{ latestCompositeOrganCount }}</strong>
          </div>
        </div>
      </div>
      <div class="modi-organs">{{ latestCompositeInvolvedText }}</div>
      <div class="modi-chart">
        <DetailChart :option="compositeRadarOption" autoresize />
      </div>
    </div>
    <div v-if="alerts.length" class="alert-feed">
      <article
        v-for="(item, idx) in alerts"
        :key="item._id || item.created_at || idx"
        :class="['alert-card', `sev-${normalizeSeverity(item.severity)}`]"
      >
        <div class="alert-rail">
          <span :class="['alert-dot', `sev-${normalizeSeverity(item.severity)}`]"></span>
          <span v-if="idx < alerts.length - 1" class="alert-line"></span>
        </div>
        <div class="alert-body">
          <div class="alert-head">
            <div class="alert-title-row">
              <h4 class="alert-title">{{ item.name || item.rule_id || '预警' }}</h4>
              <span :class="['alert-pill', `sev-${normalizeSeverity(item.severity)}`]">
                {{ alertSeverityText(item.severity) }}
              </span>
            </div>
            <div class="alert-value">{{ formatAlertValue(item) }}</div>
          </div>
          <div class="alert-meta">
            <span>{{ fmtTime(item.created_at) || '时间未知' }}</span>
            <span v-if="item.alert_type">{{ alertTypeText(item.alert_type) }}</span>
            <span v-if="item.category">{{ alertCategoryText(item.category) }}</span>
          </div>
          <div
            v-if="item.parameter || item.condition?.operator || item.condition?.threshold"
            class="alert-rule"
          >
            {{ item.parameter || '参数' }}
            {{ item.condition?.operator || '' }}
            {{ item.condition?.threshold || '' }}
          </div>
          <div v-if="alertDetailFields(item).length" class="alert-detail-grid">
            <div v-for="f in alertDetailFields(item)" :key="f.label" class="alert-detail-item">
              <span class="detail-label">{{ f.label }}</span>
              <span class="detail-value">{{ f.value ?? '—' }}</span>
            </div>
          </div>
          <div v-if="isAiRiskAlert(item)" class="ai-risk-panel">
            <div class="ai-risk-head">
              <div :class="['ai-risk-summary', aiConfidenceClass(aiRiskConfidenceLevel(item))]">
                <strong>{{ item.extra?.primary_risk || item.name || 'AI综合风险' }}</strong>
                <span>风险等级 {{ aiRiskLevelText(item.extra?.risk_level || item.condition?.risk_level || item.value) }}</span>
                <span v-if="item.ai_feedback?.outcome">反馈 {{ feedbackOutcomeText(item.ai_feedback.outcome) }}</span>
              </div>
              <div class="ai-risk-feedback">
                <a-button size="small" @click="submitAiFeedback(item, 'confirmed')">采纳</a-button>
                <a-button size="small" @click="submitAiFeedback(item, 'dismissed')">忽略</a-button>
                <a-button size="small" danger ghost @click="submitAiFeedback(item, 'inaccurate')">不准确</a-button>
              </div>
            </div>
            <div v-if="aiRiskOrganRows(item).length" class="ai-risk-organ-grid">
              <div
                v-for="row in aiRiskOrganRows(item)"
                :key="row.key"
                :class="['ai-risk-organ', aiConfidenceClass(row.confidence_level)]"
              >
                <div class="ai-risk-organ-top">
                  <span class="ai-risk-organ-name">{{ row.label }}</span>
                  <span class="ai-risk-organ-status">{{ row.status_text }}</span>
                </div>
                <div class="ai-risk-organ-evidence">{{ row.evidence || '未见证据' }}</div>
                <div class="ai-risk-organ-conf">置信度 {{ row.confidence_level }}</div>
              </div>
            </div>
            <div v-if="aiRiskValidationIssues(item).length" class="ai-risk-section">
              <div class="ai-risk-section-title">安全校验</div>
              <ul class="ai-risk-list ai-risk-list-warning">
                <li v-for="(issue, issueIdx) in aiRiskValidationIssues(item)" :key="issueIdx">
                  {{ issue.message || issue.type || '存在校验问题' }}
                </li>
              </ul>
            </div>
            <div v-if="aiRiskHallucinations(item).length" class="ai-risk-section">
              <div class="ai-risk-section-title">幻觉检测</div>
              <ul class="ai-risk-list ai-risk-list-hallucination">
                <li
                  v-for="(flag, flagIdx) in aiRiskHallucinations(item)"
                  :key="flagIdx"
                  :class="['hallucination-pill', `hallucination-${flag.level || 'warning'}`]"
                >
                  {{ flag.metric || '指标' }}: 输出 {{ flag.claimed }} / 实测 {{ flag.observed }}
                </li>
              </ul>
            </div>
            <div v-if="aiRiskEvidenceList(item).length" class="ai-risk-section">
              <div class="ai-risk-section-title">证据脚注</div>
              <ol class="ai-risk-evidence-list">
                <li v-for="(evidence, evidenceIdx) in aiRiskEvidenceList(item)" :key="evidence.chunk_id || evidenceIdx">
                  <a-popover placement="topLeft">
                    <template #content>
                      <div class="ai-evidence-popover">
                        <div><strong>{{ evidence.source || '指南证据' }}</strong></div>
                        <div v-if="evidence.recommendation">{{ evidence.recommendation }}</div>
                        <div class="ai-evidence-quote">{{ evidence.quote || '暂无原文片段' }}</div>
                      </div>
                    </template>
                    <a class="ai-evidence-link" @click.prevent="openEvidence(evidence)">
                      [{{ evidenceIdx + 1 }}] {{ evidence.source || '未知来源' }}<span v-if="evidence.recommendation"> · {{ evidence.recommendation }}</span>
                    </a>
                  </a-popover>
                </li>
              </ol>
            </div>
            <div v-if="aiRiskExplainabilityRows(item).length" class="ai-risk-section">
              <div class="ai-risk-section-title">归因解释</div>
              <ul class="ai-risk-list">
                <li v-for="(factor, factorIdx) in aiRiskExplainabilityRows(item)" :key="factorIdx">
                  {{ factor.factor }}<span v-if="factor.weight != null"> ({{ Math.round(Number(factor.weight || 0) * 100) }}%)</span>
                  <span v-if="factor.evidence">：{{ factor.evidence }}</span>
                </li>
              </ul>
            </div>
          </div>
          <pre v-else-if="item.extra && !alertDetailFields(item).length" class="alert-extra">{{ formatAlertExtra(item.extra) }}</pre>
        </div>
      </article>
    </div>
    <div v-if="!alerts.length" class="tab-empty">暂无预警记录</div>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { Button as AButton, Popover as APopover } from 'ant-design-vue'

defineProps<{
  latestCompositeAlert: any
  latestCompositeWindowHours: any
  latestCompositeModi: any
  latestCompositeOrganCount: any
  latestCompositeInvolvedText: any
  compositeRadarOption: any
  alerts: any[]
  fmtTime: (v: any) => string
  normalizeSeverity: (v: any) => string
  alertSeverityText: (v: any) => string
  formatAlertValue: (item: any) => string
  alertTypeText: (v: any) => string
  alertCategoryText: (v: any) => string
  alertDetailFields: (item: any) => any[]
  isAiRiskAlert: (item: any) => boolean
  aiConfidenceClass: (v: any) => string
  aiRiskConfidenceLevel: (item: any) => string
  aiRiskLevelText: (v: any) => string
  feedbackOutcomeText: (v: any) => string
  submitAiFeedback: (item: any, outcome: 'confirmed' | 'dismissed' | 'inaccurate') => void | Promise<void>
  aiRiskOrganRows: (item: any) => any[]
  aiRiskValidationIssues: (item: any) => any[]
  aiRiskHallucinations: (item: any) => any[]
  aiRiskEvidenceList: (item: any) => any[]
  openEvidence: (evidence: any) => void
  aiRiskExplainabilityRows: (item: any) => any[]
  formatAlertExtra: (extra: any) => string
}>()

const DetailChart = defineAsyncComponent(async () => {
  await import('../../charts/patient-detail')
  const mod = await import('vue-echarts')
  return mod.default
})
</script>
