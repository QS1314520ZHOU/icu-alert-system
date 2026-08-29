<template>
  <div class="documents-view">
    <section class="doc-overview-row">
      <div class="doc-overview-card">
        <h4>数据完整性</h4>
        <DataCompletenessRing :value="dataCompleteness" :size="110" />
        <p class="doc-overview-hint">病历所需检验、影像、护理记录的完整度</p>
      </div>
      <div class="doc-overview-card doc-overview-timeline">
        <h4>文书事件时间线</h4>
        <ClinicalTimeline v-if="docTimelineEvents.length" :events="docTimelineEvents" direction="vertical" :type-filters="docEventTypeFilters" :show-filters="true" />
        <a-empty v-else description="暂无文书事件" :image-style="{ height: '30px' }" />
      </div>
    </section>
    <CollapseSection default-open>
      <template #title><h3 style="margin:0;font-size:15px;font-weight:600">AI智能分析</h3></template>
      <template #extra><a-button size="small" @click="loadAiAll" :loading="aiLabLoading || aiRuleLoading">加载全部</a-button></template>
      <div class="ai-grid">
        <div class="ai-card">
          <h4>检验解读</h4>
          <div v-if="aiLabLoading" class="ai-loading"><a-spin size="small" /></div>
          <div v-else-if="aiLabSummary" class="ai-content" v-html="renderMarkdown(aiLabSummary)"></div>
          <div v-else-if="aiLabError" class="ai-error">{{ aiLabError }}</div>
          <a-empty v-else description="暂无" :image-style="{ height: '30px' }" />
        </div>
        <div class="ai-card">
          <h4>规则推荐</h4>
          <div v-if="aiRuleLoading" class="ai-loading"><a-spin size="small" /></div>
          <div v-else-if="aiRuleRows.length" class="ai-content">
            <a-table :columns="ruleColumns" :data-source="aiRuleRows" :pagination="false" size="small" />
          </div>
          <div v-else-if="aiRuleError" class="ai-error">{{ aiRuleError }}</div>
          <a-empty v-else description="暂无" :image-style="{ height: '30px' }" />
        </div>
        <div v-if="metabolicPhaseRecord || metabolicPhaseLoading" class="ai-card">
          <h4>代谢阶段</h4>
          <a-button size="small" @click="loadMetabolicPhase" :loading="metabolicPhaseLoading" style="margin-bottom:8px">刷新</a-button>
          <div v-if="metabolicPhaseLoading" class="ai-loading"><a-spin size="small" /></div>
          <div v-else-if="metabolicPhaseRecord" class="ai-content">
            <p>阶段：{{ metabolicPhaseRecord.phase || metabolicPhaseRecord.stage || '—' }}</p>
            <p v-if="metabolicPhaseRecord.summary">{{ metabolicPhaseRecord.summary }}</p>
          </div>
          <div v-else-if="metabolicPhaseError" class="ai-error">{{ metabolicPhaseError }}</div>
        </div>
        <div v-if="betaBlockerAdvisorRecord || betaBlockerAdvisorLoading" class="ai-card">
          <h4>β受体阻滞剂建议</h4>
          <a-button size="small" @click="loadBetaBlockerAdvisor" :loading="betaBlockerAdvisorLoading" style="margin-bottom:8px">刷新</a-button>
          <div v-if="betaBlockerAdvisorLoading" class="ai-loading"><a-spin size="small" /></div>
          <div v-else-if="betaBlockerAdvisorRecord" class="ai-content">
            <p>建议：{{ betaBlockerAdvisorRecord.recommendation || betaBlockerAdvisorRecord.summary || '—' }}</p>
          </div>
          <div v-else-if="betaBlockerAdvisorError" class="ai-error">{{ betaBlockerAdvisorError }}</div>
        </div>
        <div v-if="fibrinolysisRecord || fibrinolysisLoading" class="ai-card">
          <h4>溶栓评估</h4>
          <a-button size="small" @click="loadFibrinolysis" :loading="fibrinolysisLoading" style="margin-bottom:8px">刷新</a-button>
          <div v-if="fibrinolysisLoading" class="ai-loading"><a-spin size="small" /></div>
          <div v-else-if="fibrinolysisRecord" class="ai-content">
            <p>评估：{{ fibrinolysisRecord.recommendation || fibrinolysisRecord.summary || '—' }}</p>
          </div>
          <div v-else-if="fibrinolysisError" class="ai-error">{{ fibrinolysisError }}</div>
        </div>
        <div v-if="pronePositionRecord || pronePositionLoading" class="ai-card">
          <h4>俯卧位建议</h4>
          <a-button size="small" @click="loadPronePosition" :loading="pronePositionLoading" style="margin-bottom:8px">刷新</a-button>
          <div v-if="pronePositionLoading" class="ai-loading"><a-spin size="small" /></div>
          <div v-else-if="pronePositionRecord" class="ai-content">
            <p>建议：{{ pronePositionRecord.recommendation || pronePositionRecord.summary || '—' }}</p>
          </div>
          <div v-else-if="pronePositionError" class="ai-error">{{ pronePositionError }}</div>
        </div>
        <div v-if="picsRiskRecord || picsRiskLoading" class="ai-card">
          <h4>PICS风险评估</h4>
          <a-button size="small" @click="loadPicsRisk" :loading="picsRiskLoading" style="margin-bottom:8px">刷新</a-button>
          <div v-if="picsRiskLoading" class="ai-loading"><a-spin size="small" /></div>
          <div v-else-if="picsRiskRecord" class="ai-content">
            <p>风险等级：{{ picsRiskRecord.risk_level || picsRiskRecord.level || '—' }}</p>
            <p v-if="picsRiskRecord.summary">{{ picsRiskRecord.summary }}</p>
          </div>
          <div v-else-if="picsRiskError" class="ai-error">{{ picsRiskError }}</div>
        </div>
      </div>
    </CollapseSection>
    <div class="doc-split-grid">
      <CollapseSection>
        <template #title><h3 style="margin:0;font-size:15px;font-weight:600">交班摘要 (I-PASS)</h3></template>
        <template #extra>
          <div class="handoff-actions">
            <a-button size="small" @click="loadAiHandoff" :loading="aiHandoffLoading">刷新</a-button>
            <a-button v-if="aiHandoff" size="small" @click="copyHandoffSummary">复制</a-button>
          </div>
        </template>
        <div v-if="aiHandoffLoading" class="loading-placeholder"><a-spin /></div>
        <div v-else-if="aiHandoff" class="handoff-detail">
          <div class="handoff-row"><span class="handoff-label">疾病严重度：</span><a-tag :color="handoffSeverityColor">{{ aiHandoff.illness_severity || '—' }}</a-tag></div>
          <div class="handoff-row"><span class="handoff-label">患者摘要：</span><span>{{ aiHandoff.patient_summary || '—' }}</span></div>
          <div class="handoff-row"><span class="handoff-label">待办事项：</span><ul v-if="actionList.length"><li v-for="(item, idx) in actionList" :key="idx">{{ item }}</li></ul><span v-else>—</span></div>
          <div class="handoff-row"><span class="handoff-label">情境意识：</span><ul v-if="situationAwareness.length"><li v-for="(item, idx) in situationAwareness" :key="idx">{{ item }}</li></ul><span v-else>—</span></div>
          <div class="handoff-row"><span class="handoff-label">接收者综合：</span><span>{{ aiHandoff.synthesis_by_receiver || '—' }}</span></div>
          <div class="handoff-confidence"><span>置信度：</span><a-tag :color="confidenceColor">{{ confidenceLabel }}</a-tag></div>
        </div>
        <a-empty v-else-if="!aiHandoffLoading" description="暂无交班摘要" :image-style="{ height: '40px' }" />
      </CollapseSection>
      <CollapseSection>
        <template #title><h3 style="margin:0;font-size:15px;font-weight:600">相似病例</h3></template>
        <template #extra><a-button size="small" @click="loadSimilarCaseReview(true)" :loading="similarCaseLoading">刷新</a-button></template>
        <div v-if="similarCaseLoading" class="loading-placeholder"><a-spin /></div>
        <div v-else-if="similarCaseReview" class="similar-cases">
          <div class="similar-summary">
            <span v-if="similarCaseReview.summary?.matched_cases">匹配 {{ similarCaseReview.summary.matched_cases }} 例</span>
            <span v-if="similarCaseReview.summary?.survival_rate">存活率 {{ Math.round(similarCaseReview.summary.survival_rate * 100) }}%</span>
            <a-tag v-if="similarCaseReview.summary?.degraded" color="warning">降级模式</a-tag>
          </div>
          <div v-if="similarCaseReview.cases?.length" class="cases-list">
            <div v-for="c in similarCaseReview.cases" :key="c.id || c.case_id" class="case-item">
              <div class="case-header"><span class="case-id">{{ c.case_id || c.id || '—' }}</span><span class="case-similarity">相似度 {{ c.similarity != null ? `${Math.round(c.similarity * 100)}%` : '—' }}</span></div>
              <p v-if="c.summary || c.description" class="case-summary">{{ c.summary || c.description }}</p>
              <div v-if="c.outcome" class="case-outcome"><span class="outcome-label">结局：</span><span :class="outcomeClass(c.outcome)">{{ c.outcome }}</span></div>
            </div>
          </div>
        </div>
        <a-empty v-else-if="!similarCaseLoading && similarCaseLoaded" description="暂无相似病例" :image-style="{ height: '40px' }" />
      </CollapseSection>
    </div>
    <CollapseSection>
      <template #title><h3 style="margin:0;font-size:15px;font-weight:600">离线知识库</h3></template>
      <template #extra>
        <div class="knowledge-actions">
          <a-button size="small" @click="loadKnowledgeDocs" :loading="knowledgeLoading">刷新</a-button>
          <a-button size="small" @click="handleReloadKnowledge" :loading="knowledgeLoading">热更新</a-button>
        </div>
      </template>
      <div v-if="knowledgeLoading" class="loading-placeholder"><a-spin /></div>
      <div v-else-if="knowledgeDocs.length" class="knowledge-list">
        <div v-for="doc in knowledgeDocs" :key="doc.doc_id" class="knowledge-item" :class="{ active: selectedKnowledgeDocId === doc.doc_id }" @click="selectKnowledgeDoc(doc)">
          <span class="doc-title">{{ doc.title || doc.filename || doc.doc_id }}</span>
          <span class="doc-scope">{{ knowledgeScopeText(doc.scope) }}</span>
        </div>
      </div>
      <a-empty v-else-if="!knowledgeLoading" description="暂无知识库文档" :image-style="{ height: '40px' }" />
    </CollapseSection>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import CollapseSection from '../../components/common/CollapseSection.vue'
import { usePatientDetail } from '../../composables/usePatientDetail'
import DataCompletenessRing from '../../components/charts/risk/DataCompletenessRing.vue'
import ClinicalTimeline from '../../components/charts/timeline/ClinicalTimeline.vue'
import type { TimelineEvent } from '../../components/charts'

const {
  aiLabSummary, aiLabLoading, aiLabError,
  aiRuleRows, aiRuleLoading, aiRuleError,
  aiHandoff, aiHandoffLoading, aiHandoffConfidence,
  loadAiAll, loadAiHandoff, copyHandoffSummary,
  similarCaseReview, similarCaseLoading, similarCaseLoaded,
  loadSimilarCaseReview,
  knowledgeDocs, selectedKnowledgeDocId, knowledgeLoading,
  knowledgeScopeText,
  loadKnowledgeDocs, loadKnowledgeDocument, handleReloadKnowledge,
  normalizeList, alerts,
  metabolicPhaseRecord, metabolicPhaseLoading, metabolicPhaseError, loadMetabolicPhase,
  betaBlockerAdvisorRecord, betaBlockerAdvisorLoading, betaBlockerAdvisorError, loadBetaBlockerAdvisor,
  fibrinolysisRecord, fibrinolysisLoading, fibrinolysisError, loadFibrinolysis,
  pronePositionRecord, pronePositionLoading, pronePositionError, loadPronePosition,
  picsRiskRecord, picsRiskLoading, picsRiskError, loadPicsRisk,
} = usePatientDetail()

// ── 数据完整性 ──────────────────────────────────────────────────────
const dataCompleteness = computed(() => {
  // 基于已加载的数据类型计算完整性
  let total = 5
  let filled = 0
  if (aiLabSummary.value) filled++
  if (aiRuleRows.value?.length) filled++
  if (aiHandoff.value) filled++
  if (similarCaseReview.value) filled++
  if (knowledgeDocs.value?.length) filled++
  return Math.round((filled / total) * 100)
})

// ── 文书事件时间线 ──────────────────────────────────────────────────
const docTimelineEvents = computed<TimelineEvent[]>(() => {
  const events: TimelineEvent[] = []
  // 从 alerts 中提取文书相关事件
  const docTypes = ['lab', 'imaging', 'order', 'note', 'assessment']
  for (const a of (alerts.value || [])) {
    const t = a.alert_type || a.type || ''
    if (docTypes.some(dt => String(t).toLowerCase().includes(dt))) {
      events.push({
        time: a.triggered_at || a.created_at || '',
        type: t.includes('lab') ? '检验' : t.includes('imaging') ? '影像' : t.includes('order') ? '医嘱' : '评估',
        title: a.name || a.rule_id || a.title || '事件',
        description: a.description || a.message || '',
      })
    }
  }
  return events.slice(0, 20)
})

const docEventTypeFilters = computed(() => {
  const types = new Set(docTimelineEvents.value.map(e => e.type))
  return [...types].map(t => ({ label: t, value: t }))
})

const ruleColumns = [
  { title: '参数', dataIndex: 'parameter', key: 'parameter' },
  { title: '条件', dataIndex: 'operator', key: 'operator' },
  { title: '阈值', dataIndex: 'threshold', key: 'threshold' },
  { title: '级别', dataIndex: 'severity', key: 'severity' },
  { title: '依据', dataIndex: 'reason', key: 'reason', ellipsis: true },
]

const actionList = computed(() => normalizeList(aiHandoff.value?.action_list))
const situationAwareness = computed(() => normalizeList(aiHandoff.value?.situation_awareness))

const handoffSeverityColor = computed(() => {
  const v = String(aiHandoff.value?.illness_severity || '').toLowerCase()
  if (v === 'critical' || v === 'unstable') return 'error'
  if (v === 'watcher' || v === 'watch') return 'warning'
  return 'success'
})

const confidenceColor = computed(() => {
  const map: Record<string, string> = { high: 'success', medium: 'warning', low: 'error' }
  return map[aiHandoffConfidence.value] || 'default'
})

const confidenceLabel = computed(() => {
  const map: Record<string, string> = { high: '高', medium: '中', low: '低' }
  return map[aiHandoffConfidence.value] || '—'
})

function renderMarkdown(text: string) {
  if (!text) return ''
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
}

function outcomeClass(outcome: string) {
  const v = String(outcome || '').toLowerCase()
  if (v.includes('死亡') || v.includes('death')) return 'outcome-death'
  if (v.includes('存活') || v.includes('survival')) return 'outcome-survival'
  return ''
}

function selectKnowledgeDoc(doc: any) {
  selectedKnowledgeDocId.value = doc.doc_id
  loadKnowledgeDocument(doc.doc_id)
}
</script>

<style scoped>
.documents-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 数据完整性 + 文书事件概览 */
.doc-overview-row {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 16px;
}

.doc-overview-card {
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  padding: 16px;
}

.doc-overview-card h4 {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: #1a1a1a;
}

.doc-overview-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: #8c8c8c;
  text-align: center;
}

.doc-overview-timeline {
  min-height: 200px;
  max-height: 360px;
  overflow-y: auto;
}

.documents-section {
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

.loading-placeholder {
  display: flex;
  justify-content: center;
  padding: 40px 0;
}

/* AI Grid - 2 columns for all cards */
.ai-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

/* Split grid for handoff + similar */
.doc-split-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.doc-split-grid > .documents-section {
  margin: 0;
}

@media (max-width: 900px) {
  .ai-grid {
    grid-template-columns: 1fr;
  }
  .doc-split-grid {
    grid-template-columns: 1fr;
  }
}

.ai-card {
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  padding: 12px;
  background: #fafbfc;
}

.ai-card h4 {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: #333;
}

.ai-loading {
  display: flex;
  justify-content: center;
  padding: 20px 0;
}

.ai-content {
  font-size: 13px;
  color: #333;
  line-height: 1.6;
}

.ai-error {
  font-size: 12px;
  color: #ff4d4f;
}

/* Handoff */
.handoff-actions {
  display: flex;
  gap: 8px;
}

.handoff-detail {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.handoff-row {
  display: flex;
  gap: 8px;
  font-size: 13px;
  color: #333;
}

.handoff-label {
  flex-shrink: 0;
  font-weight: 600;
  color: #666;
  min-width: 90px;
}

.handoff-row ul {
  margin: 0;
  padding-left: 16px;
}

.handoff-row li {
  margin-bottom: 2px;
}

.handoff-confidence {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #666;
}

/* Similar cases */
.similar-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  font-size: 13px;
  color: #666;
}

.cases-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.case-item {
  padding: 10px 12px;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  background: #fafbfc;
}

.case-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.case-id {
  font-size: 13px;
  font-weight: 600;
  color: #333;
}

.case-similarity {
  font-size: 12px;
  color: #1890ff;
}

.case-summary {
  margin: 0 0 4px;
  font-size: 12px;
  color: #666;
  line-height: 1.5;
}

.case-outcome {
  font-size: 12px;
}

.outcome-label {
  color: #999;
}

.outcome-death { color: #ff4d4f; font-weight: 600; }
.outcome-survival { color: #52c41a; font-weight: 600; }

/* Knowledge */
.knowledge-actions {
  display: flex;
  gap: 8px;
}

.knowledge-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.knowledge-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.knowledge-item:hover {
  background: #f0f7ff;
  border-color: #1890ff;
}

.knowledge-item.active {
  background: #e6f7ff;
  border-color: #1890ff;
}

.doc-title {
  font-size: 13px;
  color: #333;
  font-weight: 500;
}

.doc-scope {
  font-size: 11px;
  color: #999;
  padding: 1px 6px;
  background: #f5f5f5;
  border-radius: 4px;
}
</style>






