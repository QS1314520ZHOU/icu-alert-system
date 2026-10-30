<template>
  <div class="saki-analysis">
    <div class="analysis-scope">
      <span class="scope-label">分析人群</span>
      <a-select v-model:value="cohortId" style="width: 240px" size="small">
        <a-select-option value="">S-AKI 病例库全部病例</a-select-option>
        <a-select-option v-for="c in cohorts" :key="c.cohort_id" :value="c.cohort_id">{{ c.name }}（{{ c.patient_count ?? '-' }} 例）</a-select-option>
      </a-select>
      <span class="scope-label">结局</span>
      <a-select v-model:value="outcome" style="width: 150px" size="small">
        <a-select-option value="icu_mortality">ICU 死亡</a-select-option>
        <a-select-option value="mortality_28d">28 天死亡</a-select-option>
        <a-select-option value="hospital_mortality">院内死亡</a-select-option>
      </a-select>
      <span class="scope-hint">切换人群或结局后需重新运行</span>
    </div>
    <a-tabs v-model:activeKey="activeTab">
      <a-tab-pane key="table1" tab="基线特征表 (Table 1)">
        <div class="analysis-form">
          <a-button type="primary" @click="runAnalysis('table1')" :loading="loading">生成基线特征表</a-button>
          <span class="analysis-hint">按所选结局分组（存活 vs 死亡）；纳入年龄、性别、SOFA、APACHE II、乳酸、肌酐、机械通气、血管活性药、CRRT、ICU 住院天数</span>
        </div>
        <div v-if="table1Data?.error" class="result-panel error">{{ table1Data.error }}</div>
        <div v-else-if="table1Data" class="result-panel">
          <div class="result-title">{{ table1Data.title || '基线特征表' }}<span v-if="table1Data.n_total != null">（n={{ table1Data.n_total }}）</span></div>
          <table v-if="(table1Data.rows || []).length" class="stat-table">
            <thead><tr><th>变量</th><th v-for="g in table1Data.groups || []" :key="g">{{ t1GroupLabel(g) }}</th><th>P 值</th></tr></thead>
            <tbody>
              <tr v-for="(row, i) in table1Data.rows" :key="i">
                <td>{{ row.variable }}</td>
                <td v-for="(v, j) in row.values || []" :key="j">{{ v }}</td>
                <td :class="{ 'p-sig': row.significant }">{{ row.p_display ?? '—' }}</td>
              </tr>
            </tbody>
          </table>
          <a-empty v-else description="无可用数据" />
          <p v-if="table1Data.footnote" class="result-foot">{{ table1Data.footnote }}</p>
        </div>
        <a-empty v-else description="点击“生成基线特征表”，按当前 S-AKI 病例库计算" />
      </a-tab-pane>
      <a-tab-pane key="km" tab="生存分析 (KM)">
        <div class="analysis-form">
          <span class="scope-label">分组</span>
          <a-select v-model:value="kmGroup" style="width: 150px" size="small">
            <a-select-option v-for="g in GROUP_OPTIONS" :key="g.value" :value="g.value">{{ g.label }}</a-select-option>
          </a-select>
          <a-button type="primary" @click="runAnalysis('km')" :loading="loading">运行 KM 分析</a-button>
          <span class="analysis-hint">时间：ICU 住院天数（最长 28 天）；事件：所选结局</span>
        </div>
        <div v-if="kmData?.error" class="result-panel error">{{ kmData.error }}</div>
        <div v-else-if="kmData && !kmCurves.length" class="result-panel warn">{{ reasonText(kmData.reason) || '无可绘制的生存曲线' }}</div>
        <div v-else-if="kmData" class="result-panel">
          <div class="result-head">
            <span class="result-title">Kaplan-Meier 生存曲线</span>
            <span class="metric">n={{ kmData.n_total }}</span>
            <span class="metric">事件 {{ kmData.n_events }}</span>
            <span v-if="kmCurves.length > 1" :class="['metric', { 'p-sig': (kmData.kaplan_meier?.log_rank_p ?? 1) < 0.05 }]">Log-rank P = {{ kmData.kaplan_meier?.log_rank_p_display ?? '—' }}</span>
            <span v-if="kmHr" class="metric">HR {{ fmt(kmHr.hr) }}（{{ fmt(kmHr.ci_lower) }}–{{ fmt(kmHr.ci_upper) }}）</span>
          </div>
          <v-chart :option="kmOption" style="height: 340px" autoresize />
          <table class="stat-table">
            <thead><tr><th>分组</th><th>例数</th><th>事件</th><th>中位生存（天）</th></tr></thead>
            <tbody>
              <tr v-for="c in kmCurves" :key="c.key"><td>{{ c.label }}</td><td>{{ c.n }}</td><td>{{ c.events }}</td><td>{{ c.median == null ? '未达到' : fmt(c.median, 1) }}</td></tr>
            </tbody>
          </table>
        </div>
        <a-empty v-else description="选择分组后点击“运行 KM 分析”" />
      </a-tab-pane>

      <a-tab-pane v-for="m in MODEL_TABS" :key="m.key" :tab="m.tab">
        <div class="analysis-form">
          <a-button type="primary" @click="runAnalysis(m.key)" :loading="loading">运行 {{ m.short }}</a-button>
          <span class="analysis-hint">候选变量：{{ DEFAULT_PREDICTORS.map(varLabel).join('、') }}；单因素 P&lt;0.1 进入多因素</span>
        </div>
        <template v-if="modelData[m.key]">
          <div v-if="modelData[m.key].error" class="result-panel error">{{ modelData[m.key].error }}</div>
          <div v-else-if="!(modelData[m.key].univariate || []).length" class="result-panel warn">{{ reasonText(modelData[m.key].reason) || '模型未能拟合' }}</div>
          <div v-else class="result-panel">
            <div class="result-head">
              <span class="result-title">{{ m.title }}（结局：{{ OUTCOME_LABELS[outcome] || outcome }}）</span>
              <span class="metric">n={{ modelData[m.key].n_total }}</span>
              <span v-if="modelData[m.key].outcome_positive != null" class="metric">事件 {{ modelData[m.key].outcome_positive }}</span>
              <span v-for="mt in metricChips(modelData[m.key].model_metrics)" :key="mt" class="metric">{{ mt }}</span>
            </div>
            <div v-if="!(modelData[m.key].multivariate || []).length" class="result-note">无变量满足单因素 P&lt;0.1，未建立多因素模型；下表仅为单因素结果。</div>
            <v-chart v-if="(modelData[m.key].multivariate || []).length" :option="forestOption(modelData[m.key].multivariate, m.effect)" :style="{ height: 60 + modelData[m.key].multivariate.length * 34 + 'px' }" autoresize />
            <table class="stat-table">
              <thead><tr><th>变量</th><th>单因素 {{ m.effect }} (95% CI)</th><th>P</th><th>多因素 {{ m.effect }} (95% CI)</th><th>P</th></tr></thead>
              <tbody>
                <tr v-for="row in mergedRows(modelData[m.key])" :key="row.variable">
                  <td>{{ varLabel(row.variable) }}</td>
                  <td>{{ effectText(row.uni) }}</td>
                  <td :class="{ 'p-sig': (row.uni?.p ?? 1) < 0.05 }">{{ row.uni?.p_display ?? '—' }}</td>
                  <td>{{ row.multi ? effectText(row.multi) : '未纳入' }}</td>
                  <td :class="{ 'p-sig': (row.multi?.p ?? 1) < 0.05 }">{{ row.multi?.p_display ?? '—' }}</td>
                </tr>
              </tbody>
            </table>
            <p class="result-foot">{{ m.foot }}</p>
          </div>
        </template>
        <a-empty v-else :description="`点击“运行 ${m.short}”`" />
      </a-tab-pane>

      <a-tab-pane key="roc" tab="ROC 分析">
        <div class="analysis-form">
          <a-button type="primary" @click="runAnalysis('roc')" :loading="loading">运行 ROC</a-button>
          <span class="analysis-hint">评估 {{ DEFAULT_ROC_SCORES.map(varLabel).join('、') }} 对所选结局的区分度</span>
        </div>
        <div v-if="rocData?.error" class="result-panel error">{{ rocData.error }}</div>
        <div v-else-if="rocData && !rocRows.length" class="result-panel warn">{{ reasonText(rocData.reason) || '无可绘制的 ROC 曲线' }}</div>
        <div v-else-if="rocData" class="result-panel">
          <div class="result-head">
            <span class="result-title">ROC 曲线</span>
            <span class="metric">n={{ rocData.n_total }}</span>
            <span class="metric">事件 {{ rocData.outcome_positive }}</span>
          </div>
          <v-chart :option="rocOption" style="height: 360px" autoresize />
          <table class="stat-table">
            <thead><tr><th>评分</th><th>AUC (95% CI)</th><th>最佳截断值</th><th>敏感度</th><th>特异度</th><th>n</th></tr></thead>
            <tbody>
              <tr v-for="r in rocRows" :key="r.key">
                <td>{{ r.label }}</td><td><b>{{ fmt(r.auc, 3) }}</b>（{{ fmt(r.ci_lower, 3) }}–{{ fmt(r.ci_upper, 3) }}）</td>
                <td>{{ fmt(r.optimal_cutoff, 1) }}</td><td>{{ pct(r.sensitivity_at_cutoff) }}</td><td>{{ pct(r.specificity_at_cutoff) }}</td><td>{{ r.n }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="Object.keys(rocData.delong_test || {}).length" class="result-note">
            AUC 两两比较（bootstrap）：
            <span v-for="(v, k) in rocData.delong_test" :key="k" class="cmp">{{ pairLabel(String(k)) }} P={{ v.p_display }}</span>
          </div>
          <p class="result-foot">最佳截断值按 Youden 指数；AUC 置信区间为 bootstrap 估计。</p>
        </div>
        <a-empty v-else description="点击“运行 ROC”" />
      </a-tab-pane>

      <a-tab-pane key="outcomes" tab="住院结局">
        <div class="analysis-form">
          <a-button type="primary" @click="runAnalysis('outcomes')" :loading="loading">查看结局</a-button>
        </div>
        <div v-if="outcomesData?.error" class="result-panel error">{{ outcomesData.error }}</div>
        <div v-else-if="outcomesData" class="result-panel">
          <div class="tiles">
            <div class="tile"><span>病例总数</span><b>{{ outcomesData.total ?? 0 }}</b></div>
            <div class="tile"><span>S-AKI 阳性</span><b>{{ outcomesData.saki_positive ?? 0 }}</b><em v-if="outcomesData.total">{{ pct((outcomesData.saki_positive || 0) / outcomesData.total) }}</em></div>
            <div class="tile"><span>AKI 3 期占比</span><b>{{ pct(outcomesData.severe_aki_rate) }}</b></div>
          </div>
          <table v-if="outcomesData.stage_distribution" class="stat-table">
            <thead><tr><th>KDIGO 分期</th><th v-for="(_v, k) in outcomesData.stage_distribution" :key="k">{{ k === '0' ? '无 AKI' : `${k} 期` }}</th></tr></thead>
            <tbody><tr><td>例数</td><td v-for="(v, k) in outcomesData.stage_distribution" :key="k">{{ v }}</td></tr></tbody>
          </table>
        </div>
        <a-empty v-else description="点击“查看结局”" />
      </a-tab-pane>
    </a-tabs>
    <div class="disclaimer">统计分析结果基于观察性数据，仅提示关联性，不可作为因果推断依据。</div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { use } from 'echarts/core'
import { LineChart, ScatterChart, CustomChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, MarkLineComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import { runTable1, runKM, runLogistic, runCox, runROC, runOutcomes, getSakiCohorts } from '../../api/saki'

use([CanvasRenderer, LineChart, ScatterChart, CustomChart, GridComponent, TooltipComponent, LegendComponent, MarkLineComponent])

const VAR_LABELS: Record<string, string> = {
  age: '年龄', sex: '性别', sofa_admission: '入科 SOFA', apache2: 'APACHE II', lactate_admission: '入科乳酸',
  creatinine_admission: '入科肌酐', mechanical_ventilation: '机械通气', vasopressor: '血管活性药', crrt: 'CRRT',
}
const DEFAULT_PREDICTORS = ['age', 'sofa_admission', 'apache2', 'lactate_admission', 'creatinine_admission', 'mechanical_ventilation', 'vasopressor']
const DEFAULT_ROC_SCORES = ['sofa_admission', 'apache2', 'lactate_admission']
const GROUP_OPTIONS = [
  { value: '', label: '不分组' }, { value: 'vasopressor', label: '血管活性药' },
  { value: 'mechanical_ventilation', label: '机械通气' }, { value: 'crrt', label: 'CRRT' }, { value: 'sex', label: '性别' },
]
const GROUP_VALUE_LABELS: Record<string, Record<string, string>> = {
  vasopressor: { '0': '未用血管活性药', '1': '使用血管活性药' },
  mechanical_ventilation: { '0': '无机械通气', '1': '机械通气' },
  crrt: { '0': '无 CRRT', '1': 'CRRT' },
  sex: { M: '男', F: '女' },
}
const MODEL_TABS = [
  { key: 'logistic', tab: 'Logistic 回归', short: 'Logistic', title: 'Logistic 回归', effect: 'OR', foot: 'OR>1 表示该因素与结局风险升高相关；连续变量 OR 为每增加 1 个单位的变化。' },
  { key: 'cox', tab: 'Cox 回归', short: 'Cox', title: 'Cox 比例风险回归', effect: 'HR', foot: 'HR>1 表示风险升高；未检验比例风险假设，解读时需谨慎。' },
] as const
const REASONS: Record<string, string> = {
  no_valid_predictors: '没有可用的预测变量（字段在数据中不存在）',
  outcome_single_class: '结局只有一类（例如全部存活），无法建模',
  no_model_fit: '模型未能拟合：样本量或事件数不足，或服务器未安装 statsmodels / lifelines（见 requirements.analytics.txt）',
  no_valid_time_event_data: '没有有效的时间/结局数据',
  no_valid_predictor_pairs: '评分与结局没有有效配对数据',
  empty_cohort: '所选人群为空',
}

const activeTab = ref('table1')
const loading = ref(false)
const cohorts = ref<any[]>([])
const cohortId = ref('')
const outcome = ref('icu_mortality')
const OUTCOME_LABELS: Record<string, string> = { icu_mortality: 'ICU 死亡', mortality_28d: '28 天死亡', hospital_mortality: '院内死亡' }
const kmGroup = ref('vasopressor')
const table1Data = ref<any>(null)
const kmData = ref<any>(null)
const modelData = reactive<Record<string, any>>({ logistic: null, cox: null })
const rocData = ref<any>(null)
const outcomesData = ref<any>(null)

function t1GroupLabel(g: string) { return String(g).replace(/^0 \(/, '存活 (').replace(/^1 \(/, '死亡 (') }
function varLabel(v: string) { return VAR_LABELS[v] || v }
function fmt(v: any, d = 2) { const n = Number(v); return v == null || !Number.isFinite(n) ? '—' : n.toFixed(d) }
function pct(v: any) { const n = Number(v); return v == null || !Number.isFinite(n) ? '—' : `${(n * 100).toFixed(1)}%` }
function reasonText(r: any) { return r && r !== 'ok' ? (REASONS[String(r)] || String(r)) : '' }
function effectText(r: any) { return r ? `${fmt(r.estimate)}（${fmt(r.ci_lower)}–${fmt(r.ci_upper)}）` : '—' }
function pairLabel(k: string) { return k.split(' vs ').map(varLabel).join(' vs ') }
function metricChips(m: any) {
  if (!m) return []
  const out: string[] = []
  if (m.c_index != null) out.push(`C-index ${fmt(m.c_index, 3)}`)
  if (m.auc != null) out.push(`AUC ${fmt(m.auc, 3)}`)
  if (m.pseudo_r2 != null) out.push(`伪 R² ${fmt(m.pseudo_r2, 3)}`)
  if (m.hosmer_lemeshow_p != null) out.push(`H-L 检验 P=${fmt(m.hosmer_lemeshow_p, 3)}`)
  if (m.aic != null) out.push(`AIC ${fmt(m.aic, 1)}`)
  return out
}
function mergedRows(d: any) {
  const multi = new Map((d?.multivariate || []).map((r: any) => [r.variable, r]))
  return (d?.univariate || []).map((u: any) => ({ variable: u.variable, uni: u, multi: multi.get(u.variable) as any }))
}

const kmCurves = computed(() => {
  const curves = kmData.value?.kaplan_meier?.curves || {}
  const med = kmData.value?.kaplan_meier?.median_survival || {}
  const labels = GROUP_VALUE_LABELS[kmData.value?.__group || ''] || {}
  return Object.entries(curves).map(([key, c]: [string, any]) => ({ key, label: labels[key] || (key === 'all' || key === '全部' ? '全部' : key), ...c, median: med[key] }))
})
const kmHr = computed(() => kmData.value?.cox_regression || null)
const PALETTE = ['#5392FF', '#E8901C', '#2F7D55', '#B91C1C', '#7C3AED']
const kmOption = computed(() => ({
  color: PALETTE,
  tooltip: { trigger: 'axis', valueFormatter: (v: any) => pct(v) },
  legend: { top: 0 },
  grid: { left: 50, right: 20, top: 34, bottom: 40 },
  xAxis: { type: 'value', name: 'ICU 住院天数', min: 0, max: 28, nameLocation: 'middle', nameGap: 24 },
  yAxis: { type: 'value', name: '生存概率', min: 0, max: 1, axisLabel: { formatter: (v: number) => `${Math.round(v * 100)}%` } },
  series: kmCurves.value.map((c: any) => ({
    name: `${c.label}（n=${c.n}）`, type: 'line', step: 'end', symbol: 'none', lineStyle: { width: 2 },
    data: (c.timeline || []).map((t: number, i: number) => [t, c.survival?.[i]]),
  })),
}))
const rocRows = computed(() => Object.entries(rocData.value?.curves || {}).map(([key, c]: [string, any]) => ({ key, label: varLabel(key), ...c })).sort((a: any, b: any) => (b.auc || 0) - (a.auc || 0)))
const rocOption = computed(() => ({
  color: PALETTE,
  tooltip: { trigger: 'item', formatter: (p: any) => `${p.seriesName}<br/>1-特异度 ${fmt(p.value?.[0])}，敏感度 ${fmt(p.value?.[1])}` },
  legend: { top: 0, data: rocRows.value.map((r: any) => `${r.label} AUC ${fmt(r.auc, 3)}`) },
  grid: { left: 50, right: 20, top: 34, bottom: 40 },
  xAxis: { type: 'value', name: '1 - 特异度', min: 0, max: 1, nameLocation: 'middle', nameGap: 24 },
  yAxis: { type: 'value', name: '敏感度', min: 0, max: 1 },
  series: [
    ...rocRows.value.map((r: any) => ({ name: `${r.label} AUC ${fmt(r.auc, 3)}`, type: 'line', symbol: 'none', lineStyle: { width: 2 }, data: (r.fpr || []).map((x: number, i: number) => [x, r.tpr?.[i]]) })),
    { name: '参考线', type: 'line', symbol: 'none', silent: true, lineStyle: { type: 'dashed', color: '#CBD5E1', width: 1 }, data: [[0, 0], [1, 1]], tooltip: { show: false } },
  ],
}))
function forestOption(rows: any[], effect: string) {
  const list = [...rows].reverse()
  const cats = list.map((r) => varLabel(r.variable))
  const vals = list.flatMap((r) => [r.ci_lower, r.ci_upper, r.estimate]).map(Number).filter((n) => Number.isFinite(n) && n > 0)
  const min = Math.max(0.05, Math.min(0.5, ...vals) * 0.8)
  const max = Math.max(2, ...vals) * 1.2
  return {
    grid: { left: 110, right: 40, top: 20, bottom: 30 },
    tooltip: { trigger: 'item', formatter: (p: any) => { const r = list[p.dataIndex]; return `${varLabel(r.variable)}<br/>${effect} ${effectText(r)}<br/>P=${r.p_display}` } },
    xAxis: { type: 'log', min, max, name: effect, axisLabel: { formatter: (v: number) => String(+v.toFixed(2)) } },
    yAxis: { type: 'category', data: cats },
    series: [
      {
        type: 'custom',
        renderItem: (_: any, api: any) => {
          const lo = api.coord([api.value(1), api.value(0)]); const hi = api.coord([api.value(2), api.value(0)])
          return { type: 'line', shape: { x1: lo[0], y1: lo[1], x2: hi[0], y2: hi[1] }, style: { stroke: '#64748B', lineWidth: 1.5 } }
        },
        data: list.map((r, i) => [i, r.ci_lower, r.ci_upper]),
        encode: { x: [1, 2], y: 0 },
      },
      {
        type: 'scatter', symbol: 'rect', symbolSize: 10,
        data: list.map((r, i) => ({ value: [r.estimate, i], itemStyle: { color: (r.p ?? 1) < 0.05 ? (r.estimate > 1 ? '#B91C1C' : '#2F7D55') : '#94A3B8' } })),
        markLine: { silent: true, symbol: 'none', lineStyle: { type: 'dashed', color: '#5392FF' }, data: [{ xAxis: 1 }], label: { show: false } },
      },
    ],
  }
}

function scopeParams(extra: Record<string, any> = {}) {
  return { ...(cohortId.value ? { cohort_id: cohortId.value } : {}), outcome: outcome.value, event_field: outcome.value, ...extra }
}

const runAnalysis = async (type: string) => {
  loading.value = true
  try {
    if (type === 'table1') table1Data.value = (await runTable1(scopeParams({ group_by: outcome.value }))).data
    else if (type === 'km') kmData.value = { ...(await runKM(scopeParams({ group_by: kmGroup.value || null }))).data, __group: kmGroup.value }
    else if (type === 'logistic') modelData.logistic = (await runLogistic(scopeParams())).data
    else if (type === 'cox') modelData.cox = (await runCox(scopeParams())).data
    else if (type === 'roc') rocData.value = (await runROC(scopeParams())).data
    else if (type === 'outcomes') outcomesData.value = (await runOutcomes(scopeParams())).data
  } catch (e) {
    message.error('分析失败，请检查后端 S-AKI 服务')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try { const res = await getSakiCohorts(); cohorts.value = Array.isArray(res.data) ? res.data : (res.data?.cohorts || []) } catch { cohorts.value = [] }
})
</script>

<style scoped>
.saki-analysis { display: flex; flex-direction: column; gap: 16px; }
.analysis-form { margin-bottom: 12px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.analysis-hint { font-size: var(--text-caption); color: var(--color-text-tertiary); }
.result-title { font-weight: 600; margin-bottom: 8px; }
.result-foot { margin: 8px 0 0; font-size: var(--text-caption); color: var(--color-text-tertiary); }
.p-sig { color: var(--color-danger); font-weight: 600; }
.result-panel { background: var(--color-bg-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: 16px 18px; font-variant-numeric: tabular-nums; }
.result-panel.error { color: var(--color-danger); }
.stat-table { width: 100%; border-collapse: collapse; font-size: var(--text-table); }
.stat-table th, .stat-table td { border-bottom: 1px solid var(--color-divider); padding: 8px 10px; text-align: left; }
.stat-table th { background: var(--color-bg-surface-secondary); font-size: var(--text-caption); font-weight: var(--text-table-header-weight); color: var(--color-text-secondary); }
.disclaimer { text-align: center; font-size: var(--text-caption); color: var(--color-warning); padding: 8px; background: var(--color-warning-soft-bg); border: 1px solid var(--color-warning-soft-border); border-radius: var(--radius-md); }
.analysis-scope { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 10px 14px; background: var(--color-bg-surface); border: 1px solid var(--color-border); border-radius: 10px; }
.scope-label { font-size: var(--text-caption); color: var(--color-text-secondary); }
.scope-hint { font-size: var(--text-caption); color: var(--color-text-tertiary); }
.result-panel.warn { color: #B45309; background: #FFFBEB; border-color: #FCD34D; }
.result-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.result-head .result-title { margin: 0 6px 0 0; }
.metric { font-size: 12px; padding: 1px 8px; border-radius: 10px; background: #F1F5F9; color: var(--color-text-secondary); }
.metric.p-sig { background: #FEF2F2; color: #B91C1C; }
.result-note { font-size: var(--text-caption); color: var(--color-text-secondary); margin: 6px 0; }
.cmp { margin-left: 10px; }
.tiles { display: flex; gap: 12px; margin-bottom: 12px; }
.tile { flex: 1; border: 1px solid var(--color-border); border-radius: 10px; padding: 10px 14px; display: flex; flex-direction: column; gap: 2px; }
.tile span { font-size: 12px; color: var(--color-text-tertiary); }
.tile b { font-size: 22px; }
.tile em { font-style: normal; font-size: 12px; color: var(--color-text-secondary); }
.stat-table { margin-top: 8px; }
</style>
