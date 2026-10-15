<template>
  <div class="what-if">
    <!-- 三栏布局：当前状态 | 可调变量 | 模拟结果 -->
    <div class="wi-layout">
      <!-- 左侧：当前状态 -->
      <div class="wi-panel wi-panel--current">
        <h3 class="wi-panel-title">当前状态</h3>
        <div v-if="stateLoading" class="wi-loading">加载中...</div>
        <template v-else>
          <div class="wi-vitals-grid">
            <div v-for="v in currentVitals" :key="v.label" class="wi-vital-item">
              <span class="wi-vital-label">{{ v.label }}</span>
              <span class="wi-vital-value" :class="`wi-vital--${v.tone}`">{{ v.value }}</span>
            </div>
          </div>
          <div class="wi-section">
            <h4>当前风险</h4>
            <div class="wi-risk-display">
              <span class="wi-risk-value" :class="`wi-risk--${currentRiskLevel}`">{{ currentRisk }}%</span>
              <span class="wi-risk-label">{{ currentRiskLabel }}</span>
            </div>
          </div>
          <div v-if="currentTreatments.length" class="wi-section">
            <h4>当前治疗</h4>
            <div class="wi-treatment-list">
              <div v-for="t in currentTreatments" :key="t" class="wi-treatment-item">{{ t }}</div>
            </div>
          </div>
        </template>
      </div>

      <!-- 中间：可调整变量 -->
      <div class="wi-panel wi-panel--controls">
        <h3 class="wi-panel-title">调整变量</h3>
        <div class="wi-controls-grid">
          <div v-for="ctrl in controls" :key="ctrl.key" class="wi-control-item">
            <label class="wi-control-label">
              {{ ctrl.label }}
              <span class="wi-control-value">{{ ctrl.modelValue }}{{ ctrl.unit }}</span>
            </label>
            <input
              type="range"
              :min="ctrl.min"
              :max="ctrl.max"
              :step="ctrl.step"
              v-model.number="ctrl.modelValue"
              class="wi-slider"
            />
            <div class="wi-control-range">
              <span>{{ ctrl.min }}{{ ctrl.unit }}</span>
              <span>{{ ctrl.max }}{{ ctrl.unit }}</span>
            </div>
          </div>
        </div>
        <div class="wi-actions">
          <button class="wi-btn wi-btn--primary" @click="runSimulation" :disabled="simulating">
            {{ simulating ? '模拟中...' : '运行模拟' }}
          </button>
          <button class="wi-btn" @click="resetControls">重置</button>
          <button class="wi-btn" @click="addScenario" :disabled="scenarios.length >= 3">
            + 添加情景
          </button>
        </div>
      </div>

      <!-- 右侧：模拟结果 -->
      <div class="wi-panel wi-panel--result">
        <h3 class="wi-panel-title">模拟结果</h3>
        <div v-if="simulationResult" class="wi-result-content">
          <div class="wi-result-risk">
            <div class="wi-risk-before">
              <span class="wi-risk-label-sm">原始风险</span>
              <span class="wi-risk-num">{{ simulationResult.originalRisk }}%</span>
            </div>
            <span class="wi-risk-arrow">→</span>
            <div class="wi-risk-after">
              <span class="wi-risk-label-sm">模拟后风险</span>
              <span class="wi-risk-num" :class="riskChangeClass">{{ simulationResult.simulatedRisk != null ? simulationResult.simulatedRisk + '%' : '—' }}</span>
            </div>
          </div>
          <div class="wi-risk-diff" :class="riskChangeClass">
            {{ riskDiffText }}
          </div>
          <div v-if="simulationResult.uncertainty" class="wi-uncertainty">
            不确定区间：{{ simulationResult.uncertainty.lower }}% ~ {{ simulationResult.uncertainty.upper }}%
          </div>
          <div v-if="simulationResult.changedFactors?.length" class="wi-section">
            <h4>主要变化因素</h4>
            <div v-for="f in simulationResult.changedFactors" :key="f.name" class="wi-factor-item">
              <span>{{ f.name }}</span>
              <span :class="f.direction > 0 ? 'wi-change-up' : 'wi-change-down'">
                {{ f.direction > 0 ? '↑' : '↓' }}{{ Math.abs(f.impact) }}%
              </span>
            </div>
          </div>
        </div>
        <div v-else class="wi-result-empty">
          调整变量后点击"运行模拟"查看结果
        </div>

        <!-- 情景比较 -->
        <div v-if="scenarios.length > 0" class="wi-scenarios">
          <h4>情景比较</h4>
          <div v-for="(s, idx) in scenarios" :key="idx" class="wi-scenario-item">
            <span class="wi-scenario-name">情景 {{ idx + 1 }}</span>
            <span class="wi-scenario-risk" :class="riskLevelClass(s.risk)">{{ s.risk }}%</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 声明 -->
    <div class="wi-disclaimer">
      ⚠ What-if结果表示模型输入变化后的预测差异，不自动代表真实因果效应。
      模拟结果仅供临床参考，需结合专业知识综合判断。
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useEmbedBridge } from '../../../composables/useEmbedBridge'
import { getAiRiskForecast, postAiWhatIfSimulation } from '../../../api'

const route = useRoute()
const patientId = computed(() => String(route.params.patientId || ''))

const { sendUpdateTitle, sendReportError } = useEmbedBridge({
  moduleKey: 'what-if',
  targetOrigin: window.location.origin,
  onPatientContextChanged: () => loadCurrentState(),
  onRefresh: () => loadCurrentState(),
})

// ── 当前状态（从API加载）────────────────────────────

const stateLoading = ref(false)
const currentVitals = ref<Array<{ label: string; value: string; tone: string }>>([])
const currentRisk = ref(0)
const currentTreatments = ref<string[]>([])
const currentRiskLevel = computed(() => currentRisk.value >= 60 ? 'high' : currentRisk.value >= 40 ? 'medium' : 'low')
const currentRiskLabel = computed(() => currentRisk.value >= 60 ? '高风险' : currentRisk.value >= 40 ? '中风险' : '低风险')

async function loadCurrentState() {
  if (!patientId.value) return
  stateLoading.value = true
  try {
    const res = await getAiRiskForecast(patientId.value)
    const data = res.data || {}

    // 当前风险
    const prob = data.current_probability ?? data.horizon_probabilities?.[0]?.probability ?? 0
    currentRisk.value = Math.round(prob * 100)

    // 体征概览
    const vitals: Array<{ label: string; value: string; tone: string }> = []
    const overview = data.vital_overview || data.latest_vitals || {}
    if (overview.hr != null) vitals.push({ label: 'HR', value: String(overview.hr), tone: overview.hr > 100 || overview.hr < 60 ? 'warning' : 'normal' })
    if (overview.map != null || overview.mbp != null) { const v = overview.map ?? overview.mbp; vitals.push({ label: 'MAP', value: String(v), tone: v < 65 ? 'warning' : 'normal' }) }
    if (overview.spo2 != null) vitals.push({ label: 'SpO₂', value: `${overview.spo2}%`, tone: overview.spo2 < 94 ? 'warning' : 'normal' })
    if (overview.rr != null) vitals.push({ label: 'RR', value: String(overview.rr), tone: overview.rr > 20 || overview.rr < 12 ? 'warning' : 'normal' })
    if (overview.lactate != null) vitals.push({ label: '乳酸', value: String(overview.lactate), tone: overview.lactate > 2 ? 'high' : 'normal' })
    if (overview.creatinine != null) vitals.push({ label: '肌酐', value: String(overview.creatinine), tone: overview.creatinine > 1.5 ? 'high' : 'normal' })
    currentVitals.value = vitals

    // 当前治疗
    currentTreatments.value = data.current_treatments || data.active_interventions || []
  } catch (e: any) {
    sendReportError('LOAD_FAILED', e?.message || '加载当前状态失败')
  } finally {
    stateLoading.value = false
  }
}

// ── 可调变量 ─────────────────────────────────────

const controls = reactive([
  { key: 'map_target', label: 'MAP目标', unit: 'mmHg', min: 55, max: 85, step: 5, modelValue: 65 },
  { key: 'fluid_balance', label: '液体平衡', unit: 'ml/h', min: -200, max: 200, step: 25, modelValue: 0 },
  { key: 'vasopressor', label: '升压药剂量', unit: 'μg/kg/min', min: 0, max: 0.5, step: 0.05, modelValue: 0.15 },
  { key: 'peep', label: 'PEEP', unit: 'cmH₂O', min: 5, max: 20, step: 1, modelValue: 10 },
  { key: 'fio2', label: 'FiO₂', unit: '%', min: 21, max: 100, step: 5, modelValue: 50 },
  { key: 'sedation', label: '镇静水平(RASS)', unit: '', min: -5, max: 0, step: 1, modelValue: -2 },
])

// ── 模拟 ─────────────────────────────────────────

const simulating = ref(false)
const simulationResult = ref<any>(null)
const scenarios = ref<Array<{ risk: number }>>([])

const riskDiff = computed(() => {
  if (!simulationResult.value) return 0
  return simulationResult.value.simulatedRisk - simulationResult.value.originalRisk
})

const riskDiffText = computed(() => {
  const d = riskDiff.value
  if (d === 0) return '风险无变化'
  return d > 0 ? `风险升高 ${d}%` : `风险降低 ${Math.abs(d)}%`
})

const riskChangeClass = computed(() => {
  if (riskDiff.value > 0) return 'wi-change-up'
  if (riskDiff.value < 0) return 'wi-change-down'
  return ''
})

function riskLevelClass(risk: number) {
  if (risk >= 60) return 'wi-risk--high'
  if (risk >= 40) return 'wi-risk--medium'
  return 'wi-risk--low'
}

async function runSimulation() {
  if (!patientId.value) return
  simulating.value = true
  try {
    const interventions: Record<string, number> = {}
    for (const ctrl of controls) {
      interventions[ctrl.key] = ctrl.modelValue
    }
    const res = await postAiWhatIfSimulation(patientId.value, interventions as any)
    const data = res.data || {}

    const origProb = data.original_probability ?? (currentRisk.value / 100)
    const simProb = data.simulated_probability ?? data.new_risk ?? null
    const simResult: any = {
      originalRisk: Math.round(origProb * 100),
      simulatedRisk: simProb != null ? Math.round(simProb * 100) : null,
    }

    // 不确定区间
    if (data.confidence_interval || data.ci) {
      const ci = data.confidence_interval || data.ci
      simResult.uncertainty = {
        lower: Math.round((ci.lower || ci[0] || 0) * 100),
        upper: Math.round((ci.upper || ci[1] || 0) * 100),
      }
    }

    // 变化因素
    const factors = data.risk_factors || data.changed_factors || data.contributors || []
    simResult.changedFactors = factors.slice(0, 5).map((f: any) => ({
      name: f.feature || f.name || '',
      direction: f.direction || (f.weight > 0 ? 1 : -1),
      impact: Math.round(Math.abs(f.impact || f.weight || 0) * 100),
    }))

    simulationResult.value = simResult
  } catch (e: any) {
    sendReportError('SIM_FAILED', e?.message || '模拟失败')
    simulationResult.value = null
  } finally {
    simulating.value = false
  }
}

function resetControls() {
  controls[0]!.modelValue = 65
  controls[1]!.modelValue = 0
  controls[2]!.modelValue = 0.15
  controls[3]!.modelValue = 10
  controls[4]!.modelValue = 50
  controls[5]!.modelValue = -2
  simulationResult.value = null
}

function addScenario() {
  if (simulationResult.value?.simulatedRisk != null) {
    scenarios.value.push({ risk: simulationResult.value.simulatedRisk })
  }
}

onMounted(() => {
  sendUpdateTitle('What-if模拟')
  loadCurrentState()
})

// 直接渲染模式下组件会被复用：切换患者时路由参数变化需手动重载
watch(patientId, (id, prev) => {
  if (id && id !== prev) loadCurrentState()
})
</script>

<style scoped>.what-if { display: flex; flex-direction: column; gap: 16px }
.wi-layout { display: grid; grid-template-columns: 1fr 1.2fr 1fr; gap: 12px }
.wi-panel { background: var(--color-bg-surface, #FFFFFF); border-radius: var(--radius-lg, 10px); padding: 16px; border: 1px solid var(--color-border, #E5E7EB) }
.wi-panel-title { margin: 0 0 14px; font-size: var(--text-body, 13px); font-weight: 600; color: var(--color-text-primary, #111827) }
.wi-loading { text-align: center; padding: 24px; color: var(--color-text-tertiary, #9CA3AF); font-size: var(--text-body, 13px) }
.wi-vitals-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 16px }
.wi-vital-item { text-align: center; padding: 8px; background: var(--color-bg-surface-secondary, #F1F4F8); border-radius: var(--radius-md, 6px) }
.wi-vital-label { display: block; font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF) }
.wi-vital-value  {  font-size: var(--text-section-title, 15px); font-weight: 700; font-family: var(--font-digit, monospace) ; font-variant-numeric: tabular-nums }
.wi-vital--normal { color: var(--color-normal, #12A66A) }
.wi-vital--warning { color: var(--color-warning, #B54708) }
.wi-vital--high { color: var(--color-danger, #D92D20) }
.wi-section { margin-top: 12px }
.wi-section h4 { margin: 0 0 8px; font-size: var(--text-caption, 12px); font-weight: 600; color: var(--color-text-secondary, #4B5563) }
.wi-risk-display { text-align: center; padding: 12px; background: var(--color-bg-surface-secondary, #F1F4F8); border-radius: var(--radius-md, 6px) }
.wi-risk-value  {  font-size: var(--text-metric-key, 26px); font-weight: 700; font-family: var(--font-digit, monospace) ; font-variant-numeric: tabular-nums }
.wi-risk--high { color: var(--color-danger, #D92D20) }
.wi-risk--medium { color: var(--color-warning, #B54708) }
.wi-risk--low { color: var(--color-normal, #12A66A) }
.wi-risk-label { display: block; font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563); margin-top: 4px }
.wi-treatment-list { display: flex; flex-direction: column; gap: 4px }
.wi-treatment-item { font-size: var(--text-caption, 12px); padding: 6px 8px; background: var(--color-bg-surface-secondary, #F1F4F8); border-radius: var(--radius-tag, 4px); color: var(--color-text-secondary, #4B5563) }

/* Controls */ .wi-controls-grid { display: flex; flex-direction: column; gap: 14px; margin-bottom: 16px }
.wi-control-label { display: flex; justify-content: space-between; font-size: var(--text-caption, 12px); font-weight: 500; color: var(--color-text-secondary, #4B5563); margin-bottom: 4px }
.wi-control-value { font-weight: 700; color: var(--color-primary, #2563EB); font-family: var(--font-digit, monospace) }
.wi-slider { width: 100%; height: 4px; appearance: none; background: var(--color-bg-inset, #E9EEF5); border-radius: var(--radius-tag, 4px); outline: none }
.wi-slider::-webkit-slider-thumb { appearance: none; width: 14px; height: 14px; background: var(--color-primary, #2563EB); border-radius: 50%; cursor: pointer }
.wi-control-range { display: flex; justify-content: space-between; font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF); margin-top: 2px }
.wi-actions { display: flex; gap: 8px }
.wi-btn { flex: 1; padding: 8px; border-radius: var(--radius-md, 6px); font-size: var(--text-body, 13px); border: 1px solid var(--color-border, #E5E7EB); background: var(--color-bg-surface, #FFFFFF); cursor: pointer; transition: all 0.15s }
.wi-btn--primary { background: var(--color-primary, #2563EB); color: var(--color-text-inverse, #FFFFFF); border-color: var(--color-primary, #2563EB) }
.wi-btn--primary:hover { background: var(--color-primary-hover, #3B82F6) }
.wi-btn:disabled { opacity: 0.5; cursor: not-allowed }

/* Results */ .wi-result-content { display: flex; flex-direction: column; gap: 12px }
.wi-result-risk { display: flex; align-items: center; justify-content: center; gap: 16px; padding: 16px; background: var(--color-bg-surface-secondary, #F1F4F8); border-radius: var(--radius-md, 6px) }
.wi-risk-before, .wi-risk-after { text-align: center }
.wi-risk-label-sm { display: block; font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF) }
.wi-risk-num  {  font-size: var(--text-page-title, 20px); font-weight: 700; font-family: var(--font-digit, monospace) ; font-variant-numeric: tabular-nums }
.wi-risk-arrow { font-size: var(--text-page-title, 20px); color: var(--color-text-tertiary, #9CA3AF) }
.wi-risk-diff { text-align: center; font-size: var(--text-body, 13px); font-weight: 600 }
.wi-change-up { color: var(--color-danger, #D92D20) }
.wi-change-down { color: var(--color-normal, #12A66A) }
.wi-uncertainty { text-align: center; font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF) }
.wi-factor-item { display: flex; justify-content: space-between; padding: 6px 0; font-size: var(--text-caption, 12px); border-bottom: 1px solid var(--color-divider, #F0F2F5) }
.wi-result-empty { text-align: center; padding: 32px; color: var(--color-text-tertiary, #9CA3AF); font-size: var(--text-body, 13px) }
.wi-scenarios { margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--color-border, #E5E7EB) }
.wi-scenarios h4 { margin: 0 0 8px; font-size: var(--text-caption, 12px); font-weight: 600; color: var(--color-text-secondary, #4B5563) }
.wi-scenario-item { display: flex; justify-content: space-between; padding: 6px 0; font-size: var(--text-caption, 12px) }
.wi-scenario-risk { font-weight: 700; font-family: var(--font-digit, monospace) }
.wi-disclaimer { padding: 10px 16px; background: var(--color-warning-soft-bg, #FFF9D8); border: 1px solid var(--color-warning-soft-border, #FFE58F); border-radius: var(--radius-md, 6px); font-size: var(--text-caption, 12px); color: var(--color-warning, #B54708) }

@media (max-width: 1200px) {.wi-layout { grid-template-columns: 1fr }

}

</style>

