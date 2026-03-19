<template>
  <section class="twin-shell">
    <div class="twin-head">
      <div>
        <div class="twin-kicker">数字孪生闭环工作台</div>
        <h3 class="twin-title">数字孪生诊疗推理</h3>
        <p class="twin-sub">把风险预测、建议、追踪、效果评估、因果链和 MDT 会诊收敛到一个 AI 临床工作台。</p>
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
              <span class="info-chip">置信 {{ row.confidence_level || 'medium' }}</span>
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
        <div class="card-head"><div><div class="card-title">MDT 多智能体会诊</div><div class="card-sub">专科 Agent 观点、冲突与 Meta-Agent 裁决</div></div></div>
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
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  getAiClinicalReasoning,
  getAiMultiAgentAssessment,
  getAiNursingNoteSignals,
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
function pct(value: any) { const n = Number(value || 0); return `${Math.max(0, Math.min(100, n * 100)).toFixed(n >= 0.1 ? 1 : 0)}%` }
function effectText(value: any) { const key = String(value || '').toLowerCase(); if (key === 'improving') return '干预后风险下降'; if (key === 'worsening') return '干预后风险上升'; return '干预后风险平稳' }
function effectDelta(value: any) { const n = Number(value || 0); return `${n > 0 ? '+' : ''}${(n * 100).toFixed(1)}%` }
function interventionStatusText(status: any) { const key = String(status || 'pending').toLowerCase(); return ({ pending: '待执行', in_progress: '追踪中', completed: '已完成', dismissed: '不采纳' } as Record<string, string>)[key] || '待执行' }
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
    const [riskRes, proactiveRes, reasoningRes, mdtRes, nursingRes, subtypeRes] = await Promise.all([
      getAiRiskForecast(props.patientId),
      getAiProactiveManagement(props.patientId, { refresh }),
      getAiClinicalReasoning(props.patientId, { refresh }),
      getAiMultiAgentAssessment(props.patientId, { refresh }),
      getAiNursingNoteSignals(props.patientId, { refresh }),
      getAiSubphenotype(props.patientId, { refresh }),
    ])
    riskForecast.value = riskRes.data || null
    proactivePlan.value = proactiveRes.data || null
    reasoningPlan.value = reasoningRes.data || null
    mdtAssessment.value = mdtRes.data || null
    nursingSignals.value = nursingRes.data || null
    subphenotypeProfile.value = subtypeRes.data || null
    await loadCausal(selectedFinding.value)
    await runWhatIf(whatIfPresets.find((item) => item.type === whatIfSelected.value) || whatIfPresets[0])
  } catch {
    error.value = '数字孪生工作台加载失败，请检查后端 AI 接口。'
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
watch(() => props.patientId, () => { riskForecast.value = null; proactivePlan.value = null; reasoningPlan.value = null; mdtAssessment.value = null; causalAnalysis.value = null; nursingSignals.value = null; subphenotypeProfile.value = null; whatIfResult.value = null; void loadAll(false) }, { immediate: true })
onMounted(() => { void loadAll(false) })
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
.bullet-list { margin: 0; padding-left: 18px; color: #d7edf7; display: grid; gap: 8px; }
.bullet-list.compact { gap: 6px; }
.summary-panel,.empty-panel,.error-panel,.effect-box { padding: 12px 14px; border-radius: 14px; line-height: 1.6; }
.summary-panel,.empty-panel { background: rgba(7,20,34,.78); color: #d5edf8; border: 1px solid rgba(79,153,191,.12); }
.conflict-title { color: #fef3c7; font-size: 13px; font-weight: 700; }
.conflict-meta { margin-top: 6px; color: #d9edf8; font-size: 12px; line-height: 1.6; }
.conflict-title { color: #fef3c7; font-size: 13px; font-weight: 700; }
.conflict-meta { margin-top: 6px; color: #d9edf8; font-size: 12px; line-height: 1.6; }
.conflict-title { color: #fef3c7; font-size: 13px; font-weight: 700; }
.conflict-meta { margin-top: 6px; color: #d9edf8; font-size: 12px; line-height: 1.6; }
.conflict-title { color: #fef3c7; font-size: 13px; font-weight: 700; }
.conflict-meta { margin-top: 6px; color: #d9edf8; font-size: 12px; line-height: 1.6; }
.chip-row,.action-row { display: flex; flex-wrap: wrap; gap: 8px; }
.info-chip,.cause-chip,.mini-btn { border-radius: 999px; padding: 7px 12px; font-size: 12px; }
.info-chip { background: rgba(16,52,71,.7); color: #bfefff; border: 1px solid rgba(74,175,208,.12); }
.info-chip--muted { opacity: .72; background: rgba(15,37,51,.55); color: #8bb5c7; }
.cause-chip,.mini-btn { cursor: pointer; border: 1px solid rgba(81,163,201,.16); background: rgba(6,21,34,.86); color: #dff8ff; }
.cause-chip.active { background: rgba(34,211,238,.16); border-color: rgba(110,231,249,.3); }
.mini-btn--soft { background: rgba(20,184,166,.14); }
.mini-btn--ghost { background: rgba(244,63,94,.12); }
.effect-box { display: flex; justify-content: space-between; gap: 12px; color: #f4fbff; }
.effect-box.is-improving { background: rgba(20,184,166,.14); }
.effect-box.is-worsening { background: rgba(244,63,94,.14); }
.effect-box.is-stable { background: rgba(56,189,248,.14); }
.mdt-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.error-panel { background: rgba(127,29,29,.22); border: 1px solid rgba(248,113,113,.26); color: #fecaca; }
@media (max-width: 1100px) { .twin-kpis,.loop-grid,.twin-grid,.mdt-grid { grid-template-columns: 1fr 1fr; } .twin-card-wide { grid-column: span 2; } }
@media (max-width: 720px) { .twin-kpis,.loop-grid,.twin-grid,.mdt-grid { grid-template-columns: 1fr; } .twin-card-wide { grid-column: auto; } }
</style>


