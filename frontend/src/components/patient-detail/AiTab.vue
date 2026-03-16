<template>
  <div class="ai-grid">
    <a-card title="检验异常摘要" :bordered="false" class="ai-card">
      <div class="ai-card-head">
        <span class="ai-card-note">进入详情自动生成</span>
        <a-button size="small" type="link" :loading="aiLabLoading" @click="loadAiLab">重新生成</a-button>
      </div>
      <a-spin :spinning="aiLabLoading">
        <div v-if="aiLabSummary" class="ai-rich" v-html="renderAiRichText(aiLabSummary)"></div>
        <div v-else class="ai-empty">暂无内容</div>
      </a-spin>
      <div v-if="aiLabError" class="ai-error">{{ aiLabError }}</div>
    </a-card>

    <a-card title="规则推荐" :bordered="false" class="ai-card">
      <div class="ai-card-head">
        <span class="ai-card-note">进入详情自动生成</span>
        <a-button size="small" type="link" :loading="aiRuleLoading" @click="loadAiRules">重新生成</a-button>
      </div>
      <a-spin :spinning="aiRuleLoading">
        <div v-if="aiRuleRows.length" class="ai-rule-wrap">
          <a-table
            size="small"
            class="ai-rule-table"
            :columns="aiRuleColumns"
            :data-source="aiRuleRows"
            :pagination="{ pageSize: 8, hideOnSinglePage: true }"
            :scroll="{ x: 920 }"
            row-key="key"
          />
        </div>
        <div v-else-if="aiRuleText" class="ai-rich" v-html="renderAiRichText(aiRuleText)"></div>
        <div v-else class="ai-empty">暂无内容</div>
      </a-spin>
      <div v-if="aiRuleError" class="ai-error">{{ aiRuleError }}</div>
    </a-card>

    <a-card title="恶化风险预测" :bordered="false" class="ai-card">
      <div class="ai-card-head">
        <span class="ai-card-note">进入详情自动生成</span>
        <a-button size="small" type="link" :loading="aiRiskLoading" @click="loadAiRisk">重新生成</a-button>
      </div>
      <a-spin :spinning="aiRiskLoading">
        <div v-if="latestAiRiskAlert" :class="['ai-risk-card', aiConfidenceClass(aiRiskConfidenceLevel(latestAiRiskAlert))]">
          <div class="workbench-kpis">
            <div class="wb-kpi">
              <span>主要风险</span>
              <strong>{{ latestAiRiskAlert.extra?.primary_risk || latestAiRiskAlert.name || '综合风险' }}</strong>
            </div>
            <div class="wb-kpi">
              <span>风险等级</span>
              <strong>{{ aiRiskLevelText(latestAiRiskAlert.extra?.risk_level || latestAiRiskAlert.condition?.risk_level || latestAiRiskAlert.value) }}</strong>
            </div>
            <div class="wb-kpi">
              <span>安全校验</span>
              <strong>{{ latestAiRiskAlert.extra?.safety_validation?.status || 'ok' }}</strong>
            </div>
          </div>
          <div v-if="aiRiskEvidenceList(latestAiRiskAlert).length" class="ai-workbench-section">
            <div class="ai-workbench-title">证据脚注</div>
            <div class="ai-footnote-row">
              <span
                v-for="(evidence, idx) in aiRiskEvidenceList(latestAiRiskAlert)"
                :key="evidence.chunk_id || idx"
                class="ai-evidence-inline"
              >
                <a-popover placement="topLeft" overlay-class-name="icu-monitor-popover">
                  <template #default>
                    <a
                      class="ai-evidence-link"
                      @click.prevent="openEvidence(evidence)"
                    >
                      [{{ idx + 1 }}]
                    </a>
                  </template>
                  <template #content>
                    <div class="ai-evidence-popover">
                      <div><strong>{{ evidence.source || '指南证据' }}</strong></div>
                      <div v-if="evidence.recommendation">{{ evidence.recommendation }}</div>
                      <div class="ai-evidence-quote">{{ evidence.quote || '暂无原文片段' }}</div>
                    </div>
                  </template>
                </a-popover>
              </span>
            </div>
          </div>
          <div v-if="aiRiskHallucinations(latestAiRiskAlert).length" class="ai-workbench-section">
            <div class="ai-workbench-title handoff-warning">幻觉检测</div>
            <div class="workbench-flag">提示 {{ aiRiskHallucinations(latestAiRiskAlert).length }} 条异常声明</div>
          </div>
        </div>
        <div v-else-if="aiRiskText" class="ai-rich" v-html="renderAiRichText(aiRiskText)"></div>
        <div v-else class="ai-empty">暂无内容</div>
      </a-spin>
      <div v-if="aiRiskError" class="ai-error">{{ aiRiskError }}</div>
    </a-card>

    <a-card title="交班摘要(I-PASS)" :bordered="false" class="ai-card">
      <div class="ai-card-head">
        <span class="ai-card-note">最近12h自动归纳</span>
        <div>
          <a-button size="small" type="link" :loading="aiHandoffLoading" @click="loadAiHandoff">重新生成</a-button>
          <a-button size="small" type="link" :disabled="!aiHandoff" @click="copyHandoffSummary">复制</a-button>
        </div>
      </div>
      <a-spin :spinning="aiHandoffLoading">
        <div v-if="aiHandoff" :class="['handoff-wrap', aiConfidenceClass(aiHandoffConfidence)]">
          <div class="workbench-kpis">
            <div class="wb-kpi">
              <span>Illness severity</span>
              <strong>{{ aiHandoff.illness_severity || 'watcher' }}</strong>
            </div>
            <div class="wb-kpi">
              <span>Confidence</span>
              <strong>{{ aiHandoff.confidence_level || 'low' }}</strong>
            </div>
            <div class="wb-kpi">
              <span>Validation</span>
              <strong>{{ aiHandoff?.validation?.issues?.length ? `警告 ${aiHandoff.validation.issues.length}` : 'ok' }}</strong>
            </div>
          </div>
          <div class="ai-workbench-section">
            <div class="ai-workbench-title">Patient summary</div>
            <div class="workbench-text">{{ aiHandoff.patient_summary || '—' }}</div>
          </div>
          <div class="ai-workbench-section">
            <div class="ai-workbench-title">Action list</div>
            <ul class="workbench-list">
              <li v-for="(item, idx) in normalizeList(aiHandoff.action_list)" :key="`a-${idx}`">{{ item }}</li>
            </ul>
          </div>
          <div class="ai-workbench-section">
            <div class="ai-workbench-title">Situation awareness</div>
            <ul class="workbench-list">
              <li v-for="(item, idx) in normalizeList(aiHandoff.situation_awareness)" :key="`s-${idx}`">{{ item }}</li>
            </ul>
          </div>
          <div class="ai-workbench-section">
            <div class="ai-workbench-title">Synthesis by receiver</div>
            <div class="workbench-text">{{ aiHandoff.synthesis_by_receiver || '—' }}</div>
          </div>
        </div>
        <div v-else class="ai-empty">暂无内容</div>
      </a-spin>
      <div v-if="aiHandoffError" class="ai-error">{{ aiHandoffError }}</div>
    </a-card>

    <a-card title="离线知识包" :bordered="false" class="ai-card">
      <div class="ai-card-head">
        <span class="ai-card-note">内网离线知识证据浏览</span>
        <div>
          <a-button size="small" type="link" :loading="knowledgeLoading" @click="loadKnowledgeDocs">刷新列表</a-button>
          <a-button size="small" type="link" :loading="knowledgeLoading" @click="handleReloadKnowledge">热更新</a-button>
        </div>
      </div>
      <a-spin :spinning="knowledgeLoading">
        <div v-if="knowledgeDocs.length" class="kb-browser">
          <div v-if="knowledgeStatus" class="kb-status">
            <span>{{ knowledgeStatus.package_name || '离线知识包' }}</span>
            <span v-if="knowledgeStatus.package_version">v{{ knowledgeStatus.package_version }}</span>
            <span>文档 {{ knowledgeStatus.document_count ?? 0 }}</span>
            <span>院内SOP {{ knowledgeStatus.institutional_document_count ?? 0 }}</span>
          </div>
          <a-select
            :value="selectedKnowledgeDocId"
            size="small"
            popup-class-name="icu-monitor-select-dropdown"
            style="width: 100%; margin-bottom: 8px;"
            placeholder="选择离线文档"
            @change="loadKnowledgeDocument"
          >
            <a-select-option v-for="doc in knowledgeDocs" :key="doc.doc_id" :value="doc.doc_id">
              {{ doc.title }} · P{{ doc.priority ?? 0 }}
            </a-select-option>
          </a-select>
          <div v-if="selectedKnowledgeDoc" class="kb-doc-meta">
            <p><strong>来源:</strong> {{ selectedKnowledgeDoc.source || '本地知识库' }}</p>
            <p><strong>知识包:</strong> {{ selectedKnowledgeDoc.package_name || '离线知识包' }} <span v-if="selectedKnowledgeDoc.package_version">v{{ selectedKnowledgeDoc.package_version }}</span></p>
            <p><strong>作用域:</strong> {{ knowledgeScopeText(selectedKnowledgeDoc.scope) }}<span v-if="selectedKnowledgeDoc.overridden" class="kb-overridden"> · 已被 {{ selectedKnowledgeDoc.overridden_by }} 覆盖</span></p>
            <p><strong>优先级:</strong> {{ selectedKnowledgeDoc.priority ?? '—' }}</p>
            <p v-if="selectedKnowledgeDoc.local_ref"><strong>离线路径:</strong> <code>{{ selectedKnowledgeDoc.local_ref }}</code></p>
          </div>
          <div v-if="selectedKnowledgeDoc?.chunks?.length" class="kb-chunk-list">
            <div
              v-for="chunk in selectedKnowledgeDoc.chunks"
              :key="chunk.chunk_id"
              class="kb-chunk-item"
            >
              <div class="kb-chunk-title">
                {{ chunk.recommendation || chunk.section_title || chunk.chunk_id }}
                <span v-if="chunk.recommendation_grade">· {{ chunk.recommendation_grade }}</span>
              </div>
              <div class="kb-chunk-content">{{ chunk.content }}</div>
            </div>
          </div>
          <div v-else class="ai-empty">暂无章节内容</div>
        </div>
        <div v-else class="ai-empty">暂无离线知识文档</div>
      </a-spin>
      <div v-if="knowledgeError" class="ai-error">{{ knowledgeError }}</div>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import {
  Button as AButton,
  Card as ACard,
  Popover as APopover,
  Select as ASelect,
  SelectOption as ASelectOption,
  Spin as ASpin,
  Table as ATable,
} from 'ant-design-vue'

defineProps<{
  aiLabLoading: boolean
  aiLabSummary: string
  loadAiLab: () => void
  renderAiRichText: (v: string) => string
  aiLabError: string
  aiRuleLoading: boolean
  loadAiRules: () => void
  aiRuleRows: any[]
  aiRuleColumns: any[]
  aiRuleText: string
  aiRuleError: string
  aiRiskLoading: boolean
  loadAiRisk: () => void
  latestAiRiskAlert: any
  aiConfidenceClass: (v: any) => string
  aiRiskConfidenceLevel: (item: any) => string
  aiRiskLevelText: (v: any) => string
  aiRiskEvidenceList: (item: any) => any[]
  openEvidence: (evidence: any) => void
  aiRiskHallucinations: (item: any) => any[]
  aiRiskText: string
  aiRiskError: string
  aiHandoffLoading: boolean
  loadAiHandoff: () => void
  copyHandoffSummary: () => void
  aiHandoff: any
  aiHandoffConfidence: any
  normalizeList: (v: any) => any[]
  aiHandoffError: string
  knowledgeLoading: boolean
  loadKnowledgeDocs: () => void
  handleReloadKnowledge: () => void
  knowledgeDocs: any[]
  knowledgeStatus: any
  selectedKnowledgeDocId: any
  loadKnowledgeDocument: (docId?: any) => void
  selectedKnowledgeDoc: any
  knowledgeScopeText: (v: any) => string
  knowledgeError: string
}>()
</script>

<style scoped>
.ai-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
  gap: 12px;
}
.ai-card {
  background: linear-gradient(180deg, rgba(7,20,34,.94) 0%, rgba(4,12,22,.96) 100%);
  border: 1px solid rgba(80,199,255,.14);
  min-height: 520px;
  box-shadow: inset 0 1px 0 rgba(145,228,255,.04), 0 12px 28px rgba(0,0,0,.2);
  border-radius: 12px;
}
.ai-card :deep(.ant-card-head) {
  border-bottom: 1px solid rgba(80,199,255,.1);
}
.ai-card :deep(.ant-card-head-title) {
  color: #67e8f9;
  font-size: 13px;
  letter-spacing: .12em;
  text-transform: uppercase;
}
.ai-card :deep(.ant-card-body) {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.ai-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  gap: 8px;
  flex-wrap: wrap;
}
.ai-card-note {
  font-size: 11px;
  color: #7f97bd;
}
.ai-card :deep(.ant-btn),
.ai-card :deep(.ant-select-selector),
.ai-card :deep(.ant-pagination .ant-pagination-item),
.ai-card :deep(.ant-pagination .ant-pagination-prev),
.ai-card :deep(.ant-pagination .ant-pagination-next) {
  background: rgba(8,28,44,.78) !important;
  border-color: rgba(80,199,255,.14) !important;
  color: #dffbff !important;
}
.ai-card :deep(.ant-pagination .ant-pagination-item-active) {
  background: linear-gradient(180deg, rgba(11,107,137,.96) 0%, rgba(7,63,86,.98) 100%) !important;
  border-color: rgba(110,231,249,.28) !important;
}
.ai-card :deep(.ant-pagination .ant-pagination-item-active a) {
  color: #effcff !important;
}
.ai-empty {
  color: #8898b5;
  font-size: 12px;
  padding: 8px 2px;
}
.ai-rich {
  margin-top: 2px;
  color: #dffbff;
  font-size: 13px;
  line-height: 1.8;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
  max-height: 62vh;
  overflow: auto;
  padding-right: 4px;
}
.ai-rich :deep(h4) {
  margin: 12px 0 6px;
  font-size: 15px;
  color: #effcff;
  font-weight: 700;
}
.ai-rich :deep(p) { margin: 0; }
.ai-rich :deep(code) {
  background: rgba(8,28,44,.78);
  border: 1px solid rgba(80,199,255,.12);
  border-radius: 4px;
  padding: 1px 5px;
  color: #eaffff;
}
.ai-risk-card,
.handoff-wrap,
.kb-doc-meta,
.kb-chunk-item {
  border: 1px solid rgba(80,199,255,.12);
  border-radius: 10px;
  background: rgba(8,28,44,.72);
  padding: 10px 12px;
}
.handoff-wrap p,
.ai-risk-card p,
.kb-doc-meta p {
  color: #c3d3ec;
  font-size: 12px;
  margin: 0 0 6px;
}
.workbench-kpis {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}
.wb-kpi {
  border: 1px solid rgba(80,199,255,.12);
  border-radius: 10px;
  background: rgba(5,16,27,.88);
  padding: 8px 10px;
  display: grid;
  gap: 4px;
}
.wb-kpi span {
  color: #7ecce1;
  font-size: 10px;
  letter-spacing: .1em;
  text-transform: uppercase;
}
.wb-kpi strong {
  color: #effcff;
  font-size: 13px;
  line-height: 1.35;
}
.ai-workbench-section {
  border: 1px solid rgba(80,199,255,.1);
  border-radius: 10px;
  background: rgba(6,19,32,.78);
  padding: 10px 12px;
  margin-top: 8px;
}
.ai-workbench-title {
  color: #67e8f9;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .1em;
  text-transform: uppercase;
  margin-bottom: 8px;
}
.workbench-text {
  color: #c3d3ec;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
}
.workbench-list {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 6px;
  color: #c3d3ec;
  font-size: 12px;
  line-height: 1.65;
}
.ai-footnote-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.workbench-flag {
  color: #fda4af;
  font-size: 12px;
  line-height: 1.6;
}
.handoff-warning {
  color: #fda4af !important;
}
.kb-browser {
  display: grid;
  gap: 8px;
}
.kb-status {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: #8fd4e6;
  font-size: 11px;
}
.kb-overridden { color: #fbbf24; }
.kb-chunk-list {
  display: grid;
  gap: 8px;
  max-height: 52vh;
  overflow: auto;
}
.kb-chunk-title {
  color: #dce8fb;
  font-weight: 700;
  margin-bottom: 6px;
  font-size: 12px;
}
.kb-chunk-content {
  white-space: pre-wrap;
  color: #b6c8e4;
  line-height: 1.65;
  font-size: 12px;
}
.ai-rule-wrap {
  max-height: 62vh;
  overflow: auto;
  border: 1px solid rgba(80,199,255,.12);
  border-radius: 10px;
}
.ai-rule-table {
  margin-top: 2px;
  width: 100%;
}
.ai-rule-table :deep(.ant-table) {
  background: #0f1a2b;
}
.ai-rule-table :deep(.ant-table-content) {
  overflow-x: auto !important;
}
.ai-rule-table :deep(table) {
  min-width: 920px;
}
.ai-rule-table :deep(.ant-table-thead > tr > th) {
  background: rgba(8,28,44,.82);
  color: #7ccfe4;
  border-bottom-color: rgba(80,199,255,.1);
  white-space: nowrap;
}
.ai-rule-table :deep(.ant-table-tbody > tr > td) {
  background: rgba(7,20,34,.72);
  color: #dffbff;
  border-bottom-color: rgba(80,199,255,.08);
  white-space: nowrap;
}
.ai-rule-table :deep(.ant-table-tbody > tr > td:nth-child(1)),
.ai-rule-table :deep(.ant-table-tbody > tr > td:nth-child(5)) {
  white-space: normal;
  word-break: break-word;
}
.ai-evidence-link {
  color: #93c5fd;
  cursor: pointer;
}
.ai-evidence-link:hover {
  color: #bfdbfe;
}
.ai-evidence-inline {
  margin-left: 4px;
}
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
.ai-error {
  color: #f87171;
  font-size: 11px;
  margin-top: 6px;
}

@media (max-width: 1500px) {
  .ai-grid {
    grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  }
}

@media (max-width: 980px) {
  .ai-grid {
    grid-template-columns: 1fr;
  }
  .ai-card {
    min-height: 0;
  }
  .ai-rule-wrap,
  .ai-rich {
    max-height: 56vh;
  }
  .workbench-kpis {
    grid-template-columns: 1fr;
  }
}
</style>
