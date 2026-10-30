<template>
  <div class="causal-inference">
    <!-- 步骤向导 -->
    <div class="ci-steps">
      <div v-for="(step, idx) in steps" :key="idx" class="ci-step" :class="{ 'ci-step--active': currentStep === idx, 'ci-step--done': currentStep > idx }">
        <span class="ci-step-num">{{ idx + 1 }}</span>
        <span class="ci-step-label">{{ step.label }}</span>
      </div>
    </div>

    <!-- Step 1: 定义问题 -->
    <section v-if="currentStep === 0" class="ci-section">
      <h3 class="ci-section-title">定义研究问题</h3>
      <div class="ci-form-grid">
        <div class="ci-form-item">
          <label>治疗/暴露</label>
          <select v-model="question.exposure" class="ci-select">
            <option value="">请选择</option>
            <option v-for="opt in exposureOptions" :key="opt" :value="opt">{{ opt }}</option>
          </select>
        </div>
        <div class="ci-form-item">
          <label>对照</label>
          <select v-model="question.control" class="ci-select">
            <option value="">请选择</option>
            <option value="standard">标准治疗</option>
            <option value="none">无干预</option>
          </select>
        </div>
        <div class="ci-form-item">
          <label>结局</label>
          <select v-model="question.outcome" class="ci-select">
            <option value="">请选择</option>
            <option value="mortality">死亡率</option>
            <option value="aki_progression">AKI进展</option>
            <option value="ventilator_days">机械通气天数</option>
            <option value="icu_los">ICU住院天数</option>
          </select>
        </div>
        <div class="ci-form-item">
          <label>观察窗</label>
          <select v-model="question.window" class="ci-select">
            <option value="24h">24小时</option>
            <option value="48h">48小时</option>
            <option value="72h">72小时</option>
          </select>
        </div>
      </div>
      <button class="ci-btn ci-btn--primary" @click="nextStep" :disabled="!canProceed">下一步</button>
    </section>

    <!-- Step 2: 因果DAG -->
    <section v-if="currentStep === 1" class="ci-section">
      <h3 class="ci-section-title">因果DAG</h3>
      <div class="ci-dag-area">
        <div class="ci-dag-chart">
          <svg viewBox="0 0 520 300" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" role="img" aria-label="因果DAG">
            <defs>
              <marker id="ci-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#60a5fa"/>
              </marker>
            </defs>
            <path
              v-for="(edge, i) in dagEdges"
              :key="`edge-${i}`"
              :d="edge.path"
              fill="none"
              :stroke="edgeColor(edge.kind)"
              :stroke-width="edge.kind === 'effect' ? 2.5 : 1.5"
              :stroke-dasharray="edge.kind === 'toOutcome' ? '4 3' : undefined"
              :opacity="edge.kind === 'effect' ? 1 : 0.6"
              marker-end="url(#ci-arrow)"
            />
            <text v-if="hasEffectEdge" x="260" y="142" text-anchor="middle" fill="#fbbf24" font-size="11" font-weight="600">因果效应?</text>
            <g v-for="node in dagNodes" :key="node.id">
              <rect
                :x="node.x" :y="node.y" :width="node.w" :height="node.h" rx="8"
                :fill="nodeFill(node.kind)" :stroke="nodeStroke(node.kind)" :stroke-width="node.kind === 'confounder' ? 1.5 : 2"
              />
              <text
                :x="node.x + node.w / 2" :y="node.y + node.h / 2 + 4"
                text-anchor="middle" :fill="nodeTextFill(node.kind)"
                :font-size="node.kind === 'confounder' ? 12 : 13"
              >{{ shortLabel(node.label, node.kind) }}</text>
            </g>
            <text v-if="!dagNodes.length" x="260" y="150" text-anchor="middle" fill="#94A3B8" font-size="13">暂无因果结构数据</text>
          </svg>
        </div>
      </div>
      <div class="ci-dag-legend">
        <span class="ci-legend-item"><span class="ci-dot ci-dot--exposure"></span>暴露</span>
        <span class="ci-legend-item"><span class="ci-dot ci-dot--outcome"></span>结局</span>
        <span class="ci-legend-item"><span class="ci-dot ci-dot--confounder"></span>混杂因素</span>
        <span class="ci-legend-item"><span class="ci-dot ci-dot--mediator"></span>中介因素</span>
      </div>
      <button class="ci-btn ci-btn--primary" @click="nextStep">下一步</button>
    </section>

    <!-- Step 3: 匹配与平衡 -->
    <section v-if="currentStep === 2" class="ci-section">
      <h3 class="ci-section-title">匹配与平衡</h3>
      <div class="ci-chart-grid">
        <div class="ci-chart-card">
          <h4>候选原因后验概率</h4>
          <ClinicalChart :option="posteriorChartOption" :loading="loadingAnalysis" :height="200" empty-text="暂无候选原因数据" />
        </div>
        <div class="ci-chart-card">
          <h4>先验 vs 后验概率</h4>
          <ClinicalChart :option="priorPosteriorChartOption" :loading="loadingAnalysis" :height="200" empty-text="暂无证据更新数据" />
        </div>
      </div>
      <div class="ci-flow-diagram">
        <div class="ci-flow-node ci-flow-node--included">总样本 {{ matchResult.total || 0 }}</div>
        <div class="ci-flow-arrow">→</div>
        <div class="ci-flow-node">匹配成功 {{ matchResult.matched || 0 }}</div>
        <div class="ci-flow-arrow">→</div>
        <div class="ci-flow-node ci-flow-node--excluded">排除 {{ matchResult.excluded || 0 }}</div>
      </div>
      <button class="ci-btn ci-btn--primary" @click="nextStep">查看结果</button>
    </section>

    <!-- Step 4: 因果效应 -->
    <section v-if="currentStep === 3" class="ci-section">
      <h3 class="ci-section-title">因果效应估计</h3>
      <div class="ci-disclaimer ci-disclaimer--inline">
        ⚠ 当前为探索性分析结果，不等同于正式因果推断。ATE/ATT 基于观察性数据的近似估计，不可直接用于临床决策。
      </div>
      <div class="ci-effect-cards">
        <div class="ci-effect-card">
          <span class="ci-effect-label">ATE (平均处理效应)</span>
          <span class="ci-effect-value">{{ effectResult.ate || '—' }}</span>
          <span class="ci-effect-ci">{{ effectResult.ate_ci || '' }}</span>
        </div>
        <div class="ci-effect-card">
          <span class="ci-effect-label">ATT (处理组效应)</span>
          <span class="ci-effect-value">{{ effectResult.att || '—' }}</span>
          <span class="ci-effect-ci">{{ effectResult.att_ci || '' }}</span>
        </div>
      </div>
      <div class="ci-chart-grid">
        <div class="ci-chart-card">
          <h4>Forest Plot</h4>
          <div ref="forestRef" class="ci-chart-area"></div>
        </div>
        <div class="ci-chart-card">
          <h4>敏感性分析</h4>
          <div ref="sensitivityRef" class="ci-chart-area"></div>
        </div>
      </div>

      <!-- 重要声明 -->
      <div class="ci-disclaimer">
        <h4>⚠ 重要声明</h4>
        <ul>
          <li>这是基于观察性数据的估计，不能替代随机对照试验</li>
          <li>未测量混杂仍可能存在</li>
          <li>不能直接作为单个患者治疗指令</li>
          <li>结果需结合临床专业知识综合判断</li>
        </ul>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import type { EChartsOption } from 'echarts'
import { useEmbedBridge } from '../../../composables/useEmbedBridge'
import { postAiCausalAnalysis } from '../../../api'
import ClinicalChart from '../../../components/charts/base/ClinicalChart.vue'

const route = useRoute()
const patientId = computed(() => String(route.params.patientId || ''))

const { sendUpdateTitle, sendReportError } = useEmbedBridge({
  moduleKey: 'causal-inference',
  targetOrigin: window.location.origin,
})

const currentStep = ref(0)
const steps = [
  { label: '定义问题' },
  { label: '因果DAG' },
  { label: '匹配平衡' },
  { label: '效应估计' },
]

const question = ref({
  exposure: '',
  control: 'standard',
  outcome: 'mortality',
  window: '48h',
})

const exposureOptions = [
  '高剂量升压药', '液体正平衡', '俯卧位通气', 'CRRT早期启动',
  '高PEEP', '镇静深度', '早期活动', '肠内营养',
]

const canProceed = computed(() => question.value.exposure && question.value.outcome)

const OUTCOME_LABELS: Record<string, string> = {
  mortality: '死亡率',
  aki_progression: 'AKI进展',
  ventilator_days: '机械通气天数',
  icu_los: 'ICU住院天数',
}

const loadingAnalysis = ref(false)
const analysis = ref<any>(null)
const matchResult = ref({ total: 0, matched: 0, excluded: 0 })
const effectResult = ref({ ate: '', ate_ci: '', att: '', att_ci: '' })

function nextStep() {
  if (currentStep.value < steps.length - 1) {
    currentStep.value++
    // DAG 与图表都依赖 causal-analysis 返回的候选原因/概率数据
    if (currentStep.value === 1 || currentStep.value === 3) loadResults()
  }
}

// ── 因果 DAG：由 candidate_causes 动态构建分层布局 ──

interface CandidateCause {
  cause_key?: string
  label?: string
  prior?: number
  posterior?: number
}

interface DagNode {
  id: string
  label: string
  x: number
  y: number
  w: number
  h: number
  kind: 'exposure' | 'outcome' | 'confounder'
}

interface DagEdge {
  path: string
  kind: 'toExposure' | 'toOutcome' | 'effect'
}

const candidateCauses = computed<CandidateCause[]>(() => {
  const rows = analysis.value?.candidate_causes
  return Array.isArray(rows) ? rows : []
})

const exposureLabel = computed(() =>
  String(analysis.value?.finding_label || analysis.value?.abnormal_finding || question.value.exposure || '暴露'))

const outcomeLabel = computed(() =>
  OUTCOME_LABELS[question.value.outcome] || question.value.outcome || '结局')

const dagNodes = computed<DagNode[]>(() => {
  const nodes: DagNode[] = []
  const causes = candidateCauses.value.slice(0, 4)
  const n = causes.length
  if (n > 0) {
    const h = 36
    const gap = (300 - n * h) / (n + 1)
    causes.forEach((cause, i) => {
      nodes.push({
        id: `cause-${i}`,
        label: String(cause.label || cause.cause_key || '候选原因'),
        x: 10,
        y: gap * (i + 1) + h * i,
        w: 140,
        h,
        kind: 'confounder',
      })
    })
  }
  nodes.push({ id: 'exposure', label: exposureLabel.value, x: 195, y: 125, w: 130, h: 50, kind: 'exposure' })
  nodes.push({ id: 'outcome', label: outcomeLabel.value, x: 380, y: 125, w: 130, h: 50, kind: 'outcome' })
  return nodes
})

const dagEdges = computed<DagEdge[]>(() => {
  const edges: DagEdge[] = []
  for (const node of dagNodes.value) {
    if (node.kind !== 'confounder') continue
    const cy = node.y + node.h / 2
    edges.push({ kind: 'toExposure', path: `M ${node.x + node.w} ${cy} L 195 150` })
    // 绕开中间的暴露节点：上方原因从顶部绕行，下方原因从底部绕行
    const ctrlY = cy < 150 ? Math.max(cy - 30, 20) : Math.min(cy + 30, 280)
    edges.push({ kind: 'toOutcome', path: `M ${node.x + node.w} ${cy} Q 290 ${ctrlY} 380 150` })
  }
  edges.push({ kind: 'effect', path: 'M 325 150 L 378 150' })
  return edges
})

const hasEffectEdge = computed(() => dagNodes.value.length >= 2)

function nodeFill(kind: DagNode['kind']) {
  return kind === 'exposure' ? '#1e3a5f' : kind === 'outcome' ? '#3b1f2b' : '#1e3b2f'
}
function nodeStroke(kind: DagNode['kind']) {
  return kind === 'exposure' ? '#60a5fa' : kind === 'outcome' ? '#f87171' : '#34d399'
}
function nodeTextFill(kind: DagNode['kind']) {
  return kind === 'exposure' ? '#e0f2fe' : kind === 'outcome' ? '#fecdd3' : '#a7f3d0'
}
function edgeColor(kind: DagEdge['kind']) {
  return kind === 'effect' ? '#fbbf24' : kind === 'toOutcome' ? '#f87171' : '#60a5fa'
}
function shortLabel(label: string, kind: DagNode['kind']) {
  const max = kind === 'confounder' ? 11 : 9
  return label.length > max ? `${label.slice(0, max - 1)}…` : label
}

// ── 图表：候选原因 prior/posterior（真实贝叶斯估计） ──

function toPercent(value: unknown): number {
  const n = Number(value)
  if (!Number.isFinite(n)) return 0
  return Math.round(Math.min(100, Math.max(0, n <= 1 ? n * 100 : n)))
}

/** 候选原因后验概率（替换原倾向评分直方图） */
const posteriorChartOption = computed<EChartsOption | null>(() => {
  const rows = candidateCauses.value
    .map(c => ({ name: String(c.label || c.cause_key || ''), value: toPercent(c.posterior) }))
    .filter(r => r.name)
  if (!rows.length) return null
  rows.sort((a, b) => a.value - b.value)
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 8, right: 44, top: 8, bottom: 8, containLabel: true },
    xAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%', fontSize: 11 } },
    yAxis: { type: 'category', data: rows.map(r => r.name), axisLabel: { fontSize: 11 } },
    series: [{
      type: 'bar',
      data: rows.map(r => r.value),
      barWidth: 14,
      itemStyle: { borderRadius: [0, 3, 3, 0] },
      label: { show: true, position: 'right', fontSize: 11, formatter: '{c}%' },
    }],
  }
})

/** 先验 vs 后验对比（替换原 Love Plot 的前后对比语义） */
const priorPosteriorChartOption = computed<EChartsOption | null>(() => {
  const rows = candidateCauses.value
    .map(c => ({
      name: String(c.label || c.cause_key || ''),
      prior: toPercent(c.prior),
      posterior: toPercent(c.posterior),
    }))
    .filter(r => r.name)
  if (!rows.length) return null
  rows.sort((a, b) => a.posterior - b.posterior)
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['先验概率', '后验概率'], top: 0 },
    grid: { left: 8, right: 16, top: 32, bottom: 8, containLabel: true },
    xAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%', fontSize: 11 } },
    yAxis: { type: 'category', data: rows.map(r => r.name), axisLabel: { fontSize: 11 } },
    series: [
      { name: '先验概率', type: 'bar', data: rows.map(r => r.prior), barWidth: 8, itemStyle: { borderRadius: [0, 3, 3, 0] } },
      { name: '后验概率', type: 'bar', data: rows.map(r => r.posterior), barWidth: 8, itemStyle: { borderRadius: [0, 3, 3, 0] } },
    ],
  }
})

async function loadResults() {
  if (!patientId.value || loadingAnalysis.value || analysis.value) return
  loadingAnalysis.value = true
  try {
    const res = await postAiCausalAnalysis(patientId.value, {
      abnormal_finding: question.value.exposure,
      outcome: question.value.outcome,
    })
    const data = res.data?.analysis || res.data?.data || res.data || {}
    analysis.value = data
    effectResult.value = {
      ate: data.ate || '—',
      ate_ci: data.ate_ci || '',
      att: data.att || '—',
      att_ci: data.att_ci || '',
    }
    matchResult.value = {
      total: data.total_samples || 0,
      matched: data.matched_samples || 0,
      excluded: data.excluded_samples || 0,
    }
  } catch (e: any) {
    sendReportError('LOAD_FAILED', e?.message || '因果分析失败')
  } finally {
    loadingAnalysis.value = false
  }
}

onMounted(() => {
  sendUpdateTitle('因果推断')
})
</script>

<style scoped>.causal-inference { display: flex; flex-direction: column; gap: 20px }
.ci-steps { display: flex; gap: 4px; background: var(--color-bg-surface, #FFFFFF); border-radius: var(--radius-md, 6px); padding: 12px 16px; border: 1px solid var(--color-border, #E5E7EB) }
.ci-step { display: flex; align-items: center; gap: 8px; padding: 8px 16px; border-radius: var(--radius-md, 6px); font-size: var(--text-body, 13px); color: var(--color-text-tertiary, #9CA3AF); flex: 1; justify-content: center }
.ci-step--active { background: var(--color-primary-bg, #E8F0FE); color: var(--color-primary, #2F6FED); font-weight: 600 }
.ci-step--done { color: var(--color-normal, #12A66A) }
.ci-step-num { width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; border-radius: 50%; background: var(--color-border, #E5E7EB); font-size: 11px; font-weight: 600 }
.ci-step--active .ci-step-num { background: var(--color-primary, #2F6FED); color: var(--color-text-inverse, #FFFFFF) }
.ci-step--done .ci-step-num { background: var(--color-normal, #12A66A); color: var(--color-text-inverse, #FFFFFF) }
.ci-section { background: var(--color-bg-surface, #FFFFFF); border-radius: var(--radius-lg, 10px); padding: 20px; border: 1px solid var(--color-border, #E5E7EB) }
.ci-section-title { margin: 0 0 16px; font-size: var(--text-section-title, 15px); font-weight: 600 }
.ci-form-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 16px }
.ci-form-item label { display: block; font-size: var(--text-caption, 12px); font-weight: 500; color: var(--color-text-secondary, #4B5563); margin-bottom: 4px }
.ci-select { width: 100%; padding: 8px 12px; border: 1px solid var(--color-border, #E5E7EB); border-radius: var(--radius-md, 6px); font-size: var(--text-body, 13px); background: var(--color-bg-surface, #FFFFFF) }
.ci-btn { padding: 8px 20px; border-radius: var(--radius-md, 6px); font-size: var(--text-body, 13px); font-weight: 500; cursor: pointer; border: 1px solid var(--color-border, #E5E7EB); background: var(--color-bg-surface, #FFFFFF); transition: all 0.15s }
.ci-btn--primary { background: var(--color-primary, #2F6FED); color: var(--color-text-inverse, #FFFFFF); border-color: var(--color-primary, #2F6FED) }
.ci-btn--primary:hover { background: var(--color-primary-hover, #3B82F6) }
.ci-btn:disabled { opacity: 0.5; cursor: not-allowed }
.ci-dag-area { margin-bottom: 12px }
.ci-dag-chart { height: 300px; background: var(--color-bg-surface-secondary, #F1F4F8); border-radius: var(--radius-md, 6px) }
.ci-dag-legend { display: flex; gap: 16px; margin-bottom: 16px }
.ci-legend-item { display: flex; align-items: center; gap: 6px; font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563) }
.ci-dot { width: 10px; height: 10px; border-radius: 50% }
.ci-dot--exposure { background: var(--color-primary, #2F6FED) }
.ci-dot--outcome { background: var(--color-critical, #D92D20) }
.ci-dot--confounder { background: var(--color-warning, #B54708) }
.ci-dot--mediator { background: var(--color-accent, #0891B2) }
.ci-chart-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px }
.ci-chart-card { background: var(--color-bg-surface-secondary, #F1F4F8); border-radius: var(--radius-md, 6px); padding: 12px }
.ci-chart-card h4 { margin: 0 0 8px; font-size: var(--text-body, 13px); font-weight: 600 }
.ci-chart-area { height: 220px }
.ci-flow-diagram { display: flex; align-items: center; justify-content: center; gap: 12px; margin-bottom: 16px }
.ci-flow-node { padding: 10px 20px; background: var(--color-primary-bg, #E8F0FE); border: 1px solid var(--color-primary, #2F6FED); border-radius: var(--radius-md, 6px); font-size: var(--text-body, 13px); font-weight: 500 }
.ci-flow-node--included { background: var(--color-normal-bg, #E8F7F0); border-color: var(--color-normal, #12A66A) }
.ci-flow-node--excluded { background: var(--color-critical-bg, #FEECEB); border-color: var(--color-danger, #D92D20) }
.ci-flow-arrow { font-size: var(--text-section-title, 15px); color: var(--color-text-tertiary, #9CA3AF) }
.ci-effect-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px }
.ci-effect-card { background: var(--color-bg-surface-secondary, #F1F4F8); border-radius: var(--radius-lg, 10px); padding: 16px; text-align: center; border: 1px solid var(--color-border, #E5E7EB) }
.ci-effect-label { display: block; font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563); margin-bottom: 8px }
.ci-effect-value  {  display: block; font-size: var(--text-metric-key, 26px); font-weight: 700; font-family: var(--font-digit, monospace); color: var(--color-primary, #2F6FED) ; font-variant-numeric: tabular-nums }
.ci-effect-ci { display: block; font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF); margin-top: 4px }
.ci-disclaimer { background: var(--color-warning-soft-bg, #FFF9D8); border: 1px solid var(--color-warning-soft-border, #FFE58F); border-radius: var(--radius-md, 6px); padding: 16px; margin-top: 16px }
.ci-disclaimer--inline { margin: 0 0 12px; padding: 8px 12px; font-size: var(--text-caption, 12px); color: var(--color-warning, #B54708) }

.ci-disclaimer h4 { margin: 0 0 8px; font-size: var(--text-body, 13px); color: var(--color-warning, #B54708) }
.ci-disclaimer ul { margin: 0; padding-left: 20px; font-size: var(--text-body, 13px); color: var(--color-warning, #B54708); line-height: 1.8 }

@media (max-width: 1200px) {.ci-chart-grid { grid-template-columns: 1fr }
.ci-form-grid { grid-template-columns: 1fr }

}

</style>

