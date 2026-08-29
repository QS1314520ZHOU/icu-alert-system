<template>
  <div class="risk-prediction">
    <!-- 风险指标卡行 -->
    <div class="rp-overview-row">
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
        <ClinicalChart :option="trendChartOption" :loading="loading" :height="280" :updated-at="updatedAt" show-toolbar />
      </div>
    </div>

    <div class="rp-chart-row">
      <div class="rp-chart-card">
        <h3 class="rp-chart-title">器官风险</h3>
        <ClinicalChart :option="organChartOption" :loading="loading" :height="260" />
      </div>
      <div class="rp-chart-card">
        <h3 class="rp-chart-title">特征贡献</h3>
        <ClinicalChart :option="contributorChartOption" :loading="loading" :height="260" />
      </div>
    </div>

    <!-- 模型信息 -->
    <div class="rp-info-row">
      <div class="rp-info-card">
        <h3 class="rp-info-title">模型信息</h3>
        <div class="rp-model-info">
          <div class="rp-model-row"><span>预测来源</span><span>{{ displayLabel }}</span></div>
          <div class="rp-model-row"><span>模型名称</span><span>{{ modelMeta.model_name || '—' }}</span></div>
          <div class="rp-model-row"><span>模型版本</span><span>{{ modelMeta.model_version || '—' }}</span></div>
          <div class="rp-model-row"><span>校准版本</span><span>{{ modelMeta.calibration_version || '—' }}</span></div>
          <div class="rp-model-row"><span>模型状态</span><span :class="modelMeta.model_available ? 'rp-status-ok' : 'rp-status-warn'">{{ modelMeta.model_status || '—' }}</span></div>
          <div v-if="modelMeta.fallback_used" class="rp-model-row"><span>降级原因</span><span class="rp-status-warn">{{ modelMeta.fallback_reason || '使用规则兜底' }}</span></div>
        </div>
      </div>
      <div class="rp-info-card">
        <h3 class="rp-info-title">安全声明</h3>
        <p class="rp-safety-notice">{{ safetyNotice }}</p>
        <p class="rp-updated">预测时间：{{ updatedAt }}</p>
      </div>
    </div>

    <!-- AI解释折叠区 -->
    <details class="rp-ai-explanation">
      <summary>AI解释与证据（{{ topContributors.length }}个因素）</summary>
      <div class="rp-ai-content">
        <div v-if="topContributors.length" class="rp-contributors-list">
          <div v-for="(c, idx) in topContributors" :key="idx" class="rp-contributor-item">
            <span class="rp-contributor-rank">{{ idx + 1 }}</span>
            <span class="rp-contributor-name">{{ c.feature || c.name || '' }}</span>
            <span class="rp-contributor-impact" :class="c.direction > 0 ? 'rp-change-up' : 'rp-change-down'">
              {{ c.direction > 0 ? '↑' : '↓' }}{{ (Math.abs(c.impact || c.weight || 0) * 100).toFixed(1) }}%
            </span>
          </div>
        </div>
        <p v-else class="rp-no-contributors">暂无特征贡献数据</p>
        <p class="rp-ai-disclaimer">⚠ 以上为模型输入特征的贡献度分析，不代表因果关系。预测结果仅供临床决策参考，不替代医生判断。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
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

const horizonProbabilities = computed(() => rawData.value?.horizon_probabilities || [])

const riskCards = computed(() => {
  const hps = horizonProbabilities.value
  if (!hps.length && !rawData.value?.current_probability) return []
  const cards = []
  if (rawData.value?.current_probability != null) {
    const v = Math.round((rawData.value.current_probability || 0) * 100)
    cards.push({ key: 'current', label: '当前风险', value: v, change: null, horizon: '当前', level: getRiskLevel(v) })
  }
  for (const hp of hps) {
    const v = Math.round((hp.probability || 0) * 100)
    const prev = hp.previous_probability != null ? Math.round(hp.previous_probability * 100) : null
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

const trendChartOption = computed(() => {
  const history = rawData.value?.history_risk_curve || []
  const forecast = rawData.value?.forecast_risk_curve || []
  const all = [...history, ...forecast]
  if (!all.length) return null

  const xData = all.map((p: any) => p.time || p.t || '')
  const yData = all.map((p: any) => Math.round((p.probability || p.value || 0) * 100))
  const isHistory = all.map((_: any, i: number) => i < history.length)

  // 阈值线
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
      ...(thresholds.length ? [{
        name: '高风险阈值',
        type: 'line',
        data: xData.map(() => Math.round((thresholds[0]?.value || 0.6) * 100)),
        lineStyle: { color: '#DC2626', type: 'dotted', width: 1 },
        symbol: 'none',
      }] : []),
    ],
  }
})

const organChartOption = computed(() => {
  const scores = organRiskScores.value
  const keys = Object.keys(scores)
  if (!keys.length) return null

  const labels: Record<string, string> = {
    respiratory: '呼吸', cardiovascular: '循环', circulatory: '循环',
    renal: '肾脏', coagulation: '凝血', hepatic: '肝脏',
    neurological: '神经', neurologic: '神经', infection: '感染',
  }

  const data = keys.map(k => ({
    name: labels[k] || k,
    value: Math.round((scores[k]?.score || scores[k] || 0) * 100),
  })).sort((a, b) => b.value - a.value)

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

const contributorChartOption = computed(() => {
  const contribs = topContributors.value
  if (!contribs.length) return null

  const data = contribs.slice(0, 8).map((c: any) => ({
    name: c.feature || c.name || '',
    value: Math.abs(c.weight || c.impact || 0),
    direction: c.direction || (c.weight > 0 ? 1 : -1),
  }))

  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 120, right: 16, top: 12, bottom: 12 },
    xAxis: { type: 'value', axisLabel: { fontSize: 11 } },
    yAxis: { type: 'category', data: data.map(d => d.name), axisLabel: { fontSize: 11 } },
    series: [{
      type: 'bar',
      data: data.map(d => ({
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

