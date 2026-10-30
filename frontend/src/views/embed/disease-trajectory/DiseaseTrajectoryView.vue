<template>
  <div class="disease-trajectory">
    <!-- 时间窗口选择 -->
    <div class="dt-window-selector">
      <span class="dt-window-label">回看历史</span>
      <button v-for="w in windows" :key="w.value" class="dt-window-btn" :class="{ 'dt-window-btn--active': w.value === selectedWindow }" @click="selectedWindow = w.value">{{ w.label }}</button>
      <span class="dt-source" :class="sourceTone">{{ sourceLabel }}</span>
      <span v-if="currentPct !== null" class="dt-current">当前风险 <b>{{ currentPct }}%</b></span>
    </div>
    <div v-if="scaleMissing" class="dt-warn">部分风险值缺少量纲（scale），已按“无数据”处理，不做推测。</div>

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
              <span class="dt-path-prob" :class="`dt-path--${p.level}`">{{ p.probability === null ? '无数据' : `${p.probability}%` }}</span>
            </div>
            <div class="dt-path-bar">
              <div class="dt-path-fill" :class="`dt-fill--${p.level}`" :style="{ width: `${p.probability ?? 0}%` }"></div>
            </div>
            <span class="dt-path-desc">{{ p.description }}</span>
          </div>
        </div>
        <div v-else class="dt-empty">暂无预测路径数据</div>
        <p class="dt-band-note">分级：≥70% 高危 · 50–69% 中高 · 30–49% 中等 · &lt;30% 低</p>
      </div>
    </div>

    <div v-if="contributors.length" class="dt-card">
      <h3 class="dt-card-title">轨迹的主要驱动因素</h3>
      <div class="dt-contrib-list">
        <div v-for="(c, idx) in contributors" :key="idx" class="dt-contrib">
          <span class="dt-contrib-name">{{ c.name }}</span>
          <span v-if="c.value" class="dt-contrib-val">{{ c.value }}</span>
          <span class="dt-contrib-dir" :class="c.up ? 'dt-path--high' : 'dt-path--stable'">{{ c.up ? '推高风险' : '降低风险' }}</span>
          <span v-if="c.impact" class="dt-contrib-impact">{{ c.impact }}</span>
        </div>
      </div>
    </div>

    <div class="dt-disclaimer">
      ⚠ 轨迹预测基于当前数据的模型外推，不代表确定的疾病进程。仅供临床参考。
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
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

/** 与风险预测页一致：必须有显式 scale 才换算，缺失返回 null，禁止把 null 画成 0% */
function toPercent(value: unknown, scale: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const n = Number(value)
  if (!Number.isFinite(n)) return null
  if (scale === 'probability_0_1') return n >= 0 && n <= 1 ? Math.round(n * 100) : null
  if (scale === 'percent_0_100') return n >= 0 && n <= 100 ? Math.round(n) : null
  return null
}
const WINDOW_HOURS: Record<string, number> = { '6h': 6, '12h': 12, '24h': 24, '72h': 72 }

const currentPct = computed(() => toPercent(rawData.value?.current_probability, rawData.value?.probability_scale))
const sourceLabel = computed(() => {
  const d = rawData.value
  if (!d) return ''
  if (d.is_model_prediction) return `模型预测${d.model_name ? ` · ${d.model_name}${d.model_version ? ` v${d.model_version}` : ''}` : ''}`
  if (d.is_rule_estimate) return '规则估算（非模型）'
  if (d.fallback_used) return `降级估算${d.fallback_reason ? `：${d.fallback_reason}` : ''}`
  return d.prediction_source || ''
})
const sourceTone = computed(() => (rawData.value?.is_model_prediction ? 'dt-source--model' : 'dt-source--rule'))
const scaleMissing = computed(() => {
  const d = rawData.value
  if (!d) return false
  const pts = [...(d.history_risk_curve || []), ...(d.forecast_risk_curve || []), ...(d.horizon_probabilities || [])]
  return pts.some((p: any) => (p?.probability ?? p?.value) != null && !p?.scale)
})

const contributors = computed(() =>
  (Array.isArray(rawData.value?.top_contributors) ? rawData.value.top_contributors : []).slice(0, 6).map((c: any) => {
    const imp = Number(c?.contribution ?? c?.impact ?? c?.shap ?? c?.weight)
    const up = Number(c?.direction ?? imp) >= 0
    return {
      name: c?.feature || c?.name || '—',
      value: c?.value !== undefined && c?.value !== null ? `当前 ${c.value}${c.unit || ''}` : '',
      up,
      impact: Number.isFinite(imp) ? `贡献 ${imp > 0 ? '+' : ''}${Math.abs(imp) < 1 ? imp.toFixed(3) : imp.toFixed(1)}` : '',
    }
  }),
)

const updatedAt = computed(() => {
  const t = rawData.value?.model_meta?.prediction_time
  if (!t) return ''
  try { return new Date(t).toLocaleString('zh-CN') } catch { return '' }
})

// ── 轨迹图 ──────────────────────────────────────

const trajectoryChartOption = computed(() => {
  const hours = WINDOW_HOURS[selectedWindow.value] || 24
  const cutoff = Date.now() - hours * 3600 * 1000
  const history = (rawData.value?.history_risk_curve || []).filter((p: any) => {
    const t = new Date(p?.time || p?.t || '').getTime()
    return !Number.isFinite(t) || t >= cutoff
  })
  const forecast = rawData.value?.forecast_risk_curve || []
  const all = [...history, ...forecast]
  if (!all.length) return null

  const fmtX = (t: any) => {
    const d = new Date(t)
    if (Number.isNaN(d.getTime())) return String(t || '')
    return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  }
  const xData = all.map((p: any) => fmtX(p.time || p.t || ''))
  const yData: (number | null)[] = all.map((p: any) => toPercent(p.probability ?? p.value, p.scale))
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
        data: yData.map((v, i) => i < historyLen ? v : null),
        connectNulls: false,
        smooth: true,
        lineStyle: { width: 2 },
        areaStyle: { color: 'rgba(37,99,235,0.08)' },
        markLine,
      },
      {
        name: '预测轨迹',
        type: 'line' as const,
        data: yData.map((v, i) => i >= historyLen - 1 ? v : null),
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

  const data = keys
    .map(k => ({
      name: labels[k] || k,
      value: typeof scores[k] === 'object' ? toPercent(scores[k]?.score, scores[k]?.scale) : null,
    }))
    .filter((d): d is { name: string; value: number } => d.value !== null)
    .sort((a, b) => b.value - a.value)
  if (!data.length) return null

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
    const prob = toPercent(hp.probability, hp.scale)
    const level = prob === null ? 'stable' : prob >= 70 ? 'critical' : prob >= 50 ? 'high' : prob >= 30 ? 'warning' : 'stable'
    const horizon = hp.horizon_hours || hp.horizon || '?'
    const delta = prob !== null && currentPct.value !== null ? prob - currentPct.value : null
    return {
      name: `${horizon}小时后`,
      probability: prob,
      level,
      description: prob === null
        ? '该时间点无有效预测值'
        : `${delta === null ? '' : `较当前 ${delta > 0 ? '+' : ''}${delta} 个百分点；`}${prob >= 70 ? '高危区间' : prob >= 50 ? '中高风险区间' : prob >= 30 ? '中等风险区间' : '低风险区间'}`,
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

// 直接渲染模式下组件会被复用：切换患者时路由参数变化需手动重载
watch(patientId, (id, prev) => {
  if (id && id !== prev) loadData()
})
</script>

<style scoped>.disease-trajectory { display: flex; flex-direction: column; gap: 14px }
.dt-window-selector { display: flex; align-items: center; gap: 8px; background: var(--color-bg-surface, #FFFFFF); padding: 10px 14px; border-radius: var(--radius-md, 6px); border: 1px solid var(--color-border, #E5E7EB) }
.dt-window-label { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563); font-weight: 500 }
.dt-window-btn { padding: 4px 12px; border-radius: var(--radius-tag, 4px); border: 1px solid var(--color-border, #E5E7EB); background: var(--color-bg-surface, #FFFFFF); font-size: var(--text-caption, 12px); cursor: pointer; transition: all 0.15s }
.dt-window-btn--active { background: var(--color-primary, #2563EB); color: var(--color-text-inverse, #FFFFFF); border-color: var(--color-primary, #2563EB) }
.dt-timeline-card, .dt-card { background: var(--color-bg-surface, #FFFFFF); border-radius: var(--radius-lg, 10px); padding: 16px; border: 1px solid var(--color-border, #E5E7EB) }
.dt-card-title { margin: 0 0 12px; font-size: var(--text-body, 13px); font-weight: 600; color: var(--color-text-primary, #111827) }
.dt-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px }
.dt-paths-list { display: flex; flex-direction: column; gap: 10px }
.dt-path-item { display: flex; flex-direction: column; gap: 4px }
.dt-path-header { display: flex; align-items: center; gap: 6px }
.dt-path-icon { font-size: 10px }
.dt-path--stable { color: var(--color-normal, #12A66A) }
.dt-path--warning { color: var(--color-warning, #B54708) }
.dt-path--high { color: var(--color-danger, #D92D20) }
.dt-path--critical { color: var(--color-critical, #D92D20) }
.dt-path-name { font-size: var(--text-caption, 12px); font-weight: 500 }
.dt-path-prob { font-size: var(--text-body, 13px); font-weight: 700; font-family: 'Rajdhani', monospace; margin-left: auto }
.dt-path-bar { height: 4px; background: var(--color-bg-inset, #E9EEF5); border-radius: var(--radius-tag, 4px); overflow: hidden }
.dt-path-fill { height: 100%; border-radius: var(--radius-tag, 4px); transition: width 0.4s ease }
.dt-fill--stable { background: var(--color-normal, #12A66A) }
.dt-fill--warning { background: var(--color-warning, #B54708) }
.dt-fill--high { background: var(--color-danger, #D92D20) }
.dt-fill--critical { background: var(--color-critical, #D92D20) }
.dt-path-desc { font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF) }
.dt-empty { text-align: center; padding: 24px; color: var(--color-text-tertiary, #9CA3AF); font-size: var(--text-body, 13px) }
.dt-disclaimer { padding: 10px 16px; background: var(--color-warning-soft-bg, #FFF9D8); border: 1px solid var(--color-warning-soft-border, #FFE58F); border-radius: var(--radius-md, 6px); font-size: var(--text-caption, 12px); color: var(--color-warning, #B54708) }

@media (max-width: 1200px) {.dt-row { grid-template-columns: 1fr }
 }

.dt-source { margin-left: auto; font-size: var(--text-caption, 12px); padding: 2px 8px; border-radius: var(--radius-tag, 4px) }
.dt-source--model { background: var(--color-ai-bg, #F5F3FF); color: var(--color-ai, #7C3AED) }
.dt-source--rule { background: var(--color-warning-soft-bg, #FFF9D8); color: var(--color-warning, #B54708) }
.dt-current { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563) }
.dt-warn { font-size: var(--text-caption, 12px); color: var(--color-warning, #B54708); background: var(--color-warning-soft-bg, #FFF9D8); padding: 8px 12px; border-radius: var(--radius-md, 6px) }
.dt-band-note { margin: 10px 0 0; font-size: 11px; color: var(--color-text-tertiary, #9CA3AF) }
.dt-contrib-list { display: flex; flex-direction: column; gap: 6px }
.dt-contrib { display: grid; grid-template-columns: 160px 120px 80px 1fr; gap: 8px; font-size: var(--text-caption, 12px); align-items: center }
.dt-contrib-name { font-weight: 600; color: var(--color-text-primary, #111827) }
.dt-contrib-val, .dt-contrib-impact { color: var(--color-text-secondary, #4B5563); font-family: 'SF Mono', Consolas, monospace }
</style>

