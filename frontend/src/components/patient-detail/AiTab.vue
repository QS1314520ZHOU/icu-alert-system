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
          <p><strong>主要风险:</strong> {{ latestAiRiskAlert.extra?.primary_risk || latestAiRiskAlert.name || '综合风险' }}</p>
          <p><strong>风险等级:</strong> {{ aiRiskLevelText(latestAiRiskAlert.extra?.risk_level || latestAiRiskAlert.condition?.risk_level || latestAiRiskAlert.value) }}</p>
          <p><strong>安全校验:</strong> {{ latestAiRiskAlert.extra?.safety_validation?.status || 'ok' }}</p>
          <p v-if="aiRiskEvidenceList(latestAiRiskAlert).length">
            <strong>证据脚注:</strong>
            <span
              v-for="(evidence, idx) in aiRiskEvidenceList(latestAiRiskAlert)"
              :key="evidence.chunk_id || idx"
              class="ai-evidence-inline"
            >
              <a-popover placement="topLeft">
                <template #content>
                  <div class="ai-evidence-popover">
                    <div><strong>{{ evidence.source || '指南证据' }}</strong></div>
                    <div v-if="evidence.recommendation">{{ evidence.recommendation }}</div>
                    <div class="ai-evidence-quote">{{ evidence.quote || '暂无原文片段' }}</div>
                  </div>
                </template>
                <a class="ai-evidence-link" @click.prevent="openEvidence(evidence)">
                  [{{ idx + 1 }}]
                </a>
              </a-popover>
            </span>
          </p>
          <p v-if="aiRiskHallucinations(latestAiRiskAlert).length" class="handoff-warning">
            幻觉检测提示 {{ aiRiskHallucinations(latestAiRiskAlert).length }} 条
          </p>
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
          <p><strong>Illness severity:</strong> {{ aiHandoff.illness_severity || 'watcher' }}</p>
          <p><strong>Patient summary:</strong> {{ aiHandoff.patient_summary || '—' }}</p>
          <p><strong>Action list:</strong> {{ normalizeList(aiHandoff.action_list).join('；') || '—' }}</p>
          <p><strong>Situation awareness:</strong> {{ normalizeList(aiHandoff.situation_awareness).join('；') || '—' }}</p>
          <p><strong>Synthesis:</strong> {{ aiHandoff.synthesis_by_receiver || '—' }}</p>
          <p><strong>Confidence:</strong> {{ aiHandoff.confidence_level || 'low' }}</p>
          <p v-if="aiHandoff?.validation?.issues?.length" class="handoff-warning">
            数值校验告警 {{ aiHandoff.validation.issues.length }} 条
          </p>
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
