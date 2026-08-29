<template>
  <div class="disease-trajectory">
    <!-- 时间窗口选择 -->
    <div class="dt-window-selector">
      <span class="dt-window-label">预测窗口</span>
      <button v-for="w in windows" :key="w.value" class="dt-window-btn" :class="{ 'dt-window-btn--active': w.value === selectedWindow }" @click="selectedWindow = w.value">{{ w.label }}</button>
    </div>

    <!-- 主时间线 -->
    <div class="dt-timeline-card">
      <h3 class="dt-card-title">疾病轨迹</h3>
      <ClinicalChart :option="trajectoryChartOption" :loading="loading" :height="300" :updated-at="updatedAt" show-toolbar />
    </div>

    <!-- 器官小多图 + 未来路径 -->
    <div class="dt-row">
      <div class="dt-card">
        <h3 class="dt-card-title">器官轨迹</h3>
        <ClinicalChart :option="organChartOption" :loading="loading" :height="260" />
      </div>
      <div class="dt-card">
        <h3 class="dt-card-title">预测路径</h3>
        <div v-if="forecastPaths.length" class="dt-paths-list">
          <div v-for="(p, idx) in forecastPaths" :key="idx" class="dt-path-item">
            <div class="dt-path-header">
              <span class="dt-path-icon" :class="`dt-path--${p.level}`">●</span>
              <span class="dt-path-name">{{ p.name }}</span>
              <span class="dt-path-prob" :class="`dt-path--${p.level}`">{{ p.probability }}%</span>
            </div>
            <div class="dt-path-bar">
              <div class="dt-path-fill" :class="`dt-fill--${p.level}`" :style="{ width: `${p.probability}%` }"></div>
            </div>
            <span class="dt-path-desc">{{ p.description }}</span>
          </div>
        </div>
        <div v-else class="dt-empty">暂无预测路径数据</div>
      </div>
    </div>

    <div class="dt-disclaimer">
      ⚠ 轨迹预测基于当前数据的模型外推，不代表确定的疾病进程。仅供临床参考。
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useEmbedBridge } from '../../../composables/useEmbedBridge'
import { getAiRiskForecast } from '../../../api'
import ClinicalChart from '../../../components/charts/base/ClinicalChart.vue'

const route = useRoute()
const patientId = computed(() => String(route.params.patientId || ''))

const { sendUpdateTitle, sendReportError } = useEmbedBridge({
  moduleKey: 'disease-trajectory',
  targetOrigin: window.location.origin,
  onPatientContextChanged: () => loadData(),
  onRefresh: () => loadData(),
})

const windows = [
  { value: '6h', label: '6小时' },
  { value: '12h', label: '12小时' },
  { value: '24h', label: '24小时' },
  { value: '72h', label: '72小时' },
]
const selectedWindow = ref('24h')

const loading = ref(false)
const rawData = ref<any>(null)

const updatedAt = computed(() => {
  const t = rawData.value?.model_meta?.prediction_time
  if (!t) return ''
  try { return new Date(t).toLocaleString('zh-CN') } catch { return '' }
})

// ── 轨迹图 ──────────────────────────────────────

const trajectoryChartOption = computed(() => {
  const history = rawData.value?.history_risk_curve || []
  const forecast = rawData.value?.forecast_risk_curve || []
  const all = [...history, ...forecast]
  if (!all.length) return null

  const xData = all.map((p: any) => p.time || p.t || '')
  const yData = all.map((p: any) => Math.round((p.probability || p.value || 0) * 100))
  const historyLen = history.length

  // 分界标记
  const markLine = historyLen > 0 ? {
    data: [{ xAxis: historyLen - 1, label: { formatter: '当前', fontSize: 11 } }],
    lineStyle: { type: 'dashed' as const, color: '#94A3B8' },
  } : undefined

  return {
    tooltip: { trigger: 'axis' as const },
    legend: { data: ['历史风险', '预测轨迹'], top: 0 },
    grid: { left: 12, right: 16, top: 40, bottom: 30, containLabel: true },
    xAxis: { type: 'category' as const, data: xData, axisLabel: { fontSize: 11 } },
    yAxis: { type: 'value' as const, max: 100, axisLabel: { formatter: '{value}%', fontSize: 11 } },
    series: [
      {
        name: '历史风险',
        type: 'line' as const,
        data: yData.map((v: number, i: number) => i < historyLen ? v : null),
        smooth: true,
        lineStyle: { width: 2 },
        areaStyle: { color: 'rgba(37,99,235,0.08)' },
        markLine,
      },
      {
        name: '预测轨迹',
        type: 'line' as const,
        data: yData.map((v: number, i: number) => i >= historyLen ? v : null),
        smooth: true,
        lineStyle: { width: 2, type: 'dashed' as const },
        areaStyle: { color: 'rgba(8,145,178,0.06)' },
      },
    ],
  }
})

// ── 器官轨迹 ────────────────────────────────────

const organChartOption = computed(() => {
  const scores = rawData.value?.organ_risk_scores || {}
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
    tooltip: { trigger: 'axis' as const, axisPointer: { type: 'shadow' as const } },
    grid: { left: 60, right: 16, top: 12, bottom: 12 },
    xAxis: { type: 'value' as const, max: 100, axisLabel: { formatter: '{value}%', fontSize: 11 } },
    yAxis: { type: 'category' as const, data: data.map(d => d.name), axisLabel: { fontSize: 12 } },
    series: [{
      type: 'bar' as const,
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

// ── 预测路径（从horizon_probabilities生成）─────────

const forecastPaths = computed(() => {
  const hps = rawData.value?.horizon_probabilities || []
  if (!hps.length) return []

  return hps.map((hp: any) => {
    const prob = Math.round((hp.probability || 0) * 100)
    const level = prob >= 70 ? 'critical' : prob >= 50 ? 'high' : prob >= 30 ? 'warning' : 'stable'
    const horizon = hp.horizon_hours || hp.horizon || '?'
    return {
      name: `${horizon}小时预测`,
      probability: prob,
      level,
      description: prob >= 70 ? '高危，需密切监护' : prob >= 50 ? '中高风险，建议加强干预' : prob >= 30 ? '中等风险，持续观察' : '低风险，维持当前方案',
    }
  })
})

// ── 加载 ────────────────────────────────────────

async function loadData() {
  if (!patientId.value || loading.value) return
  loading.value = true
  try {
    const res = await getAiRiskForecast(patientId.value)
    rawData.value = res.data || null
  } catch (e: any) {
    sendReportError('LOAD_FAILED', e?.message || '加载疾病轨迹失败')
    rawData.value = null
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  sendUpdateTitle('疾病轨迹')
  loadData()
})
</script>

<style scoped>
.disease-trajectory { display: flex; flex-direction: column; gap: 14px; }

.dt-window-selector { display: flex; align-items: center; gap: 8px; background: #fff; padding: 10px 14px; border-radius: 8px; border: 1px solid #DCE3EC; }
.dt-window-label { font-size: 12px; color: #52606D; font-weight: 500; }
.dt-window-btn { padding: 4px 12px; border-radius: 4px; border: 1px solid #DCE3EC; background: #fff; font-size: 12px; cursor: pointer; transition: all 0.15s; }
.dt-window-btn--active { background: #2563EB; color: #fff; border-color: #2563EB; }

.dt-timeline-card, .dt-card { background: #fff; border-radius: 8px; padding: 16px; border: 1px solid #DCE3EC; }
.dt-card-title { margin: 0 0 12px; font-size: 14px; font-weight: 600; color: #182230; }

.dt-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

.dt-paths-list { display: flex; flex-direction: column; gap: 10px; }
.dt-path-item { display: flex; flex-direction: column; gap: 4px; }
.dt-path-header { display: flex; align-items: center; gap: 6px; }
.dt-path-icon { font-size: 10px; }
.dt-path--stable { color: #16A34A; }
.dt-path--warning { color: #F59E0B; }
.dt-path--high { color: #DC2626; }
.dt-path--critical { color: #991B1B; }
.dt-path-name { font-size: 12px; font-weight: 500; }
.dt-path-prob { font-size: 13px; font-weight: 700; font-family: 'Rajdhani', monospace; margin-left: auto; }
.dt-path-bar { height: 4px; background: #E8EEF5; border-radius: 2px; overflow: hidden; }
.dt-path-fill { height: 100%; border-radius: 2px; transition: width 0.4s ease; }
.dt-fill--stable { background: #16A34A; }
.dt-fill--warning { background: #F59E0B; }
.dt-fill--high { background: #DC2626; }
.dt-fill--critical { background: #991B1B; }
.dt-path-desc { font-size: 11px; color: #94A3B8; }

.dt-empty { text-align: center; padding: 24px; color: #94A3B8; font-size: 13px; }

.dt-disclaimer { padding: 10px 16px; background: #FFFBEB; border: 1px solid #FDE68A; border-radius: 6px; font-size: 12px; color: #92400E; }

@media (max-width: 1200px) { .dt-row { grid-template-columns: 1fr; } }
</style>

