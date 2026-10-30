<template>
  <div class="what-if">
    <div class="wi-disclaimer">
      ⚠ What-if 为基于近期生理数据和简化生理方程的推演，不代表真实因果效应；仅用于讨论方案，执行前需床旁评估。
    </div>

    <div class="wi-layout">
      <!-- 左：当前状态（来自模拟器读取的真实数据） -->
      <div class="wi-panel">
        <h3 class="wi-panel-title">当前状态 <span class="wi-sub">模拟器输入</span></h3>
        <div class="wi-section">
          <h4>当前整体风险</h4>
          <div v-if="riskLoading" class="wi-loading">加载中...</div>
          <div v-else class="wi-risk-display">
            <span class="wi-risk-value" :class="riskTone(currentRisk)">{{ currentRisk != null ? currentRisk + '%' : '—' }}</span>
            <span class="wi-risk-label">{{ riskSourceText }}</span>
          </div>
        </div>
        <div class="wi-section">
          <h4>生理参数（回看 {{ lookbackHours }}h）</h4>
          <div v-if="!baselineState" class="wi-muted">运行任一模拟后显示模拟器实际读取的数值</div>
          <div v-else class="wi-vitals-grid">
            <div v-for="v in stateItems" :key="v.key" class="wi-vital-item">
              <span class="wi-vital-label">{{ v.label }}</span>
              <span class="wi-vital-value" :class="v.tone">{{ v.text }}</span>
            </div>
          </div>
        </div>
        <div v-if="stateFactors.length" class="wi-section">
          <h4>状态因子（决定干预反应幅度）</h4>
          <div v-for="f in stateFactors" :key="f.label" class="wi-factor-item">
            <span>{{ f.label }}</span><span class="wi-mono">{{ f.text }}</span>
          </div>
        </div>
      </div>

      <!-- 中：选择干预 -->
      <div class="wi-panel">
        <h3 class="wi-panel-title">选择干预</h3>
        <div class="wi-option-list">
          <label v-for="opt in OPTIONS" :key="opt.type" class="wi-option" :class="{ 'wi-option--active': selectedType === opt.type }">
            <input type="radio" :value="opt.type" v-model="selectedType" />
            <span class="wi-option-name">{{ opt.label }}</span>
            <span class="wi-option-desc">{{ opt.desc }}</span>
          </label>
        </div>
        <div v-if="selectedOption.param" class="wi-control-item">
          <label class="wi-control-label">
            {{ selectedOption.param.label }}
            <span class="wi-control-value">{{ magnitude }}{{ selectedOption.param.unit }}</span>
          </label>
          <input type="range" class="wi-slider" :min="selectedOption.param.min" :max="selectedOption.param.max"
            :step="selectedOption.param.step" v-model.number="magnitude" />
          <div class="wi-control-range">
            <span>{{ selectedOption.param.min }}{{ selectedOption.param.unit }}</span>
            <span>{{ selectedOption.param.max }}{{ selectedOption.param.unit }}</span>
          </div>
        </div>
        <div class="wi-control-item">
          <label class="wi-control-label">反应曲线时长 <span class="wi-sub">对比表固定为 30 分钟</span></label>
          <select v-model.number="horizon" class="wi-select">
            <option :value="30">30 分钟</option>
            <option :value="45">45 分钟</option>
            <option :value="60">60 分钟</option>
            <option :value="120">120 分钟</option>
          </select>
        </div>
        <div class="wi-actions">
          <button class="wi-btn wi-btn--primary" :disabled="simulating || !patientId" @click="runSimulation">
            {{ simulating ? '模拟中...' : '运行模拟（同时计算不干预基线）' }}
          </button>
        </div>
        <div v-if="errorText" class="wi-error">{{ errorText }}</div>
      </div>

      <!-- 右：结果 -->
      <div class="wi-panel">
        <h3 class="wi-panel-title">模拟结果</h3>
        <div v-if="!result" class="wi-result-empty">选择干预后点击“运行模拟”</div>
        <div v-else class="wi-result-content">
          <div class="wi-result-head">
            <strong>{{ result.intervention_label || selectedOption.label }}</strong>
            <span v-if="result.data_available === false" class="wi-tag wi-tag--warn">数据不足</span>
          </div>
          <div v-if="result.summary" class="wi-summary">{{ result.summary }}</div>
          <div v-if="result.ood_warning?.is_ood" class="wi-error">
            超出模型适用范围：{{ (result.ood_warning.reasons || []).join('；') || '输入偏离训练分布' }}，结果可信度低
          </div>
          <table class="wi-table">
            <thead><tr><th>指标</th><th>当前</th><th>不干预 30′</th><th>干预后 30′</th><th>净效应</th></tr></thead>
            <tbody>
              <tr v-for="row in compareRows" :key="row.key">
                <td>{{ row.label }}</td>
                <td class="wi-mono">{{ row.current }}</td>
                <td class="wi-mono">{{ row.baseline }}</td>
                <td class="wi-mono">{{ row.projected }}</td>
                <td class="wi-mono" :class="row.netTone">{{ row.net }}</td>
              </tr>
            </tbody>
          </table>
          <div class="wi-note">净效应 = 干预后 − 不干预基线（30 分钟），用于剔除病情自然趋势；完整时间过程见反应曲线。</div>

          <div v-if="curveRows.length" class="wi-section">
            <h4>反应曲线</h4>
            <div v-for="c in curveRows" :key="c.key" class="wi-curve">
              <span class="wi-curve-label">{{ c.label }}</span>
              <span class="wi-mono wi-curve-points">{{ c.text }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 推演过程 -->
    <div v-if="result" class="wi-panel">
      <h3 class="wi-panel-title">推演依据与限制</h3>
      <div class="wi-process">
        <div v-if="asList(result.rationale).length" class="wi-section">
          <h4>推演理由</h4>
          <ul><li v-for="(r, i) in asList(result.rationale)" :key="i">{{ r }}</li></ul>
        </div>
        <div v-if="asList(result.model_meta?.equations).length" class="wi-section">
          <h4>使用的方程</h4>
          <ul><li v-for="(r, i) in asList(result.model_meta?.equations)" :key="i" class="wi-mono">{{ r }}</li></ul>
        </div>
        <div v-if="asList(result.assumptions).length" class="wi-section">
          <h4>假设</h4>
          <ul><li v-for="(r, i) in asList(result.assumptions)" :key="i">{{ r }}</li></ul>
        </div>
        <div v-if="asList(result.cautions).length" class="wi-section">
          <h4>注意事项</h4>
          <ul class="wi-cautions"><li v-for="(r, i) in asList(result.cautions)" :key="i">{{ r }}</li></ul>
        </div>
      </div>
    </div>

    <!-- 情景对比：保存真实结果 -->
    <div v-if="history.length" class="wi-panel">
      <h3 class="wi-panel-title">本次会话已运行的情景</h3>
      <table class="wi-table">
        <thead><tr><th>干预</th><th>时长</th><th>MAP 净效应</th><th>SpO₂ 净效应</th><th>乳酸净效应</th><th>适用范围</th></tr></thead>
        <tbody>
          <tr v-for="(h, i) in history" :key="i">
            <td>{{ h.label }}</td><td>30min</td>
            <td class="wi-mono">{{ fmtDelta(h.net.map) }}</td>
            <td class="wi-mono">{{ fmtDelta(h.net.spo2) }}</td>
            <td class="wi-mono">{{ fmtDelta(h.net.lactate, 1) }}</td>
            <td>{{ h.ood ? '超出' : '范围内' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useEmbedBridge } from '../../../composables/useEmbedBridge'
import { getAiRiskForecast, postAiWhatIfSimulation } from '../../../api'

type InterventionType = 'vasopressor_up' | 'fluid_bolus' | 'diuresis' | 'fio2_up' | 'peep_up'
interface ParamDef { field: 'dose_delta_pct' | 'fluid_bolus_ml' | 'diuretic_intensity' | 'fio2_delta' | 'peep_delta'; label: string; unit: string; min: number; max: number; step: number; def: number }
interface OptionDef { type: InterventionType; label: string; desc: string; param: ParamDef }

const OPTIONS: OptionDef[] = [
  { type: 'vasopressor_up', label: '升压药上调', desc: '按当前剂量百分比上调', param: { field: 'dose_delta_pct', label: '上调幅度', unit: '%', min: 10, max: 100, step: 10, def: 20 } },
  { type: 'fluid_bolus', label: '液体冲击', desc: '晶体液快速输注', param: { field: 'fluid_bolus_ml', label: '输液量', unit: 'ml', min: 100, max: 1000, step: 50, def: 250 } },
  { type: 'diuresis', label: '利尿', desc: '袢利尿剂强度系数', param: { field: 'diuretic_intensity', label: '强度', unit: '×', min: 0.5, max: 2, step: 0.25, def: 1 } },
  { type: 'fio2_up', label: 'FiO₂ 上调', desc: '在当前 FiO₂ 基础上增加', param: { field: 'fio2_delta', label: '增加', unit: '%', min: 5, max: 40, step: 5, def: 10 } },
  { type: 'peep_up', label: 'PEEP 上调', desc: '在当前 PEEP 基础上增加', param: { field: 'peep_delta', label: '增加', unit: 'cmH₂O', min: 1, max: 6, step: 1, def: 2 } },
]

const route = useRoute()
const patientId = computed(() => String(route.params.patientId || ''))

const { sendUpdateTitle, sendReportError } = useEmbedBridge({
  moduleKey: 'what-if',
  targetOrigin: window.location.origin,
  onPatientContextChanged: () => resetAll(),
  onRefresh: () => resetAll(),
})

// ── 当前风险 ──
const riskLoading = ref(false)
const riskData = ref<any>(null)
function toPercent(value: unknown, scale: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const n = Number(value)
  if (!Number.isFinite(n)) return null
  if (scale === 'probability_0_1') return n >= 0 && n <= 1 ? Math.round(n * 100) : null
  if (scale === 'percent_0_100') return n >= 0 && n <= 100 ? Math.round(n) : null
  return null
}
const currentRisk = computed(() => toPercent(riskData.value?.current_probability, riskData.value?.probability_scale))
const riskSourceText = computed(() => {
  const d = riskData.value
  if (!d) return '风险数据不可用'
  if (currentRisk.value == null) return '当前无法计算（数据不足或量纲缺失）'
  return d.is_model_prediction ? '模型预测' : d.is_rule_estimate ? '规则估算（非模型）' : '来源未知'
})
function riskTone(v: number | null) {
  if (v == null) return ''
  return v >= 60 ? 'wi-risk--high' : v >= 40 ? 'wi-risk--medium' : 'wi-risk--low'
}
async function loadRisk() {
  if (!patientId.value) return
  riskLoading.value = true
  try {
    const res = await getAiRiskForecast(patientId.value)
    riskData.value = res.data || null
  } catch {
    riskData.value = null
  } finally {
    riskLoading.value = false
  }
}

// ── 干预选择 ──
const selectedType = ref<InterventionType>('vasopressor_up')
const selectedOption = computed(() => OPTIONS.find(o => o.type === selectedType.value) || OPTIONS[0]!)
const magnitude = ref<number>(OPTIONS[0]!.param.def)
watch(selectedType, () => { magnitude.value = selectedOption.value.param.def })
const horizon = ref(60)

// ── 模拟 ──
const simulating = ref(false)
const errorText = ref('')
const result = ref<any>(null)
const baseline = ref<any>(null)
const history = ref<Array<{ label: string; horizon: number; net: Record<string, number | null>; ood: boolean }>>([])

const baselineState = computed(() => result.value?.current_state || baseline.value?.current_state || null)
const lookbackHours = computed(() => result.value?.model_meta?.lookback_hours ?? baseline.value?.model_meta?.lookback_hours ?? '—')

function num(v: unknown): number | null {
  if (v === null || v === undefined || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}
function fmt(v: unknown, digits = 0): string {
  const n = num(v)
  return n == null ? '—' : n.toFixed(digits)
}
function fmtDelta(v: unknown, digits = 0): string {
  const n = num(v)
  if (n == null) return '—'
  const s = n.toFixed(digits)
  return n > 0 ? `+${s}` : s
}
function asList(v: unknown): string[] {
  if (!v) return []
  if (Array.isArray(v)) return v.map(x => (typeof x === 'string' ? x : x?.text || x?.description || JSON.stringify(x))).filter(Boolean)
  if (typeof v === 'string') return [v]
  if (typeof v === 'object') return Object.entries(v as Record<string, unknown>).map(([k, x]) => `${k}: ${x}`)
  return []
}

const STATE_DEFS: Array<{ key: string; label: string; unit: string; digits: number; abnormal: (n: number) => boolean }> = [
  { key: 'map', label: 'MAP', unit: 'mmHg', digits: 0, abnormal: n => n < 65 || n > 110 },
  { key: 'hr', label: 'HR', unit: '次/分', digits: 0, abnormal: n => n < 50 || n > 120 },
  { key: 'spo2', label: 'SpO₂', unit: '%', digits: 0, abnormal: n => n < 92 },
  { key: 'lactate', label: '乳酸', unit: 'mmol/L', digits: 1, abnormal: n => n >= 2 },
  { key: 'fio2', label: 'FiO₂', unit: '%', digits: 0, abnormal: n => n >= 60 },
  { key: 'peep', label: 'PEEP', unit: 'cmH₂O', digits: 0, abnormal: n => n >= 12 },
  { key: 'urine_ml_kg_h_6h', label: '尿量(6h)', unit: 'ml/kg/h', digits: 2, abnormal: n => n < 0.5 },
  { key: 'vaso_dose_ug_kg_min', label: 'NE当量', unit: 'μg/kg/min', digits: 2, abnormal: n => n >= 0.3 },
]
const stateItems = computed(() => {
  const s = baselineState.value || {}
  return STATE_DEFS.map(d => {
    const n = num(s[d.key])
    return {
      key: d.key, label: d.label,
      text: n == null ? '无数据' : `${n.toFixed(d.digits)} ${d.unit}`,
      tone: n == null ? 'wi-muted' : d.abnormal(n) ? 'wi-vital--warning' : 'wi-vital--normal',
    }
  })
})

const FACTOR_LABELS: Record<string, string> = {
  vasoplegia_burden: '血管麻痹负荷', preload_responsiveness: '容量反应性', recruitability: '肺可复张性', sofa_score: 'SOFA',
}
const stateFactors = computed(() => {
  const f = result.value?.state_factors || baseline.value?.state_factors || {}
  return Object.entries(FACTOR_LABELS)
    .filter(([k]) => f[k] != null)
    .map(([k, label]) => ({ label, text: k === 'sofa_score' ? fmt(f[k]) : fmt(f[k], 2) }))
})

// 投射值：后端 projected_state 固定为 30 分钟终点
function projected(rec: any, key: string): number | null {
  if (!rec) return null
  return num(rec.projected_state?.[`${key}_30m`] ?? rec.projected_state?.[key])
}
const METRICS: Array<{ key: string; label: string; digits: number; goodUp: boolean }> = [
  { key: 'map', label: 'MAP (mmHg)', digits: 0, goodUp: true },
  { key: 'hr', label: 'HR (次/分)', digits: 0, goodUp: false },
  { key: 'spo2', label: 'SpO₂ (%)', digits: 0, goodUp: true },
  { key: 'lactate', label: '乳酸 (mmol/L)', digits: 1, goodUp: false },
]
function netEffect(key: string): number | null {
  const p = projected(result.value, key)
  const b = projected(baseline.value, key)
  if (p == null) return null
  if (b == null) return num(result.value?.delta?.[`${key}_30m`])
  return p - b
}
const compareRows = computed(() => METRICS
  .filter(m => projected(result.value, m.key) != null || num(baselineState.value?.[m.key]) != null)
  .map(m => {
    const net = netEffect(m.key)
    const better = net == null || Math.abs(net) < 1e-9 ? null : (net > 0) === m.goodUp
    return {
      key: m.key, label: m.label,
      current: fmt(baselineState.value?.[m.key], m.digits),
      baseline: fmt(projected(baseline.value, m.key), m.digits),
      projected: fmt(projected(result.value, m.key), m.digits),
      net: fmtDelta(net, m.digits),
      netTone: better == null ? '' : better ? 'wi-change-down' : 'wi-change-up',
    }
  }))

const curveRows = computed(() => {
  const curves = result.value?.response_curve || {}
  const labels: Record<string, string> = { map: 'MAP', spo2: 'SpO₂', lactate: '乳酸' }
  return Object.keys(labels)
    .filter(k => Array.isArray(curves[k]) && curves[k].length)
    .map(k => ({
      key: k, label: labels[k]!,
      text: (curves[k] as any[]).map(p => `${p.minute}′ ${fmt(p.value, k === 'lactate' ? 1 : 0)}`).join(' → '),
    }))
})

async function simulate(payload: any) {
  const res = await postAiWhatIfSimulation(patientId.value, payload)
  const data = res.data || {}
  if (!data.simulation) throw new Error(data.error || data.message || '模拟器未返回结果')
  return data.simulation
}

async function runSimulation() {
  if (!patientId.value) return
  simulating.value = true
  errorText.value = ''
  const opt = selectedOption.value
  try {
    const [base, sim] = await Promise.all([
      simulate({ intervention_type: 'current_baseline', intervention_label: '维持当前治疗', horizon_minutes: horizon.value }),
      simulate({ intervention_type: opt.type, intervention_label: `${opt.label} ${magnitude.value}${opt.param.unit}`, horizon_minutes: horizon.value, [opt.param.field]: magnitude.value }),
    ])
    baseline.value = base
    result.value = sim
    history.value.unshift({
      label: sim.intervention_label || opt.label,
      horizon: horizon.value,
      net: { map: netEffect('map'), spo2: netEffect('spo2'), lactate: netEffect('lactate') },
      ood: !!sim.ood_warning?.is_ood,
    })
    if (history.value.length > 6) history.value.length = 6
  } catch (e: any) {
    errorText.value = e?.message || '模拟失败'
    sendReportError('SIM_FAILED', errorText.value)
  } finally {
    simulating.value = false
  }
}

function resetAll() {
  result.value = null
  baseline.value = null
  history.value = []
  errorText.value = ''
  loadRisk()
}

onMounted(() => {
  sendUpdateTitle('What-if模拟')
  loadRisk()
})

watch(patientId, (id, prev) => {
  if (id && id !== prev) resetAll()
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
.wi-control-value { font-weight: 700; color: var(--color-primary, #2F6FED); font-family: var(--font-digit, monospace) }
.wi-slider { width: 100%; height: 4px; appearance: none; background: var(--color-bg-inset, #E9EEF5); border-radius: var(--radius-tag, 4px); outline: none }
.wi-slider::-webkit-slider-thumb { appearance: none; width: 14px; height: 14px; background: var(--color-primary, #2F6FED); border-radius: 50%; cursor: pointer }
.wi-control-range { display: flex; justify-content: space-between; font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF); margin-top: 2px }
.wi-actions { display: flex; gap: 8px }
.wi-btn { flex: 1; padding: 8px; border-radius: var(--radius-md, 6px); font-size: var(--text-body, 13px); border: 1px solid var(--color-border, #E5E7EB); background: var(--color-bg-surface, #FFFFFF); cursor: pointer; transition: all 0.15s }
.wi-btn--primary { background: var(--color-primary, #2F6FED); color: var(--color-text-inverse, #FFFFFF); border-color: var(--color-primary, #2F6FED) }
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


.wi-sub { font-weight: 400; font-size: 12px; color: var(--color-text-tertiary, #9CA3AF); margin-left: 6px }
.wi-muted { color: var(--color-text-tertiary, #9CA3AF); font-size: 12px }
.wi-mono { font-family: var(--font-digit, monospace); font-variant-numeric: tabular-nums }
.wi-option-list { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px }
.wi-option { display: grid; grid-template-columns: auto 1fr; column-gap: 8px; padding: 8px; border: 1px solid var(--color-border, #E5E7EB); border-radius: 6px; cursor: pointer; font-size: 13px }
.wi-option input { grid-row: span 2 }
.wi-option-desc { font-size: 12px; color: var(--color-text-tertiary, #9CA3AF) }
.wi-option--active { border-color: var(--color-primary, #2F6FED); background: var(--color-primary-soft-bg, #E8F0FE) }
.wi-control-item { margin-bottom: 12px }
.wi-select { width: 100%; padding: 6px; border: 1px solid var(--color-border, #E5E7EB); border-radius: 6px; font-size: 13px }
.wi-error { margin-top: 8px; padding: 8px; font-size: 12px; color: var(--color-danger, #D92D20); background: var(--color-danger-soft-bg, #FEF3F2); border-radius: 6px }
.wi-result-head { display: flex; gap: 8px; align-items: center; font-size: 13px }
.wi-tag { font-size: 11px; padding: 1px 6px; border-radius: 4px }
.wi-tag--warn { background: var(--color-warning-soft-bg, #FFF9D8); color: var(--color-warning, #B54708) }
.wi-summary { font-size: 13px; color: var(--color-text-secondary, #4B5563); line-height: 1.5 }
.wi-table { width: 100%; border-collapse: collapse; font-size: 12px }
.wi-table th, .wi-table td { padding: 5px 6px; border-bottom: 1px solid var(--color-divider, #F0F2F5); text-align: left }
.wi-table th { color: var(--color-text-tertiary, #9CA3AF); font-weight: 500 }
.wi-note { font-size: 11px; color: var(--color-text-tertiary, #9CA3AF) }
.wi-curve { display: flex; gap: 8px; font-size: 12px; padding: 3px 0 }
.wi-curve-label { min-width: 40px; color: var(--color-text-secondary, #4B5563) }
.wi-curve-points { word-break: break-all }
.wi-process { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px }
.wi-process ul { margin: 0; padding-left: 18px; font-size: 12px; line-height: 1.6; color: var(--color-text-secondary, #4B5563) }
.wi-cautions li { color: var(--color-warning, #B54708) }
</style>

