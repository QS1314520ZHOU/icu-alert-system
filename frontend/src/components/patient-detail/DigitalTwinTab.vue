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
      <div class="twin-kpi"><span>FM基础模型</span><strong>{{ foundationModelStatus }}</strong></div>
      <div class="twin-kpi"><span>工作台状态</span><strong>{{ workbenchState }}</strong></div>
      <div class="twin-kpi"><span>已追踪干预</span><strong>{{ trackedInterventions }}</strong></div>
    </div>

    <div v-if="foundationModelChips.length" class="chip-row fm-chip-row">
      <span v-for="item in foundationModelChips" :key="item.label" class="info-chip">{{ item.label }} {{ item.value }}</span>
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
        <div class="twin-overview-split">
          <DigitalTwinAvatarPanel
            :snapshot="twinSnapshot"
            :vitals-snapshot="twinVitals?.snapshot || {}"
            :scores="twinRecord?.scores || {}"
            :calc-time="fmtTime(twinRecord?.calc_time)"
            :silhouette="patientSilhouette"
          />
          <div class="twin-overview-copy">
            <div class="summary-panel">{{ twinOverviewSummary }}</div>
            <div class="overview-grid">
              <article v-for="item in twinOverviewCards" :key="item.label" class="overview-item">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
                <small>{{ item.meta }}</small>
              </article>
            </div>
          </div>
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

      <section class="twin-card twin-card-wide whatif-workbench">
        <div class="card-head">
          <div>
            <div class="card-title">WhatIfConsole</div>
            <div class="card-sub">右侧抽屉对比单干预反事实轨迹；仅模拟，不生成医嘱。</div>
          </div>
          <button class="mini-btn" @click="whatIfDrawerOpen = !whatIfDrawerOpen">{{ whatIfDrawerOpen ? '收起面板' : '打开面板' }}</button>
        </div>
        <div v-if="whatIfBanner" :class="['whatif-banner', { muted: whatIfDegraded }]">{{ whatIfBanner }}</div>
        <div class="whatif-layout">
          <div class="whatif-chart">
            <div class="whatif-axis">
              <span>过去实际值</span><span>6h baseline / what-if</span>
            </div>
            <div v-for="metric in whatIfChartRows" :key="metric.key" class="whatif-metric">
              <div class="curve-top"><span>{{ metric.label }}</span><strong>{{ metric.delta }}</strong></div>
              <div class="whatif-track">
                <i class="actual-line" :style="{ width: metric.actualWidth }"></i>
                <i class="baseline-line" :style="{ width: metric.baselineWidth }"></i>
                <i :class="['whatif-line', { degraded: whatIfDegraded }]" :style="{ width: metric.whatIfWidth }"></i>
                <span class="band band80" :style="{ left: metric.bandLeft, width: metric.band80 }"></span>
                <span class="band band95" :style="{ left: metric.bandLeft, width: metric.band95 }"></span>
              </div>
              <div class="whatif-legend">
                <span><i class="legend-sample legend-actual"></i>实际</span>
                <span><i class="legend-sample legend-baseline"></i>Baseline</span>
                <span><i class="legend-sample legend-counterfactual"></i>反事实</span>
              </div>
            </div>
          </div>
          <aside v-if="whatIfDrawerOpen" class="whatif-drawer">
            <div class="card-sub">单干预模板</div>
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
          </aside>
        </div>
      </section>
    </div>

    <div v-if="error" class="error-panel">{{ error }}</div>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import DigitalTwinAvatarPanel from './DigitalTwinAvatarPanel.vue'
import { formatStatusLabel } from '../../utils/displayLabels'
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
const whatIfBaseline = ref<any>(null)
const selectedFinding = ref('乳酸升高')
const whatIfSelected = ref('fluid_500')
const whatIfLoading = ref(false)
const whatIfDrawerOpen = ref(true)
const savingMap = reactive<Record<string, boolean>>({})
const causalOptions = ['乳酸升高', '肌酐升高', '低氧', '低血压', '血小板下降', '胆红素升高', '凝血异常']
const MAIN_LOAD_TIMEOUT_MS = 12000
const DEFERRED_LOAD_TIMEOUT_MS = 15000
const whatIfPresets = [
  { type: 'fluid_500', label: '液体 500ml', payload: { intervention_type: 'fluid_bolus', intervention_label: '晶体液补液 500mL', fluid_bolus_ml: 500, horizon_minutes: 360 } },
  { type: 'fluid_1000', label: '液体 1000ml', payload: { intervention_type: 'fluid_bolus', intervention_label: '晶体液补液 1000mL', fluid_bolus_ml: 1000, horizon_minutes: 360 } },
  { type: 'fluid_2000', label: '液体 2000ml', payload: { intervention_type: 'fluid_bolus', intervention_label: '晶体液补液 2000mL', fluid_bolus_ml: 2000, horizon_minutes: 360 } },
  { type: 'vaso_005', label: '去甲 +0.05', payload: { intervention_type: 'vasopressor_up', intervention_label: '去甲肾上腺素 +0.05 ug/kg/min', dose_delta_pct: 20, horizon_minutes: 360 } },
  { type: 'vaso_01', label: '去甲 +0.1', payload: { intervention_type: 'vasopressor_up', intervention_label: '去甲肾上腺素 +0.1 ug/kg/min', dose_delta_pct: 35, horizon_minutes: 360 } },
  { type: 'diuretic_40', label: '呋塞米 40mg', payload: { intervention_type: 'diuresis', intervention_label: '呋塞米 40mg', diuretic_intensity: 1, horizon_minutes: 360 } },
  { type: 'peep_2', label: 'PEEP +2', payload: { intervention_type: 'peep_up', intervention_label: 'PEEP 上调 2 cmH2O', peep_delta: 2, horizon_minutes: 360 } },
  { type: 'fio2_down10', label: 'FiO2 -10%', payload: { intervention_type: 'fio2_up', intervention_label: 'FiO2 下调 10%', fio2_delta: -10, horizon_minutes: 360 } },
] as const
const twinRecord = computed(() => digitalTwin.value?.record || digitalTwin.value || {})
const twinSnapshot = computed(() => twinRecord.value?.snapshot || {})
const twinPatient = computed(() => twinRecord.value?.patient || {})
const twinVitals = computed(() => twinRecord.value?.vitals || {})
const twinSummary = computed(() => twinRecord.value?.summary || {})
const foundationModelPredictions = computed(() => twinRecord.value?.foundation_model_predictions || {})
const foundationModelStatus = computed(() => foundationModelPredictions.value?.available === false ? '未加载' : '已接入')
const foundationModelChips = computed(() => {
  const tasks = foundationModelPredictions.value?.tasks || {}
  if (foundationModelPredictions.value?.available === false) {
    return [{ label: '模型状态', value: foundationModelPredictions.value?.reason || '本地权重未就绪' }]
  }
  const labels: Record<string, string> = { mortality: '死亡风险', aki: 'AKI', circulation_failure: '循环衰竭' }
  return Object.entries(tasks).map(([key, row]: any) => ({
    label: labels[key] || key,
    value: row?.probability == null ? '—' : pct(row.probability),
  })).slice(0, 3)
})
const patientSilhouette = computed<'female' | 'male'>(() => {
  const text = String(patient.value?.gender || patient.value?.genderText || patient.value?.hisSex || '').toLowerCase()
  if (text.includes('female') || text.includes('女')) return 'female'
  if (text.includes('male') || text.includes('男')) return 'male'
  return 'female'
})
const planRecord = computed(() => proactivePlan.value?.plan || proactivePlan.value || {})
const reasoningRecord = computed(() => reasoningPlan.value?.plan || reasoningPlan.value || {})
const mdtRecord = computed(() => mdtAssessment.value?.assessment || mdtAssessment.value || {})
const mdtResult = computed(() => mdtRecord.value?.result || mdtRecord.value || {})
const mdtMetaSummary = computed(() => mdtResult.value?.meta_agent || mdtRecord.value?.meta_summary || {})
const nursingRecord = computed(() => nursingSignals.value?.analysis || nursingSignals.value || {})
const subphenotypeRecord = computed(() => subphenotypeProfile.value?.profile || subphenotypeProfile.value || {})
const whatIfRecord = computed(() => whatIfResult.value?.simulation || whatIfResult.value || {})
const whatIfBaselineRecord = computed(() => whatIfBaseline.value?.simulation || whatIfBaseline.value || {})
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
function metricCurrent(key: string) {
  const direct = whatIfRecord.value?.current_state?.[key]
  const fallback = twinSnapshot.value?.[key]?.current ?? twinSnapshot.value?.[key]?.latest ?? twinSnapshot.value?.[key]?.snapshot?.latest
  const value = Number(direct ?? fallback)
  return Number.isFinite(value) ? value : null
}
const whatIfNoData = computed(() => {
  return ['map', 'spo2', 'hr', 'lactate'].every((key) => metricCurrent(key) == null)
})
const whatIfSummary = computed(() => {
  if (whatIfRecord.value?.data_available === false && whatIfNoData.value) return '当前患者暂无可用生命体征数据（MAP/SpO2/乳酸），无法执行反事实模拟。请确认监护仪数据已接入。'
  if (whatIfRecord.value?.summary && whatIfRecord.value.summary !== '模拟已生成') return String(whatIfRecord.value.summary)
  if (whatIfNoData.value) return '当前患者暂无可用生命体征数据（MAP/SpO2/乳酸），无法执行反事实模拟。请确认监护仪数据已接入。'
  return '选择一个单干预模板，模拟未来 6 小时关键指标变化。'
})
const whatIfDegraded = computed(() => Boolean(whatIfRecord.value?.model_meta?.degraded))
const whatIfBanner = computed(() => {
  if (whatIfRecord.value?.data_available === false && whatIfNoData.value) return '⚠️ 当前患者暂无生命体征数据，反事实模拟无法执行。请确认监护仪数据已接入。'
  if (whatIfDegraded.value) return '反事实模型降级为半机制模型，置信度降低，仅供参考。'
  const ood = whatIfRecord.value?.ood_warning
  if (ood?.is_ood) return `该患者状态在历史数据中罕见，预测可信度低：${(ood.reasons || []).join('；')}`
  return ''
})
const whatIfProjectionRows = computed(() => {
  if (whatIfNoData.value) return []
  const projected = whatIfRecord.value?.projected_state || {}
  const rows = [
    { label: 'MAP 30m', current: Number(metricCurrent('map')), projected: Number(projected.map_30m), scale: 100, unit: 'mmHg' },
    { label: 'SpO2 30m', current: Number(metricCurrent('spo2')), projected: Number(projected.spo2_30m), scale: 100, unit: '%' },
    { label: '乳酸 30m', current: Number(metricCurrent('lactate')), projected: Number(projected.lactate_30m), scale: 8, unit: 'mmol/L' },
  ]
  return rows.filter((item) => Number.isFinite(item.projected)).map((item) => ({ label: item.label, value: `${Number.isFinite(item.current) ? item.current : '—'} → ${item.projected}${item.unit}`, width: `${Math.max(8, Math.min(100, (item.projected / item.scale) * 100))}%` }))
})
const whatIfChartRows = computed(() => {
  if (whatIfNoData.value && !whatIfBaselineRecord.value?.response_curve) return []
  const defs = [
    { key: 'map', label: 'MAP', scale: 120, currentKey: 'map', projectedKey: 'map_30m' },
    { key: 'spo2', label: 'SpO2', scale: 100, currentKey: 'spo2', projectedKey: 'spo2_30m' },
    { key: 'lactate', label: '乳酸', scale: 10, currentKey: 'lactate', projectedKey: 'lactate_30m' },
  ]
  return defs
    .map((def) => {
      const current = Number(metricCurrent(def.key))
      const baselineCurve = whatIfBaselineRecord.value?.response_curve?.[def.key] || []
      const branchCurve = whatIfRecord.value?.response_curve?.[def.key] || []
      const band = whatIfRecord.value?.confidence_bands?.[def.key] || []
      const baseline = Number(baselineCurve.length ? baselineCurve[baselineCurve.length - 1]?.value : current)
      const branch = Number(branchCurve.length ? branchCurve[branchCurve.length - 1]?.value : (whatIfRecord.value?.projected_state?.[def.projectedKey] ?? current))
      // 如果 current、baseline、branch 全部无效，跳过该行
      if (!Number.isFinite(current) && !Number.isFinite(baseline) && !Number.isFinite(branch)) return null
      const bandLast = band?.[band.length - 1] || {}
      const p10 = Number(bandLast.p10 ?? branch)
      const p90 = Number(bandLast.p90 ?? branch)
      const p025 = Number(bandLast.p025 ?? branch)
      const p975 = Number(bandLast.p975 ?? branch)
      const pctWidth = (value: number) => `${Math.max(6, Math.min(100, (Math.abs(value) / def.scale) * 100))}%`
      return {
        key: def.key,
        label: def.label,
        delta: `${Number.isFinite(baseline) ? baseline.toFixed(def.key === 'lactate' ? 1 : 0) : '—'} → ${Number.isFinite(branch) ? branch.toFixed(def.key === 'lactate' ? 1 : 0) : '—'}`,
        actualWidth: pctWidth(current),
        baselineWidth: pctWidth(baseline),
        whatIfWidth: pctWidth(branch),
        bandLeft: pctWidth(Math.min(p10, p025)),
        band80: pctWidth(Math.abs(p90 - p10)),
        band95: pctWidth(Math.abs(p975 - p025)),
      }
    })
    .filter((row): row is NonNullable<typeof row> => row !== null)
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
    vap_bundle_missing: 'VAP 预防清单缺项提醒',
    weaning: 'SBT 前建议先处理',
    liberation_bundle: 'ABCDEF 防控清单待补全',
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
  return formatStatusLabel(value, '状态待补')
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
function withTimeout<T>(promise: Promise<T>, timeoutMs: number, label: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error(`${label} timeout`)), timeoutMs)
    promise.then(
      (value) => {
        window.clearTimeout(timer)
        resolve(value)
      },
      (err) => {
        window.clearTimeout(timer)
        reject(err)
      },
    )
  })
}
async function loadCausal(finding: string) { selectedFinding.value = finding; try { const res = await withTimeout(postAiCausalAnalysis(props.patientId, { abnormal_finding: finding }), DEFERRED_LOAD_TIMEOUT_MS, 'causal'); causalAnalysis.value = res.data || null } catch { error.value = '因果链分析加载失败' } }
async function runWhatIf(preset: any) {
  if (!props.patientId || whatIfLoading.value) return
  whatIfSelected.value = String(preset?.type || '')
  whatIfLoading.value = true
  try {
    const [baseRes, res] = await Promise.all([
      withTimeout(postAiWhatIfSimulation(props.patientId, { intervention_type: 'current_baseline', intervention_label: '当前治疗基线', horizon_minutes: 360 }), DEFERRED_LOAD_TIMEOUT_MS, 'what-if baseline'),
      withTimeout(postAiWhatIfSimulation(props.patientId, preset.payload), DEFERRED_LOAD_TIMEOUT_MS, 'what-if branch'),
    ])
    whatIfBaseline.value = baseRes.data || null
    whatIfResult.value = res.data || null
  } catch {
    error.value = '干预情景模拟加载失败'
  } finally {
    whatIfLoading.value = false
  }
}
async function loadDeferredAnalyses() {
  const preset = whatIfPresets.find((item) => item.type === whatIfSelected.value) || whatIfPresets[0]
  try { await loadCausal(selectedFinding.value) } catch { /* handled inside loadCausal */ }
  try { await runWhatIf(preset) } catch { /* handled inside runWhatIf */ }
}
async function loadAll(refresh = false) {
  if (!props.patientId || loading.value) return
  loading.value = true
  error.value = ''
  try {
    const results = await Promise.allSettled([
      withTimeout(getAiPatientDigitalTwin(props.patientId, { refresh, hours: 24 }), MAIN_LOAD_TIMEOUT_MS, 'digital twin'),
      withTimeout(getAiRiskForecast(props.patientId), MAIN_LOAD_TIMEOUT_MS, 'risk forecast'),
      withTimeout(getAiProactiveManagement(props.patientId, { refresh }), MAIN_LOAD_TIMEOUT_MS, 'proactive management'),
      withTimeout(getAiClinicalReasoning(props.patientId, { refresh }), MAIN_LOAD_TIMEOUT_MS, 'clinical reasoning'),
      withTimeout(getAiMultiAgentAssessment(props.patientId, { refresh }), MAIN_LOAD_TIMEOUT_MS, 'multi-agent assessment'),
      withTimeout(getAiNursingNoteSignals(props.patientId, { refresh }), MAIN_LOAD_TIMEOUT_MS, 'nursing signals'),
      withTimeout(getAiSubphenotype(props.patientId, { refresh }), MAIN_LOAD_TIMEOUT_MS, 'subphenotype'),
    ])
    const labels = ['数字孪生快照', '风险预测', '主动管理', '临床推理', 'MDT多智能体', '护理文本分析', '亚表型分析']
    const settled = (i: number) => {
      const r = results[i]
      return r && r.status === 'fulfilled' ? (r as PromiseFulfilledResult<any>).value : null
    }
    digitalTwin.value = settled(0)?.data || null
    riskForecast.value = settled(1)?.data || null
    proactivePlan.value = settled(2)?.data || null
    reasoningPlan.value = settled(3)?.data || null
    mdtAssessment.value = settled(4)?.data || null
    nursingSignals.value = settled(5)?.data || null
    subphenotypeProfile.value = settled(6)?.data || null
    const failedNames = results.map((r, i) => r.status === 'rejected' ? labels[i] : null).filter(Boolean)
    if (failedNames.length === labels.length) {
      error.value = '数字孪生工作台加载失败，请检查后端智能接口。'
    } else if (failedNames.length > 0) {
      error.value = `部分模块加载失败：${failedNames.join('、')}，其余数据已正常显示。`
    }
    // 后置任务：因果链 + 干预模拟，失败不影响主面板
    void loadDeferredAnalyses()
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
watch(() => props.patientId, () => { digitalTwin.value = null; riskForecast.value = null; proactivePlan.value = null; reasoningPlan.value = null; mdtAssessment.value = null; causalAnalysis.value = null; nursingSignals.value = null; subphenotypeProfile.value = null; whatIfResult.value = null; whatIfBaseline.value = null; void loadAll(false) }, { immediate: true })
</script>

<style scoped>
.twin-shell { display: grid; gap: 16px; }
.twin-head { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; flex-wrap: wrap; padding: 18px; border-radius: var(--card-radius); border: 1px solid rgba(71,145,191,.18); background: var(--bg-surface), transparent 36%), var(--bg-surface) 0%, rgba(6,17,30,.98) 58%, rgba(4,12,24,.99) 100%); }
.twin-kicker { color: var(--accent); font-size: 11px; letter-spacing: .22em; text-transform: uppercase; }
.twin-title { margin: 6px 0 0; color: var(--text-primary); font-size: 24px; font-weight: 800; }
.twin-sub { margin: 8px 0 0; color: #8ab5ca; font-size: 13px; max-width: 760px; }
.twin-refresh { border: 1px solid rgba(110,231,249,.24); background: var(--bg-surface),.84); color: var(--text-primary); border-radius: var(--card-radius); padding: 10px 16px; cursor: pointer; }
.twin-refresh:disabled { opacity: .6; cursor: default; }
.twin-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.twin-kpi,.loop-card,.twin-card { border-radius: var(--card-radius); border: 1px solid rgba(81,163,201,.16); background: var(--bg-surface), var(--bg-surface)); box-shadow: var(--card-shadow); }
.twin-kpi { padding: 16px; display: grid; gap: 6px; }
.twin-kpi span,.loop-label,.card-sub,.intervention-meta,.causal-meta,.mdt-meta { color: #7ea8bc; font-size: 12px; }
.twin-kpi strong,.loop-value,.card-title,.intervention-title,.mdt-title { color: var(--text-primary); }
.loop-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.loop-card { padding: 16px; display: grid; gap: 8px; }
.loop-step { width: 32px; height: 32px; border-radius: var(--card-radius); display: inline-flex; align-items: center; justify-content: center; background: rgba(34,211,238,.12); color: #7ee9f6; font-weight: 800; }
.loop-value { font-size: 18px; font-weight: 700; }
.loop-meta { color: #9ac0d2; font-size: 12px; line-height: 1.5; }
.twin-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.twin-card { padding: 16px; display: grid; gap: 12px; }
.twin-card-wide { grid-column: span 2; }
.card-head,.intervention-top,.causal-top { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.card-title { font-size: 18px; font-weight: 700; }
.risk-badge,.status-pill { border-radius: var(--card-radius); padding: 5px 10px; font-size: 11px; font-weight: 700; }
.risk-badge.is-critical,.status-pill.is-completed { background: rgba(244,63,94,.16); color: var(--danger-soft); }
.risk-badge.is-high,.status-pill.is-in_progress { background: rgba(251,146,60,.16); color: var(--warning-soft); }
.risk-badge.is-medium,.status-pill.is-pending { background: rgba(56,189,248,.16); color: var(--chart-1); }
.risk-badge.is-low,.status-pill.is-dismissed { background: rgba(52,211,153,.16); color: var(--success); }
.curve-list,.intervention-list,.causal-list,.mdt-grid,.conflict-list,.causal-guidelines { display: grid; gap: 10px; }
.curve-row,.causal-item,.mdt-item,.intervention-item,.conflict-item { padding: 12px; border-radius: var(--card-radius); background: var(--bg-surface),.8); border: 1px solid rgba(77,152,188,.12); }
.curve-top { display: flex; justify-content: space-between; gap: 10px; margin-bottom: 6px; color: #d8eff8; font-size: 12px; }
.curve-bar { height: 8px; border-radius: var(--card-radius); background: rgba(43,85,108,.36); overflow: hidden; }
.curve-fill { height: 100%; border-radius: inherit; background: var(--bg-surface); }
.causal-fill { background: var(--bg-surface); }
.overview-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.twin-overview-split { display: grid; grid-template-columns: minmax(280px, 360px) minmax(0, 1fr); gap: 14px; align-items: start; }
.twin-overview-copy { display: grid; gap: 12px; }
.overview-item { display: grid; gap: 4px; }
.overview-item span,.overview-item small { color: var(--text-secondary); font-size: 12px; }
.overview-item strong { color: var(--text-primary); font-size: 16px; }
.timeline-list { display: grid; gap: 12px; }
.timeline-item { display: grid; grid-template-columns: 120px minmax(0, 1fr); gap: 12px; align-items: stretch; }
.timeline-rail { position: relative; display: grid; justify-items: end; gap: 8px; padding-right: 12px; }
.timeline-time { color: #8fb6c9; font-size: 12px; line-height: 1.5; text-align: right; }
.timeline-dot { width: 12px; height: 12px; border-radius: var(--card-radius); border: 2px solid rgba(198,239,255,.16); background: var(--text-secondary); z-index: 1; }
.timeline-dot--danger { background: var(--danger); }
.timeline-dot--warning { background: var(--warning); }
.timeline-dot--accent { background: var(--chart-2); }
.timeline-dot--info { background: var(--brand); }
.timeline-dot--neutral { background: var(--text-secondary); }
.timeline-line { position: absolute; top: 44px; right: 17px; bottom: -12px; width: 1px; background: var(--bg-surface), rgba(110,231,249,0)); }
.timeline-card { display: grid; gap: 8px; }
.timeline-card-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.timeline-card-title { color: #edf9ff; font-size: 14px; font-weight: 700; line-height: 1.5; }
.timeline-card-sub,.timeline-card-meta { color: var(--text-secondary); font-size: 12px; line-height: 1.6; }
.timeline-source { border-radius: var(--card-radius); padding: 5px 10px; font-size: 11px; font-weight: 700; white-space: nowrap; }
.timeline-source.is-danger { background: rgba(244,63,94,.14); color: var(--danger-soft); }
.timeline-source.is-warning { background: rgba(245,158,11,.14); color: var(--warning-soft); }
.timeline-source.is-accent { background: rgba(52,211,153,.16); color: var(--success); }
.timeline-source.is-info { background: rgba(34,211,238,.15); color: #c4fbff; }
.timeline-source.is-neutral { background: rgba(71,85,105,.3); color: #d7e6ef; }
.bullet-list { margin: 0; padding-left: 18px; color: #d7edf7; display: grid; gap: 8px; }
.bullet-list.compact { gap: 6px; }
.summary-panel,.empty-panel,.error-panel,.effect-box { padding: 12px 14px; border-radius: var(--card-radius); line-height: 1.75; }
.summary-panel,.empty-panel { background: var(--bg-surface),.78); color: #d5edf8; border: 1px solid rgba(79,153,191,.12); box-shadow: var(--card-shadow); }
.conflict-title { color: var(--warning-soft); font-size: 13px; font-weight: 700; }
.conflict-meta { margin-top: 6px; color: var(--chart-1); font-size: 12px; line-height: 1.6; }
.conflict-title { color: var(--warning-soft); font-size: 13px; font-weight: 700; }
.conflict-meta { margin-top: 6px; color: var(--chart-1); font-size: 12px; line-height: 1.6; }
.conflict-title { color: var(--warning-soft); font-size: 13px; font-weight: 700; }
.conflict-meta { margin-top: 6px; color: var(--chart-1); font-size: 12px; line-height: 1.6; }
.conflict-title { color: var(--warning-soft); font-size: 13px; font-weight: 700; }
.conflict-meta { margin-top: 6px; color: var(--chart-1); font-size: 12px; line-height: 1.6; }
.chip-row,.action-row { display: flex; flex-wrap: wrap; gap: 8px; }
.info-chip,.cause-chip,.mini-btn { border-radius: var(--card-radius); min-height: 30px; padding: 0 12px; font-size: 12px; line-height: 1.4; display: inline-flex; align-items: center; }
.info-chip { background: var(--bg-surface),.92); color: var(--text-primary); border: 1px solid rgba(125,211,252,.14); }
.info-chip--muted { opacity: .72; background: var(--bg-surface),.55); color: #8bb5c7; }
.cause-chip,.mini-btn { cursor: pointer; border: 1px solid rgba(81,163,201,.16); background: var(--bg-surface),.86); color: var(--text-primary); }
.cause-chip.active { background: rgba(34,211,238,.16); border-color: rgba(110,231,249,.3); box-shadow: var(--card-shadow); }
.mini-btn--soft { background: rgba(20,184,166,.14); }
.mini-btn--ghost { background: rgba(244,63,94,.12); }
.effect-box { display: flex; justify-content: space-between; gap: 12px; color: var(--text-primary); }
.effect-box.is-improving { background: rgba(20,184,166,.14); }
.effect-box.is-worsening { background: rgba(244,63,94,.14); }
.effect-box.is-stable { background: rgba(56,189,248,.14); }
.mdt-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.error-panel { background: rgba(127,29,29,.22); border: 1px solid rgba(248,113,113,.26); color: var(--danger-soft); }
.whatif-layout { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 12px; align-items: start; }
.whatif-chart,.whatif-drawer { display: grid; gap: 12px; padding: 12px; border-radius: var(--card-radius); background: var(--bg-surface),.78); border: 1px solid rgba(79,153,191,.12); }
.whatif-axis,.whatif-legend { display: flex; justify-content: space-between; gap: 10px; color: var(--text-secondary); font-size: 11px; }
.whatif-legend span { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
.legend-sample { display: inline-block; width: 28px; height: 0; border-radius: 999px; }
.legend-actual { border-top: 4px solid var(--brand); }
.legend-baseline { border-top: 3px dashed var(--text-secondary); }
.legend-counterfactual { height: 4px; background: repeating-linear-gradient(90deg, var(--brand) 0 8px, transparent 8px 12px); }
.whatif-metric { display: grid; gap: 8px; }
.whatif-track { position: relative; height: 36px; border-radius: var(--card-radius); background: rgba(43,85,108,.26); overflow: hidden; }
.whatif-track i,.whatif-track .band { position: absolute; left: 0; top: 50%; display: block; transform: translateY(-50%); pointer-events: none; }
.actual-line { height: 3px; border-radius: var(--card-radius); background: var(--bg-surface); }
.baseline-line { height: 0; border-top: 2px dashed #15558D; }
.whatif-line { height: 3px; border-radius: var(--card-radius); background: repeating-var(--bg-surface); }
.whatif-line.degraded { border-top-color: var(--text-secondary); filter: grayscale(1); }
.band { height: 18px; border-radius: var(--card-radius); opacity: .22; }
.band80 { background: var(--danger); }
.band95 { background: var(--warning); opacity: .14; }
.whatif-banner { padding: 10px 12px; border-radius: var(--card-radius); background: rgba(245,158,11,.16); color: var(--warning-soft); border: 1px solid rgba(245,158,11,.24); font-size: 12px; line-height: 1.6; }
.whatif-banner.muted { background: rgba(100,116,139,.18); color: var(--text-secondary); border-color: rgba(148,163,184,.24); }
@media (max-width: 900px) { .overview-grid,.timeline-item,.twin-overview-split { grid-template-columns: 1fr; } .timeline-rail { justify-items: start; padding-right: 0; padding-bottom: 8px; } .timeline-time { text-align: left; } .timeline-line { left: 5px; right: auto; top: 32px; bottom: -8px; } }
@media (max-width: 1100px) { .twin-kpis,.loop-grid,.twin-grid,.mdt-grid,.whatif-layout { grid-template-columns: 1fr 1fr; } .twin-card-wide { grid-column: span 2; } }
@media (max-width: 720px) { .twin-kpis,.loop-grid,.twin-grid,.mdt-grid,.whatif-layout { grid-template-columns: 1fr; } .twin-card-wide { grid-column: auto; } }

/* Light mode overrides */
html[data-theme='light'] .twin-sub { color: var(--text-secondary); }
html[data-theme='light'] .twin-refresh { background: rgba(243, 248, 252, 0.96); border-color: rgba(187, 204, 220, 0.72); color: var(--text-secondary); }
html[data-theme='light'] .twin-kpi, html[data-theme='light'] .loop-card, html[data-theme='light'] .twin-card { background: var(--bg-surface), rgba(242,247,252,0.98)); border-color: rgba(187,204,220,0.72); box-shadow: var(--card-shadow); }
html[data-theme='light'] .twin-kpi span, html[data-theme='light'] .loop-label, html[data-theme='light'] .card-sub, html[data-theme='light'] .intervention-meta, html[data-theme='light'] .causal-meta, html[data-theme='light'] .mdt-meta { color: var(--text-secondary); }
html[data-theme='light'] .twin-kpi strong, html[data-theme='light'] .loop-value, html[data-theme='light'] .card-title, html[data-theme='light'] .intervention-title, html[data-theme='light'] .mdt-title { color: var(--text-secondary); }
html[data-theme='light'] .loop-step { background: rgba(59,130,246,0.1); color: var(--brand); }
html[data-theme='light'] .loop-meta { color: var(--text-secondary); }
html[data-theme='light'] .risk-badge.is-medium, html[data-theme='light'] .status-pill.is-pending { background: rgba(59,130,246,.16); color: var(--brand); }
html[data-theme='light'] .risk-badge.is-low, html[data-theme='light'] .status-pill.is-dismissed { background: rgba(16,185,129,.16); color: var(--chart-2); }
html[data-theme='light'] .risk-badge.is-high, html[data-theme='light'] .status-pill.is-in_progress { background: rgba(245,158,11,.16); color: var(--warning); }
html[data-theme='light'] .risk-badge.is-critical, html[data-theme='light'] .status-pill.is-completed { background: rgba(239,68,68,.16); color: var(--danger); }
html[data-theme='light'] .curve-row, html[data-theme='light'] .causal-item, html[data-theme='light'] .mdt-item, html[data-theme='light'] .intervention-item, html[data-theme='light'] .conflict-item { background: rgba(243,248,252,0.96); border-color: rgba(187,204,220,0.72); }
html[data-theme='light'] .curve-top { color: var(--text-secondary); }
html[data-theme='light'] .curve-bar { background: rgba(187,204,220,0.4); }
html[data-theme='light'] .overview-item span, html[data-theme='light'] .overview-item small { color: var(--text-secondary); }
html[data-theme='light'] .overview-item strong { color: var(--text-secondary); }
html[data-theme='light'] .timeline-time { color: var(--text-secondary); }
html[data-theme='light'] .timeline-dot { border-color: rgba(255,255,255,0.8); }
html[data-theme='light'] .timeline-line { background: var(--bg-surface), rgba(59,130,246,0)); }
html[data-theme='light'] .timeline-card-title { color: var(--text-secondary); }
html[data-theme='light'] .timeline-card-sub, html[data-theme='light'] .timeline-card-meta { color: var(--text-secondary); }
html[data-theme='light'] .timeline-source.is-neutral { background: rgba(187,204,220,0.3); color: var(--text-secondary); }
html[data-theme='light'] .timeline-source.is-info { background: rgba(59,130,246,.15); color: var(--brand); }
html[data-theme='light'] .bullet-list { color: var(--text-secondary); }
html[data-theme='light'] .summary-panel, html[data-theme='light'] .empty-panel { background: rgba(243,248,252,0.96); border-color: rgba(187,204,220,0.72); color: var(--text-secondary); }
html[data-theme='light'] .conflict-title { color: var(--warning); }
html[data-theme='light'] .conflict-meta { color: var(--text-secondary); }
html[data-theme='light'] .info-chip { background: var(--bg-surface); border-color: rgba(187,204,220,0.72); color: var(--text-secondary); }
html[data-theme='light'] .info-chip--muted { background: rgba(243,248,252,0.96); color: var(--text-secondary); }
html[data-theme='light'] .cause-chip, html[data-theme='light'] .mini-btn { background: var(--bg-surface); border-color: rgba(187,204,220,0.72); color: var(--text-secondary); }
html[data-theme='light'] .cause-chip.active { background: rgba(239,246,255,0.96); border-color: rgba(59,130,246,0.3); }
html[data-theme='light'] .mini-btn--soft { background: rgba(16,185,129,.14); }
html[data-theme='light'] .mini-btn--ghost { background: rgba(239,68,68,.12); }
html[data-theme='light'] .effect-box { color: var(--text-secondary); }
html[data-theme='light'] .error-panel { background: rgba(254,226,226,0.8); border-color: rgba(239,68,68,.3); color: var(--danger-strong); }

/* === Additional light-mode overrides === */
html[data-theme='light'] .twin-head {
  background: var(--bg-surface), rgba(242,247,252,0.98));
  border-color: rgba(187,204,220,0.72);
}
html[data-theme='light'] .twin-kicker,
html[data-theme='light'] .loop-step { color: var(--brand); }
html[data-theme='light'] .twin-title,
html[data-theme='light'] .twin-kpi strong,
html[data-theme='light'] .loop-value,
html[data-theme='light'] .card-title,
html[data-theme='light'] .overview-item strong,
html[data-theme='light'] .timeline-card-title,
html[data-theme='light'] .effect-box,
html[data-theme='light'] .whatif-banner { color: var(--text-primary); }
html[data-theme='light'] .twin-sub,
html[data-theme='light'] .twin-kpi span,
html[data-theme='light'] .loop-label,
html[data-theme='light'] .loop-meta,
html[data-theme='light'] .overview-item span,
html[data-theme='light'] .timeline-time,
html[data-theme='light'] .timeline-card-sub,
html[data-theme='light'] .whatif-axis,
html[data-theme='light'] .whatif-legend { color: var(--text-secondary); }
html[data-theme='light'] .whatif-chart,
html[data-theme='light'] .whatif-drawer {
  background: rgba(243,248,252,0.96);
  border-color: rgba(187,204,220,0.72);
}
html[data-theme='light'] .whatif-banner { color: var(--warning); }

/* Softer light-mode hierarchy: keep outer cards, remove the boxed-grid feel inside cards. */
html[data-theme='light'] .twin-card,
html[data-theme='light'] .twin-kpi,
html[data-theme='light'] .loop-card {
  background: rgba(255, 253, 248, 0.92);
  border-color: rgba(166, 181, 169, 0.32);
  box-shadow: 0 10px 28px rgba(64, 78, 66, 0.055);
}
html[data-theme='light'] .card-head {
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(166, 181, 169, 0.18);
}
html[data-theme='light'] .summary-panel,
html[data-theme='light'] .empty-panel,
html[data-theme='light'] .curve-row,
html[data-theme='light'] .causal-item,
html[data-theme='light'] .mdt-item,
html[data-theme='light'] .intervention-item,
html[data-theme='light'] .conflict-item,
html[data-theme='light'] .whatif-chart,
html[data-theme='light'] .whatif-drawer {
  background: rgba(248, 249, 244, 0.72);
  border-color: transparent;
  box-shadow: none;
}
html[data-theme='light'] .overview-item {
  padding: 10px 0;
  border-bottom: 1px solid rgba(166, 181, 169, 0.16);
}
html[data-theme='light'] .overview-item:nth-last-child(-n + 2) {
  border-bottom: 0;
}
html[data-theme='light'] .info-chip,
html[data-theme='light'] .cause-chip,
html[data-theme='light'] .mini-btn {
  background: rgba(248, 249, 244, 0.86);
  border-color: rgba(166, 181, 169, 0.26);
}
html[data-theme='light'] .cause-chip.active {
  background: rgba(224, 242, 235, 0.92);
  border-color: rgba(48, 120, 105, 0.32);
  color: var(--brand);
  box-shadow: none;
}
html[data-theme='light'] .risk-badge,
html[data-theme='light'] .status-pill,
html[data-theme='light'] .timeline-source {
  border: 0;
  box-shadow: none;
}
html[data-theme='light'] .risk-badge.is-critical,
html[data-theme='light'] .status-pill.is-completed,
html[data-theme='light'] .timeline-source.is-danger {
  background: #FEE2E2;
  color: #991B1B;
}
html[data-theme='light'] .risk-badge.is-high,
html[data-theme='light'] .status-pill.is-in_progress,
html[data-theme='light'] .timeline-source.is-warning {
  background: #FEF3C7;
  color: #92400E;
}
html[data-theme='light'] .risk-badge.is-medium,
html[data-theme='light'] .status-pill.is-pending,
html[data-theme='light'] .timeline-source.is-info {
  background: #DBEAFE;
  color: #1E3A8A;
}
html[data-theme='light'] .risk-badge.is-low,
html[data-theme='light'] .status-pill.is-dismissed,
html[data-theme='light'] .timeline-source.is-accent,
html[data-theme='light'] .timeline-source.is-neutral {
  background: #DCFCE7;
  color: #166534;
}

/* Warm clinical light theme for the What-if workbench. Scoped here so table/card
   fixes elsewhere do not accidentally recolor labels or headings. */
html[data-theme='light'] .whatif-workbench {
  background: linear-gradient(180deg, rgba(255, 253, 248, 0.98), rgba(248, 250, 244, 0.94));
  border-color: rgba(139, 157, 142, 0.28);
  box-shadow: 0 14px 34px rgba(55, 74, 59, 0.08);
}
html[data-theme='light'] .whatif-workbench .card-title,
html[data-theme='light'] .whatif-workbench .curve-top {
  color: #23382f;
}
html[data-theme='light'] .whatif-workbench .card-sub,
html[data-theme='light'] .whatif-workbench .whatif-axis,
html[data-theme='light'] .whatif-workbench .whatif-legend {
  color: #66766b;
}
html[data-theme='light'] .whatif-workbench .whatif-legend {
  justify-content: flex-start;
  gap: 18px;
  padding: 2px 0 4px;
  color: #4a6156;
  font-size: 12px;
  font-weight: 650;
}
html[data-theme='light'] .whatif-workbench .legend-sample {
  width: 34px;
}
html[data-theme='light'] .whatif-workbench .legend-actual {
  border-top-color: #2f7a68;
  box-shadow: 0 2px 5px rgba(47, 122, 104, 0.18);
}
html[data-theme='light'] .whatif-workbench .legend-baseline {
  border-top-color: #66766b;
}
html[data-theme='light'] .whatif-workbench .legend-counterfactual {
  background: repeating-linear-gradient(90deg, #0f766e 0 9px, transparent 9px 13px);
}
html[data-theme='light'] .whatif-workbench .whatif-chart,
html[data-theme='light'] .whatif-workbench .whatif-drawer {
  background: rgba(255, 254, 250, 0.88);
  border: 1px solid rgba(139, 157, 142, 0.2);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
}
html[data-theme='light'] .whatif-workbench .summary-panel {
  background: #f5f8f2;
  border: 1px solid rgba(139, 157, 142, 0.18);
  color: #31473d;
}
html[data-theme='light'] .whatif-workbench .whatif-banner {
  background: #fff7e8;
  border-color: rgba(180, 122, 36, 0.24);
  border-left: 4px solid #b47a24;
  color: #7a430a;
  box-shadow: 0 8px 18px rgba(120, 80, 28, 0.055);
}
html[data-theme='light'] .whatif-workbench .whatif-banner.muted {
  background: #eef4f0;
  border-color: rgba(139, 157, 142, 0.24);
  border-left-color: #7f9b8b;
  color: #4d6259;
}
html[data-theme='light'] .whatif-workbench .whatif-track {
  height: 38px;
  background: linear-gradient(90deg, #edf3ed, #f7f9f3);
  border: 1px solid rgba(139, 157, 142, 0.2);
  box-shadow: inset 0 1px 2px rgba(64, 78, 66, 0.06);
}
html[data-theme='light'] .whatif-workbench .band80 {
  background: rgba(47, 122, 104, 0.16);
  opacity: 1;
}
html[data-theme='light'] .whatif-workbench .band95 {
  background: rgba(180, 122, 36, 0.12);
  opacity: 1;
}
html[data-theme='light'] .whatif-workbench .actual-line {
  top: 30%;
  min-width: 46px;
  height: 4px;
  background: #2f7a68;
  box-shadow: 0 0 0 1px rgba(47, 122, 104, 0.12), 0 3px 9px rgba(47, 122, 104, 0.16);
}
html[data-theme='light'] .whatif-workbench .baseline-line {
  top: 50%;
  min-width: 46px;
  border-top: 3px dashed #66766b;
}
html[data-theme='light'] .whatif-workbench .whatif-line {
  top: 70%;
  min-width: 46px;
  height: 4px;
  background: repeating-linear-gradient(90deg, #0f766e 0 12px, transparent 12px 17px);
  filter: drop-shadow(0 3px 6px rgba(15, 118, 110, 0.18));
}
html[data-theme='light'] .whatif-workbench .whatif-line.degraded {
  background: repeating-linear-gradient(90deg, #7b8a81 0 12px, transparent 12px 17px);
  filter: none;
}
html[data-theme='light'] .whatif-workbench .cause-chip,
html[data-theme='light'] .whatif-workbench .mini-btn {
  background: #fbfcf7;
  border-color: rgba(139, 157, 142, 0.28);
  color: #3f574c;
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.85);
}
html[data-theme='light'] .whatif-workbench .cause-chip:hover,
html[data-theme='light'] .whatif-workbench .mini-btn:hover {
  background: #f1f8f1;
  border-color: rgba(47, 122, 104, 0.28);
  color: #245f52;
}
html[data-theme='light'] .whatif-workbench .cause-chip.active,
html[data-theme='light'] .whatif-workbench .mini-btn--soft {
  background: #e0f2eb;
  border-color: rgba(29, 111, 99, 0.34);
  color: #1d6f63;
}
html[data-theme='light'] .whatif-workbench .mini-btn:disabled,
html[data-theme='light'] .whatif-workbench .cause-chip:disabled {
  background: #eef2ec;
  border-color: rgba(139, 157, 142, 0.16);
  color: #87978d;
  cursor: not-allowed;
  box-shadow: none;
}
</style>



















