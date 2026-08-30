<template>
  <div class="risk-prediction">
    <!-- 模型不可用时的提示 -->
    <div v-if="!modelAvailable" class="rp-model-unavailable">
      <span class="rp-model-unavailable__icon">ℹ️</span>
      <span class="rp-model-unavailable__text">{{ modelUnavailableReason }}</span>
    </div>

    <!-- 风险指标卡行 -->
    <div v-if="riskCards.length" class="rp-overview-row">
      <div v-for="card in riskCards" :key="card.key" class="rp-risk-card" :class="`rp-risk-card--${card.level}`">
        <div class="rp-risk-card__header">
          <span class="rp-risk-card__label">{{ card.label }}</span>
          <span class="rp-risk-card__source">{{ displayLabel }}</span>
        </div>
        <div class="rp-risk-card__value-row">
          <div class="rp-risk-ring">
            <svg viewBox="0 0 36 36">
              <path class="rp-ring-bg" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
              <path class="rp-ring-fill" :class="`rp-ring-fill--${card.level}`" :stroke-dasharray="`${card.value}, 100`" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
            </svg>
            <span class="rp-ring-value">{{ card.value }}%</span>
          </div>
          <div class="rp-risk-card__meta">
            <span v-if="card.change != null" class="rp-risk-change" :class="card.change > 0 ? 'rp-change-up' : card.change < 0 ? 'rp-change-down' : ''">
              {{ card.change > 0 ? '↑' : card.change < 0 ? '↓' : '—' }}{{ Math.abs(card.change) }}%
            </span>
            <span class="rp-risk-horizon">{{ card.horizon }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 图表行：趋势 + 器官风险 -->
    <div class="rp-chart-row">
      <div class="rp-chart-card rp-chart-card--wide">
        <h3 class="rp-chart-title">风险趋势</h3>
        <div v-if="trendChartOption">
          <ClinicalChart :option="trendChartOption" :loading="loading" :height="280" :updated-at="updatedAt" show-toolbar />
        </div>
        <div v-else-if="!loading" class="rp-chart-empty">
          <span>暂无风险趋势数据</span>
        </div>
      </div>
    </div>

    <div class="rp-chart-row">
      <div class="rp-chart-card">
        <h3 class="rp-chart-title">器官风险</h3>
        <div v-if="organChartOption">
          <ClinicalChart :option="organChartOption" :loading="loading" :height="260" />
        </div>
        <div v-else-if="!loading" class="rp-chart-empty">
          <span v-if="!modelAvailable">当前无模型器官风险数据</span>
          <span v-else>暂无器官风险数据</span>
        </div>
      </div>
      <div class="rp-chart-card">
        <h3 class="rp-chart-title">特征贡献</h3>
        <div v-if="contributorChartOption">
          <ClinicalChart :option="contributorChartOption" :loading="loading" :height="260" />
        </div>
        <div v-else-if="!loading" class="rp-chart-empty">
          <span>当前无模型贡献度数据</span>
        </div>
      </div>
    </div>

    <!-- 规则估算信息（模型不可用时） -->
    <div v-if="!modelAvailable && ruleInfo" class="rp-info-row">
      <div class="rp-info-card">
        <h3 class="rp-info-title">规则估算信息</h3>
        <div class="rp-model-info">
          <div v-if="ruleInfo.rule_name" class="rp-model-row"><span>规则名称</span><span>{{ ruleInfo.rule_name }}</span></div>
          <div v-if="ruleInfo.trigger_indicator" class="rp-model-row"><span>触发指标</span><span>{{ ruleInfo.trigger_indicator }}</span></div>
          <div v-if="ruleInfo.threshold" class="rp-model-row"><span>阈值</span><span>{{ ruleInfo.threshold }}</span></div>
          <div v-if="ruleInfo.rule_version" class="rp-model-row"><span>规则版本</span><span>{{ ruleInfo.rule_version }}</span></div>
          <div v-if="ruleInfo.data_time" class="rp-model-row"><span>数据时间</span><span>{{ formatTime(ruleInfo.data_time) }}</span></div>
          <div v-if="ruleInfo.evidence" class="rp-model-row"><span>支持证据</span><span>{{ ruleInfo.evidence }}</span></div>
        </div>
      </div>
      <div class="rp-info-card">
        <h3 class="rp-info-title">安全声明</h3>
        <p class="rp-safety-notice">{{ safetyNotice }}</p>
        <p class="rp-updated">预测时间：{{ updatedAt }}</p>
      </div>
    </div>

    <!-- 模型信息（模型可用时） -->
    <div v-else-if="modelAvailable" class="rp-info-row">
      <div class="rp-info-card">
        <h3 class="rp-info-title">模型信息</h3>
        <div class="rp-model-info">
          <div class="rp-model-row"><span>预测来源</span><span>{{ displayLabel }}</span></div>
          <div class="rp-model-row"><span>模型名称</span><span>{{ modelNameDisplay }}</span></div>
          <div class="rp-model-row"><span>模型版本</span><span>{{ modelVersionDisplay }}</span></div>
          <div class="rp-model-row"><span>校准版本</span><span>{{ calibrationVersionDisplay }}</span></div>
          <div class="rp-model-row"><span>模型状态</span><span :class="modelStatusClass">{{ modelStatusDisplay }}</span></div>
          <div v-if="modelMeta.fallback_used" class="rp-model-row"><span>降级原因</span><span class="rp-status-warn">{{ fallbackReasonDisplay }}</span></div>
        </div>
      </div>
      <div class="rp-info-card">
        <h3 class="rp-info-title">安全声明</h3>
        <p class="rp-safety-notice">{{ safetyNotice }}</p>
        <p class="rp-updated">预测时间：{{ updatedAt }}</p>
      </div>
    </div>

    <!-- AI解释折叠区 -->
    <details v-if="topContributors.length" class="rp-ai-explanation">
      <summary>AI解释与证据（{{ topContributors.length }}个因素）</summary>
      <div class="rp-ai-content">
        <div class="rp-contributors-list">
          <div v-for="(c, idx) in topContributors" :key="idx" class="rp-contributor-item">
            <span class="rp-contributor-rank">{{ Number(idx) + 1 }}</span>
            <span class="rp-contributor-name">{{ c.feature || c.name || '' }}</span>
            <span class="rp-contributor-impact" :class="c.direction > 0 ? 'rp-change-up' : 'rp-change-down'">
              {{ c.direction > 0 ? '↑' : '↓' }}{{ (Math.abs(c.impact || c.weight || 0) * 100).toFixed(1) }}%
            </span>
          </div>
        </div>
        <p class="rp-ai-disclaimer">⚠ 以上为模型输入特征的贡献度分析，不代表因果关系。预测结果仅供临床决策参考，不替代医生判断。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import type { EChartsOption } from 'echarts'
import { useEmbedBridge } from '../../../composables/useEmbedBridge'
import { getAiRiskForecast } from '../../../api'
import { getRiskLevel } from '../../../styles/tokens/risk'
import ClinicalChart from '../../../components/charts/base/ClinicalChart.vue'

const route = useRoute()
const patientId = computed(() => String(route.params.patientId || ''))

const { sendUpdateTitle, sendReportError } = useEmbedBridge({
  moduleKey: 'risk-prediction',
  targetOrigin: window.location.origin,
  onPatientContextChanged: () => loadData(),
  onRefresh: () => loadData(),
})

// ── 模型状态中文映射 ────────────────────────────────

const MODEL_STATUS_MAP: Record<string, string> = {
  unknown: '未提供',
  weight_missing: '模型权重未加载',
  model_missing: '预测模型未部署',
  not_ready: '模型尚未就绪',
  unavailable: '当前不可用',
  pending: '计算中',
  fallback: '当前使用规则评估',
  ready: '就绪',
  available: '可用',
  loaded: '已加载',
}

const FALLBACK_REASON_MAP: Record<string, string> = {
  weight_missing: '模型权重文件缺失',
  model_missing: '预测模型未部署',
  not_ready: '模型初始化未完成',
  unavailable: '模型服务不可用',
  timeout: '模型推理超时',
  error: '模型推理出错',
}

function formatTime(t: string) {
  if (!t) return ''
  try { return new Date(t).toLocaleString('zh-CN') } catch { return t }
}

/** 标准化状态字符串：小写、去空格 */
function normalizeStatus(raw: unknown): string {
  return String(raw || '').toLowerCase().trim()
}

// ── 数据 ─────────────────────────────────────────

const loading = ref(false)
const rawData = ref<any>(null)

const displayLabel = computed(() => rawData.value?.display_label || '风险预测')
const safetyNotice = computed(() => rawData.value?.safety_notice || '预测结果仅供临床决策支持，不替代医生判断')

const updatedAt = computed(() => {
  const t = rawData.value?.model_meta?.prediction_time || rawData.value?.updated_at
  if (!t) return ''
  try { return new Date(t).toLocaleString('zh-CN') } catch { return '' }
})

const modelMeta = computed(() => rawData.value?.model_meta || {})

/** Is the AI model actually available (has valid weights) */
const modelAvailable = computed(() => {
  if (modelMeta.value.model_available === false) return false
  const status = normalizeStatus(modelMeta.value.model_status)
  if (['weight_missing', 'model_missing', 'not_ready', 'unavailable', 'unknown', 'pending', ''].includes(status)) return false
  return true
})

/** Reason for model unavailability */
const modelUnavailableReason = computed(() => {
  const statusRaw = normalizeStatus(modelMeta.value.model_status)
  const fallbackRaw = normalizeStatus(modelMeta.value.fallback_reason)
  if (fallbackRaw) {
    return FALLBACK_REASON_MAP[fallbackRaw] || '模型当前不可用，使用规则评估'
  }
  const mapped = MODEL_STATUS_MAP[statusRaw]
  if (mapped) return `模型状态：${mapped}，当前显示规则估算风险`
  return '当前使用规则估算风险'
})

const modelNameDisplay = computed(() => {
  const v = modelMeta.value.model_name
  if (!v || v === 'unknown' || v === 'null' || v === 'none') return '未加载'
  return String(v)
})

const modelVersionDisplay = computed(() => {
  const v = modelMeta.value.model_version
  if (!v || v === 'unknown' || v === 'null' || v === 'none') return '未加载'
  return String(v)
})

const calibrationVersionDisplay = computed(() => {
  const v = modelMeta.value.calibration_version
  if (!v || v === 'unknown' || v === 'null' || v === 'none') return '未加载'
  return String(v)
})

const modelStatusDisplay = computed(() => {
  const raw = normalizeStatus(modelMeta.value.model_status)
  return MODEL_STATUS_MAP[raw] || '状态异常，请联系管理员'
})

const modelStatusClass = computed(() => {
  const raw = String(modelMeta.value.model_status || '').toLowerCase()
  if (['ready', 'available', 'loaded'].includes(raw)) return 'rp-status-ok'
  return 'rp-status-warn'
})

const fallbackReasonDisplay = computed(() => {
  const raw = normalizeStatus(modelMeta.value.fallback_reason)
  return FALLBACK_REASON_MAP[raw] || '模型当前不可用'
})

/** Rule-based estimation info */
const ruleInfo = computed(() => rawData.value?.rule_info || null)

const horizonProbabilities = computed(() => rawData.value?.horizon_probabilities || [])

/**
 * 显式量纲转换：将风险值转为百分数 (0-100)。
 * 后端应返回 scale 字段标明量纲；缺少 scale 时使用保守推断。
 * 禁止：猜测量纲、截断超限值、null 显示为 0%。
 */
function toPercent(value: unknown, scale?: string): number | null {
  if (value == null || value === '') return null
  const n = Number(value)
  if (!Number.isFinite(n)) return null

  // 显式 scale 优先
  if (scale === 'probability_0_1') {
    if (n < 0 || n > 1) return null
    return Math.round(n * 100)
  }
  if (scale === 'percent_0_100') {
    if (n < 0 || n > 100) return null
    return Math.round(n)
  }

  // 无显式 scale 时的保守推断：
  // 如果值在 0-1 之间（含 1），视为概率
  if (n >= 0 && n <= 1) return Math.round(n * 100)
  // 如果值在 1-100 之间，视为百分数
  if (n > 1 && n <= 100) return Math.round(n)
  // 超出合理范围，不显示
  return null
}

const riskCards = computed(() => {
  const hps = horizonProbabilities.value
  if (!hps.length && rawData.value?.current_probability == null) return []
  const cards = []
  if (rawData.value?.current_probability != null) {
    const v = toPercent(rawData.value.current_probability, rawData.value?.probability_scale)
    if (v != null) cards.push({ key: 'current', label: '当前风险', value: v, change: null, horizon: '当前', level: getRiskLevel(v) })
  }
  for (const hp of hps) {
    const v = toPercent(hp.probability, hp.scale)
    if (v == null) continue
    const prev = hp.previous_probability != null ? toPercent(hp.previous_probability, hp.scale) : null
    cards.push({
      key: `h${hp.horizon_hours || hp.horizon}`,
      label: `${hp.horizon_hours || hp.horizon}h恶化风险`,
      value: v,
      change: prev != null ? v - prev : null,
      horizon: `${hp.horizon_hours || hp.horizon}小时`,
      level: getRiskLevel(v),
    })
  }
  return cards
})

const topContributors = computed(() => rawData.value?.top_contributors || [])

const organRiskScores = computed(() => rawData.value?.organ_risk_scores || {})

// ── 图表 option ──────────────────────────────────

const trendChartOption = computed<any>(() => {
  const history = rawData.value?.history_risk_curve || []
  const forecast = rawData.value?.forecast_risk_curve || []
  const all = [...history, ...forecast]
  if (!all.length) return null

  const xData = all.map((p: any) => p.time || p.t || '')
  const yData = all.map((p: any) => toPercent(p.probability ?? p.value, p.scale) ?? 0)
  const isHistory = all.map((_: any, i: number) => i < history.length)

  const thresholds = rawData.value?.threshold_bands || []

  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['历史风险', '预测风险', '高风险阈值'], top: 0 },
    grid: { left: 12, right: 16, top: 40, bottom: 30, containLabel: true },
    xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 11 } },
    yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%', fontSize: 11 } },
    series: [
      {
        name: '历史风险',
        type: 'line',
        data: yData.map((v: number, i: number) => isHistory[i] ? v : null),
        smooth: true,
        lineStyle: { width: 2 },
        areaStyle: { color: 'rgba(37,99,235,0.08)' },
      },
      {
        name: '预测风险',
        type: 'line',
        data: yData.map((v: number, i: number) => !isHistory[i] ? v : null),
        smooth: true,
        lineStyle: { width: 2, type: 'dashed' },
        areaStyle: { color: 'rgba(37,99,235,0.04)' },
      },
      ...(thresholds.length && thresholds[0]?.value != null ? [{
        name: '高风险阈值',
        type: 'line',
        data: xData.map(() => toPercent(thresholds[0]?.value, thresholds[0]?.scale) ?? 0),
        lineStyle: { color: '#DC2626', type: 'dotted', width: 1 },
        symbol: 'none',
      }] : []),
    ],
  }
})

const organChartOption = computed<EChartsOption | null>(() => {
  const scores = organRiskScores.value
  const keys = Object.keys(scores)
  if (!keys.length) return null

  const labels: Record<string, string> = {
    respiratory: '呼吸', cardiovascular: '循环', circulatory: '循环',
    renal: '肾脏', coagulation: '凝血', hepatic: '肝脏',
    neurological: '神经', neurologic: '神经', infection: '感染',
  }
  const ORGAN_LABEL_FALLBACK = '其他器官系统'

  const data = keys.map(k => ({
    name: labels[k] || ORGAN_LABEL_FALLBACK,
    value: toPercent(scores[k]?.score ?? scores[k], scores[k]?.scale) ?? 0,
  })).filter(d => d.value > 0).sort((a, b) => b.value - a.value)

  // Don't show chart if no valid data
  if (!data.length) return null

  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 60, right: 16, top: 12, bottom: 12 },
    xAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%', fontSize: 11 } },
    yAxis: { type: 'category', data: data.map(d => d.name), axisLabel: { fontSize: 12 } },
    series: [{
      type: 'bar',
      data: data.map(d => ({
        value: d.value,
        itemStyle: {
          color: d.value >= 80 ? '#991B1B' : d.value >= 60 ? '#DC2626' : d.value >= 40 ? '#F59E0B' : '#16A34A',
          borderRadius: [0, 3, 3, 0],
        },
      })),
      barWidth: 16,
    }],
  }
})

const contributorChartOption = computed<EChartsOption | null>(() => {
  const contribs = topContributors.value
  if (!contribs.length) return null

  const data = contribs.slice(0, 8).map((c: any) => ({
    name: c.feature || c.name || '',
    value: Math.abs(c.weight || c.impact || 0),
    direction: c.direction || (c.weight > 0 ? 1 : -1),
  })).filter((d: { value: number }) => d.value > 0)

  if (!data.length) return null

  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 120, right: 16, top: 12, bottom: 12 },
    xAxis: { type: 'value', axisLabel: { fontSize: 11 } },
    yAxis: { type: 'category', data: data.map((d: { name: string }) => d.name), axisLabel: { fontSize: 11 } },
    series: [{
      type: 'bar',
      data: data.map((d: { value: number; direction: number }) => ({
        value: d.value,
        itemStyle: {
          color: d.direction > 0 ? '#DC2626' : '#16A34A',
          borderRadius: [0, 3, 3, 0],
        },
      })),
      barWidth: 14,
    }],
  }
})

// ── 加载数据 ─────────────────────────────────────

async function loadData() {
  if (!patientId.value || loading.value) return
  loading.value = true
  try {
    const res = await getAiRiskForecast(patientId.value)
    rawData.value = res.data || null
  } catch (e: any) {
    sendReportError('LOAD_FAILED', e?.message || '加载风险预测失败')
    rawData.value = null
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  sendUpdateTitle('风险预测')
  loadData()
})
</script>

<style scoped>
.risk-prediction { display: flex; flex-direction: column; gap: 16px; }

.rp-model-unavailable {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: #EFF6FF;
  border: 1px solid #BDDEFF;
  border-radius: 8px;
  font-size: 13px;
  color: #1E40AF;
}

.rp-model-unavailable__icon { font-size: 16px; }

.rp-overview-row { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }

.rp-risk-card { background: #fff; border-radius: 8px; padding: 14px 16px; border: 1px solid #DCE3EC; transition: box-shadow 0.2s; }
.rp-risk-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.06); }
.rp-risk-card--critical { border-left: 3px solid #991B1B; }
.rp-risk-card--high { border-left: 3px solid #DC2626; }
.rp-risk-card--medium { border-left: 3px solid #F59E0B; }
.rp-risk-card--low { border-left: 3px solid #16A34A; }
.rp-risk-card--stable { border-left: 3px solid #16A34A; }

.rp-risk-card__header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.rp-risk-card__label { font-size: 12px; font-weight: 500; color: #52606D; }
.rp-risk-card__source { font-size: 10px; color: #94A3B8; max-width: 80px; text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.rp-risk-card__value-row { display: flex; align-items: center; gap: 12px; }

.rp-risk-ring { width: 56px; height: 56px; position: relative; }
.rp-risk-ring svg { width: 100%; height: 100%; transform: rotate(-90deg); }
.rp-ring-bg { fill: none; stroke: #E8EEF5; stroke-width: 3; }
.rp-ring-fill { fill: none; stroke-width: 3; stroke-linecap: round; transition: stroke-dasharray 0.6s ease; }
.rp-ring-fill--stable, .rp-ring-fill--low { stroke: #16A34A; }
.rp-ring-fill--medium { stroke: #F59E0B; }
.rp-ring-fill--high { stroke: #DC2626; }
.rp-ring-fill--critical { stroke: #991B1B; }

.rp-ring-value { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 700; font-family: 'Rajdhani', monospace; color: #182230; }

.rp-risk-card__meta { display: flex; flex-direction: column; gap: 4px; }
.rp-risk-change { font-size: 12px; font-weight: 600; }
.rp-change-up { color: #DC2626; }
.rp-change-down { color: #16A34A; }
.rp-risk-horizon { font-size: 10px; color: #94A3B8; }

.rp-chart-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.rp-chart-card--wide { grid-column: 1 / -1; }
.rp-chart-card { background: #fff; border-radius: 8px; padding: 16px; border: 1px solid #DCE3EC; }
.rp-chart-title { margin: 0 0 8px; font-size: 14px; font-weight: 600; color: #182230; }

.rp-chart-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
  font-size: 13px;
  color: #94A3B8;
}

.rp-info-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.rp-info-card { background: #fff; border-radius: 8px; padding: 16px; border: 1px solid #DCE3EC; }
.rp-info-title { margin: 0 0 12px; font-size: 14px; font-weight: 600; }
.rp-model-info { display: flex; flex-direction: column; gap: 8px; }
.rp-model-row { display: flex; justify-content: space-between; font-size: 12px; }
.rp-model-row span:first-child { color: #52606D; }
.rp-model-row span:last-child { font-weight: 500; color: #182230; }
.rp-status-ok { color: #16A34A; }
.rp-status-warn { color: #F59E0B; }

.rp-safety-notice { margin: 0; font-size: 13px; line-height: 1.6; color: #52606D; }
.rp-updated { margin: 8px 0 0; font-size: 11px; color: #94A3B8; }

.rp-ai-explanation { background: #fff; border-radius: 8px; border: 1px solid #DCE3EC; }
.rp-ai-explanation summary { padding: 12px 16px; font-size: 13px; font-weight: 600; cursor: pointer; color: #52606D; }
.rp-ai-content { padding: 0 16px 16px; }

.rp-contributors-list { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
.rp-contributor-item { display: grid; grid-template-columns: 24px 1fr 60px; gap: 8px; padding: 6px 8px; background: #F8FAFC; border-radius: 4px; font-size: 12px; align-items: center; }
.rp-contributor-rank { width: 20px; height: 20px; display: flex; align-items: center; justify-content: center; background: #E8EEF5; border-radius: 50%; font-size: 10px; font-weight: 600; }
.rp-contributor-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rp-contributor-impact { text-align: right; font-weight: 600; font-family: 'Rajdhani', monospace; }

.rp-no-contributors { font-size: 13px; color: #94A3B8; text-align: center; padding: 16px; }
.rp-ai-disclaimer { margin-top: 12px; padding: 8px 12px; background: #FFFBEB; border: 1px solid #FDE68A; border-radius: 6px; font-size: 12px; color: #92400E; }

@media (max-width: 1200px) { .rp-chart-row { grid-template-columns: 1fr; } .rp-info-row { grid-template-columns: 1fr; } }
</style>
