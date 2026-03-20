<template>
  <section class="twin-shell">
    <div class="twin-head">
      <div>
        <div class="twin-kicker">数字孪生闭环工作台</div>
        <h3 class="twin-title">数字孪生诊疗推理</h3>
        <p class="twin-sub">把风险预测、建议、追踪、效果评估、因果链和 MDT 会诊收敛到一个智能临床工作台。</p>
      </div>
      <button class="twin-refresh" :disabled="loading" @click="loadAll(true)">{{ loading ? '刷新中…' : '刷新工作台' }}</button>
    </div>

    <div class="twin-kpis">
      <div class="twin-kpi"><span>患者</span><strong>{{ patient?.name || patient?.hisName || '当前患者' }}</strong></div>
      <div class="twin-kpi"><span>短时恶化风险</span><strong>{{ deteriorationProbability }}</strong></div>
      <div class="twin-kpi"><span>工作台状态</span><strong>{{ workbenchState }}</strong></div>
      <div class="twin-kpi"><span>已追踪干预</span><strong>{{ trackedInterventions }}</strong></div>
    </div>

    <div class="loop-grid">
      <article class="loop-card"><div class="loop-step">01</div><div class="loop-label">风险预测</div><div class="loop-value">{{ forecastHeadline }}</div><div class="loop-meta">{{ forecastSummary }}</div></article>
      <article class="loop-card"><div class="loop-step">02</div><div class="loop-label">建议</div><div class="loop-value">{{ topRecommendation }}</div><div class="loop-meta">{{ monitoringHeadline }}</div></article>
      <article class="loop-card"><div class="loop-step">03</div><div class="loop-label">追踪</div><div class="loop-value">{{ trackedInterventions }}</div><div class="loop-meta">{{ interventionHeadline }}</div></article>
      <article class="loop-card"><div class="loop-step">04</div><div class="loop-label">效果评估</div><div class="loop-value">{{ effectivenessHeadline }}</div><div class="loop-meta">{{ effectSummary }}</div></article>
    </div>

    <div class="twin-grid">
      <section class="twin-card">
        <div class="card-head">
          <div>
            <div class="card-title">统一状态总览</div>
            <div class="card-sub">直接消费数字孪生快照，作为工作台与后续 Scanner 迁移的统一底座</div>
          </div>
          <span :class="['risk-badge', hasTwinSnapshot ? 'is-low' : 'is-medium']">{{ hasTwinSnapshot ? '快照已接入' : '等待快照' }}</span>
        </div>
        <div class="summary-panel">{{ twinOverviewSummary }}</div>
        <div class="overview-grid">
          <article v-for="item in twinOverviewCards" :key="item.label" class="overview-item">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
            <small>{{ item.meta }}</small>
          </article>
        </div>
        <div class="chip-row">
          <span v-for="item in twinMetricChips" :key="item.label" class="info-chip">{{ item.label }} {{ item.value }}</span>
        </div>
        <div v-if="twinTrendChips.length" class="chip-row">
          <span v-for="item in twinTrendChips" :key="item.label" class="info-chip info-chip--muted">{{ item.label }} {{ item.value }}</span>
        </div>
      </section>

      <section class="twin-card">
        <div class="card-head"><div><div class="card-title">风险预测与驱动</div><div class="card-sub">未来 2-12h 恶化概率与主要驱动因子</div></div><span :class="['risk-badge', `is-${riskLevel}`]">{{ riskLevelText }}</span></div>
        <div class="curve-list">
          <div v-for="item in horizonRows" :key="item.label" class="curve-row">
            <div class="curve-top"><span>{{ item.label }}</span><strong>{{ item.value }}</strong></div>
            <div class="curve-bar"><div class="curve-fill" :style="{ width: item.width }"></div></div>
          </div>
        </div>
        <ul class="bullet-list"><li v-for="(item, idx) in topDrivers" :key="`driver-${idx}`">{{ item }}</li></ul>
      </section>

      <section class="twin-card">
        <div class="card-head"><div><div class="card-title">诊疗推理建议</div><div class="card-sub">数字孪生上下文驱动的个体化推理</div></div></div>
        <div class="summary-panel">{{ reasoningSummary }}</div>
        <div class="chip-row"><span v-for="(item, idx) in problemList" :key="`problem-${idx}`" class="info-chip">{{ item }}</span></div>
        <ul class="bullet-list"><li v-for="(item, idx) in recommendationList" :key="`rec-${idx}`">{{ item }}</li></ul>
      </section>

      <section class="twin-card">
        <div class="card-head"><div><div class="card-title">护理文本智能分析</div><div class="card-sub">近 12h 护理记录与计划执行信号</div></div><span :class="['risk-badge', `is-${nursingRiskLevel}`]">{{ nursingRiskText }}</span></div>
        <div class="summary-panel">{{ nursingSummary }}</div>
        <div class="chip-row"><span v-for="item in nursingSignalLabels" :key="item" class="info-chip">{{ item }}</span></div>
        <ul class="bullet-list"><li v-for="(item, idx) in nursingSuggestions" :key="`nursing-${idx}`">{{ item }}</li></ul>
      </section>

      <section class="twin-card">
        <div class="card-head"><div><div class="card-title">综合征亚表型识别</div><div class="card-sub">把患者映射到可执行的差异化工作流</div></div></div>
        <div class="summary-panel">{{ subphenotypeSummary }}</div>
        <div v-if="primarySubphenotype" class="causal-item">
          <div class="causal-top"><strong>{{ primarySubphenotype.subtype_label || '未命名亚型' }}</strong><span>{{ pct(primarySubphenotype.confidence || 0) }}</span></div>
          <div class="causal-meta">{{ primarySubphenotype.summary || '暂无亚型摘要' }}</div>
          <div class="chip-row"><span class="info-chip">综合征 {{ primarySubphenotype.syndrome || '通用' }}</span><span class="info-chip">置信 {{ pct(primarySubphenotype.confidence || 0) }}</span></div>
          <ul v-if="primarySubphenotype.care_implications?.length" class="bullet-list compact"><li v-for="(item, idx) in primarySubphenotype.care_implications" :key="`subtype-${idx}`">{{ item }}</li></ul>
        </div>
        <div v-else class="empty-panel">当前暂无高置信度亚表型。</div>
      </section>
      <section class="twin-card twin-card-wide">
        <div class="card-head">
          <div>
            <div class="card-title">患者全景时间轴</div>
            <div class="card-sub">把生命体征、检验、用药、报警和文本信号收敛到同一条患者级事件轴</div>
          </div>
          <span class="status-pill is-pending">{{ timelineRows.length }} 条事件</span>
        </div>
        <div v-if="timelineRows.length" class="timeline-list">
          <article v-for="(item, idx) in timelineRows" :key="`${item.time || item.label || idx}-${idx}`" class="timeline-item">
            <div class="timeline-rail">
              <span class="timeline-time">{{ fmtTime(item.time) }}</span>
              <i :class="['timeline-dot', `timeline-dot--${item.tone}`]" />
              <span v-if="Number(idx) < timelineRows.length - 1" class="timeline-line" />
            </div>
            <div class="timeline-card">
              <div class="timeline-card-head">
                <div>
                  <div class="timeline-card-title">{{ item.label }}</div>
                  <div class="timeline-card-sub">{{ item.detail }}</div>
                </div>
                <span :class="['timeline-source', `is-${item.tone}`]">{{ item.sourceLabel }}</span>
              </div>
              <div v-if="item.metaText" class="timeline-card-meta">{{ item.metaText }}</div>
            </div>
          </article>
        </div>
        <div v-else class="empty-panel">当前快照中暂无可展示的患者时间轴事件。</div>
      </section>


      <section class="twin-card twin-card-wide">
        <div class="card-head"><div><div class="card-title">主动管理追踪</div><div class="card-sub">风险闭环从建议直接进入执行与回看</div></div></div>
        <div v-if="interventions.length" class="intervention-list">
          <article v-for="item in interventions" :key="item.intervention_id" class="intervention-item">
            <div class="intervention-top"><div><div class="intervention-title">{{ item.title }}</div><div class="intervention-meta">{{ item.rationale || '待补充依据' }}</div></div><span :class="['status-pill', `is-${String(item.status || 'pending').toLowerCase()}`]">{{ interventionStatusText(item.status) }}</span></div>
            <div class="chip-row"><span class="info-chip">优先级 {{ item.priority || '高' }}</span><span class="info-chip">责任 {{ item.owner || '医生' }}</span><span class="info-chip">采纳 {{ item.adopted == null ? '未标记' : (item.adopted ? '已采纳' : '未采纳') }}</span></div>
            <ul class="bullet-list compact"><li v-for="(act, idx) in item.actions || []" :key="`act-${idx}`">{{ act }}</li></ul>
            <div class="action-row"><button class="mini-btn" :disabled="savingMap[item.intervention_id]" @click="submitFeedback(item, { status: 'in_progress', adopted: true })">开始追踪</button><button class="mini-btn mini-btn--soft" :disabled="savingMap[item.intervention_id]" @click="submitFeedback(item, { status: 'completed', adopted: true })">已完成</button><button class="mini-btn mini-btn--ghost" :disabled="savingMap[item.intervention_id]" @click="submitFeedback(item, { status: 'dismissed', adopted: false })">不采纳</button></div>
            <div v-if="item.effectiveness" :class="['effect-box', `is-${item.effectiveness.effect || 'stable'}`]"><strong>{{ effectText(item.effectiveness.effect) }}</strong><span>风险变化 {{ effectDelta(item.effectiveness.delta) }}</span></div>
          </article>
        </div>
        <div v-else class="empty-panel">当前未触发主动管理阈值，保持连续监测。</div>
      </section>

      <section class="twin-card">
        <div class="card-head"><div><div class="card-title">因果链解释</div><div class="card-sub">把异常入口映射成候选病因链</div></div></div>
        <div class="chip-row"><button v-for="item in causalOptions" :key="item" :class="['cause-chip', { active: selectedFinding === item }]" @click="loadCausal(item)">{{ item }}</button></div>
        <div class="summary-panel">{{ causalSummary }}</div>
        <div v-if="causalEvidenceProfile.length" class="chip-row">
          <span v-for="item in causalEvidenceProfile" :key="item.key" :class="['info-chip', { 'info-chip--muted': !item.present }]">{{ item.label }} {{ item.present ? '命中' : '缺失' }}</span>
        </div>
        <div v-if="causalRows.length" class="causal-list">
          <article v-for="row in causalRows" :key="row.cause_key" class="causal-item">
            <div class="causal-top"><strong>{{ row.label }}</strong><span>{{ pct(row.posterior) }}</span></div>
            <div class="curve-bar"><div class="curve-fill causal-fill" :style="{ width: pct(row.posterior) }"></div></div>
            <div class="causal-meta">{{ row.mechanism || '暂无病理机制说明' }}</div>
            <div class="chip-row">
              <span class="info-chip">领域 {{ row.clinical_domain || '通用' }}</span>
              <span class="info-chip">置信 {{ ({ low: '低', medium: '中', high: '高', critical: '危急' } as Record<string, string>)[String(row.confidence_level || 'medium').toLowerCase()] || '中' }}</span>
            </div>
            <div class="causal-meta">命中证据：{{ (row.matched_evidence || []).join(' / ') || '暂无' }}</div>
            <div v-if="row.missing_evidence?.length" class="causal-meta">待补证据：{{ row.missing_evidence.join(' / ') }}</div>
            <ul v-if="row.pathway_steps?.length" class="bullet-list compact"><li v-for="(item, idx) in row.pathway_steps" :key="`${row.cause_key}-path-${idx}`">{{ item }}</li></ul>
            <ul v-if="row.recommended_checks?.length" class="bullet-list compact"><li v-for="(item, idx) in row.recommended_checks" :key="`${row.cause_key}-check-${idx}`">{{ item }}</li></ul>
          </article>
        </div>
        <div v-else class="empty-panel">选择一个异常入口后生成因果链。</div>
        <div v-if="causalGuidelines.length" class="causal-guidelines">
          <div class="card-sub">相关指南证据</div>
          <article v-for="item in causalGuidelines" :key="item.chunk_id || item.source" class="conflict-item">
            <div class="conflict-title">{{ item.source || '指南片段' }}<span v-if="item.recommendation_grade"> · {{ item.recommendation_grade }}</span></div>
            <div class="conflict-meta">{{ item.recommendation || item.quote || '暂无推荐摘录' }}</div>
          </article>
        </div>
      </section>

      <section class="twin-card">
        <div class="card-head"><div><div class="card-title">MDT 多智能体会诊</div><div class="card-sub">专科智能体观点、冲突与总控智能体裁决</div></div></div>
        <div class="summary-panel">{{ mdtSummary }}</div>
        <div v-if="conflictRows.length" class="conflict-list">
          <article v-for="(item, idx) in conflictRows" :key="`${item.type || 'conflict'}-${idx}`" class="conflict-item"><div class="conflict-title">{{ item.summary || '存在跨专科冲突待裁决' }}</div><div class="conflict-meta">{{ item.resolution_focus || '需结合床旁动态数据与治疗目标综合判断。' }}</div></article>
        </div>
        <div class="mdt-grid"><article v-for="item in specialistCards" :key="item.agent" class="mdt-item"><div class="mdt-title">{{ item.domain }}</div><div class="mdt-meta">{{ item.summary }}</div></article></div>
        <ul class="bullet-list"><li v-for="(item, idx) in metaActions" :key="`meta-${idx}`">{{ item }}</li></ul>
        <div class="action-row"><button class="mini-btn" @click="openMdtBoard">打开 MDT 多智能体会诊页</button></div>
      </section>

      <section class="twin-card twin-card-wide">
        <div class="card-head"><div><div class="card-title">干预情景模拟</div><div class="card-sub">基于过去 12h 响应曲线，预估干预后 30 分钟内关键指标变化</div></div></div>
        <div class="chip-row">
          <button v-for="item in whatIfPresets" :key="item.type" :class="['cause-chip', { active: whatIfSelected === item.type }]" :disabled="whatIfLoading" @click="runWhatIf(item)">{{ item.label }}</button>
        </div>
        <div class="summary-panel">{{ whatIfSummary }}</div>
        <div v-if="whatIfProjectionRows.length" class="curve-list">
          <div v-for="item in whatIfProjectionRows" :key="item.label" class="curve-row">
            <div class="curve-top"><span>{{ item.label }}</span><strong>{{ item.value }}</strong></div>
            <div class="curve-bar"><div class="curve-fill causal-fill" :style="{ width: item.width }"></div></div>
          </div>
        </div>
        <ul v-if="whatIfCautions.length" class="bullet-list compact"><li v-for="(item, idx) in whatIfCautions" :key="`caution-${idx}`">{{ item }}</li></ul>
      </section>
    </div>

    <div v-if="error" class="error-panel">{{ error }}</div>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  getAiClinicalReasoning,
  getAiMultiAgentAssessment,
  getAiNursingNoteSignals,
  getAiPatientDigitalTwin,
  getAiProactiveManagement,
  getAiRiskForecast,
  getAiSubphenotype,
  postAiCausalAnalysis,
  postAiProactiveInterventionFeedback,
  postAiWhatIfSimulation,
} from '../../api'

const props = defineProps<{ patientId: string; patient?: any }>()
const router = useRouter()
const patient = computed(() => props.patient || null)
const loading = ref(false)
const error = ref('')
const digitalTwin = ref<any>(null)
const riskForecast = ref<any>(null)
const proactivePlan = ref<any>(null)
const reasoningPlan = ref<any>(null)
const mdtAssessment = ref<any>(null)
const causalAnalysis = ref<any>(null)
const nursingSignals = ref<any>(null)
const subphenotypeProfile = ref<any>(null)
const whatIfResult = ref<any>(null)
const selectedFinding = ref('乳酸升高')
const whatIfSelected = ref('vasopressor_up')
const whatIfLoading = ref(false)
const savingMap = reactive<Record<string, boolean>>({})
const causalOptions = ['乳酸升高', '肌酐升高', '低氧', '低血压', '血小板下降', '胆红素升高', '凝血异常']
const whatIfPresets = [
  { type: 'vasopressor_up', label: '升压药上调', payload: { intervention_type: 'vasopressor_up', intervention_label: '去甲肾上腺素上调', dose_delta_pct: 20, horizon_minutes: 30 } },
  { type: 'fluid_bolus', label: '补液 250mL', payload: { intervention_type: 'fluid_bolus', intervention_label: '晶体液补液 250mL', fluid_bolus_ml: 250, horizon_minutes: 30 } },
  { type: 'peep_up', label: 'PEEP +2', payload: { intervention_type: 'peep_up', intervention_label: 'PEEP 上调 2 cmH2O', peep_delta: 2, horizon_minutes: 30 } },
  { type: 'fio2_up', label: 'FiO2 +10%', payload: { intervention_type: 'fio2_up', intervention_label: 'FiO2 上调 10%', fio2_delta: 10, horizon_minutes: 30 } },
] as const
const twinRecord = computed(() => digitalTwin.value?.record || digitalTwin.value || {})
const twinSnapshot = computed(() => twinRecord.value?.snapshot || {})
const twinPatient = computed(() => twinRecord.value?.patient || {})
const twinVitals = computed(() => twinRecord.value?.vitals || {})
const twinSummary = computed(() => twinRecord.value?.summary || {})
const planRecord = computed(() => proactivePlan.value?.plan || proactivePlan.value || {})
const reasoningRecord = computed(() => reasoningPlan.value?.plan || reasoningPlan.value || {})
const mdtRecord = computed(() => mdtAssessment.value?.assessment || mdtAssessment.value || {})
const mdtResult = computed(() => mdtRecord.value?.result || mdtRecord.value || {})
const mdtMetaSummary = computed(() => mdtResult.value?.meta_agent || mdtRecord.value?.meta_summary || {})
const nursingRecord = computed(() => nursingSignals.value?.analysis || nursingSignals.value || {})
const subphenotypeRecord = computed(() => subphenotypeProfile.value?.profile || subphenotypeProfile.value || {})
const whatIfRecord = computed(() => whatIfResult.value?.simulation || whatIfResult.value || {})
const riskLevel = computed(() => String(planRecord.value?.risk_profile?.risk_level || riskForecast.value?.risk_level || 'medium').toLowerCase())
const riskLevelText = computed(() => ({ low: '低风险', medium: '中风险', high: '高风险', critical: '危急' } as Record<string, string>)[riskLevel.value] || '中风险')
const deteriorationProbability = computed(() => pct(planRecord.value?.risk_profile?.deterioration_probability ?? riskForecast.value?.current_probability ?? 0))
const workbenchState = computed(() => String(planRecord.value?.status || 'active') === 'monitoring' ? '连续监测中' : '闭环运行中')
const hasTwinSnapshot = computed(() => Object.keys(twinSnapshot.value || {}).length > 0)
const interventions = computed(() => Array.isArray(planRecord.value?.interventions) ? planRecord.value.interventions : [])
const trackedInterventions = computed(() => `${interventions.value.filter((item: any) => item?.status && item.status !== 'pending').length}/${interventions.value.length || 0}`)
const forecastHeadline = computed(() => `${riskLevelText.value} · ${deteriorationProbability.value}`)
const forecastSummary = computed(() => String(planRecord.value?.summary || riskForecast.value?.risk_summary || '暂无风险摘要'))
const monitoringHeadline = computed(() => monitoringFocus.value[0] || '等待监测焦点')
const interventionHeadline = computed(() => interventions.value[0]?.title || '尚未触发强干预')
const topRecommendation = computed(() => recommendationList.value[0] || '等待推理建议')
const effectivenessHeadline = computed(() => effectSummary.value)
const topDrivers = computed(() => {
  const planDrivers = Array.isArray(planRecord.value?.risk_profile?.drivers) ? planRecord.value.risk_profile.drivers : []
  const forecastDrivers = Array.isArray(riskForecast.value?.top_contributors) ? riskForecast.value.top_contributors : []
  const rows = planDrivers.length ? planDrivers.map((item: any) => `${item.label || item.key} · ${item.evidence || '—'}`) : forecastDrivers.map((item: any) => `${item.feature || item.organ || '风险因素'} · ${item.evidence || '—'}`)
  return rows.slice(0, 5)
})
const horizonRows = computed(() => {
  const horizon = planRecord.value?.risk_profile?.forecast?.horizon_probabilities || riskForecast.value?.horizon_probabilities || []
  if (Array.isArray(horizon)) return horizon.map((item: any) => ({ label: `${item.offset_hours || item.hours || '?'}h`, value: pct(item.probability || 0), width: pct(item.probability || 0) }))
  return Object.entries(horizon || {}).map(([key, value]: any) => ({ label: `${key}h`, value: pct(value || 0), width: pct(value || 0) }))
})
const reasoningSummary = computed(() => String(reasoningRecord.value?.result?.overview?.summary || reasoningRecord.value?.summary || '暂无诊疗推理结果'))
const problemList = computed(() => {
  const result = reasoningRecord.value?.result || {}
  return Array.isArray(result?.overview?.core_problems) ? result.overview.core_problems.slice(0, 6) : []
})
const recommendationList = computed(() => {
  const result = reasoningRecord.value?.result || {}
  const rows = Array.isArray(result?.treatment_recommendations) ? result.treatment_recommendations : []
  return rows.slice(0, 5).map((item: any) => `${item.recommendation}${item.rationale ? ` · ${item.rationale}` : ''}`)
})
const nursingRiskLevel = computed(() => String(nursingRecord.value?.risk_level || 'low').toLowerCase())
const nursingRiskText = computed(() => ({ low: '低风险', medium: '中风险', high: '高风险', critical: '危急' } as Record<string, string>)[nursingRiskLevel.value] || '低风险')
const nursingSummary = computed(() => String(nursingRecord.value?.summary || '等待护理文本分析结果'))
const nursingSignalLabels = computed(() => {
  const rows = Array.isArray(nursingRecord.value?.signal_labels) ? nursingRecord.value.signal_labels : []
  return rows.slice(0, 6)
})
const nursingSuggestions = computed(() => {
  const rows = Array.isArray(nursingRecord.value?.suggestions) ? nursingRecord.value.suggestions : []
  return rows.slice(0, 4)
})
const monitoringFocus = computed(() => {
  const result = reasoningRecord.value?.result || {}
  const rows = Array.isArray(result?.monitoring_focus) ? result.monitoring_focus : []
  return rows.slice(0, 4).map((item: any) => `${item.item || '监测项'} ${item.threshold || item.target || ''}`.trim())
})
const effectSummary = computed(() => {
  const effects = interventions.value.map((item: any) => item?.effectiveness?.effect).filter(Boolean)
  if (effects.includes('improving')) return '风险下降'
  if (effects.includes('worsening')) return '仍需升级'
  if (effects.length) return '趋势平稳'
  return '待评估'
})
const causalRows = computed(() => {
  const rows = causalAnalysis.value?.analysis?.candidate_causes || causalAnalysis.value?.candidate_causes || []
  return Array.isArray(rows) ? rows.slice(0, 4) : []
})
const causalSummary = computed(() => String(causalAnalysis.value?.analysis?.context_summary?.summary || causalAnalysis.value?.context_summary?.summary || '选择一个异常入口后生成因果链。'))
const causalEvidenceProfile = computed(() => {
  const rows = causalAnalysis.value?.analysis?.evidence_profile || causalAnalysis.value?.evidence_profile || []
  return Array.isArray(rows) ? rows.slice(0, 8) : []
})
const causalGuidelines = computed(() => {
  const rows = causalAnalysis.value?.analysis?.guideline_evidence || causalAnalysis.value?.guideline_evidence || []
  return Array.isArray(rows) ? rows.slice(0, 4) : []
})
const mdtSummary = computed(() => String(mdtMetaSummary.value?.summary || mdtRecord.value?.summary || '暂无 MDT 会诊摘要'))
const specialistCards = computed(() => Object.values(mdtResult.value?.assessments || mdtRecord.value?.specialist_assessments || {}).slice(0, 6) as any[])
const conflictRows = computed(() => Array.isArray(mdtResult.value?.conflicts) ? mdtResult.value.conflicts.slice(0, 4) : [])
const metaActions = computed(() => Array.isArray(mdtMetaSummary.value?.final_actions) ? mdtMetaSummary.value.final_actions.slice(0, 6) : [])
const primarySubphenotype = computed(() => subphenotypeRecord.value?.primary_profile || null)
const subphenotypeSummary = computed(() => String(subphenotypeRecord.value?.summary || '等待亚表型识别结果'))
const whatIfSummary = computed(() => String(whatIfRecord.value?.summary || '选择一个干预，模拟 30 分钟内的关键指标变化。'))
const whatIfProjectionRows = computed(() => {
  const projected = whatIfRecord.value?.projected_state || {}
  const current = whatIfRecord.value?.current_state || {}
  const rows = [
    { label: 'MAP 30m', current: Number(current.map), projected: Number(projected.map_30m), scale: 100, unit: 'mmHg' },
    { label: 'SpO2 30m', current: Number(current.spo2), projected: Number(projected.spo2_30m), scale: 100, unit: '%' },
    { label: '乳酸 30m', current: Number(current.lactate), projected: Number(projected.lactate_30m), scale: 8, unit: 'mmol/L' },
  ]
  return rows.filter((item) => Number.isFinite(item.projected)).map((item) => ({ label: item.label, value: `${Number.isFinite(item.current) ? item.current : '—'} → ${item.projected}${item.unit}`, width: `${Math.max(8, Math.min(100, (item.projected / item.scale) * 100))}%` }))
})
const whatIfCautions = computed(() => {
  const rows = Array.isArray(whatIfRecord.value?.cautions) ? whatIfRecord.value.cautions : []
  return rows.slice(0, 4)
})
const twinOverviewSummary = computed(() => {
  const calcTime = fmtTime(twinRecord.value?.calc_time)
  const diagnosis = String(twinPatient.value?.diagnosis || '').trim()
  const alerts = Number(twinSummary.value?.active_alerts_24h || 0)
  const problems = Number(twinSummary.value?.problem_count || 0)
  if (!hasTwinSnapshot.value) return '数字孪生快照已预留接入位，当前等待底层状态生成。'
  return `${calcTime} 更新快照，${diagnosis || '诊断待补充'}；当前识别 ${problems} 个问题，近 24h 报警 ${alerts} 条。`
})
const twinOverviewCards = computed(() => [
  { label: '快照时间', value: fmtTime(twinRecord.value?.calc_time), meta: `窗口 ${twinRecord.value?.snapshot_window_hours || 24}h` },
  { label: '在床位置', value: `${twinPatient.value?.dept || 'ICU'} / ${twinPatient.value?.bed || '床位待补'}`, meta: twinPatient.value?.nursing_level || '护理级别待补' },
  { label: '活动报警', value: String(twinSummary.value?.active_alerts_24h ?? 0), meta: '近 24 小时' },
  { label: '时间轴事件', value: String(twinSummary.value?.timeline_events ?? 0), meta: '统一患者事件流' },
])
const twinMetricChips = computed(() => {
  const defs = [
    { label: 'MAP', value: twinSnapshot.value?.map?.current, unit: 'mmHg', digits: 0 },
    { label: 'HR', value: twinSnapshot.value?.hr?.current, unit: 'bpm', digits: 0 },
    { label: 'SpO2', value: twinSnapshot.value?.spo2?.current, unit: '%', digits: 0 },
    { label: 'RR', value: twinSnapshot.value?.rr?.current, unit: '/min', digits: 0 },
    { label: 'Temp', value: twinSnapshot.value?.temp?.current, unit: '℃', digits: 1 },
    { label: '乳酸', value: twinSnapshot.value?.lactate?.current, unit: 'mmol/L', digits: 1 },
    { label: '尿量', value: twinSnapshot.value?.urine_ml_kg_h_6h, unit: 'mL/kg/h', digits: 2 },
    { label: '血管活性药', value: twinSnapshot.value?.vasoactive_support?.current_dose_ug_kg_min, unit: 'ug/kg/min', digits: 3 },
  ]
  return defs.map((item) => ({ label: item.label, value: formatMetric(item.value, item.unit, item.digits) })).filter((item) => item.value !== '—')
})
const twinTrendChips = computed(() => {
  const vitalsSnapshot = twinVitals.value?.snapshot || {}
  const defs = [
    { key: 'map', label: 'MAP 趋势' },
    { key: 'hr', label: 'HR 趋势' },
    { key: 'spo2', label: 'SpO2 趋势' },
    { key: 'rr', label: 'RR 趋势' },
    { key: 'temp', label: 'Temp 趋势' },
  ]
  return defs.map((item) => {
    const row = vitalsSnapshot?.[item.key] || {}
    if (!row.points) return null
    return { label: item.label, value: `${trendText(row.trend)} · ${formatSigned(row.delta)}` }
  }).filter(Boolean) as Array<{ label: string; value: string }>
})
const timelineRows = computed(() => {
  const rows = Array.isArray(twinRecord.value?.timeline) ? twinRecord.value.timeline : []
  return rows.slice(0, 16).map((item: any) => {
    const source = String(item?.source || 'snapshot').toLowerCase()
    const meta = item?.meta || {}
    return {
      ...item,
      label: timelineDisplayLabel(item),
      tone: timelineTone(source, meta),
      sourceLabel: timelineSourceLabel(source),
      detail: timelineDetail(item),
      metaText: timelineMetaText(meta),
    }
  })
})
function pct(value: any) { const n = Number(value || 0); return `${Math.max(0, Math.min(100, n * 100)).toFixed(n >= 0.1 ? 1 : 0)}%` }
function fmtTime(value: any) {
  if (!value) return '时间未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return `${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}
function formatMetric(value: any, unit = '', digits = 0) {
  if (value == null || value === '') return '—'
  const num = Number(value)
  if (Number.isNaN(num)) return `${String(value)}${unit ? ` ${unit}` : ''}`.trim()
  const rendered = digits > 0 ? num.toFixed(digits) : `${Math.round(num)}`
  return `${rendered}${unit ? ` ${unit}` : ''}`.trim()
}
function trendText(value: any) {
  const key = String(value || '').toLowerCase()
  if (key === 'up') return '上升'
  if (key === 'down') return '下降'
  if (key === 'stable') return '平稳'
  return '数据不足'
}
function formatSigned(value: any) {
  const num = Number(value)
  if (!Number.isFinite(num)) return 'Δ —'
  const abs = Math.abs(num)
  const digits = abs >= 10 ? 0 : abs >= 1 ? 1 : 2
  return `Δ ${num > 0 ? '+' : ''}${num.toFixed(digits)}`
}
function effectText(value: any) { const key = String(value || '').toLowerCase(); if (key === 'improving') return '干预后风险下降'; if (key === 'worsening') return '干预后风险上升'; return '干预后风险平稳' }
function effectDelta(value: any) { const n = Number(value || 0); return `${n > 0 ? '+' : ''}${(n * 100).toFixed(1)}%` }
function interventionStatusText(status: any) { const key = String(status || 'pending').toLowerCase(); return ({ pending: '待执行', in_progress: '追踪中', completed: '已完成', dismissed: '不采纳' } as Record<string, string>)[key] || '待执行' }
function timelineSourceLabel(source: string) { return ({ vitals: '生命体征', labs: '检验', medication: '用药', score_records: '评分', imaging: '影像', nursing: '护理文本', alert: '报警' } as Record<string, string>)[source] || '快照' }
function timelineTypeLabel(value: any) {
  const key = String(value || '').toLowerCase()
  return ({
    arc_risk: 'ARC 风险',
    weaning_assessment: '撤机评估',
    sepsis_bundle_tracker: '脓毒症 1 小时解放束追踪',
    temporal_risk_scanner: '时序风险扫描',
    nutrition_start_delay: '营养支持启动延迟',
    refractory_hypoxemia: '难治性低氧血症风险',
    hypertensive_emergency: '高血压急症风险',
    seizure_prophylaxis: '癫痫预防评估提醒',
    vap_bundle_missing: 'VAP Bundle 缺项提醒',
    weaning: 'SBT 前建议先处理',
    liberation_bundle: 'ABCDEF Bundle 合规待补全',
    drug_order: '用药执行',
    imaging_report_signal_analysis: '影像信号更新',
    nursing_note_signal_analysis: '护理文本信号更新',
    warning: '警示',
    high: '高危',
    critical: '危急',
    medium: '中等',
    low: '低危',
    pending: '待处理',
    stable: '平稳'
  } as Record<string, string>)[key] || String(value || '').replace(/_/g, ' ').trim() || '事件更新'
}
function timelineMetricLabel(value: any) {
  const key = String(value || '').toLowerCase()
  return ({ map: 'MAP', hr: 'HR', spo2: 'SpO2', rr: 'RR', temp: '体温', lac: '乳酸', lactate: '乳酸', cr: '肌酐', wbc: '白细胞', plt: '血小板', tbil: '总胆红素', inr: 'INR', ph: 'pH', pao2: 'PaO2' } as Record<string, string>)[key] || String(value || '').toUpperCase()
}
function timelineLevelLabel(value: any) {
  const key = String(value || '').toLowerCase()
  return ({ warning: '警示', high: '高危', critical: '危急', medium: '中等', low: '低危', pending: '待处理', completed: '已完成', in_progress: '处理中', dismissed: '已忽略' } as Record<string, string>)[key] || String(value || '状态待补')
}
function timelineDisplayLabel(item: any) {
  const source = String(item?.source || '').toLowerCase()
  const explicit = String(item?.label || '').trim()
  if (source === 'score_records') return timelineTypeLabel(item?.type)
  if (source === 'alert') return /[\u4e00-\u9fa5]/.test(explicit) ? explicit : timelineTypeLabel(item?.type)
  return explicit || timelineTypeLabel(item?.type)
}
function timelineTone(source: string, meta: any) { const severity = String(meta?.severity || '').toLowerCase(); if (severity === 'critical' || severity === 'high') return 'danger'; if (source === 'alert') return 'warning'; if (source === 'medication') return 'accent'; if (source === 'imaging' || source === 'nursing') return 'info'; return 'neutral' }
function timelineDetail(item: any) {
  const source = String(item?.source || '').toLowerCase()
  if (source === 'alert') return `类型 ${timelineTypeLabel(item?.type)}`
  if (source === 'medication') return `来源 ${item?.meta?.route || '给药路径待补'} · 剂量 ${formatMetric(item?.meta?.dose, item?.meta?.dose_unit || '', 0)}`
  if (source === 'score_records') return `评分 ${timelineTypeLabel(item?.type)} · ${timelineLevelLabel(item?.meta?.risk_level || 'pending')}`
  if (source === 'labs' || source === 'vitals') return `指标 ${timelineMetricLabel(item?.type)}`
  return `来源 ${timelineSourceLabel(source)}`
}
function timelineMetaText(meta: any) {
  if (!meta || typeof meta !== 'object') return ''
  return [meta?.severity ? `严重度 ${timelineLevelLabel(meta.severity)}` : '', meta?.status ? `状态 ${timelineLevelLabel(meta.status)}` : '', meta?.summary ? String(meta.summary) : '', meta?.action_taken ? `处置 ${meta.action_taken}` : ''].filter(Boolean).join(' · ')
}
function openMdtBoard() { router.push({ path: '/mdt', query: { patient_id: props.patientId } }) }
async function loadCausal(finding: string) { selectedFinding.value = finding; try { const res = await postAiCausalAnalysis(props.patientId, { abnormal_finding: finding }); causalAnalysis.value = res.data || null } catch { error.value = '因果链分析加载失败' } }
async function runWhatIf(preset: any) {
  if (!props.patientId || whatIfLoading.value) return
  whatIfSelected.value = String(preset?.type || '')
  whatIfLoading.value = true
  try {
    const res = await postAiWhatIfSimulation(props.patientId, preset.payload)
    whatIfResult.value = res.data || null
  } catch {
    error.value = '干预情景模拟加载失败'
  } finally {
    whatIfLoading.value = false
  }
}
async function loadAll(refresh = false) {
  if (!props.patientId || loading.value) return
  loading.value = true
  error.value = ''
  try {
    const [twinRes, riskRes, proactiveRes, reasoningRes, mdtRes, nursingRes, subtypeRes] = await Promise.all([
      getAiPatientDigitalTwin(props.patientId, { refresh, hours: 24 }),
      getAiRiskForecast(props.patientId),
      getAiProactiveManagement(props.patientId, { refresh }),
      getAiClinicalReasoning(props.patientId, { refresh }),
      getAiMultiAgentAssessment(props.patientId, { refresh }),
      getAiNursingNoteSignals(props.patientId, { refresh }),
      getAiSubphenotype(props.patientId, { refresh }),
    ])
    digitalTwin.value = twinRes.data || null
    riskForecast.value = riskRes.data || null
    proactivePlan.value = proactiveRes.data || null
    reasoningPlan.value = reasoningRes.data || null
    mdtAssessment.value = mdtRes.data || null
    nursingSignals.value = nursingRes.data || null
    subphenotypeProfile.value = subtypeRes.data || null
    await loadCausal(selectedFinding.value)
    await runWhatIf(whatIfPresets.find((item) => item.type === whatIfSelected.value) || whatIfPresets[0])
  } catch {
    error.value = '数字孪生工作台加载失败，请检查后端智能接口。'
  } finally {
    loading.value = false
  }
}
async function submitFeedback(item: any, payload: { status?: string; adopted?: boolean }) {
  const interventionId = String(item?.intervention_id || '')
  if (!interventionId) return
  savingMap[interventionId] = true
  try {
    const res = await postAiProactiveInterventionFeedback(props.patientId, interventionId, { record_id: planRecord.value?._id, actor: 'digital_twin_tab', note: '前端数字孪生工作台更新', ...payload })
    const record = res.data?.record
    if (record) proactivePlan.value = { ...(proactivePlan.value || {}), plan: record }
  } catch {
    error.value = '干预反馈提交失败'
  } finally {
    savingMap[interventionId] = false
  }
}
watch(() => props.patientId, () => { digitalTwin.value = null; riskForecast.value = null; proactivePlan.value = null; reasoningPlan.value = null; mdtAssessment.value = null; causalAnalysis.value = null; nursingSignals.value = null; subphenotypeProfile.value = null; whatIfResult.value = null; void loadAll(false) }, { immediate: true })
</script>

<style scoped>
.twin-shell { display: grid; gap: 16px; }
.twin-head { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; flex-wrap: wrap; padding: 18px; border-radius: 22px; border: 1px solid rgba(71,145,191,.18); background: radial-gradient(circle at top right, rgba(24,126,173,.18), transparent 36%), linear-gradient(160deg, rgba(8,24,39,.98) 0%, rgba(6,17,30,.98) 58%, rgba(4,12,24,.99) 100%); }
.twin-kicker { color: #6ee7f9; font-size: 11px; letter-spacing: .22em; text-transform: uppercase; }
.twin-title { margin: 6px 0 0; color: #effcff; font-size: 24px; font-weight: 800; }
.twin-sub { margin: 8px 0 0; color: #8ab5ca; font-size: 13px; max-width: 760px; }
.twin-refresh { border: 1px solid rgba(110,231,249,.24); background: rgba(7,27,40,.84); color: #dffbff; border-radius: 999px; padding: 10px 16px; cursor: pointer; }
.twin-refresh:disabled { opacity: .6; cursor: default; }
.twin-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.twin-kpi,.loop-card,.twin-card { border-radius: 18px; border: 1px solid rgba(81,163,201,.16); background: linear-gradient(180deg, rgba(9,24,38,.96), rgba(5,14,24,.98)); box-shadow: inset 0 1px 0 rgba(193,233,255,.04); }
.twin-kpi { padding: 16px; display: grid; gap: 6px; }
.twin-kpi span,.loop-label,.card-sub,.intervention-meta,.causal-meta,.mdt-meta { color: #7ea8bc; font-size: 12px; }
.twin-kpi strong,.loop-value,.card-title,.intervention-title,.mdt-title { color: #f4fbff; }
.loop-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.loop-card { padding: 16px; display: grid; gap: 8px; }
.loop-step { width: 32px; height: 32px; border-radius: 10px; display: inline-flex; align-items: center; justify-content: center; background: rgba(34,211,238,.12); color: #7ee9f6; font-weight: 800; }
.loop-value { font-size: 18px; font-weight: 700; }
.loop-meta { color: #9ac0d2; font-size: 12px; line-height: 1.5; }
.twin-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.twin-card { padding: 16px; display: grid; gap: 12px; }
.twin-card-wide { grid-column: span 2; }
.card-head,.intervention-top,.causal-top { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.card-title { font-size: 18px; font-weight: 700; }
.risk-badge,.status-pill { border-radius: 999px; padding: 5px 10px; font-size: 11px; font-weight: 700; }
.risk-badge.is-critical,.status-pill.is-completed { background: rgba(244,63,94,.16); color: #fecdd3; }
.risk-badge.is-high,.status-pill.is-in_progress { background: rgba(251,146,60,.16); color: #fed7aa; }
.risk-badge.is-medium,.status-pill.is-pending { background: rgba(56,189,248,.16); color: #bae6fd; }
.risk-badge.is-low,.status-pill.is-dismissed { background: rgba(52,211,153,.16); color: #bbf7d0; }
.curve-list,.intervention-list,.causal-list,.mdt-grid,.conflict-list,.causal-guidelines { display: grid; gap: 10px; }
.curve-row,.causal-item,.mdt-item,.intervention-item,.conflict-item { padding: 12px; border-radius: 14px; background: rgba(7,20,34,.8); border: 1px solid rgba(77,152,188,.12); }
.curve-top { display: flex; justify-content: space-between; gap: 10px; margin-bottom: 6px; color: #d8eff8; font-size: 12px; }
.curve-bar { height: 8px; border-radius: 999px; background: rgba(43,85,108,.36); overflow: hidden; }
.curve-fill { height: 100%; border-radius: inherit; background: linear-gradient(90deg, #22d3ee, #38bdf8); }
.causal-fill { background: linear-gradient(90deg, #f59e0b, #fb7185); }
.overview-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.overview-item { display: grid; gap: 4px; }
.overview-item span,.overview-item small { color: #8fb4c8; font-size: 12px; }
.overview-item strong { color: #f4fbff; font-size: 16px; }
.timeline-list { display: grid; gap: 12px; }
.timeline-item { display: grid; grid-template-columns: 120px minmax(0, 1fr); gap: 12px; align-items: stretch; }
.timeline-rail { position: relative; display: grid; justify-items: end; gap: 8px; padding-right: 12px; }
.timeline-time { color: #8fb6c9; font-size: 12px; line-height: 1.5; text-align: right; }
.timeline-dot { width: 12px; height: 12px; border-radius: 999px; border: 2px solid rgba(198,239,255,.16); background: #64748b; z-index: 1; }
.timeline-dot--danger { background: #fb7185; }
.timeline-dot--warning { background: #f59e0b; }
.timeline-dot--accent { background: #34d399; }
.timeline-dot--info { background: #22d3ee; }
.timeline-dot--neutral { background: #64748b; }
.timeline-line { position: absolute; top: 44px; right: 17px; bottom: -12px; width: 1px; background: linear-gradient(180deg, rgba(110,231,249,.4), rgba(110,231,249,0)); }
.timeline-card { display: grid; gap: 8px; }
.timeline-card-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.timeline-card-title { color: #edf9ff; font-size: 14px; font-weight: 700; line-height: 1.5; }
.timeline-card-sub,.timeline-card-meta { color: #8fb4c8; font-size: 12px; line-height: 1.6; }
.timeline-source { border-radius: 999px; padding: 5px 10px; font-size: 11px; font-weight: 700; white-space: nowrap; }
.timeline-source.is-danger { background: rgba(244,63,94,.14); color: #fecdd3; }
.timeline-source.is-warning { background: rgba(245,158,11,.14); color: #fde68a; }
.timeline-source.is-accent { background: rgba(52,211,153,.16); color: #bbf7d0; }
.timeline-source.is-info { background: rgba(34,211,238,.15); color: #c4fbff; }
.timeline-source.is-neutral { background: rgba(71,85,105,.3); color: #d7e6ef; }
.bullet-list { margin: 0; padding-left: 18px; color: #d7edf7; display: grid; gap: 8px; }
.bullet-list.compact { gap: 6px; }
.summary-panel,.empty-panel,.error-panel,.effect-box { padding: 12px 14px; border-radius: 14px; line-height: 1.75; }
.summary-panel,.empty-panel { background: rgba(7,20,34,.78); color: #d5edf8; border: 1px solid rgba(79,153,191,.12); box-shadow: inset 0 1px 0 rgba(145,228,255,.04); }
.conflict-title { color: #fef3c7; font-size: 13px; font-weight: 700; }
.conflict-meta { margin-top: 6px; color: #d9edf8; font-size: 12px; line-height: 1.6; }
.conflict-title { color: #fef3c7; font-size: 13px; font-weight: 700; }
.conflict-meta { margin-top: 6px; color: #d9edf8; font-size: 12px; line-height: 1.6; }
.conflict-title { color: #fef3c7; font-size: 13px; font-weight: 700; }
.conflict-meta { margin-top: 6px; color: #d9edf8; font-size: 12px; line-height: 1.6; }
.conflict-title { color: #fef3c7; font-size: 13px; font-weight: 700; }
.conflict-meta { margin-top: 6px; color: #d9edf8; font-size: 12px; line-height: 1.6; }
.chip-row,.action-row { display: flex; flex-wrap: wrap; gap: 8px; }
.info-chip,.cause-chip,.mini-btn { border-radius: 999px; min-height: 30px; padding: 0 12px; font-size: 12px; line-height: 1.4; display: inline-flex; align-items: center; }
.info-chip { background: rgba(13,35,54,.92); color: #d8f5ff; border: 1px solid rgba(125,211,252,.14); }
.info-chip--muted { opacity: .72; background: rgba(15,37,51,.55); color: #8bb5c7; }
.cause-chip,.mini-btn { cursor: pointer; border: 1px solid rgba(81,163,201,.16); background: rgba(6,21,34,.86); color: #dff8ff; }
.cause-chip.active { background: rgba(34,211,238,.16); border-color: rgba(110,231,249,.3); box-shadow: inset 0 1px 0 rgba(186,230,253,.08); }
.mini-btn--soft { background: rgba(20,184,166,.14); }
.mini-btn--ghost { background: rgba(244,63,94,.12); }
.effect-box { display: flex; justify-content: space-between; gap: 12px; color: #f4fbff; }
.effect-box.is-improving { background: rgba(20,184,166,.14); }
.effect-box.is-worsening { background: rgba(244,63,94,.14); }
.effect-box.is-stable { background: rgba(56,189,248,.14); }
.mdt-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.error-panel { background: rgba(127,29,29,.22); border: 1px solid rgba(248,113,113,.26); color: #fecaca; }
@media (max-width: 900px) { .overview-grid,.timeline-item { grid-template-columns: 1fr; } .timeline-rail { justify-items: start; padding-right: 0; padding-bottom: 8px; } .timeline-time { text-align: left; } .timeline-line { left: 5px; right: auto; top: 32px; bottom: -8px; } }
@media (max-width: 1100px) { .twin-kpis,.loop-grid,.twin-grid,.mdt-grid { grid-template-columns: 1fr 1fr; } .twin-card-wide { grid-column: span 2; } }
@media (max-width: 720px) { .twin-kpis,.loop-grid,.twin-grid,.mdt-grid { grid-template-columns: 1fr; } .twin-card-wide { grid-column: auto; } }
</style>



















