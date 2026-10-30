<template>
  <div class="risk-prediction">
    <!-- 状态提示区 -->
    <div v-if="(!modelAvailable && !isRuleEstimate) || (modelAvailable && !calculable) || hasScaleMissing" class="rp-alerts">
      <div v-if="!modelAvailable && !isRuleEstimate" class="rp-alert rp-alert--info">
        <span class="rp-alert__icon">ℹ️</span>
        <span class="rp-alert__text">{{ modelUnavailableReason }}</span>
      </div>
      <div v-else-if="!calculable" class="rp-alert rp-alert--warning">
        <span class="rp-alert__icon">⚠️</span>
        <span class="rp-alert__text">当前无法评估风险等级，数据不足或模型未返回有效结果。</span>
      </div>
      <div v-if="hasScaleMissing" class="rp-alert rp-alert--warning">
        <span class="rp-alert__icon">⚠️</span>
        <span class="rp-alert__text">风险值量纲缺失，当前无法展示部分数据。请联系管理员确认后端返回的 scale 字段。</span>
      </div>
    </div>

    <!-- 结论先行 -->
    <section class="rp-brief">
      <header class="rp-brief__head">
        <span>风险预测结论</span>
        <span class="rp-brief__src">{{ displayLabel }}</span>
      </header>
      <div class="rp-brief__body">
        <div class="rp-brief__main">
          <span class="rp-brief__level" :class="`rp-lv--${briefLevel.tone}`">{{ briefLevel.text }}</span>
          <p class="rp-brief__headline">{{ briefHeadline }}</p>
          <div v-if="riskCards.length" class="rp-brief__chips">
            <span v-for="card in riskCards" :key="card.key" class="rp-brief__chip" :class="`rp-chip--${chipTone(card.value)}`">
              {{ card.horizon === '当前' ? '当前' : `${card.horizon}后` }} <b>{{ card.value }}{{ isRuleEstimate ? '' : '%' }}</b>
            </span>
          </div>
          <p class="rp-brief__meta">
            <template v-if="isRuleEstimate">规则风险指数 0–100，非概率；</template>
            <template v-if="updatedAt">更新于 {{ updatedAt }}</template>
          </p>
        </div>
        <div v-if="topContributors.length" class="rp-brief__side">
          <div class="rp-brief__side-title">主要驱动因素</div>
          <ol class="rp-brief__drivers">
            <li v-for="(c, i) in topContributors.slice(0, 4)" :key="i">
              <b>{{ c.feature || c.name }}</b><span v-if="c.evidence">{{ c.evidence }}</span>
            </li>
          </ol>
        </div>
      </div>
    </section>

    <!-- 主内容区：左侧风险概览 + 右侧趋势图 -->
    <div v-if="trendChartOption" class="rp-main-layout rp-main-layout--single">
      <!-- 右侧：趋势图 -->
      <div class="rp-trend-panel">
        <div class="rp-panel-header">
          <h3 class="rp-panel-title">风险趋势</h3>
          <span v-if="updatedAt" class="rp-panel-time">更新于 {{ updatedAt }}</span>
        </div>
        <div v-if="trendChartOption" class="rp-chart-container">
          <ClinicalChart :option="trendChartOption" :loading="loading" :height="240" show-toolbar />
        </div>
        <div v-else-if="!loading" class="rp-empty-state">暂无风险趋势数据</div>
      </div>
    </div>

    <!-- 图表行：器官风险 + 特征贡献 -->
    <div v-if="hasAnyChart" class="rp-charts-row">
      <div class="rp-chart-card">
        <div class="rp-panel-header">
          <h3 class="rp-panel-title">器官风险（相对强度）</h3>
        </div>
        <div v-if="organChartOption" class="rp-chart-container">
          <ClinicalChart :option="organChartOption" :loading="loading" :height="220" />
        </div>
        <div v-else-if="!loading" class="rp-empty-state">
          <span v-if="!modelAvailable">当前无模型器官风险数据</span>
          <span v-else>暂无器官风险数据</span>
        </div>
      </div>
      <div class="rp-chart-card">
        <div class="rp-panel-header">
          <h3 class="rp-panel-title">特征贡献</h3>
        </div>
        <div v-if="contributorChartOption" class="rp-chart-container">
          <ClinicalChart :option="contributorChartOption" :loading="loading" :height="220" />
        </div>
        <div v-else-if="!loading" class="rp-empty-state">当前无模型贡献度数据</div>
      </div>
    </div>

    <!-- 信息区：模型信息/规则信息 + 安全声明 -->
    <div class="rp-info-row">
      <div class="rp-info-card">
        <div class="rp-panel-header">
          <h3 class="rp-panel-title">{{ !modelAvailable && ruleInfo ? '规则估算信息' : '模型信息' }}</h3>
        </div>
        <div v-if="!modelAvailable && ruleInfo" class="rp-info-grid">
          <div v-if="ruleInfo.rule_name" class="rp-info-item">
            <span class="rp-info-label">规则名称</span>
            <span class="rp-info-value">{{ ruleInfo.rule_name }}</span>
          </div>
          <div v-if="ruleInfo.trigger_indicator" class="rp-info-item">
            <span class="rp-info-label">触发指标</span>
            <span class="rp-info-value">{{ ruleInfo.trigger_indicator }}</span>
          </div>
          <div v-if="ruleInfo.threshold" class="rp-info-item">
            <span class="rp-info-label">阈值</span>
            <span class="rp-info-value">{{ ruleInfo.threshold }}</span>
          </div>
          <div v-if="ruleInfo.rule_version" class="rp-info-item">
            <span class="rp-info-label">规则版本</span>
            <span class="rp-info-value">{{ ruleInfo.rule_version }}</span>
          </div>
          <div v-if="ruleInfo.data_time" class="rp-info-item">
            <span class="rp-info-label">数据时间</span>
            <span class="rp-info-value">{{ formatTime(ruleInfo.data_time) }}</span>
          </div>
          <div v-if="ruleInfo.evidence" class="rp-info-item">
            <span class="rp-info-label">支持证据</span>
            <span class="rp-info-value">{{ ruleInfo.evidence }}</span>
          </div>
        </div>
        <div v-else-if="modelAvailable" class="rp-info-grid">
          <div class="rp-info-item">
            <span class="rp-info-label">预测来源</span>
            <span class="rp-info-value">{{ displayLabel }}</span>
          </div>
          <div class="rp-info-item">
            <span class="rp-info-label">模型名称</span>
            <span class="rp-info-value">{{ modelNameDisplay }}</span>
          </div>
          <div class="rp-info-item">
            <span class="rp-info-label">模型版本</span>
            <span class="rp-info-value">{{ modelVersionDisplay }}</span>
          </div>
          <div class="rp-info-item">
            <span class="rp-info-label">校准版本</span>
            <span class="rp-info-value">{{ calibrationVersionDisplay }}</span>
          </div>
          <div class="rp-info-item">
            <span class="rp-info-label">模型状态</span>
            <span class="rp-info-value" :class="modelStatusClass">{{ modelStatusDisplay }}</span>
          </div>
          <div v-if="modelMeta.fallback_used" class="rp-info-item">
            <span class="rp-info-label">降级原因</span>
            <span class="rp-info-value rp-status-warn">{{ fallbackReasonDisplay }}</span>
          </div>
        </div>
        <div v-else class="rp-info-grid">
          <div class="rp-info-item">
            <span class="rp-info-label">预测来源</span>
            <span class="rp-info-value">{{ displayLabel }}</span>
          </div>
          <div class="rp-info-item">
            <span class="rp-info-label">模型状态</span>
            <span class="rp-info-value rp-status-warn">{{ modelStatusDisplay }}</span>
          </div>
          <div v-if="modelMeta.fallback_reason" class="rp-info-item">
            <span class="rp-info-label">降级原因</span>
            <span class="rp-info-value rp-status-warn">{{ fallbackReasonDisplay }}</span>
          </div>
        </div>
      </div>
      <div class="rp-info-card">
        <div class="rp-panel-header">
          <h3 class="rp-panel-title">安全声明</h3>
        </div>
        <p class="rp-safety-notice">{{ safetyNotice }}</p>
        <p class="rp-updated">预测时间：{{ updatedAt }}</p>
      </div>
    </div>

    <!-- AI解释折叠区 -->
    <details v-if="topContributors.length" class="rp-ai-explanation">
      <summary class="rp-ai-summary">
        <span class="rp-ai-summary__icon">🤖</span>
        <span>AI解释与证据（{{ topContributors.length }}个因素）</span>
      </summary>
      <div class="rp-ai-content">
        <div class="rp-contributors-list">
          <div v-for="(c, idx) in topContributors" :key="idx" class="rp-contributor-item">
            <span class="rp-contributor-rank" :class="(c.direction ?? 1) >= 0 ? 'rp-rank-up' : 'rp-rank-down'">{{ Number(idx) + 1 }}</span>
            <span class="rp-contributor-name">{{ c.feature || c.name || '' }}<small v-if="c.evidence" class="rp-contributor-ev">{{ c.evidence }}</small></span>
            <span class="rp-contributor-impact" :class="(c.direction ?? 1) >= 0 ? 'rp-change-up' : 'rp-change-down'">
              {{ (c.direction ?? 1) >= 0 ? '↑' : '↓' }}{{ (Math.abs(contribWeight(c)) * 100).toFixed(1) }}%
            </span>
          </div>
        </div>
        <div class="rp-ai-disclaimer">
          <span class="rp-ai-disclaimer__icon">⚠️</span>
          <span>以上为模型输入特征的贡献度分析，不代表因果关系。预测结果仅供临床决策参考，不替代医生判断。</span>
        </div>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
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

const displayLabel = computed(() => {
  if (isRuleEstimate.value) return '规则估算风险，非AI模型预测'
  return rawData.value?.display_label || '风险预测'
})
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

/** Can the risk be calculated (model available AND probability is valid) */
const calculable = computed(() => rawData.value?.calculable === true)

/** Is this a rule estimate (rule_estimate) */
const isRuleEstimate = computed(() => rawData.value?.prediction_source === 'rule_estimate')

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

/** 是否存在量纲缺失的数据（有值但无 scale） */
const hasScaleMissing = computed(() => {
  const hps = horizonProbabilities.value
  if (rawData.value?.current_probability != null && !rawData.value?.probability_scale) return true
  if (hps.some((hp: any) => hp.probability != null && !hp.scale)) return true
  const history = rawData.value?.history_risk_curve || []
  const forecast = rawData.value?.forecast_risk_curve || []
  if ([...history, ...forecast].some((p: any) => (p.probability ?? p.value) != null && !p.scale)) return true
  // 检查器官风险
  const organs = Object.values(rawData.value?.organ_risk_scores || {})
  if (organs.some((item: any) => (item?.score ?? item) != null && !item?.scale)) return true
  // 检查阈值
  const thresholds = rawData.value?.threshold_bands || []
  if (thresholds.some((item: any) => item?.value != null && !item?.scale)) return true
  return false
})

/**
 * 显式量纲转换：将风险值转为百分数 (0-100)。
 * 后端必须返回 scale 字段标明量纲；缺少 scale 时返回 null，禁止猜测量纲。
 * 禁止：猜测量纲、截断超限值、null 显示为 0%。
 */
function toPercent(
  value: unknown,
  scale: 'probability_0_1' | 'percent_0_100' | string | undefined,
): number | null {
  if (value == null || value === '') return null
  const n = Number(value)
  if (!Number.isFinite(n)) return null

  if (scale === 'probability_0_1') {
    return n >= 0 && n <= 1 ? Math.round(n * 100) : null
  }

  if (scale === 'percent_0_100') {
    return n >= 0 && n <= 100 ? Math.round(n) : null
  }

  // 缺少显式 scale：不猜测，返回 null
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

const topContributors = computed<any[]>(() => rawData.value?.top_contributors || [])

const organRiskScores = computed(() => rawData.value?.organ_risk_scores || {})

// ── 图表 option ──────────────────────────────────

const trendChartOption = computed<any>(() => {
  const history = rawData.value?.history_risk_curve || []
  const forecast = rawData.value?.forecast_risk_curve || []
  const all = [...history, ...forecast]
  if (!all.length) return null

  // 只保留有显式 scale 的数据点，null 表示量纲缺失
  const yData = all.map((p: any) => toPercent(p.probability ?? p.value, p.scale))
  const xData = all.map((p: any) => p.label || shortTime(p.time || p.t || ''))
  const unit = isRuleEstimate.value ? '' : '%'
  const isHistory = all.map((_: any, i: number) => i < history.length)

  // 如果所有数据点都为 null（全部量纲缺失），不展示图表
  if (yData.every((v: number | null) => v == null)) return null

  const thresholds = rawData.value?.threshold_bands || []
  const thresholdValue = thresholds.length && thresholds[0]?.value != null
    ? toPercent(thresholds[0]?.value, thresholds[0]?.scale)
    : null

  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['历史风险', '预测风险', ...(thresholdValue != null ? ['高风险阈值'] : [])], top: 0 },
    grid: { left: 12, right: 16, top: 40, bottom: 30, containLabel: true },
    xAxis: { type: 'category', data: xData, axisLabel: { fontSize: 11 } },
    yAxis: { type: 'value', max: 100, axisLabel: { formatter: `{value}${unit}`, fontSize: 11 } },
    series: [
      {
        name: '历史风险',
        type: 'line',
        data: yData.map((v: number | null, i: number) => isHistory[i] ? v : null),
        smooth: true,
        lineStyle: { width: 2 },
        areaStyle: { color: 'rgba(37,99,235,0.08)' },
        connectNulls: false,
      },
      {
        name: '预测风险',
        type: 'line',
        data: yData.map((v: number | null, i: number) => (!isHistory[i] || i === history.length - 1) ? v : null),
        smooth: true,
        lineStyle: { width: 2, type: 'dashed' },
        areaStyle: { color: 'rgba(37,99,235,0.04)' },
        connectNulls: false,
      },
      ...(thresholdValue != null ? [{
        name: '高风险阈值',
        type: 'line',
        data: xData.map(() => thresholdValue),
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

  const data = keys.map(k => {
    const v = toPercent(scores[k]?.score ?? scores[k], scores[k]?.scale)
    return { name: labels[k] || ORGAN_LABEL_FALLBACK, value: v }
  }).filter(d => d.value != null && d.value > 0).sort((a, b) => (b.value ?? 0) - (a.value ?? 0))

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
        value: d.value ?? 0,
        itemStyle: {
          color: (d.value ?? 0) >= 80 ? '#991B1B' : (d.value ?? 0) >= 60 ? '#DC2626' : (d.value ?? 0) >= 40 ? '#F59E0B' : '#16A34A',
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
    value: Math.abs(contribWeight(c)),
    direction: c.direction || (contribWeight(c) >= 0 ? 1 : -1),
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

// ── 结论卡 ──────────────────────────────────────
const LEVEL_TEXT: Record<string, { text: string; tone: string }> = {
  critical: { text: '危急', tone: 'crit' },
  high: { text: '高风险', tone: 'crit' },
  warning: { text: '警戒', tone: 'warn' },
  medium: { text: '中风险', tone: 'warn' },
  moderate: { text: '中风险', tone: 'warn' },
  low: { text: '低风险', tone: 'ok' },
}
const briefLevel = computed(() => {
  if (!calculable.value) return { text: '无法评估', tone: 'muted' }
  const lv = String(rawData.value?.risk_level || '').toLowerCase()
  return LEVEL_TEXT[lv] || { text: '已评估', tone: 'muted' }
})
const briefHeadline = computed(() => {
  if (loading.value && !rawData.value) return '正在加载风险评估…'
  if (!rawData.value) return '风险服务暂不可用，请稍后刷新。'
  if (!calculable.value) {
    return modelAvailable.value
      ? '当前无法评估风险等级：数据不足或模型未返回有效结果。'
      : `当前无法评估风险等级：${modelUnavailableReason.value}。`
  }
  const summary = String(rawData.value?.risk_summary || '').trim()
  return summary || '已完成风险评估，详见下方趋势与驱动因素。'
})
const hasAnyChart = computed(() => !!(riskCards.value.length || trendChartOption.value || organChartOption.value || contributorChartOption.value))
function chipTone(v: number) {
  if (v >= 64) return 'crit'
  if (v >= 42) return 'warn'
  return 'ok'
}
function shortTime(t: string) {
  const d = new Date(t)
  if (!t || Number.isNaN(d.getTime())) return t
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
function contribWeight(c: any): number {
  const n = Number(c?.impact ?? c?.weight ?? c?.score ?? 0)
  return Number.isFinite(n) ? n : 0
}

onMounted(() => {
  sendUpdateTitle('风险预测')
  loadData()
})

// 直接渲染模式下组件会被复用：切换患者时路由参数变化需手动重载
watch(patientId, (id, prev) => {
  if (id && id !== prev) loadData()
})
</script>

<style scoped>
.rp-main-layout--single { grid-template-columns: 1fr !important; min-height: 0 !important }
.rp-brief { background: #fff; border: 1px solid #E6E5E3; border-radius: 10px; overflow: hidden }
.rp-brief__head { height: 38px; background: #5392FF; color: #fff; display: flex; align-items: center; justify-content: space-between; padding: 0 16px; font-size: 14px; font-weight: 600 }
.rp-brief__src { font-size: 12px; font-weight: 400; background: rgba(255,255,255,0.18); padding: 2px 8px; border-radius: 999px }
.rp-brief__body { display: flex; gap: 20px; padding: 14px 16px }
.rp-brief__main { flex: 1 1 auto; min-width: 0 }
.rp-brief__level { display: inline-block; font-size: 13px; font-weight: 600; padding: 2px 10px; border-radius: 999px; border: 1px solid #E6E5E3; background: #FAFAF9; color: #57534E }
.rp-lv--crit, .rp-chip--crit { background: #FEF2F2 !important; color: #B91C1C !important; border-color: #FCA5A5 !important }
.rp-lv--warn, .rp-chip--warn { background: #FFFBEB !important; color: #B45309 !important; border-color: #FCD34D !important }
.rp-lv--ok, .rp-chip--ok { background: #E7F5EE !important; color: #2F7D55 !important; border-color: #A7D9BF !important }
.rp-brief__headline { margin: 8px 0 0; font-size: 15px; font-weight: 600; color: #1C1917; line-height: 1.5 }
.rp-brief__chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px }
.rp-brief__chip { font-size: 12px; padding: 2px 10px; border-radius: 999px; border: 1px solid #E6E5E3 }
.rp-brief__chip b { font-size: 14px; margin-left: 2px }
.rp-brief__meta { margin: 8px 0 0; font-size: 12px; color: #A8A29E }
.rp-brief__side { flex: 0 0 340px; border-left: 1px solid #F0EFED; padding-left: 16px }
.rp-brief__side-title { font-size: 13px; font-weight: 600; color: #1C1917; padding-left: 8px; border-left: 3px solid #5392FF; line-height: 1.2 }
.rp-brief__drivers { margin: 8px 0 0; padding-left: 18px; font-size: 13px; color: #44403C }
.rp-brief__drivers li { margin: 3px 0 }
.rp-brief__drivers span { margin-left: 6px; color: #78716C; font-size: 12px }
.rp-contributor-ev { display: block; font-size: 12px; color: #78716C; font-weight: 400 }
@media (max-width: 900px) { .rp-brief__body { flex-direction: column } .rp-brief__side { flex-basis: auto; border-left: 0; padding-left: 0 } }
.risk-prediction { display: flex; flex-direction: column; gap: 20px; padding: 4px }

/* ── 状态提示 ── */ .rp-alerts { display: flex; flex-direction: column; gap: 8px }
.rp-alert { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-radius: var(--radius-md, 6px); font-size: var(--text-body, 13px) }
.rp-alert--info { background: var(--color-primary-bg, #E8F0FE); border: 1px solid var(--color-info-bg, #EAF4FF); color: var(--color-primary, #2F6FED) }
.rp-alert--warning { background: var(--color-warning-soft-bg, #FFF9D8); border: 1px solid var(--color-warning-soft-border, #FFE58F); color: var(--color-warning, #B54708) }
.rp-alert__icon { font-size: 16px }

/* ── 主布局：左侧风险概览 + 右侧趋势图 ── */ .rp-main-layout { display: grid; grid-template-columns: 320px 1fr; gap: 16px; min-height: 300px }
.rp-overview-panel, .rp-trend-panel, .rp-chart-card, .rp-info-card { background: var(--color-bg-surface, #FFFFFF); border-radius: var(--radius-lg, 10px); border: 1px solid var(--color-border, #E5E7EB); overflow: hidden }
.rp-panel-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid var(--color-border, #E5E7EB) }
.rp-panel-title { margin: 0; font-size: var(--text-body, 13px); font-weight: 600; color: var(--color-text-primary, #111827) }
.rp-panel-badge { font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF); background: var(--color-bg-surface-secondary, #F1F4F8); padding: 2px 8px; border-radius: var(--radius-tag, 4px) }
.rp-panel-time { font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF) }

/* ── 风险指标卡片 ── */ .rp-risk-cards { display: flex; flex-direction: column; gap: 12px; padding: 16px }
.rp-risk-card { display: flex; align-items: center; gap: 14px; padding: 14px; background: var(--color-bg-surface-secondary, #F1F4F8); border-radius: var(--radius-lg, 10px); border: 1px solid var(--color-border, #E5E7EB); transition: all 0.2s }
.rp-risk-card:hover { background: var(--color-bg-surface, #FFFFFF); }
.rp-risk-card--critical { border-left: 3px solid var(--color-critical, #D92D20) }
.rp-risk-card--high { border-left: 3px solid var(--color-danger, #D92D20) }
.rp-risk-card--medium { border-left: 3px solid var(--color-warning, #B54708) }
.rp-risk-card--low { border-left: 3px solid var(--color-normal, #12A66A) }
.rp-risk-card--stable { border-left: 3px solid var(--color-normal, #12A66A) }
.rp-risk-card__ring { width: 52px; height: 52px; position: relative; flex-shrink: 0 }
.rp-risk-card__ring svg { width: 100%; height: 100%; transform: rotate(-90deg) }
.rp-ring-bg { fill: none; stroke: var(--color-bg-inset, #E9EEF5); stroke-width: 3.5 }
.rp-ring-fill { fill: none; stroke-width: 3.5; stroke-linecap: round; transition: stroke-dasharray 0.6s ease }
.rp-ring-fill--stable, .rp-ring-fill--low { stroke: var(--color-normal, #12A66A) }
.rp-ring-fill--medium { stroke: var(--color-warning, #B54708) }
.rp-ring-fill--high { stroke: var(--color-danger, #D92D20) }
.rp-ring-fill--critical { stroke: var(--color-critical, #D92D20) }
.rp-ring-value { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: var(--text-section-title, 15px); font-weight: 700; font-family: 'Rajdhani', monospace; color: var(--color-text-primary, #111827) }
.rp-risk-card__info { flex: 1; min-width: 0 }
.rp-risk-card__label { display: block; font-size: var(--text-caption, 12px); font-weight: 500; color: var(--color-text-tertiary, #9CA3AF); margin-bottom: 4px }
.rp-risk-card__meta { display: flex; align-items: center; gap: 8px }
.rp-risk-change { font-size: var(--text-body, 13px); font-weight: 600; font-family: 'Rajdhani', monospace }
.rp-change-up { color: var(--color-danger, #D92D20) }
.rp-change-down { color: var(--color-normal, #12A66A) }
.rp-risk-horizon { font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF) }

/* ── 图表区 ── */ .rp-chart-container { padding: 12px }
.rp-charts-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px }
.rp-empty-state { display: flex; align-items: center; justify-content: center; min-height: 160px; font-size: var(--text-body, 13px); color: var(--color-text-tertiary, #9CA3AF) }

/* ── 信息区 ── */ .rp-info-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px }
.rp-info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; padding: 16px }
.rp-info-item { display: flex; flex-direction: column; gap: 4px }
.rp-info-label { font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF); font-weight: 500 }
.rp-info-value { font-size: var(--text-body, 13px); font-weight: 500; color: var(--color-text-primary, #111827) }
.rp-status-ok { color: var(--color-normal, #12A66A) }
.rp-status-warn { color: var(--color-warning, #B54708) }
.rp-safety-notice { margin: 0; padding: 16px; font-size: var(--text-body, 13px); line-height: 1.6; color: var(--color-text-secondary, #4B5563) }
.rp-updated { margin: 0; padding: 0 16px 12px; font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF) }

/* ── AI解释区 ── */ .rp-ai-explanation { background: var(--color-bg-surface, #FFFFFF); border-radius: var(--radius-lg, 10px); border: 1px solid var(--color-border, #E5E7EB); overflow: hidden }
.rp-ai-summary { display: flex; align-items: center; gap: 8px; padding: 14px 18px; font-size: var(--text-body, 13px); font-weight: 600; cursor: pointer; color: var(--color-text-secondary, #4B5563); list-style: none }
.rp-ai-summary::-webkit-details-marker { display: none }
.rp-ai-summary__icon { font-size: 16px }
.rp-ai-content { padding: 0 18px 18px }
.rp-contributors-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px }
.rp-contributor-item { display: grid; grid-template-columns: 28px 1fr 70px; gap: 10px; padding: 10px 12px; background: var(--color-bg-surface-secondary, #F1F4F8); border-radius: var(--radius-md, 6px); font-size: var(--text-caption, 12px); align-items: center }
.rp-contributor-rank { width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; border-radius: 50%; font-size: var(--text-caption, 12px); font-weight: 600 }
.rp-rank-up { background: var(--color-critical-bg, #FEECEB); color: var(--color-danger, #D92D20) }
.rp-rank-down { background: var(--color-normal-bg, #E8F7F0); color: var(--color-normal, #12A66A) }
.rp-contributor-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--color-text-secondary, #4B5563) }
.rp-contributor-impact { text-align: right; font-weight: 600; font-family: 'Rajdhani', monospace; font-size: var(--text-body, 13px) }
.rp-ai-disclaimer { display: flex; align-items: flex-start; gap: 8px; padding: 12px; background: var(--color-warning-soft-bg, #FFF9D8); border: 1px solid var(--color-warning-soft-border, #FFE58F); border-radius: var(--radius-md, 6px); font-size: var(--text-caption, 12px); color: var(--color-warning, #B54708); line-height: 1.5 }
.rp-ai-disclaimer__icon { font-size: 14px; flex-shrink: 0 }

/* ── 响应式 ── */

@media (max-width: 1200px) {.rp-main-layout { grid-template-columns: 1fr }
.rp-charts-row, .rp-info-row { grid-template-columns: 1fr }

}

</style>
