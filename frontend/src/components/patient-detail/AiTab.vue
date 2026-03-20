<template>
  <div>
    <div class="ai-service-bar">
      <span :class="['ai-service-dot', `is-${aiServiceStatus.level}`]"></span>
      <span class="ai-service-text">{{ aiServiceStatus.text }}</span>
      <span v-if="aiServiceStatus.detail" class="ai-service-detail">{{ aiServiceStatus.detail }}</span>
    </div>
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
        <div v-if="latestAiRiskAlert || hasRiskForecast" :class="['ai-risk-card', aiConfidenceClass(aiRiskConfidenceLevel(latestAiRiskAlert || {}))]">
          <div class="workbench-kpis">
            <div class="wb-kpi">
              <span>主要风险</span>
              <strong>{{ latestAiRiskAlert?.extra?.primary_risk || latestAiRiskAlert?.name || forecastPrimaryRisk }}</strong>
            </div>
            <div class="wb-kpi">
              <span>风险等级</span>
              <strong>{{ forecastRiskLabel }}</strong>
            </div>
            <div class="wb-kpi">
              <span>当前概率</span>
              <strong>{{ forecastCurrentProbability }}</strong>
            </div>
          </div>
          <div v-if="hasRiskForecast" class="ai-workbench-section">
            <div class="ai-workbench-title">病情风险趋势图</div>
            <div class="risk-curve-head">
              <span class="curve-meta">{{ forecastModelLabel }}</span>
              <span class="curve-meta">{{ forecastHorizonText }}</span>
            </div>
            <AiRiskChart :option="riskForecastOption" autoresize class="risk-curve-chart" />
          </div>
          <div v-if="forecastSummaryBlock.visible" class="ai-workbench-section">
            <div class="ai-workbench-title">模型总结</div>
            <div class="summary-panel">
              <div :class="['summary-conclusion', `summary-conclusion--${forecastSummaryBlock.level}`]">
                <div class="summary-conclusion-label">当前判断</div>
                <div class="summary-conclusion-text">{{ forecastSummaryBlock.summary }}</div>
              </div>
              <div v-if="forecastSummaryBlock.evidence.length" class="summary-section">
                <div class="summary-label">主要依据</div>
                <div class="summary-chip-group">
                  <span
                    v-for="(item, idx) in forecastSummaryBlock.evidence"
                    :key="`sum-ev-${idx}`"
                    class="summary-chip"
                  >
                    {{ item }}
                  </span>
                </div>
              </div>
              <div class="summary-section">
                <div class="summary-label">处置建议</div>
                <div class="summary-order">{{ forecastSummaryBlock.suggestion }}</div>
              </div>
            </div>
          </div>
          <div v-if="forecastContributors.length" class="ai-workbench-section">
            <div class="ai-workbench-title">主要驱动因素</div>
            <ul class="workbench-list">
              <li v-for="(item, idx) in forecastContributors" :key="`risk-${idx}`">
                {{ item.feature || item.organ || '风险因素' }} · {{ item.evidence || '—' }}
              </li>
            </ul>
          </div>
          <div v-if="latestAiRiskAlert && aiRiskEvidenceList(latestAiRiskAlert).length" class="ai-workbench-section">
            <div class="ai-workbench-title">证据注释</div>
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
          <div v-if="latestAiRiskAlert && aiRiskHallucinations(latestAiRiskAlert).length" class="ai-workbench-section">
            <div class="ai-workbench-title handoff-warning">幻觉检测</div>
            <div class="workbench-flag">提示 {{ aiRiskHallucinations(latestAiRiskAlert).length }} 条异常声明</div>
          </div>
        </div>
        <div v-else-if="aiRiskText" class="ai-rich" v-html="renderAiRichText(aiRiskText)"></div>
        <div v-else class="ai-empty">暂无内容</div>
      </a-spin>
      <div v-if="aiRiskError" class="ai-error">{{ aiRiskError }}</div>
    </a-card>

    <a-card title="交班摘要(ISBAR)" :bordered="false" class="ai-card">
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
              <span>病情级别</span>
              <strong>{{ handoffSeverityText(aiHandoff.illness_severity) }}</strong>
            </div>
            <div class="wb-kpi">
              <span>摘要可信度</span>
              <strong>{{ handoffConfidenceText(aiHandoff.confidence_level) }}</strong>
            </div>
            <div class="wb-kpi">
              <span>一致性校验</span>
              <strong>{{ handoffValidationText(aiHandoff) }}</strong>
            </div>
          </div>
          <div class="isbar-grid">
            <div
              v-for="section in handoffIsbarSections"
              :key="section.key"
              class="ai-workbench-section isbar-section"
            >
              <div class="isbar-head">
                <span class="isbar-code">{{ section.code }}</span>
                <div class="ai-workbench-title">{{ section.title }}</div>
              </div>
              <div v-if="section.mode === 'text'" class="workbench-text">{{ section.text }}</div>
              <ul v-else-if="section.mode === 'list'" class="workbench-list">
                <li v-for="(item, idx) in section.items" :key="`${section.key}-${idx}`">{{ item }}</li>
              </ul>
              <div v-else-if="section.mode === 'chips'" class="summary-chip-group">
                <span v-for="(item, idx) in section.items" :key="`${section.key}-${idx}`" class="summary-chip">
                  {{ item }}
                </span>
              </div>
            </div>
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
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import {
  Button as AButton,
  Card as ACard,
  Popover as APopover,
  Select as ASelect,
  SelectOption as ASelectOption,
  Spin as ASpin,
  Table as ATable,
} from 'ant-design-vue'
import { icuCategoryAxis, icuGrid, icuTooltip, icuValueAxis } from '../../charts/icuTheme'

const props = defineProps<{
  patient?: any
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
  aiRiskForecast: any
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

const AiRiskChart = defineAsyncComponent(async () => {
  await import('../../charts/patient-detail')
  const mod = await import('vue-echarts')
  return mod.default
})

const organLabelMap: Record<string, string> = {
  respiratory: '呼吸',
  circulatory: '循环',
  renal: '肾脏',
  neurologic: '神经',
  coagulation: '凝血',
  hepatic: '肝脏',
}
const organCurvePalette: Record<string, string> = {
  respiratory: '#38bdf8',
  circulatory: '#fb7185',
  renal: '#a78bfa',
  neurologic: '#f59e0b',
  coagulation: '#22c55e',
  hepatic: '#e879f9',
}
const hasRiskForecast = computed(() => {
  const history = Array.isArray(props.aiRiskForecast?.history_risk_curve) ? props.aiRiskForecast.history_risk_curve : []
  const future = Array.isArray(props.aiRiskForecast?.forecast_risk_curve) ? props.aiRiskForecast.forecast_risk_curve : []
  const curve = Array.isArray(props.aiRiskForecast?.risk_curve) ? props.aiRiskForecast.risk_curve : []
  return history.length > 0 || future.length > 0 || curve.length > 0
})
const forecastPrimaryRisk = computed(() => {
  const organs = props.aiRiskForecast?.organ_risk_scores || {}
  const tops = Object.keys(organs).sort((a, b) => Number(organs[b] || 0) - Number(organs[a] || 0))
  if (!tops.length) return '多模态时序风险'
  const topKey = String(tops[0] || '')
  return `${organLabelMap[topKey] || topKey}恶化`
})
const forecastRiskLabel = computed(() => props.aiRiskLevelText(
  props.latestAiRiskAlert?.extra?.risk_level ||
  props.latestAiRiskAlert?.condition?.risk_level ||
  props.aiRiskForecast?.risk_level ||
  props.latestAiRiskAlert?.value
))
const forecastCurrentProbability = computed(() => {
  const p = Number(props.aiRiskForecast?.current_probability)
  if (Number.isNaN(p)) return '—'
  return `${Math.round(p * 100)}%`
})
const forecastContributors = computed(() => Array.isArray(props.aiRiskForecast?.top_contributors) ? props.aiRiskForecast.top_contributors.slice(0, 4) : [])
const forecastModelLabel = computed(() => {
  const meta = props.aiRiskForecast?.model_meta || {}
  const runtime = meta.runtime || {}
  return [meta.mode || 'temporal-model', runtime.backend].filter(Boolean).join(' · ')
})
const forecastHorizonText = computed(() => {
  const items = Array.isArray(props.aiRiskForecast?.horizon_probabilities) ? props.aiRiskForecast.horizon_probabilities : []
  if (!items.length) return '4-12h'
  return items.map((item: any) => `+${item.hours}h ${Math.round(Number(item.probability || 0) * 100)}%`).join(' / ')
})

function cleanSummaryLine(v: any) {
  return String(v || '')
    .replace(/[*#>`~_\[\]]+/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/[：:]\s*-/g, '：')
    .trim()
}

function suggestionByRisk(level: string) {
  const map: Record<string, string> = {
    critical: '建议立即强化监护，优先复核循环/呼吸/意识变化，必要时尽快升级处置并通知上级医师。',
    high: '建议缩短复评间隔，重点盯防生命体征趋势、乳酸/肾功能等关键指标，并提前准备升级干预。',
    warning: '建议保持连续监测，结合后续趋势和检验结果再次评估，警惕风险进一步抬升。',
    low: '当前以持续观察为主，建议按常规频率复评，如出现趋势性恶化及时上调风险等级。',
  }
  return map[String(level || 'low')] || map.low
}

function handoffSeverityText(v: any) {
  const map: Record<string, string> = {
    stable: '稳定',
    watcher: '需重点观察',
    unstable: '不稳定',
    critical: '危重',
  }
  return map[String(v || '').toLowerCase()] || String(v || '需重点观察')
}

function handoffConfidenceText(v: any) {
  const map: Record<string, string> = {
    low: '低',
    medium: '中',
    high: '高',
  }
  return map[String(v || '').toLowerCase()] || String(v || '低')
}

function handoffValidationText(handoff: any) {
  const count = Number(handoff?.validation?.issues?.length || 0)
  if (count > 0) return `警告 ${count} 条`
  return '通过'
}

function genderText(v: any) {
  if (v === 'Male') return '男'
  if (v === 'Female') return '女'
  return String(v || '')
}

const handoffIsbarSections = computed(() => {
  const patient = props.patient || {}
  const summary = cleanSummaryLine(props.aiHandoff?.patient_summary || '')
  const actions = props.normalizeList(props.aiHandoff?.action_list).map((item: any) => cleanSummaryLine(item)).filter(Boolean)
  const awareness = props.normalizeList(props.aiHandoff?.situation_awareness).map((item: any) => cleanSummaryLine(item)).filter(Boolean)
  const synth = cleanSummaryLine(props.aiHandoff?.synthesis_by_receiver || '')
  const identityItems = [
    patient?.hisBed ? `${patient.hisBed}床` : '',
    patient?.name || '',
    genderText(patient?.gender),
    patient?.age ? `${patient.age}岁` : '',
  ].filter(Boolean)
  const diagnosis = cleanSummaryLine(patient?.clinicalDiagnosis || patient?.admissionDiagnosis || '')
  const severity = handoffSeverityText(props.aiHandoff?.illness_severity)
  const confidence = handoffConfidenceText(props.aiHandoff?.confidence_level)
  const validation = handoffValidationText(props.aiHandoff)

  return [
    {
      key: 'identity',
      code: 'I',
      title: '身份',
      mode: 'text',
      text: identityItems.join(' · ') || '患者身份信息待补充',
    },
    {
      key: 'situation',
      code: 'S',
      title: '现状',
      mode: 'text',
      text: summary || '当前现状暂无自动摘要',
    },
    {
      key: 'background',
      code: 'B',
      title: '背景',
      mode: diagnosis ? 'text' : 'chips',
      text: diagnosis || '',
      items: diagnosis ? [] : ['基础诊断信息待补充'],
    },
    {
      key: 'assessment',
      code: 'A',
      title: '评估',
      mode: 'chips',
      items: [
        `病情级别：${severity}`,
        `摘要可信度：${confidence}`,
        `一致性校验：${validation}`,
        ...awareness.slice(0, 2),
      ].filter(Boolean).slice(0, 4),
    },
    {
      key: 'recommendation',
      code: 'R',
      title: '建议',
      mode: actions.length ? 'list' : 'text',
      items: actions.slice(0, 4),
      text: actions.length ? '' : (synth || '建议接班后复核关键生命体征、实验室结果及当前治疗计划。'),
    },
  ]
})

const forecastSummaryBlock = computed(() => {
  const level = String(props.aiRiskForecast?.risk_level || 'low')
  const horizonItems = Array.isArray(props.aiRiskForecast?.horizon_probabilities) ? props.aiRiskForecast.horizon_probabilities : []
  const maxH = horizonItems.length ? Math.max(...horizonItems.map((item: any) => Number(item?.hours || 0)).filter((n: number) => !Number.isNaN(n))) : 12
  const currentProb = Number(props.aiRiskForecast?.current_probability)
  const currentProbText = Number.isNaN(currentProb) ? '—' : `${Math.round(currentProb * 100)}%`
  const h4 = horizonItems.find((item: any) => Number(item?.hours) === 4)
  const h12 = horizonItems.find((item: any) => Number(item?.hours) === 12) || horizonItems[horizonItems.length - 1]
  const evidenceFromContrib = forecastContributors.value
    .map((item: any) => cleanSummaryLine(item?.evidence || item?.feature || item?.organ || ''))
    .filter(Boolean)
    .slice(0, 3)
  const organScores = props.aiRiskForecast?.organ_risk_scores || {}
  const topOrgans = Object.keys(organScores)
    .sort((a, b) => Number(organScores[b] || 0) - Number(organScores[a] || 0))
    .slice(0, 2)
    .map((key) => `${organLabelMap[key] || key}风险较高`)
  const raw = String(props.aiRiskForecast?.risk_summary || props.aiRiskText || '').trim()
  const rawLines = raw
    .split(/\r?\n+/)
    .map(cleanSummaryLine)
    .filter(Boolean)
    .filter((line) => !/^(模型总结|风险等级|判断依据|主要风险因素)$/i.test(line))
  const rawEvidence = rawLines
    .filter((line) => /^[-•]/.test(String(line)) || /风险|异常|升高|下降|偏低|偏高|基础病情|住院时间|生命体征/.test(line))
    .map((line) => cleanSummaryLine(line.replace(/^[-•]\s*/, '')))
    .filter(Boolean)
    .slice(0, 3)

  const summary = hasRiskForecast.value
    ? `模型判断未来${maxH || 12}h恶化风险为${forecastRiskLabel.value}，当前概率 ${currentProbText}${h4 ? `，4h约 ${Math.round(Number(h4?.probability || 0) * 100)}%` : ''}${h12 ? `，${Number(h12?.hours || maxH)}h约 ${Math.round(Number(h12?.probability || 0) * 100)}%` : ''}。`
    : (rawLines[0] || '')

  const evidence = (evidenceFromContrib.length ? evidenceFromContrib : rawEvidence).concat(
    evidenceFromContrib.length ? [] : topOrgans
  ).slice(0, 3)

  return {
    visible: !!(summary || evidence.length || raw),
    level,
    summary: summary || '暂无模型总结',
    evidence,
    suggestion: suggestionByRisk(level),
  }
})

const riskForecastOption = computed(() => {
  const history = Array.isArray(props.aiRiskForecast?.history_risk_curve) ? props.aiRiskForecast.history_risk_curve : []
  const future = Array.isArray(props.aiRiskForecast?.forecast_risk_curve) ? props.aiRiskForecast.forecast_risk_curve : []
  const curve = history.length || future.length
    ? [...history, ...future]
    : (Array.isArray(props.aiRiskForecast?.risk_curve) ? props.aiRiskForecast.risk_curve : [])
  const xs = curve.map((item: any) => item?.label || '—')
  const historyValues = curve.map((item: any) => {
    if (String(item?.phase || '') === 'forecast') return null
    const p = Number(item?.probability)
    return Number.isNaN(p) ? null : Math.round(p * 100)
  })
  const futureValues = curve.map((item: any) => {
    if (String(item?.phase || '') === 'history') return null
    const p = Number(item?.probability)
    return Number.isNaN(p) ? null : Math.round(p * 100)
  })
  const thresholdBands = Array.isArray(props.aiRiskForecast?.threshold_bands) ? props.aiRiskForecast.threshold_bands : []
  const highRiskZone = props.aiRiskForecast?.high_risk_zone || {}
  const organCurves = props.aiRiskForecast?.organ_risk_curves || {}
  const organSeries = Object.keys(organCurves).slice(0, 4).map((organKey) => {
    const rows = Array.isArray(organCurves[organKey]) ? organCurves[organKey] : []
    const data = curve.map((point: any) => {
      const hit = rows.find((row: any) => Number(row?.offset_hours) === Number(point?.offset_hours) && String(row?.phase || '') === String(point?.phase || ''))
      const p = Number(hit?.probability)
      return Number.isNaN(p) ? null : Math.round(p * 100)
    })
    return {
      name: `${organLabelMap[organKey] || organKey}风险`,
      type: 'line',
      smooth: true,
      symbol: 'none',
      data,
      z: 2,
      lineStyle: { width: 1.2, type: 'dashed', color: organCurvePalette[organKey] || '#94a3b8', opacity: 0.7 },
    }
  })
  return {
    backgroundColor: 'transparent',
    tooltip: icuTooltip({
      trigger: 'axis',
      formatter: (params: any) => {
        const rows = Array.isArray(params) ? params.filter(Boolean) : [params]
        const lines = [`${rows[0]?.axisValue || ''}`]
        rows.forEach((row: any) => {
          lines.push(`${row?.seriesName || '风险'} ${row?.data ?? '—'}%`)
        })
        return lines.join('<br/>')
      },
    }),
    grid: icuGrid({ left: 34, right: 18, top: 26, bottom: 24 }),
    xAxis: icuCategoryAxis(xs, {
      axisLabel: { color: '#7e9fbc', fontSize: 10 },
      axisLine: { lineStyle: { color: '#1e3d5e' } },
    }),
    yAxis: icuValueAxis({
      min: 0,
      max: 100,
      axisLabel: { color: '#7e9fbc', fontSize: 10, formatter: '{value}%' },
      splitLine: { lineStyle: { color: 'rgba(80,199,255,.10)' } },
    }),
    legend: {
      top: 0,
      right: 8,
      itemWidth: 10,
      itemHeight: 6,
      textStyle: { color: '#93b7d8', fontSize: 10 },
    },
    series: [
      {
        name: '历史风险',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        data: historyValues,
        lineStyle: { width: 2, color: '#38bdf8' },
        itemStyle: { color: '#67e8f9', borderColor: '#0b2439', borderWidth: 2 },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(56,189,248,.28)' },
              { offset: 1, color: 'rgba(56,189,248,0)' },
            ],
          },
        },
        markArea: thresholdBands.length
          ? {
              silent: true,
              data: thresholdBands.map((band: any) => [
                { xAxis: xs[0] || '—', yAxis: Math.round(Number(band?.min || 0) * 100), itemStyle: { color: band?.color || 'rgba(148,163,184,.05)' } },
                { xAxis: xs[xs.length - 1] || '—', yAxis: Math.round(Number(band?.max || 0) * 100) },
              ]),
            }
          : undefined,
        markLine: {
          symbol: 'none',
          lineStyle: { type: 'dashed', color: 'rgba(251,191,36,.38)' },
          data: [{ yAxis: 64, label: { formatter: '高危阈值', color: '#fcd34d' } }],
        },
      },
      {
        name: '未来预测',
        type: 'line',
        smooth: true,
        symbol: 'diamond',
        symbolSize: 7,
        data: futureValues,
        z: 4,
        lineStyle: { width: 2.2, type: 'dashed', color: '#fb7185' },
        itemStyle: { color: '#fda4af', borderColor: '#2a0f16', borderWidth: 2 },
        markArea: highRiskZone?.max != null
          ? {
              silent: true,
              data: [[
                { xAxis: xs[0] || '—', yAxis: Math.round(Number(highRiskZone?.min || 0.64) * 100), itemStyle: { color: 'rgba(239,68,68,.08)' } },
                { xAxis: xs[xs.length - 1] || '—', yAxis: Math.round(Number(highRiskZone?.max || 1) * 100) },
              ]],
            }
          : undefined,
      },
      ...organSeries,
    ],
  }
})

const aiServiceStatus = computed(() => {
  const errors = [props.aiLabError, props.aiRuleError, props.aiRiskError, props.aiHandoffError].filter(Boolean)
  const runtime = props.aiRiskForecast?.model_meta?.runtime || {}
  const mode = String(props.aiRiskForecast?.model_meta?.mode || '')
  const degraded = Boolean(
    errors.length ||
    mode.includes('heuristic') ||
    (runtime && runtime.available === false)
  )
  if (errors.length >= 2) {
    return {
      level: 'red',
      text: 'AI服务异常',
      detail: '部分能力不可用，请检查模型或后端服务',
    }
  }
  if (degraded) {
    return {
      level: 'yellow',
      text: 'AI服务降级中',
      detail: runtime?.reason ? String(runtime.reason) : '当前已切换到降级/兜底路径',
    }
  }
  return {
    level: 'green',
    text: 'AI服务正常',
    detail: '',
  }
})
</script>

<style scoped>
.ai-service-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 10px 12px;
  border: 1px solid rgba(80,199,255,.12);
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(7,20,34,.88) 0%, rgba(4,12,22,.94) 100%);
}
.ai-service-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  box-shadow: 0 0 10px currentColor;
}
.ai-service-dot.is-green {
  color: #34d399;
  background: #34d399;
}
.ai-service-dot.is-yellow {
  color: #fbbf24;
  background: #fbbf24;
}
.ai-service-dot.is-red {
  color: #fb7185;
  background: #fb7185;
}
.ai-service-text {
  color: #e6f6ff;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .06em;
}
.ai-service-detail {
  color: #7f97bd;
  font-size: 11px;
}
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
.summary-panel {
  display: grid;
  gap: 8px;
}
.summary-section {
  border: 1px solid rgba(80,199,255,.08);
  border-radius: 8px;
  background: rgba(7,23,38,.62);
  padding: 8px 10px;
}
.summary-label {
  margin-bottom: 4px;
  color: #8fe7ff;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .12em;
  text-transform: uppercase;
}
.summary-conclusion {
  border: 1px solid rgba(80,199,255,.12);
  border-radius: 10px;
  padding: 10px 12px;
  background:
    linear-gradient(180deg, rgba(8,28,44,.94) 0%, rgba(6,19,32,.98) 100%);
  box-shadow: inset 0 1px 0 rgba(145,228,255,.04);
}
.summary-conclusion--low {
  border-color: rgba(52,211,153,.18);
  background: linear-gradient(180deg, rgba(8,44,38,.9) 0%, rgba(5,26,22,.96) 100%);
}
.summary-conclusion--warning {
  border-color: rgba(250,204,21,.2);
  background: linear-gradient(180deg, rgba(52,38,8,.92) 0%, rgba(31,23,5,.98) 100%);
}
.summary-conclusion--high,
.summary-conclusion--critical {
  border-color: rgba(251,90,122,.22);
  background: linear-gradient(180deg, rgba(57,17,27,.92) 0%, rgba(34,10,17,.98) 100%);
}
.summary-conclusion-label {
  color: #91ecff;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .14em;
  text-transform: uppercase;
}
.summary-conclusion-text {
  margin-top: 6px;
  color: #effcff;
  font-size: 15px;
  line-height: 1.5;
  font-weight: 700;
}
.summary-chip-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.summary-chip {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(9,31,48,.92);
  border: 1px solid rgba(80,199,255,.14);
  color: #d8eeff;
  font-size: 11px;
  line-height: 1.4;
}
.summary-order {
  color: #d7e6fb;
  font-size: 12px;
  line-height: 1.7;
  padding-left: 12px;
  position: relative;
}
.summary-order::before {
  content: '医嘱';
  position: absolute;
  left: 0;
  top: 0;
  color: #67e8f9;
  font-size: 10px;
  letter-spacing: .12em;
}
.summary-text {
  color: #d7e6fb;
  font-size: 12px;
  line-height: 1.65;
}
.summary-list {
  margin: 0;
  padding-left: 16px;
  color: #d7e6fb;
  font-size: 12px;
  line-height: 1.6;
}
.summary-list li + li {
  margin-top: 3px;
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
.isbar-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.isbar-section {
  margin-top: 0;
}
.isbar-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.isbar-code {
  width: 22px;
  height: 22px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(9,31,48,.92);
  border: 1px solid rgba(80,199,255,.14);
  color: #90ecff;
  font-size: 11px;
  font-weight: 800;
  font-family: 'Rajdhani', 'SF Mono', 'Consolas', monospace;
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
.risk-curve-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.curve-meta {
  color: #86a9c8;
  font-size: 10px;
  letter-spacing: .12em;
}
.risk-curve-chart {
  height: 220px;
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
  .isbar-grid {
    grid-template-columns: 1fr;
  }
}
</style>




