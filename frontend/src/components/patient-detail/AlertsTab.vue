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
          <span class="alert-time">{{ fmtTime(item.created_at) || '时间未知' }}</span>
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
          <div class="alert-terminal-line">
            <span class="terminal-tag">EVENT</span>
            <span class="terminal-id">{{ item.rule_id || item.alert_type || item.category || 'monitor.rule' }}</span>
          </div>
          <div class="alert-meta">
            <span v-if="item.alert_type">{{ alertTypeText(item.alert_type) }}</span>
            <span v-if="item.category">{{ alertCategoryText(item.category) }}</span>
            <span v-if="item.parameter">{{ item.parameter }}</span>
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
                  <a-popover placement="topLeft" overlay-class-name="icu-monitor-popover">
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

<style scoped>
.modi-panel {
  margin-bottom: 16px;
  border: 1px solid rgba(80,199,255,.14);
  border-radius: 12px;
  padding: 16px;
  background: linear-gradient(180deg, rgba(7,20,34,.94) 0%, rgba(4,12,22,.96) 100%);
  box-shadow: inset 0 1px 0 rgba(145,228,255,.04);
}
.modi-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.modi-title {
  color: #eafcff;
  font-size: 15px;
  font-weight: 800;
  letter-spacing: .06em;
}
.modi-sub,
.modi-organs {
  margin-top: 4px;
  color: #8da4c7;
  font-size: 12px;
}
.modi-kpi-group {
  display: grid;
  grid-template-columns: repeat(2, minmax(100px, 1fr));
  gap: 8px;
}
.modi-kpi {
  border: 1px solid rgba(80,199,255,.12);
  border-radius: 10px;
  padding: 10px 12px;
  background: rgba(8,28,44,.78);
  text-align: right;
}
.modi-kpi > span {
  display: block;
  color: #7ecce1;
  font-size: 11px;
  letter-spacing: .08em;
}
.modi-kpi > strong {
  color: #effcff;
  font-size: 20px;
  font-family: 'Rajdhani', 'SF Mono', 'Consolas', monospace;
}
.modi-chart {
  height: 300px;
  margin-top: 8px;
}
.alert-feed {
  display: grid;
  gap: 12px;
}
.alert-card {
  display: grid;
  grid-template-columns: 18px 1fr;
  gap: 12px;
}
.alert-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 4px;
  gap: 8px;
}
.alert-time {
  font-size: 10px;
  color: #73cde0;
  letter-spacing: .08em;
  writing-mode: vertical-rl;
  transform: rotate(180deg);
}
.alert-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  flex: 0 0 auto;
}
.alert-line {
  width: 2px;
  flex: 1 1 auto;
  margin-top: 8px;
  border-radius: 999px;
  background: linear-gradient(180deg, #1f3c67 0%, #0f233f 100%);
}
.alert-body {
  border: 1px solid rgba(80,199,255,.12);
  border-left: 5px solid #f59e0b;
  border-radius: 12px;
  padding: 14px 18px;
  background: linear-gradient(180deg, rgba(7,20,34,.94) 0%, rgba(4,12,22,.96) 100%);
  box-shadow: inset 0 1px 0 rgba(145,228,255,.04);
}
.alert-card.sev-high .alert-body { border-left-color: #f97316; }
.alert-card.sev-critical .alert-body { border-left-color: #f43f5e; }
.alert-dot.sev-warning { background: #f59e0b; box-shadow: 0 0 8px rgba(245,158,11,.55); }
.alert-dot.sev-high { background: #f97316; box-shadow: 0 0 8px rgba(249,115,22,.55); }
.alert-dot.sev-critical { background: #f43f5e; box-shadow: 0 0 10px rgba(244,63,94,.6); }
.alert-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
.alert-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 22px;
}
.alert-title {
  margin: 0;
  color: #eafcff;
  font-size: 14px;
  font-weight: 700;
  line-height: 1.25;
}
.alert-pill {
  display: inline-flex;
  align-items: center;
  height: 20px;
  border-radius: 999px;
  padding: 0 8px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .08em;
  border: 1px solid transparent;
}
.alert-pill.sev-warning { color: #fcd34d; background: #3f2d07; border-color: #6a4b0d; }
.alert-pill.sev-high { color: #fdba74; background: #41210b; border-color: #7c3816; }
.alert-pill.sev-critical { color: #fda4af; background: #47131d; border-color: #7f1d32; }
.alert-value {
  font-family: 'Rajdhani', 'JetBrains Mono', 'Consolas', monospace;
  font-size: 18px;
  line-height: 1.2;
  color: #f1f6ff;
  font-weight: 800;
  text-align: right;
  white-space: nowrap;
}
.alert-terminal-line {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.terminal-tag {
  display: inline-flex;
  align-items: center;
  height: 18px;
  padding: 0 7px;
  border-radius: 999px;
  background: rgba(8, 30, 46, 0.88);
  border: 1px solid rgba(80,199,255,.12);
  color: #73d9ee;
  font-size: 10px;
  letter-spacing: .1em;
}
.terminal-id {
  color: #a9c7dd;
  font-size: 11px;
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  line-height: 1.4;
  word-break: break-all;
}
.alert-meta {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.alert-meta > span {
  font-size: 11px;
  color: #8da4c7;
  padding: 2px 8px;
  border-radius: 999px;
  background: #10233d;
  border: 1px solid #1b3a60;
}
.alert-rule {
  margin-top: 8px;
  font-size: 12px;
  color: #d7e6ff;
  font-family: 'JetBrains Mono', 'Consolas', monospace;
}
.alert-detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 8px 10px;
  margin-top: 10px;
}
.alert-detail-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  font-size: 11px;
  color: #9ca3af;
  background: #0f2038;
  border: 1px solid #1c3d64;
  border-radius: 8px;
  padding: 6px 8px;
}
.detail-label { color: #7aa2d6; }
.detail-value { color: #e5e7eb; font-weight: 600; }
.alert-extra {
  margin-top: 10px;
  white-space: pre-wrap;
  color: #94a3b8;
  font-size: 11px;
  line-height: 1.4;
  background: #0b1626;
  border: 1px solid #19304d;
  border-radius: 8px;
  padding: 8px;
}
.ai-risk-panel {
  margin-top: 12px;
  display: grid;
  gap: 10px;
}
.ai-risk-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.ai-risk-summary,
.ai-risk-card {
  border: 1px solid #214064;
  border-radius: 10px;
  background: #0d2036;
  padding: 10px 12px;
}
.ai-risk-summary {
  display: grid;
  gap: 4px;
  min-width: 240px;
}
.ai-risk-summary strong,
.ai-risk-card strong { color: #eef4ff; }
.ai-risk-summary span,
.ai-risk-card p {
  color: #b9cae8;
  font-size: 12px;
  margin: 0;
}
.ai-risk-feedback { display: flex; gap: 8px; flex-wrap: wrap; }
.ai-risk-feedback :deep(.ant-btn) {
  background: rgba(8,28,44,.78);
  border-color: rgba(80,199,255,.14);
  color: #dffbff;
}
.ai-risk-organ-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 8px;
}
.ai-risk-organ {
  border: 1px solid #1c3a5b;
  border-radius: 10px;
  background: #0c1d31;
  padding: 8px 10px;
  transition: opacity .2s ease;
}
.ai-risk-organ-top {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}
.ai-risk-organ-name { color: #d9e8ff; font-weight: 700; }
.ai-risk-organ-status,
.ai-risk-organ-conf,
.ai-risk-organ-evidence { font-size: 11px; }
.ai-risk-organ-status { color: #93c5fd; }
.ai-risk-organ-evidence { margin-top: 6px; color: #a9bbda; line-height: 1.5; }
.ai-risk-organ-conf { margin-top: 6px; color: #7fa0d0; }
.ai-risk-section {
  border: 1px solid #1d3554;
  border-radius: 10px;
  background: #0a1829;
  padding: 10px 12px;
}
.ai-risk-section-title {
  color: #dbe9ff;
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 8px;
}
.ai-risk-list {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 6px;
  color: #bfd0ec;
  font-size: 12px;
}
.ai-risk-list-warning { color: #fecaca; }
.ai-risk-list-hallucination { list-style: none; padding-left: 0; }
.hallucination-pill {
  display: inline-flex;
  align-items: center;
  padding: 6px 8px;
  border-radius: 999px;
  width: fit-content;
  max-width: 100%;
  border: 1px solid transparent;
}
.hallucination-warning { color: #fde68a; background: #3c2d06; border-color: #6b4f11; }
.hallucination-high { color: #fecaca; background: #47131d; border-color: #7f1d32; }
.ai-risk-evidence-list {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 6px;
}
.ai-evidence-link { color: #93c5fd; cursor: pointer; }
.ai-evidence-link:hover { color: #bfdbfe; }
.ai-evidence-popover {
  max-width: 420px;
  display: grid;
  gap: 6px;
  color: #334155;
}
.ai-evidence-quote {
  max-width: 420px;
  white-space: pre-wrap;
  line-height: 1.6;
}
.ai-confidence-low { opacity: 0.58; }
.ai-confidence-medium { opacity: 0.82; }
.ai-confidence-high { opacity: 1; }
.tab-empty {
  color: #7ccfe4;
  font-size: 12px;
  padding: 12px;
  border-radius: 10px;
  background: rgba(8,28,44,.58);
  border: 1px dashed rgba(80,199,255,.14);
}

@media (max-width: 980px) {
  .alert-head {
    flex-direction: column;
    align-items: flex-start;
  }
  .alert-value {
    text-align: left;
    font-size: 16px;
  }
  .alert-time {
    writing-mode: initial;
    transform: none;
  }
  .modi-chart {
    height: 260px;
  }
}

@media (max-width: 640px) {
  .alert-card {
    grid-template-columns: 1fr;
    gap: 6px;
  }
  .alert-rail {
    display: none;
  }
  .alert-body {
    padding: 10px;
  }
  .modi-kpi-group {
    width: 100%;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .modi-kpi {
    text-align: left;
  }
  .modi-chart {
    height: 240px;
  }
}
</style>
