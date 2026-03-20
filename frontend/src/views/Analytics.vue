<template>
  <div class="analytics-page">
    <a-card :bordered="false" class="filter-card">
      <div class="filter-row">
        <div class="left-tools">
          <a-space wrap>
            <span class="label">工作区</span>
            <a-segmented
              v-model:value="analyticsSection"
              :options="sectionOptions"
              size="small"
            />
            <span class="label">时间窗口</span>
            <a-segmented
              v-model:value="windowRange"
              :options="windowOptions"
              size="small"
            />
            <span class="label">粒度</span>
            <a-segmented
              v-model:value="bucket"
              :options="bucketOptions"
              size="small"
            />
            <span class="label">前N项</span>
            <a-input-number v-model:value="topN" :min="5" :max="30" size="small" />
            <button
              :class="['rescue-toggle', { active: rescueOnly }]"
              @click="rescueOnly = !rescueOnly"
            >
              🚨 抢救期风险快筛
            </button>
          </a-space>
        </div>
        <div class="right-tools">
          <a-button size="small" :loading="loading" @click="loadAll">刷新统计</a-button>
        </div>
      </div>
    </a-card>

    <section class="section-hero">
      <div class="hero-copy">
        <div class="hero-kicker">{{ activeSectionMeta.kicker }}</div>
        <h1 class="hero-title">{{ activeSectionMeta.title }}</h1>
        <p class="hero-desc">{{ activeSectionMeta.description }}</p>
      </div>
      <div class="hero-meta">
        <div class="hero-chip">
          <span class="hero-chip__label">监测范围</span>
          <strong class="hero-chip__value">{{ analyticsScopeLabel }}</strong>
        </div>
        <div class="hero-chip">
          <span class="hero-chip__label">时间窗口</span>
          <strong class="hero-chip__value">{{ analyticsWindowLabel }}</strong>
        </div>
        <div class="hero-chip">
          <span class="hero-chip__label">分析粒度</span>
          <strong class="hero-chip__value">{{ bucket === 'hour' ? '小时' : '天' }} · 前 {{ topN }} 项</strong>
        </div>
      </div>
    </section>

    <section class="kpi-strip">
      <div
        v-for="item in activeSectionKpis"
        :key="item.code"
        :class="['kpi-tile', item.tone ? `kpi-tile--${item.tone}` : '']"
      >
        <div class="kpi-head">
          <span class="kpi-label">{{ item.label }}</span>
          <span class="kpi-code">{{ item.code }}</span>
        </div>
        <div :class="['kpi-value', { 'kpi-value--rule': item.compact }]">{{ item.value }}</div>
        <div class="kpi-sub">{{ item.meta }}</div>
      </div>
    </section>

    <section class="action-strip">
      <button
        v-for="item in activeSectionActions"
        :key="item.label"
        type="button"
        class="action-tile"
        @click="item.action()"
      >
        <span class="action-tile__label">{{ item.label }}</span>
        <strong class="action-tile__value">{{ item.value }}</strong>
        <span class="action-tile__meta">{{ item.meta }}</span>
      </button>
    </section>

    <section class="brief-board">
      <div class="brief-grid">
        <article v-for="item in activeSectionBriefs" :key="item.label" class="brief-card">
          <div class="brief-card__label">{{ item.label }}</div>
          <div class="brief-card__value">{{ item.value }}</div>
          <div class="brief-card__meta">{{ item.meta }}</div>
        </article>
      </div>
      <article class="focus-panel">
        <div class="focus-panel__head">
          <div>
            <div class="focus-panel__kicker">管理视角</div>
            <div class="focus-panel__title">{{ activeSectionFocusTitle }}</div>
          </div>
          <span class="focus-panel__badge">{{ activeSectionFocusBadge }}</span>
        </div>
        <div class="focus-list">
          <div v-for="item in activeSectionFocusRows" :key="item.label" class="focus-item">
            <div class="focus-item__label">{{ item.label }}</div>
            <div class="focus-item__value">{{ item.value }}</div>
            <div class="focus-item__meta">{{ item.meta }}</div>
          </div>
        </div>
      </article>
    </section>

    <section v-if="analyticsSection === 'alerts'" class="analytics-grid">
      <a-card title="运营摘要" :bordered="false" class="panel panel-wide">
        <div class="insight-grid">
          <div v-for="item in alertOpsHighlights" :key="item.label" class="insight-tile">
            <div class="insight-label">{{ item.label }}</div>
            <div class="insight-value">{{ item.value }}</div>
            <div class="insight-meta">{{ item.meta }}</div>
          </div>
        </div>
      </a-card>

      <a-card title="预警触发频率" :bordered="false" class="panel panel-wide">
        <div v-if="displayFreqSeries.length" class="chart-wrap chart-lg">
          <AnalyticsChart :option="frequencyOption" autoresize />
        </div>
        <div v-else class="empty">暂无频率数据</div>
      </a-card>

      <a-card title="规则类型热力图" :bordered="false" class="panel panel-wide panel-heatmap">
        <div v-if="displayHeatmapY.length" class="heatmap-summary">
          <div class="summary-chip">
            <span class="summary-k">规则数</span>
            <b class="summary-v">{{ heatmapSummary.ruleCount }}</b>
          </div>
          <div class="summary-chip">
            <span class="summary-k">时段数</span>
            <b class="summary-v">{{ heatmapSummary.slotCount }}</b>
          </div>
          <div class="summary-chip summary-chip--wide">
            <span class="summary-k">峰值时段</span>
            <b class="summary-v">{{ heatmapSummary.peakText }}</b>
          </div>
        </div>
        <div v-if="displayHeatmapY.length" class="chart-wrap chart-lg chart-heatmap">
          <AnalyticsChart :option="heatmapOption" autoresize />
        </div>
        <div v-else class="empty">暂无规则热力图数据</div>
      </a-card>

      <a-card title="科室预警排名" :bordered="false" class="panel">
        <div v-if="displayDeptRankings.length" class="chart-wrap chart-md">
          <AnalyticsChart :option="deptRankOption" autoresize />
        </div>
        <a-table
          class="rank-table"
          size="small"
          :columns="deptColumns"
          :data-source="displayDeptRankings"
          :pagination="false"
          row-key="dept"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'dept'">
              <a class="analytics-link" @click.prevent="openDeptOverview(record.dept)">{{ record.dept || '未知科室' }}</a>
            </template>
          </template>
        </a-table>
      </a-card>

      <a-card title="床位预警排名" :bordered="false" class="panel">
        <div v-if="displayBedRankings.length" class="chart-wrap chart-md">
          <AnalyticsChart :option="bedRankOption" autoresize />
        </div>
        <a-table
          class="rank-table"
          size="small"
          :columns="bedColumns"
          :data-source="displayBedRankings"
          :pagination="false"
          :scroll="{ x: 560 }"
          row-key="bedKey"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'dept'">
              <a class="analytics-link" @click.prevent="openDeptOverview(record.dept)">{{ record.dept || '未知科室' }}</a>
            </template>
          </template>
        </a-table>
      </a-card>
    </section>

    <section v-else-if="analyticsSection === 'sepsis'" class="analytics-grid">
      <a-card title="脓毒症解放束执行态" :bordered="false" class="panel panel-wide">
        <div class="bundle-status-grid">
          <div
            v-for="item in sepsisStatusCards"
            :key="item.label"
            :class="['status-card', item.tone ? `status-card--${item.tone}` : '']"
          >
            <div class="status-card__label">{{ item.label }}</div>
            <div class="status-card__value">{{ item.value }}</div>
            <div class="status-card__meta">{{ item.meta }}</div>
          </div>
        </div>
      </a-card>

      <a-card title="1 小时解放束达标拆解" :bordered="false" class="panel">
        <div class="progress-list">
          <div
            v-for="item in sepsisProgressRows"
            :key="item.label"
            class="progress-row"
          >
            <div class="progress-row__top">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
            <div class="progress-bar">
              <div class="progress-bar__fill" :style="{ width: item.width, background: item.color }"></div>
            </div>
            <div class="progress-row__meta">{{ item.meta }}</div>
          </div>
        </div>
      </a-card>

      <a-card title="本月质控提示" :bordered="false" class="panel">
        <div class="insight-list">
          <div v-for="item in sepsisNarratives" :key="item.label" class="insight-line">
            <div class="insight-line__label">{{ item.label }}</div>
            <div class="insight-line__value">{{ item.value }}</div>
            <div class="insight-line__meta">{{ item.meta }}</div>
          </div>
        </div>
      </a-card>

      <a-card title="智能管理摘要卡" :bordered="false" class="panel">
        <div class="insight-list">
          <div class="summary-card summary-card--hero">
            <div class="summary-card__label">管理结论</div>
            <div class="summary-card__value">{{ sepsisAiInsight.summary || '暂无智能摘要' }}</div>
            <div class="summary-card__meta">{{ sepsisAiInsight.degraded_mode ? '规则降级模式' : '大模型结构化输出' }}</div>
          </div>
          <div v-for="(item, idx) in sepsisAiManagementRows" :key="`sepsis-ai-finding-${idx}`" class="summary-card">
            <div class="summary-card__label">管理关注 {{ Number(idx) + 1 }}</div>
            <div class="summary-card__value summary-card__value--sm">{{ item }}</div>
          </div>
        </div>
      </a-card>

      <a-card title="智能行动建议卡" :bordered="false" class="panel">
        <div class="advice-list">
          <div v-for="(item, idx) in sepsisAiActionRows" :key="`sepsis-ai-action-${idx}`" class="advice-card">
            <div class="advice-card__index">0{{ Number(idx) + 1 }}</div>
            <div class="advice-card__body">
              <div class="advice-card__label">行动建议 {{ Number(idx) + 1 }}</div>
              <div class="advice-card__text">{{ item }}</div>
            </div>
          </div>
        </div>
      </a-card>
    </section>

    <section v-else-if="analyticsSection === 'scenarios'" class="analytics-grid">
      <a-card title="扩展场景覆盖总览" :bordered="false" class="panel panel-wide">
        <div class="insight-grid">
          <div v-for="item in scenarioHighlights" :key="item.label" class="insight-tile">
            <div class="insight-label">{{ item.label }}</div>
            <div class="insight-value">{{ item.value }}</div>
            <div class="insight-meta">{{ item.meta }}</div>
          </div>
        </div>
      </a-card>

      <a-card title="场景覆盖热力图" :bordered="false" class="panel panel-wide panel-heatmap">
        <div v-if="scenarioHeatmapY.length" class="heatmap-summary">
          <div class="summary-chip"><span class="summary-k">场景组</span><b class="summary-v">{{ scenarioHeatmapY.length }}</b></div>
          <div class="summary-chip"><span class="summary-k">高频场景</span><b class="summary-v">{{ scenarioHeatmapX.length }}</b></div>
          <div class="summary-chip summary-chip--wide"><span class="summary-k">覆盖率</span><b class="summary-v">{{ scenarioCoverageRate }}</b></div>
        </div>
        <div v-if="scenarioHeatmapY.length" class="chart-wrap chart-lg chart-heatmap">
          <AnalyticsChart :option="scenarioHeatmapOption" autoresize />
        </div>
        <div v-else class="empty">暂无扩展场景数据</div>
      </a-card>

      <a-card title="场景组覆盖率" :bordered="false" class="panel">
        <div class="progress-list">
          <div v-for="item in scenarioGroupProgressRows" :key="item.label" class="progress-row">
            <div class="progress-row__top"><span>{{ item.label }}</span><strong>{{ item.value }}</strong></div>
            <div class="progress-bar"><div class="progress-bar__fill" :style="{ width: item.width, background: item.color }"></div></div>
            <div class="progress-row__meta">{{ item.meta }}</div>
          </div>
        </div>
      </a-card>

      <a-card title="高频扩展场景" :bordered="false" class="panel">
        <a-table class="rank-table" size="small" :columns="scenarioColumns" :data-source="scenarioTopRows" :pagination="false" row-key="scenario" />
      </a-card>
    </section>

    <section v-else-if="analyticsSection === 'nursing'" class="analytics-grid">
      <a-card title="未来一个班次护理资源热力图" :bordered="false" class="panel panel-wide panel-heatmap">
        <div v-if="nursingHeatmapX.length" class="heatmap-summary">
          <div class="summary-chip"><span class="summary-k">热力床位</span><b class="summary-v">{{ nursingHeatmapX.length }}</b></div>
          <div class="summary-chip"><span class="summary-k">高/极高负荷</span><b class="summary-v">{{ Number(nursingSummary?.high_and_extreme_count || 0) }}</b></div>
          <div class="summary-chip"><span class="summary-k">有效护士</span><b class="summary-v">{{ Number(nursingSummary?.effective_nurse_count || 0) }}</b></div>
          <div class="summary-chip summary-chip--wide"><span class="summary-k">建议护士数</span><b class="summary-v">{{ Number(nursingSummary?.recommended_nurse_count || 0).toFixed(1) }} / 向上取整 {{ Number(nursingSummary?.recommended_nurse_ceiling || 0) }}</b></div>
        </div>
        <div v-if="nursingHeatmapX.length" class="chart-wrap chart-lg chart-heatmap">
          <AnalyticsChart :option="nursingHeatmapOption" autoresize />
        </div>
        <div v-else class="empty">暂无护理负荷热力图数据</div>
      </a-card>

      <a-card title="科室排班压力" :bordered="false" class="panel">
        <div class="progress-list">
          <div v-for="item in nursingDeptProgressRows" :key="item.label" class="progress-row">
            <div class="progress-row__top"><span>{{ item.label }}</span><strong>{{ item.value }}</strong></div>
            <div class="progress-bar"><div class="progress-bar__fill" :style="{ width: item.width, background: item.color }"></div></div>
            <div class="progress-row__meta">{{ item.meta }}</div>
          </div>
        </div>
      </a-card>

      <a-card title="科室负荷总览" :bordered="false" class="panel">
        <a-table class="rank-table" size="small" :columns="nursingDeptColumns" :data-source="nursingDeptRows" :pagination="false" row-key="dept" />
      </a-card>

      <a-card title="高强度患者队列" :bordered="false" class="panel panel-wide">
        <a-table class="rank-table" size="small" :columns="nursingPatientColumns" :data-source="nursingPatientRows" :pagination="false" row-key="patient_id">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'intensity_label'">
              <span :style="{ color: record?.intensity_color || '#e8fbff', fontWeight: 700 }">{{ record?.intensity_label || '中' }}</span>
            </template>
          </template>
        </a-table>
      </a-card>
    </section>

    <section v-else class="analytics-grid">
      <a-card title="撤机分析摘要" :bordered="false" class="panel panel-wide">
        <div class="insight-grid">
          <div v-for="item in weaningHighlights" :key="item.label" class="insight-tile">
            <div class="insight-label">{{ item.label }}</div>
            <div class="insight-value">{{ item.value }}</div>
            <div class="insight-meta">{{ item.meta }}</div>
          </div>
        </div>
      </a-card>

      <a-card title="月度脱机评估趋势" :bordered="false" class="panel panel-wide">
        <div v-if="weaningTrendRows.length" class="chart-wrap chart-lg">
          <AnalyticsChart :option="weaningTrendOption" autoresize />
        </div>
        <div v-else class="empty">暂无月度脱机评估趋势数据</div>
      </a-card>

      <a-card title="科室脱机 / 再插管风险对比" :bordered="false" class="panel panel-wide">
        <div v-if="weaningDeptCompare.length" class="chart-wrap chart-md">
          <AnalyticsChart :option="weaningDeptCompareOption" autoresize />
        </div>
        <a-table
          class="rank-table"
          size="small"
          :columns="weaningDeptColumns"
          :data-source="weaningDeptCompareTable"
          :pagination="false"
          row-key="dept"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'dept'">
              <a class="analytics-link" @click.prevent="openDeptOverview(record.dept)">{{ record.dept || '未知科室' }}</a>
            </template>
          </template>
        </a-table>
      </a-card>

      <a-card title="撤机风险概览" :bordered="false" class="panel">
        <div class="bundle-status-grid bundle-status-grid--compact">
          <div
            v-for="item in weaningStatusCards"
            :key="item.label"
            :class="['status-card', item.tone ? `status-card--${item.tone}` : '']"
          >
            <div class="status-card__label">{{ item.label }}</div>
            <div class="status-card__value">{{ item.value }}</div>
            <div class="status-card__meta">{{ item.meta }}</div>
          </div>
        </div>
      </a-card>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Button as AButton,
  Card as ACard,
  InputNumber as AInputNumber,
  Segmented as ASegmented,
  Space as ASpace,
  Table as ATable,
} from 'ant-design-vue'
import {
  getAlertAnalyticsFrequency,
  getAlertAnalyticsHeatmap,
  getAlertAnalyticsRankings,
  getNursingWorkloadAnalytics,
  getRecentAlerts,
  getScenarioCoverageAnalytics,
  getSepsisBundleCompliance,
  getWeaningSummary,
} from '../api'
import {
  icuCategoryAxis,
  icuGrid,
  icuLegend,
  icuTooltip,
  icuValueAxis,
} from '../charts/icuTheme'
import { formatAlertTypeLabel, formatScenarioGroupLabel } from '../utils/displayLabels'

const AnalyticsChart = defineAsyncComponent(async () => {
  await import('../charts/analytics')
  const mod = await import('vue-echarts')
  return mod.default
})

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const windowRange = ref('7d')
const bucket = ref<'hour' | 'day'>('hour')
const topN = ref(10)
const rescueOnly = ref(false)

const sectionOptions = [
  { label: '告警运营', value: 'alerts' },
  { label: '脓毒症质控', value: 'sepsis' },
  { label: '撤机分析', value: 'weaning' },
  { label: '护理资源', value: 'nursing' },
  { label: '场景覆盖', value: 'scenarios' },
]
const windowOptions = [
  { label: '24h', value: '24h' },
  { label: '7d', value: '7d' },
  { label: '14d', value: '14d' },
  { label: '30d', value: '30d' },
]
const bucketOptions = [
  { label: '小时', value: 'hour' },
  { label: '天', value: 'day' },
]

function normalizeAnalyticsSection(value: any): 'alerts' | 'sepsis' | 'weaning' | 'nursing' | 'scenarios' {
  const key = String(value || '').trim().toLowerCase()
  if (key === 'sepsis' || key === 'weaning' || key === 'nursing' || key === 'scenarios') return key
  return 'alerts'
}

const analyticsSection = ref<'alerts' | 'sepsis' | 'weaning' | 'nursing' | 'scenarios'>(normalizeAnalyticsSection(route.query.section))

const freqSeries = ref<any[]>([])
const heatmapX = ref<string[]>([])
const heatmapY = ref<string[]>([])
const heatmapData = ref<number[][]>([])
const deptRankings = ref<any[]>([])
const bedRankings = ref<any[]>([])
const sepsisBundleCompliance = ref<any>(null)
const sepsisBundleAiInsight = ref<any>(null)
const weaningSummary = ref<any>(null)
const recentAlerts = ref<any[]>([])
const scenarioCoverageSummary = ref<any>(null)
const scenarioGroupRows = ref<any[]>([])
const scenarioTopRows = ref<any[]>([])
const scenarioHeatmapX = ref<string[]>([])
const scenarioHeatmapY = ref<string[]>([])
const scenarioHeatmapData = ref<number[][]>([])
const nursingWorkload = ref<any>(null)

const deptCode = computed(() => String(route.query.dept_code || route.query.deptCode || '').trim())
const deptName = computed(() => String(route.query.dept || '').trim())
const analyticsScopeLabel = computed(() => deptName.value || deptCode.value || '全科')
const analyticsWindowLabel = computed(() => {
  const map: Record<string, string> = {
    '24h': '近24小时',
    '7d': '近7天',
    '14d': '近14天',
    '30d': '近30天',
  }
  return map[windowRange.value] || windowRange.value
})
const sepsisBundleMonth = computed(() => {
  const now = new Date()
  const y = now.getFullYear()
  const m = `${now.getMonth() + 1}`.padStart(2, '0')
  return `${y}-${m}`
})
const sepsisBundleMonthCode = computed(() => sepsisBundleMonth.value.replace('-', '.'))
const analyticsMonthCode = computed(() => sepsisBundleMonthCode.value)

function commonParams() {
  const params: Record<string, any> = { window: windowRange.value }
  if (deptCode.value) params.dept_code = deptCode.value
  else if (deptName.value) params.dept = deptName.value
  return params
}

function windowRangeMs() {
  const map: Record<string, number> = {
    '24h': 24 * 3600 * 1000,
    '7d': 7 * 24 * 3600 * 1000,
    '14d': 14 * 24 * 3600 * 1000,
    '30d': 30 * 24 * 3600 * 1000,
  }
  return map[windowRange.value] || 7 * 24 * 3600 * 1000
}

function alertTimeValue(alert: any) {
  const raw = alert?.created_at || alert?.source_time || alert?.time
  const val = new Date(raw).getTime()
  return Number.isFinite(val) ? val : 0
}

function isRescueRiskAlert(alert: any) {
  const sev = String(alert?.severity || '').toLowerCase()
  if (sev !== 'high' && sev !== 'critical') return false
  const alertType = String(alert?.alert_type || '').toLowerCase()
  const ruleId = String(alert?.rule_id || '').toLowerCase()
  const category = String(alert?.category || '').toLowerCase()
  if (alertType === 'ai_risk' || category === 'ai_analysis') return false
  const rescueKeywords = [
    'shock', 'sepsis', 'septic', 'cardiac_arrest', 'cardiac', 'pea',
    'pe_', 'embol', 'bleed', 'bleeding', 'resp', 'hypoxia', 'hypotension',
    'deterioration', 'multi_organ', 'post_extubation',
  ]
  const haystack = `${alertType} ${ruleId} ${category}`.toLowerCase()
  const extra = alert?.extra && typeof alert.extra === 'object' ? alert.extra : {}
  return rescueKeywords.some((key) => haystack.includes(key))
    || !!extra?.context_snapshot
    || !!extra?.clinical_chain
    || (Array.isArray(extra?.aggregated_groups) && extra.aggregated_groups.length > 0)
}

function bucketLabelByTime(ts: number) {
  const d = new Date(ts)
  const mm = `${d.getMonth() + 1}`.padStart(2, '0')
  const dd = `${d.getDate()}`.padStart(2, '0')
  if (bucket.value === 'day') return `${mm}-${dd}`
  const hh = `${d.getHours()}`.padStart(2, '0')
  return `${mm}-${dd} ${hh}:00`
}

function aggregateRescueFrequency(alertsInput: any[]) {
  const counter = new Map<string, { time: string; total: number; warning: number; high: number; critical: number }>()
  alertsInput.forEach((alert) => {
    const label = bucketLabelByTime(alertTimeValue(alert))
    const sev = String(alert?.severity || '').toLowerCase()
    if (!counter.has(label)) {
      counter.set(label, { time: label, total: 0, warning: 0, high: 0, critical: 0 })
    }
    const row = counter.get(label)!
    row.total += 1
    if (sev === 'critical') row.critical += 1
    else if (sev === 'high') row.high += 1
    else row.warning += 1
  })
  return Array.from(counter.values()).sort((a, b) => a.time.localeCompare(b.time))
}

function aggregateRescueHeatmap(alertsInput: any[]) {
  const bucketSet = new Set<string>()
  const ruleCounter = new Map<string, number>()
  const matrix = new Map<string, number>()
  alertsInput.forEach((alert) => {
    const bucketLabel = bucketLabelByTime(alertTimeValue(alert))
    const ruleLabel = formatAlertTypeLabel(alert?.alert_type || alert?.rule_id || alert?.name || '抢救期预警')
    bucketSet.add(bucketLabel)
    ruleCounter.set(ruleLabel, (ruleCounter.get(ruleLabel) || 0) + 1)
    const key = `${bucketLabel}__${ruleLabel}`
    matrix.set(key, (matrix.get(key) || 0) + 1)
  })
  const xLabels = Array.from(bucketSet).sort((a, b) => a.localeCompare(b))
  const yLabels = Array.from(ruleCounter.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, topN.value)
    .map(([name]) => name)
  const data: number[][] = []
  xLabels.forEach((x, xi) => {
    yLabels.forEach((y, yi) => {
      const count = matrix.get(`${x}__${y}`) || 0
      if (count > 0) data.push([xi, yi, count])
    })
  })
  return { xLabels, yLabels, data }
}

function aggregateRescueDeptRankings(alertsInput: any[]) {
  const counter = new Map<string, any>()
  alertsInput.forEach((alert) => {
    const key = String(alert?.dept || '未知科室')
    if (!counter.has(key)) {
      counter.set(key, { dept: key, count: 0, critical: 0, high: 0, warning: 0 })
    }
    const row = counter.get(key)
    const sev = String(alert?.severity || '').toLowerCase()
    row.count += 1
    if (sev === 'critical') row.critical += 1
    else if (sev === 'high') row.high += 1
    else row.warning += 1
  })
  return Array.from(counter.values()).sort((a, b) => b.count - a.count).slice(0, topN.value)
}

function aggregateRescueBedRankings(alertsInput: any[]) {
  const counter = new Map<string, any>()
  alertsInput.forEach((alert) => {
    const dept = String(alert?.dept || '未知科室')
    const bed = String(alert?.bed || alert?.hisBed || '—')
    const key = `${dept}-${bed}`
    if (!counter.has(key)) {
      counter.set(key, { dept, bed, count: 0, critical: 0, high: 0, warning: 0, bedKey: key })
    }
    const row = counter.get(key)
    const sev = String(alert?.severity || '').toLowerCase()
    row.count += 1
    if (sev === 'critical') row.critical += 1
    else if (sev === 'high') row.high += 1
    else row.warning += 1
  })
  return Array.from(counter.values()).sort((a, b) => b.count - a.count).slice(0, topN.value)
}

function toShortTime(v: string) {
  const s = String(v || '')
  if (bucket.value === 'day') return s.slice(5)
  return s.slice(5, 16)
}

function escapeHtml(v: any) {
  return String(v ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function tooltipShell(title: string, rows: string[], footer = '') {
  return `
    <div class="analytics-tooltip">
      <div class="analytics-tooltip__title">${escapeHtml(title)}</div>
      <div class="analytics-tooltip__body">${rows.join('')}</div>
      ${footer ? `<div class="analytics-tooltip__footer">${escapeHtml(footer)}</div>` : ''}
    </div>
  `
}

function tooltipRow(label: string, value: any, color = '#67e8f9') {
  return `
    <div class="analytics-tooltip__row">
      <span class="analytics-tooltip__label">
        <i class="analytics-tooltip__dot" style="background:${escapeHtml(color)}"></i>
        ${escapeHtml(label)}
      </span>
      <strong class="analytics-tooltip__value">${escapeHtml(value)}</strong>
    </div>
  `
}

function ratioText(numerator: number, denominator: number) {
  if (!denominator) return '0%'
  return `${Math.round((numerator / denominator) * 100)}%`
}

function formatPct(value: number, digits = 1) {
  return `${(Number(value || 0) * 100).toFixed(digits)}%`
}

const rescueWindowAlerts = computed(() => {
  const cutoff = Date.now() - windowRangeMs()
  return recentAlerts.value
    .filter((alert: any) => isRescueRiskAlert(alert))
    .filter((alert: any) => alertTimeValue(alert) >= cutoff)
})

const rescueFrequencySeries = computed(() => aggregateRescueFrequency(rescueWindowAlerts.value))
const rescueHeatmap = computed(() => aggregateRescueHeatmap(rescueWindowAlerts.value))
const displayFreqSeries = computed(() => rescueOnly.value ? rescueFrequencySeries.value : freqSeries.value)
const displayHeatmapX = computed(() => rescueOnly.value ? rescueHeatmap.value.xLabels : heatmapX.value)
const displayHeatmapY = computed(() => rescueOnly.value ? rescueHeatmap.value.yLabels : heatmapY.value)
const displayHeatmapData = computed(() => rescueOnly.value ? rescueHeatmap.value.data : heatmapData.value)
const displayDeptRankings = computed(() =>
  rescueOnly.value ? aggregateRescueDeptRankings(rescueWindowAlerts.value) : deptRankings.value
)
const displayBedRankings = computed(() =>
  rescueOnly.value ? aggregateRescueBedRankings(rescueWindowAlerts.value) : bedRankings.value
)

const frequencyOption = computed(() => {
  const source = displayFreqSeries.value
  const xs = source.map((p: any) => rescueOnly.value ? String(p.time || '') : toShortTime(p.time || ''))
  return {
    backgroundColor: 'transparent',
    tooltip: icuTooltip({
      trigger: 'axis',
      formatter: (params: any[]) => {
        const list = Array.isArray(params) ? params : [params]
        const title = list[0]?.axisValueLabel || list[0]?.name || '时间窗'
        const rows = list.map((item: any) => tooltipRow(item.seriesName || '指标', item.value ?? 0, item.color || '#67e8f9'))
        const total = list.find((item: any) => item.seriesName === '总量')?.value ?? 0
        return tooltipShell(title, rows, `总触发 ${total} 次`)
      },
    }),
    legend: icuLegend({ textStyle: { fontSize: 10 } }),
    grid: icuGrid({ left: 42, right: 18, top: 34, bottom: 34 }),
    xAxis: icuCategoryAxis(xs, { axisLabel: { fontSize: 10, margin: 10 } }),
    yAxis: icuValueAxis({ axisLabel: { fontSize: 10 } }),
    series: [
      {
        name: '总量',
        type: 'bar',
        data: source.map((p: any) => p.total || 0),
        itemStyle: {
          color: '#0ea5b7',
          borderRadius: [6, 6, 0, 0],
          shadowBlur: 10,
          shadowColor: 'rgba(14, 165, 183, 0.18)',
        },
        barMaxWidth: 16,
      },
      {
        name: '预警',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2, color: '#fbbf24' },
        itemStyle: { color: '#fbbf24' },
        data: source.map((p: any) => p.warning || 0),
      },
      {
        name: '高危',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2, color: '#fb923c' },
        itemStyle: { color: '#fb923c' },
        data: source.map((p: any) => p.high || 0),
      },
      {
        name: '危急',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2, color: '#fb5a7a' },
        itemStyle: { color: '#fb5a7a' },
        data: source.map((p: any) => p.critical || 0),
      },
    ],
  }
})

const heatmapOption = computed(() => {
  const sourceX = displayHeatmapX.value
  const sourceY = displayHeatmapY.value
  const sourceData = displayHeatmapData.value
  const maxVal = sourceData.reduce((m, cur) => Math.max(m, cur[2] || 0), 0)
  return {
    backgroundColor: 'transparent',
    tooltip: icuTooltip({
      extraCssText: 'box-shadow: 0 12px 28px rgba(0,0,0,.28); border-radius: 10px;',
      formatter: (params: any) => {
        const x = sourceX[params.value[0]]
        const y = sourceY[params.value[1]]
        return tooltipShell(
          `${y || '规则类型'}`,
          [
            tooltipRow('时段', x || '—', '#22d3ee'),
            tooltipRow('触发', `${params.value[2] || 0} 次`, '#fb5a7a'),
          ],
          '规则类型热区'
        )
      },
    }),
    grid: icuGrid({ left: 128, right: 22, top: 20, bottom: 62 }),
    xAxis: icuCategoryAxis(sourceX, {
      axisLine: { lineStyle: { color: 'rgba(79, 182, 219, 0.24)' } },
      axisLabel: { color: '#79d7ea', fontSize: 10, margin: 12 },
      splitArea: { show: false },
      splitLine: { show: true, lineStyle: { color: 'rgba(61, 118, 145, 0.12)' } },
    }),
    yAxis: icuCategoryAxis(sourceY, {
      axisLine: { lineStyle: { color: 'rgba(79, 182, 219, 0.24)' } },
      axisLabel: { color: '#b7ddec', fontSize: 10, margin: 14 },
      splitArea: { show: false },
      splitLine: { show: true, lineStyle: { color: 'rgba(61, 118, 145, 0.12)' } },
    }),
    visualMap: {
      min: 0,
      max: Math.max(1, maxVal),
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 8,
      itemWidth: 140,
      itemHeight: 10,
      text: ['高频', '低频'],
      textGap: 10,
      textStyle: { color: '#7fc7da', fontSize: 10 },
      inRange: {
        color: ['#0a2234', '#0e4c68', '#16b3c9', '#f59e0b', '#fb5a7a'],
      },
    },
    series: [
      {
        name: '触发频次',
        type: 'heatmap',
        data: sourceData,
        label: {
          show: true,
          formatter: ({ value }: any) => (value?.[2] ? value[2] : ''),
          color: '#effcff',
          fontSize: 10,
          fontWeight: 700,
        },
        itemStyle: {
          borderRadius: 8,
          borderColor: 'rgba(112, 226, 255, 0.1)',
          borderWidth: 1,
        },
        emphasis: {
          itemStyle: {
            borderColor: '#dffbff',
            borderWidth: 1,
            shadowBlur: 18,
            shadowColor: 'rgba(34, 211, 238, 0.22)',
          },
        },
      },
    ],
  }
})

const heatmapSummary = computed(() => {
  const sourceX = displayHeatmapX.value
  const sourceY = displayHeatmapY.value
  const sourceData = displayHeatmapData.value
  let peak = { val: 0, x: '', y: '' }
  for (const item of sourceData) {
    const xi = Number(item?.[0])
    const yi = Number(item?.[1])
    const v = item?.[2] || 0
    if (v >= peak.val) {
      peak = {
        val: v,
        x: sourceX[xi] || '',
        y: sourceY[yi] || '',
      }
    }
  }
  return {
    ruleCount: sourceY.length,
    slotCount: sourceX.length,
    peakText: peak.val ? `${peak.y} · ${peak.x} · ${peak.val}次` : '暂无峰值',
  }
})

const topRuleSummary = computed(() => {
  const totals = new Map<string, number>()
  for (const item of displayHeatmapData.value) {
    const yi = Number(item?.[1])
    const value = Number(item?.[2] || 0)
    const name = displayHeatmapY.value[yi] || ''
    if (!name) continue
    totals.set(name, (totals.get(name) || 0) + value)
  }
  const rows = Array.from(totals.entries()).sort((a, b) => b[1] - a[1])
  if (!rows.length) {
    return { name: '暂无数据', meta: '等待规则热力图数据' }
  }
  const topRow = rows[0] || ['', 0]
  const name = topRow[0]
  const count = topRow[1]
  const ratio = displayHeatmapData.value.length ? Math.round((count / Math.max(1, rows.reduce((s, [, v]) => s + v, 0))) * 100) : 0
  return {
    name,
    meta: `累计 ${count} 次 · 占规则触发 ${ratio}%`,
  }
})

const topRuleHeadline = computed(() => windowRange.value === '24h' ? '今日最高风险规则' : '当前窗口最高风险规则')

const scenarioCoverageRate = computed(() => formatPct(Number(scenarioCoverageSummary.value?.coverage_ratio || 0)))
const scenarioHighlights = computed(() => [
  { label: '场景库', value: `${Number(scenarioCoverageSummary.value?.total_catalog_scenarios || 0)} 个`, meta: '统一扩展场景配置与评估引擎' },
  { label: '已触发场景', value: `${Number(scenarioCoverageSummary.value?.triggered_catalog_scenarios || 0)} 个`, meta: `${analyticsWindowLabel.value} 内至少命中一次` },
  { label: '覆盖率', value: scenarioCoverageRate.value, meta: `${Number(scenarioCoverageSummary.value?.scenario_groups || 0)} 个场景组参与统计` },
  { label: '触发总量', value: `${Number(scenarioCoverageSummary.value?.total_alerts || 0)} 次`, meta: '来自扩展场景扫描器的实际命中' },
])
const scenarioGroupProgressRows = computed(() => scenarioGroupRows.value.map((item: any, idx: number) => ({
  label: formatScenarioGroupLabel(item.group),
  value: `${Math.round(Number(item.coverage_ratio || 0) * 100)}%`,
  width: `${Math.max(4, Number(item.coverage_ratio || 0) * 100)}%`,
  meta: `已覆盖 ${item.triggered_count}/${item.catalog_count} 个场景 · 告警 ${item.alert_count} 次`,
  color: ['linear-gradient(90deg, #22d3ee, #38bdf8)', 'linear-gradient(90deg, #2dd4bf, #34d399)', 'linear-gradient(90deg, #f59e0b, #fb7185)'][idx % 3],
})))
const scenarioHeatmapOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: icuTooltip({
    formatter: (params: any) => tooltipShell(`${scenarioHeatmapY.value[params.value[1]] || '场景组'}`, [tooltipRow('场景', scenarioHeatmapX.value[params.value[0]] || '—', '#22d3ee'), tooltipRow('命中', `${params.value[2] || 0} 次`, '#fb5a7a')], '扩展场景覆盖热区'),
  }),
  grid: icuGrid({ left: 128, right: 22, top: 20, bottom: 62 }),
  xAxis: icuCategoryAxis(scenarioHeatmapX.value, { axisLabel: { color: '#79d7ea', fontSize: 10, rotate: 18, margin: 12 } }),
  yAxis: icuCategoryAxis(scenarioHeatmapY.value, { axisLabel: { color: '#b7ddec', fontSize: 10, margin: 14 } }),
  visualMap: { min: 0, max: Math.max(1, ...scenarioHeatmapData.value.map((item: any) => Number(item?.[2] || 0))), orient: 'horizontal', left: 'center', bottom: 8, text: ['高频', '低频'], textStyle: { color: '#7fc7da', fontSize: 10 }, inRange: { color: ['#0a2234', '#0e4c68', '#16b3c9', '#f59e0b', '#fb5a7a'] } },
  series: [{ type: 'heatmap', data: scenarioHeatmapData.value, label: { show: true, formatter: ({ value }: any) => value?.[2] || '', color: '#effcff', fontSize: 10, fontWeight: 700 }, itemStyle: { borderRadius: 8, borderColor: 'rgba(112, 226, 255, 0.1)', borderWidth: 1 } }],
}))
const nursingHeatmapOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: icuTooltip({
    formatter: (params: any) => tooltipShell(
      nursingHeatmapX.value[params.value[0]] || '床位',
      [
        tooltipRow('护理强度', nursingHeatmapY.value[params.value[1]] || '未来一个班次', '#22d3ee'),
        tooltipRow('预计 NAS', `${params.value[2] || 0}`, '#fb5a7a'),
      ],
      '护理资源热力图',
    ),
  }),
  grid: icuGrid({ left: 88, right: 22, top: 20, bottom: 72 }),
  xAxis: icuCategoryAxis(nursingHeatmapX.value, { axisLabel: { color: '#79d7ea', fontSize: 10, rotate: 28, margin: 12 } }),
  yAxis: icuCategoryAxis(nursingHeatmapY.value, { axisLabel: { color: '#b7ddec', fontSize: 10, margin: 14 } }),
  visualMap: { min: 20, max: 100, orient: 'horizontal', left: 'center', bottom: 8, text: ['高负荷', '低负荷'], textStyle: { color: '#7fc7da', fontSize: 10 }, inRange: { color: ['#0a2234', '#0e4c68', '#16b3c9', '#fb923c', '#f43f5e'] } },
  series: [{ type: 'heatmap', data: nursingHeatmapData.value, label: { show: true, formatter: ({ value }: any) => value?.[2] || '', color: '#effcff', fontSize: 10, fontWeight: 700 }, itemStyle: { borderRadius: 8, borderColor: 'rgba(112, 226, 255, 0.1)', borderWidth: 1 } }],
}))
const scenarioColumns = [
  { title: '场景', dataIndex: 'title', key: 'title' },
  { title: '分组', dataIndex: 'group', key: 'group', width: 110 },
  { title: '告警', dataIndex: 'alert_count', key: 'alert_count', width: 72 },
  { title: '患者', dataIndex: 'patient_count', key: 'patient_count', width: 72 },
  { title: '危急', dataIndex: 'critical', key: 'critical', width: 72 },
  { title: '高危', dataIndex: 'high', key: 'high', width: 72 },
]
const nursingPatientColumns = [
  { title: '科室', dataIndex: 'dept', key: 'dept', width: 120 },
  { title: '床位', dataIndex: 'bed', key: 'bed', width: 70 },
  { title: '患者', dataIndex: 'patient_name', key: 'patient_name' },
  { title: '强度', dataIndex: 'intensity_label', key: 'intensity_label', width: 72 },
  { title: 'NAS', dataIndex: 'nas_score', key: 'nas_score', width: 76 },
  { title: '班次工时', dataIndex: 'predicted_next_shift_hours', key: 'predicted_next_shift_hours', width: 90 },
]
const nursingDeptColumns = [
  { title: '科室', dataIndex: 'dept', key: 'dept' },
  { title: '患者', dataIndex: 'patient_count', key: 'patient_count', width: 72 },
  { title: '均值NAS', dataIndex: 'avg_nas_score', key: 'avg_nas_score', width: 88 },
  { title: '有效护士', dataIndex: 'effective_nurse_count', key: 'effective_nurse_count', width: 88 },
  { title: '班次工时', dataIndex: 'total_predicted_shift_hours', key: 'total_predicted_shift_hours', width: 90 },
  { title: '建议护士', dataIndex: 'recommended_nurse_count', key: 'recommended_nurse_count', width: 92 },
  { title: '缺口', dataIndex: 'staffing_gap', key: 'staffing_gap', width: 76 },
]

const activeSectionMeta = computed(() => {
  if (analyticsSection.value === 'sepsis') {
    return {
      kicker: '脓毒症流程质控',
      title: '脓毒症解放束质控工作区',
      description: '聚焦 1 小时解放束达标率、超时病例和在途执行状态，适合科室质控和值班复盘。',
    }
  }
  if (analyticsSection.value === 'scenarios') {
    return {
      kicker: '扩展场景引擎',
      title: '场景覆盖工作区',
      description: '把 100+ 场景扩展的基础设施直接映射成覆盖总览、热力图和高频场景榜，便于持续下钻 ICU 高价值场景。',
    }
  }
  if (analyticsSection.value === 'nursing') {
    return {
      kicker: '护理资源预测',
      title: '护理资源工作区',
      description: '把未来一个班次的护理负荷、科室人力压力和高强度床位集中到同一视图，便于护士长排班与交班前预判。',
    }
  }
  if (analyticsSection.value === 'weaning') {
    return {
      kicker: '撤机流程分析',
      title: '撤机分析工作区',
      description: '围绕脱机评估、高风险患者和再插管风险，集中查看趋势、科室差异和月度负担。',
    }
  }
  return {
    kicker: '告警运营分析',
    title: '告警运营工作区',
    description: '查看预警频率、热区、科室和床位分布，快速识别高频规则与抢救期告警压力。',
  }
})

const activeSectionBriefs = computed(() => {
  if (analyticsSection.value === 'sepsis') {
    return [
      { label: '月度总评', value: sepsisBundleKpi.value.rate, meta: sepsisBundleKpi.value.meta },
      { label: '执行断点', value: `${Number(sepsisBundleCompliance.value?.overdue_1h_cases || 0)} 例超1h`, meta: '建议优先抽查抗菌药、补液、乳酸复测延迟链路。' },
      { label: '智能管理结论', value: sepsisAiInsight.value?.summary || '暂无智能摘要', meta: sepsisAiInsight.value?.degraded_mode ? '当前为规则降级模式' : '当前为大模型结构化输出' },
    ]
  }
  if (analyticsSection.value === 'weaning') {
    return [
      { label: '高风险占比', value: weaningHighRiskKpi.value.rate, meta: weaningHighRiskKpi.value.meta },
      { label: '再插管风险', value: reintubationRiskKpi.value.rate, meta: reintubationRiskKpi.value.meta },
      { label: '当前重点', value: `${Number(weaningSummary.value?.critical_post_extubation_patients || 0)} 例危急事件`, meta: '建议将危急拔管后事件与自主呼吸试验失败模式联动复盘。' },
    ]
  }
  if (analyticsSection.value === 'nursing') {
    return [
      { label: '建议护士数', value: `${Number(nursingSummary.value?.recommended_nurse_count || 0).toFixed(1)}`, meta: `向上取整 ${Number(nursingSummary.value?.recommended_nurse_ceiling || 0)} 人` },
      { label: '护理缺口', value: `${Number(nursingSummary.value?.staffing_gap || 0).toFixed(1)} 人`, meta: `${Number(nursingSummary.value?.extreme_count || 0)} 例极高强度患者待覆盖` },
      { label: '峰值科室', value: nursingSummary.value?.peak_dept || '暂无数据', meta: nursingSummary.value?.peak_dept ? `建议护士数 ${Number(nursingSummary.value?.peak_dept_nurse_count || 0).toFixed(1)}` : '等待护理负荷数据' },
    ]
  }
  if (analyticsSection.value === 'scenarios') {
    return [
      { label: '场景覆盖率', value: scenarioCoverageRate.value, meta: `${Number(scenarioCoverageSummary.value?.triggered_catalog_scenarios || 0)} / ${Number(scenarioCoverageSummary.value?.total_catalog_scenarios || 0)} 场景命中` },
      { label: '高频场景', value: scenarioTopRows.value[0]?.title || '暂无数据', meta: scenarioTopRows.value[0] ? `${scenarioTopRows.value[0].alert_count} 次命中` : '等待场景数据' },
      { label: '场景组数', value: `${scenarioGroupRows.value.length}`, meta: '统一引擎下的扩展场景分组' },
    ]
  }
  return [
    { label: '高危占比', value: highRiskRatio.value.ratio, meta: highRiskRatio.value.meta },
    { label: '峰值时段', value: peakSlotSummary.value.slot, meta: peakSlotSummary.value.meta },
    { label: '高频规则', value: topRuleSummary.value.name, meta: topRuleSummary.value.meta },
  ]
})
const activeSectionFocusTitle = computed(() => {
  if (analyticsSection.value === 'sepsis') return '当班脓毒症质控关注'
  if (analyticsSection.value === 'weaning') return '当班撤机管理关注'
  if (analyticsSection.value === 'nursing') return '护士长排班关注'
  if (analyticsSection.value === 'scenarios') return '扩展场景推进关注'
  return '告警运营关注'
})
const activeSectionFocusBadge = computed(() => {
  if (analyticsSection.value === 'sepsis') return '流程闭环'
  if (analyticsSection.value === 'weaning') return '失败预防'
  if (analyticsSection.value === 'nursing') return '班次负荷'
  if (analyticsSection.value === 'scenarios') return '覆盖推进'
  return '热区治理'
})
const activeSectionFocusRows = computed(() => {
  if (analyticsSection.value === 'sepsis') {
    return [
      { label: '超 3h 个案', value: `${Number(sepsisBundleCompliance.value?.overdue_3h_cases || 0)} 例`, meta: Number(sepsisBundleCompliance.value?.overdue_3h_cases || 0) ? '建议逐例追踪是否卡在首剂抗菌药、血培养或液体复苏。' : '当前没有超 3h 个案。' },
      { label: '在途病例', value: `${Number(sepsisBundleCompliance.value?.pending_active_cases || 0)} 例`, meta: Number(sepsisBundleCompliance.value?.pending_active_cases || 0) ? '交接班时应保留节点提醒，避免 1h 继续滑向 3h。' : '当前没有在途病例。' },
      { label: '管理建议', value: sepsisAiActionRows.value[0] || '暂无额外建议', meta: '智能建议卡可继续查看其余行动项。' },
    ]
  }
  if (analyticsSection.value === 'weaning') {
    return [
      { label: '高风险患者', value: `${Number(weaningSummary.value?.high_risk_patients || 0)} 例`, meta: '优先回看氧合、液体负荷和血流动力学可逆因素。'},
      { label: '拔管后风险', value: `${Number(weaningSummary.value?.reintubation_risk_patients || 0)} 例`, meta: '建议把拔管后高风险患者纳入床旁连续复评队列。'},
      { label: '危急事件', value: `${Number(weaningSummary.value?.critical_post_extubation_patients || 0)} 例`, meta: '适合和值班、呼吸治疗、护理一起做失败模式复盘。'},
    ]
  }
  if (analyticsSection.value === 'nursing') {
    return [
      { label: '峰值科室', value: nursingSummary.value?.peak_dept || '暂无数据', meta: nursingSummary.value?.peak_dept ? `建议护士数 ${Number(nursingSummary.value?.peak_dept_nurse_count || 0).toFixed(1)}` : '等待护理负荷汇总。' },
      { label: '极高强度患者', value: `${Number(nursingSummary.value?.extreme_count || 0)} 例`, meta: '建议交班前先锁定极高强度患者与高压床位。' },
      { label: '资源动作', value: `${Number(nursingSummary.value?.staffing_gap_ceiling || 0)} 人缺口`, meta: '可结合科室热力图和高强度队列调整当班排班。' },
    ]
  }
  if (analyticsSection.value === 'scenarios') {
    return [
      { label: '推进重点', value: scenarioTopRows.value[0]?.title || '暂无数据', meta: scenarioTopRows.value[0] ? '建议先复盘命中最多、业务价值最高的场景。' : '等待场景统计。' },
      { label: '覆盖缺口', value: `${Math.max(0, Number(scenarioCoverageSummary.value?.total_catalog_scenarios || 0) - Number(scenarioCoverageSummary.value?.triggered_catalog_scenarios || 0))} 个未命中`, meta: '适合继续补数据链路、规则映射或场景触发条件。' },
      { label: '运营联动', value: `${Number(scenarioCoverageSummary.value?.total_alerts || 0)} 次命中`, meta: '可回到告警运营区查看这些场景在全天的热区分布。' },
    ]
  }
  return [
    { label: '热区治理', value: topRuleSummary.value.name, meta: topRuleSummary.value.meta },
    { label: '峰值时段', value: peakSlotSummary.value.slot, meta: '建议把人力与规则治理资源投向峰值时段。' },
    { label: rescueOnly.value ? '抢救期压力' : '高危压力', value: highRiskRatio.value.ratio, meta: highRiskRatio.value.meta },
  ]
})
const activeSectionActions = computed(() => {
  if (analyticsSection.value === 'sepsis') {
    return [
      {
        label: '打开智能运营',
        value: '阈值审核 / 反馈闭环',
        meta: '继续查看个性化阈值审核和智能反馈准确率。',
        action: () => router.push('/ai-ops'),
      },
      {
        label: '切回告警运营',
        value: '查看规则热区',
        meta: '返回高频规则、峰值时段和床位排名视图。',
        action: () => setAnalyticsSection('alerts'),
      },
      {
        label: '查看进行中病例',
        value: '患者总览 / 高危以上',
        meta: '带着高危筛选返回患者总览，继续看仍需跟踪的人群。',
        action: () => router.push({ path: '/', query: { ...route.query, alert_level: 'warning' } }),
      },
    ]
  }
  if (analyticsSection.value === 'scenarios') {
    return [
      { label: '打开 MDT 会诊', value: '多智能体裁决看板', meta: '继续查看专科意见、冲突焦点和总控智能体裁决。', action: () => router.push('/mdt') },
      { label: '切回告警运营', value: '查看实时热区', meta: '从扩展场景覆盖切回全量规则热力图。', action: () => setAnalyticsSection('alerts') },
      { label: '打开患者总览', value: '继续做高危筛查', meta: '带着当前筛选条件回到患者工作台。', action: () => router.push({ path: '/', query: { ...route.query } }) },
    ]
  }
  if (analyticsSection.value === 'nursing') {
    return [
      {
        label: '切到告警运营',
        value: '联动看高峰告警',
        meta: '把护理高压床位和告警热区放在一起看，适合交班前复核。',
        action: () => setAnalyticsSection('alerts'),
      },
      {
        label: '打开患者总览',
        value: '锁定高压床位',
        meta: '带着当前科室筛选回到患者总览，继续下钻护理最重的人群。',
        action: () => router.push({ path: '/', query: { ...route.query } }),
      },
      {
        label: '查看智能运营',
        value: '反馈与阈值审核',
        meta: '继续结合智能运行态与阈值审核判断是否需要调整策略。',
        action: () => router.push('/ai-ops'),
      },
    ]
  }
  if (analyticsSection.value === 'weaning') {
    return [
      {
        label: '查看智能运营',
        value: '反馈与运行态',
        meta: '联动查看智能监控、反馈闭环和审核中心。',
        action: () => router.push('/ai-ops'),
      },
      {
        label: '切到脓毒症质控',
        value: '查看解放束闭环',
        meta: '对比流程型质控和撤机风险分析。',
        action: () => setAnalyticsSection('sepsis'),
      },
      {
        label: '查看高危床位',
        value: '患者总览 / 危重',
        meta: '直接回到患者总览并锁定危重/高危床位。',
        action: () => router.push({ path: '/', query: { ...route.query, alert_level: 'critical' } }),
      },
    ]
  }
  return [
    {
      label: '打开智能运营',
      value: '查看运行监控',
      meta: '直接进入智能监控、反馈闭环和阈值审核中心。',
      action: () => router.push('/ai-ops'),
    },
    {
      label: '切到脓毒症质控',
      value: '查看解放束合规',
      meta: '进入 1 小时解放束达标、超时病例和在途执行分析。',
      action: () => setAnalyticsSection('sepsis'),
    },
    {
      label: '打开抢救期总览',
      value: '患者总览 / 抢救期',
      meta: '带着抢救期风险筛选回到患者工作台。',
      action: () => router.push({ path: '/', query: { ...route.query, rescue_only: '1' } }),
    },
  ]
})

const peakSlotSummary = computed(() => {
  if (!heatmapSummary.value.peakText || heatmapSummary.value.peakText === '暂无峰值') {
    return { slot: '暂无峰值', meta: '等待热力图数据' }
  }
  return {
    slot: heatmapSummary.value.peakText.split(' · ').slice(1, 2)[0] || heatmapSummary.value.peakText,
    meta: heatmapSummary.value.peakText,
  }
})

const highRiskRatio = computed(() => {
  const source = displayFreqSeries.value
  const total = source.reduce((sum: number, item: any) => sum + Number(item?.total || 0), 0)
  const high = source.reduce((sum: number, item: any) => sum + Number(item?.high || 0), 0)
  const critical = source.reduce((sum: number, item: any) => sum + Number(item?.critical || 0), 0)
  const severe = high + critical
  const ratio = total > 0 ? `${Math.round((severe / total) * 100)}%` : '0%'
  return {
    ratio,
    meta: rescueOnly.value
      ? `${severe} / ${total} 次为抢救期高危 / 危急`
      : `${severe} / ${total} 次为高危或危急`,
  }
})

const alertOpsHighlights = computed(() => [
  {
    label: '当前窗口',
    value: analyticsWindowLabel.value,
    meta: `${rescueOnly.value ? '抢救期快筛' : '全量运营'} · ${bucket.value === 'hour' ? '小时' : '天'} 粒度`,
  },
  {
    label: topRuleHeadline.value,
    value: topRuleSummary.value.name,
    meta: topRuleSummary.value.meta,
  },
  {
    label: '峰值时段',
    value: peakSlotSummary.value.slot,
    meta: peakSlotSummary.value.meta,
  },
  {
    label: rescueOnly.value ? '抢救期压力' : '高危占比',
    value: highRiskRatio.value.ratio,
    meta: highRiskRatio.value.meta,
  },
])

const sepsisBundleKpi = computed(() => {
  const summary = sepsisBundleCompliance.value || {}
  const total = Number(summary?.total_cases || 0)
  const met = Number(summary?.compliant_1h_cases || 0)
  const overdue1h = Number(summary?.overdue_1h_cases || 0)
  const overdue3h = Number(summary?.overdue_3h_cases || 0)
  const pending = Number(summary?.pending_active_cases || 0)
  const rateValue = Number(summary?.compliance_rate || 0)
  return {
    rate: total ? `${(rateValue * 100).toFixed(1)}%` : '0%',
    meta: total
      ? `${met} / ${total} 达标 · 超1h ${overdue1h} · 超3h ${overdue3h}${pending ? ` · 进行中 ${pending}` : ''}`
      : '本月暂无脓毒症解放束病例',
  }
})

const sepsisStatusCards = computed(() => {
  const summary = sepsisBundleCompliance.value || {}
  const total = Number(summary?.total_cases || 0)
  const met = Number(summary?.compliant_1h_cases || 0)
  const overdue1h = Number(summary?.overdue_1h_cases || 0)
  const overdue3h = Number(summary?.overdue_3h_cases || 0)
  const pending = Number(summary?.pending_active_cases || 0)
  return [
    {
      label: '1h 达标率',
      value: sepsisBundleKpi.value.rate,
      meta: total ? `${met} / ${total} 例按时完成` : '暂无病例',
      tone: 'bundle',
    },
    {
      label: '超 1h 病例',
      value: `${overdue1h}`,
      meta: total ? `占全部病例 ${ratioText(overdue1h, total)}` : '等待病例数据',
      tone: 'risk',
    },
    {
      label: '超 3h 病例',
      value: `${overdue3h}`,
      meta: total ? `需要重点复盘 ${ratioText(overdue3h, total)}` : '等待病例数据',
      tone: 'risk',
    },
    {
      label: '进行中',
      value: `${pending}`,
      meta: pending ? '仍在 1h / 3h 时窗内跟踪' : '当前无在途病例',
      tone: 'weaning',
    },
  ]
})

const sepsisProgressRows = computed(() => {
  const summary = sepsisBundleCompliance.value || {}
  const total = Math.max(1, Number(summary?.total_cases || 0))
  const compliant = Number(summary?.compliant_1h_cases || 0)
  const overdue1h = Number(summary?.overdue_1h_cases || 0)
  const overdue3h = Number(summary?.overdue_3h_cases || 0)
  const pending = Number(summary?.pending_active_cases || 0)
  return [
    {
      label: '1h 已达标',
      value: `${compliant} 例`,
      width: `${Math.min(100, (compliant / total) * 100)}%`,
      meta: `占全部病例 ${ratioText(compliant, total)}`,
      color: 'linear-gradient(90deg, #14b8a6, #2dd4bf)',
    },
    {
      label: '超 1h 未完成',
      value: `${overdue1h} 例`,
      width: `${Math.min(100, (overdue1h / total) * 100)}%`,
      meta: `需要值班与流程复盘 ${ratioText(overdue1h, total)}`,
      color: 'linear-gradient(90deg, #f59e0b, #fb923c)',
    },
    {
      label: '超 3h 持续滞后',
      value: `${overdue3h} 例`,
      width: `${Math.min(100, (overdue3h / total) * 100)}%`,
      meta: `重点关注迟滞链路 ${ratioText(overdue3h, total)}`,
      color: 'linear-gradient(90deg, #fb7185, #f43f5e)',
    },
    {
      label: '仍在进行中',
      value: `${pending} 例`,
      width: `${Math.min(100, (pending / total) * 100)}%`,
      meta: pending ? '建议继续跟踪首小时动作闭环' : '当前没有在途病例',
      color: 'linear-gradient(90deg, #38bdf8, #60a5fa)',
    },
  ]
})

const sepsisAiInsight = computed(() => sepsisBundleAiInsight.value || {})
const sepsisAiFindings = computed(() => Array.isArray(sepsisAiInsight.value?.key_findings) ? sepsisAiInsight.value.key_findings : [])
const sepsisAiActions = computed(() => Array.isArray(sepsisAiInsight.value?.recommended_actions) ? sepsisAiInsight.value.recommended_actions : [])
const sepsisAiManagementRows = computed(() => (
  sepsisAiFindings.value.length
    ? sepsisAiFindings.value
    : ['当前没有结构化关键发现，建议结合月度统计继续复盘。']
))
const sepsisAiActionRows = computed(() => (
  sepsisAiActions.value.length
    ? sepsisAiActions.value
    : ['当前没有智能行动建议，可先从超 1 小时 / 超 3 小时个案逐例追踪。']
))

const sepsisNarratives = computed(() => {
  const summary = sepsisBundleCompliance.value || {}
  const total = Number(summary?.total_cases || 0)
  const rate = Number(summary?.compliance_rate || 0)
  const overdue3h = Number(summary?.overdue_3h_cases || 0)
  const pending = Number(summary?.pending_active_cases || 0)
  return [
    {
      label: '月度结论',
      value: total ? `${formatPct(rate)} 达标` : '暂无病例',
      meta: total ? `${analyticsScopeLabel.value} 当前共纳入 ${total} 例解放束病例` : '等待本月数据积累',
    },
    {
      label: '优先复盘',
      value: overdue3h ? `${overdue3h} 例超 3h` : '暂无超 3h',
      meta: overdue3h ? '建议排查抗菌药、补液、乳酸复测等延迟链路' : '当前没有长时间未闭环病例',
    },
    {
      label: '在途追踪',
      value: pending ? `${pending} 例进行中` : '无在途病例',
      meta: pending ? '交接班时建议保留解放束完成节点提醒' : '当前无需额外追踪',
    },
  ]
})

const reintubationRiskKpi = computed(() => {
  const summary = weaningSummary.value || {}
  const extubated = Number(summary?.extubated_patients || 0)
  const risk = Number(summary?.reintubation_risk_patients || 0)
  const critical = Number(summary?.critical_post_extubation_patients || 0)
  const rate = Number(summary?.reintubation_risk_ratio || 0)
  return {
    rate: extubated ? `${(rate * 100).toFixed(1)}%` : '0%',
    meta: extubated
      ? `${risk} / ${extubated} 例拔管后触发风险 · 危急 ${critical} 例`
      : '本月暂无拔管患者',
  }
})

const weaningHighRiskKpi = computed(() => {
  const summary = weaningSummary.value || {}
  const total = Number(summary?.weaning_assessed_patients || 0)
  const high = Number(summary?.high_risk_patients || 0)
  const rate = Number(summary?.high_risk_ratio || 0)
  return {
    rate: total ? `${(rate * 100).toFixed(1)}%` : '0%',
    meta: total
      ? `${high} / ${total} 例为高危/危急`
      : '本月暂无脱机评估',
  }
})

const weaningHighlights = computed(() => {
  const summary = weaningSummary.value || {}
  const assessed = Number(summary?.weaning_assessed_patients || 0)
  const extubated = Number(summary?.extubated_patients || 0)
  return [
    {
      label: '脱机评估覆盖',
      value: `${assessed} 例`,
      meta: assessed ? `本月已有 ${assessed} 例进入撤机评估` : '本月暂无撤机评估',
    },
    {
      label: '高风险占比',
      value: weaningHighRiskKpi.value.rate,
      meta: weaningHighRiskKpi.value.meta,
    },
    {
      label: '再插管风险',
      value: reintubationRiskKpi.value.rate,
      meta: reintubationRiskKpi.value.meta,
    },
    {
      label: '拔管患者',
      value: `${extubated} 例`,
      meta: extubated ? '建议结合自主呼吸试验时间线与术后风险复盘' : '暂无拔管患者',
    },
  ]
})

const weaningStatusCards = computed(() => {
  const summary = weaningSummary.value || {}
  const assessed = Number(summary?.weaning_assessed_patients || 0)
  const high = Number(summary?.high_risk_patients || 0)
  const extubated = Number(summary?.extubated_patients || 0)
  const risk = Number(summary?.reintubation_risk_patients || 0)
  const critical = Number(summary?.critical_post_extubation_patients || 0)
  return [
    {
      label: '高风险患者',
      value: `${high}`,
      meta: assessed ? `占脱机评估 ${ratioText(high, assessed)}` : '暂无评估基数',
      tone: 'weaning-high',
    },
    {
      label: '再插管风险患者',
      value: `${risk}`,
      meta: extubated ? `占拔管患者 ${ratioText(risk, extubated)}` : '暂无拔管基数',
      tone: 'risk',
    },
    {
      label: '危急拔管后事件',
      value: `${critical}`,
      meta: critical ? '建议回看失败模式与床旁处置链路' : '当前无危急再插管事件',
      tone: 'bundle',
    },
  ]
})

const activeSectionKpis = computed(() => {
  if (analyticsSection.value === 'scenarios') {
    return [
      { label: '场景库覆盖率', code: '场景', value: scenarioCoverageRate.value, meta: `${Number(scenarioCoverageSummary.value?.triggered_catalog_scenarios || 0)} / ${Number(scenarioCoverageSummary.value?.total_catalog_scenarios || 0)} 场景已在当前窗口命中`, tone: 'bundle' },
      { label: '场景组', code: '分组', value: `${scenarioGroupRows.value.length}`, meta: '统一引擎下的扩展场景分组' },
      { label: '高频场景', code: '首位', value: scenarioTopRows.value[0]?.title || '暂无数据', meta: scenarioTopRows.value[0] ? `${scenarioTopRows.value[0].alert_count} 次命中` : '等待扩展场景数据', compact: true },
      { label: '告警总量', code: '命中', value: `${Number(scenarioCoverageSummary.value?.total_alerts || 0)}`, meta: `${analyticsWindowLabel.value} 内扩展场景累计触发次数`, tone: 'risk' },
    ]
  }
  if (analyticsSection.value === 'sepsis') {
    return [
      {
        label: '监测范围',
        code: '范围',
        value: analyticsScopeLabel.value,
        meta: `${analyticsMonthCode.value} 月度质控视角`,
      },
      {
        label: '脓毒症 1 小时解放束',
        code: sepsisBundleMonthCode.value,
        value: sepsisBundleKpi.value.rate,
        meta: sepsisBundleKpi.value.meta,
        tone: 'bundle',
      },
      {
        label: '超 3h 病例',
        code: '超3小时',
        value: `${Number(sepsisBundleCompliance.value?.overdue_3h_cases || 0)}`,
        meta: Number(sepsisBundleCompliance.value?.overdue_3h_cases || 0)
          ? '建议优先抽查延迟原因'
          : '当前无超 3h 病例',
        tone: 'risk',
      },
      {
        label: '进行中病例',
        code: '进行中',
        value: `${Number(sepsisBundleCompliance.value?.pending_active_cases || 0)}`,
        meta: Number(sepsisBundleCompliance.value?.pending_active_cases || 0)
          ? '交接班需持续追踪'
          : '当前无在途病例',
        tone: 'weaning',
      },
    ]
  }
  if (analyticsSection.value === 'weaning') {
    return [
      {
        label: '监测范围',
        code: '范围',
        value: analyticsScopeLabel.value,
        meta: `${analyticsMonthCode.value} 月度撤机分析`,
      },
      {
        label: '本月再插管风险',
        code: '月度',
        value: reintubationRiskKpi.value.rate,
        meta: reintubationRiskKpi.value.meta,
        tone: 'weaning',
      },
      {
        label: '脱机失败高风险占比',
        code: '高风险',
        value: weaningHighRiskKpi.value.rate,
        meta: weaningHighRiskKpi.value.meta,
        tone: 'weaning-high',
      },
      {
        label: '评估患者数',
        code: '评估数',
        value: `${Number(weaningSummary.value?.weaning_assessed_patients || 0)}`,
        meta: '进入脱机评估的人群基数',
      },
    ]
  }
  if (analyticsSection.value === 'nursing') {
    return [
      {
        label: '未来班次工时',
        code: '工时',
        value: `${Number(nursingSummary.value?.total_predicted_shift_hours || 0).toFixed(1)} 小时`,
        meta: `${Number(nursingSummary.value?.patient_count || 0)} 位患者未来 ${Number(nursingSummary.value?.shift_hours || 8)} 小时预计护理投入`,
        tone: 'weaning',
      },
      {
        label: '建议护士数',
        code: '护士',
        value: `${Number(nursingSummary.value?.recommended_nurse_ceiling || 0)}`,
        meta: `建议 ${Number(nursingSummary.value?.recommended_nurse_count || 0).toFixed(1)} / 有效 ${Number(nursingSummary.value?.effective_nurse_count || 0)}`,
        tone: 'bundle',
      },
      {
        label: '护理缺口',
        code: '缺口',
        value: `${Number(nursingSummary.value?.staffing_gap_ceiling || 0)}`,
        meta: `${Number(nursingSummary.value?.staffing_gap || 0).toFixed(1)} 人，${Number(nursingSummary.value?.extreme_count || 0)} 例极高强度`,
        tone: 'risk',
      },
      {
        label: '峰值科室',
        code: '峰值科室',
        value: nursingSummary.value?.peak_dept || '暂无数据',
        meta: nursingSummary.value?.peak_dept
          ? `建议护士数 ${Number(nursingSummary.value?.peak_dept_nurse_count || 0).toFixed(1)}`
          : '等待护理负荷数据',
        compact: true,
      },
    ]
  }
  return [
    {
      label: '监测窗口',
      code: '窗口',
      value: analyticsWindowLabel.value,
      meta: `粒度 ${bucket.value === 'hour' ? '小时' : '天'} · 前 ${topN} 项`,
    },
    {
      label: topRuleHeadline.value,
      code: '规则',
      value: topRuleSummary.value.name,
      meta: topRuleSummary.value.meta,
      compact: true,
    },
    {
      label: '峰值时段',
      code: '峰值时段',
      value: peakSlotSummary.value.slot,
      meta: peakSlotSummary.value.meta,
    },
    {
      label: rescueOnly ? '抢救期占比' : '高危占比',
      code: '高危占比',
      value: highRiskRatio.value.ratio,
      meta: highRiskRatio.value.meta,
      tone: 'risk',
    },
  ]
})

function setAnalyticsSection(section: 'alerts' | 'sepsis' | 'weaning' | 'nursing' | 'scenarios') {
  analyticsSection.value = section
}

function openDeptOverview(dept: any) {
  const value = String(dept || '').trim()
  if (!value) return
  const nextQuery: Record<string, any> = { dept: value }
  if (analyticsSection.value === 'alerts' && rescueOnly.value) nextQuery.rescue_only = '1'
  if (analyticsSection.value === 'weaning') nextQuery.alert_level = 'critical'
  if (analyticsSection.value === 'sepsis') nextQuery.alert_level = 'warning'
  router.push({ path: '/', query: nextQuery })
}

const weaningTrendRows = computed(() =>
  Array.isArray(weaningSummary.value?.daily_trend) ? weaningSummary.value.daily_trend : []
)

const weaningDeptCompare = computed(() =>
  Array.isArray(weaningSummary.value?.dept_compare) ? weaningSummary.value.dept_compare : []
)

const weaningDeptCompareTable = computed(() =>
  weaningDeptCompare.value.map((row: any) => ({
    ...row,
    high_risk_ratio_text: `${(Number(row?.high_risk_ratio || 0) * 100).toFixed(1)}%`,
  }))
)

const nursingSummary = computed(() => nursingWorkload.value?.summary || {})
const nursingDeptRows = computed(() =>
  Array.isArray(nursingWorkload.value?.dept_rows) ? nursingWorkload.value.dept_rows : []
)
const nursingPatientRows = computed(() =>
  Array.isArray(nursingWorkload.value?.patient_rows) ? nursingWorkload.value.patient_rows : []
)
const nursingHeatmapX = computed(() =>
  Array.isArray(nursingWorkload.value?.heatmap?.x_labels) ? nursingWorkload.value.heatmap.x_labels : []
)
const nursingHeatmapY = computed(() =>
  Array.isArray(nursingWorkload.value?.heatmap?.y_labels) ? nursingWorkload.value.heatmap.y_labels : []
)
const nursingHeatmapData = computed(() =>
  Array.isArray(nursingWorkload.value?.heatmap?.data) ? nursingWorkload.value.heatmap.data : []
)
const nursingDeptProgressRows = computed(() =>
  nursingDeptRows.value.slice(0, 8).map((row: any) => {
    const nurses = Number(row?.recommended_nurse_count || 0)
    const intensity = Number(row?.avg_nas_score || 0)
    const width = `${Math.max(8, Math.min(100, intensity))}%`
    const color = intensity >= 85 ? '#f43f5e' : intensity >= 65 ? '#fb923c' : intensity >= 45 ? '#38bdf8' : '#34d399'
    return {
      label: row?.dept || '未知科室',
      value: `${nurses.toFixed(nurses >= 10 ? 0 : 1)} 护士`,
      width,
      color,
      meta: `${Number(row?.patient_count || 0)} 床 · 在岗 ${Number(row?.effective_nurse_count || 0)} 人 · 缺口 ${Number(row?.staffing_gap || 0).toFixed(1)}`,
    }
  })
)

const deptRankOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: icuTooltip({
    trigger: 'axis',
    axisPointer: { type: 'shadow' },
    formatter: (params: any[]) => {
      const item = Array.isArray(params) ? params[0] : params
      return tooltipShell(
        item?.name || '科室',
        [tooltipRow('预警总量', `${item?.value ?? 0} 次`, item?.color || '#16b3c9')],
        'Department Ranking'
      )
    },
  }),
  grid: icuGrid({ left: 84, right: 18, top: 16, bottom: 24 }),
  xAxis: icuValueAxis({ axisLabel: { fontSize: 10 } }),
  yAxis: icuCategoryAxis(displayDeptRankings.value.map((d: any) => d.dept), {
    axisLine: { lineStyle: { color: 'rgba(79, 182, 219, 0.18)' } },
    axisLabel: { color: '#b7ddec', fontSize: 10 },
  }),
  series: [
    {
      type: 'bar',
      data: displayDeptRankings.value.map((d: any) => d.count || 0),
      itemStyle: {
        color: (params: any) => {
          const colors = ['#16b3c9', '#0ea5b7', '#0891b2', '#0369a1']
          return colors[params.dataIndex % colors.length]
        },
        borderRadius: [0, 8, 8, 0],
      },
      barMaxWidth: 18,
      label: {
        show: true,
        position: 'right',
        color: '#dffbff',
        fontSize: 10,
      },
    },
  ],
}))

const bedRankOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: icuTooltip({
    trigger: 'axis',
    axisPointer: { type: 'shadow' },
    formatter: (params: any[]) => {
      const item = Array.isArray(params) ? params[0] : params
      return tooltipShell(
        item?.name || '床位',
        [tooltipRow('预警总量', `${item?.value ?? 0} 次`, item?.color || '#fb923c')],
        'Bed Ranking'
      )
    },
  }),
  grid: icuGrid({ left: 102, right: 18, top: 16, bottom: 24 }),
  xAxis: icuValueAxis({ axisLabel: { fontSize: 10 } }),
  yAxis: icuCategoryAxis(displayBedRankings.value.map((d: any) => `${d.dept}-${d.bed}`), {
    axisLine: { lineStyle: { color: 'rgba(79, 182, 219, 0.18)' } },
    axisLabel: { color: '#b7ddec', fontSize: 10 },
  }),
  series: [
    {
      type: 'bar',
      data: displayBedRankings.value.map((d: any) => d.count || 0),
      itemStyle: {
        color: (params: any) => {
          const colors = ['#f59e0b', '#fb923c', '#fb7185', '#f43f5e']
          return colors[params.dataIndex % colors.length]
        },
        borderRadius: [0, 8, 8, 0],
      },
      barMaxWidth: 18,
      label: {
        show: true,
        position: 'right',
        color: '#dffbff',
        fontSize: 10,
      },
    },
  ],
}))

const weaningTrendOption = computed(() => {
  const xs = weaningTrendRows.value.map((row: any) => String(row.date || '').slice(5))
  return {
    backgroundColor: 'transparent',
    tooltip: icuTooltip({
      trigger: 'axis',
      formatter: (params: any[]) => {
        const list = Array.isArray(params) ? params : [params]
        const title = list[0]?.axisValueLabel || list[0]?.name || '日期'
        const rows = list.map((item: any) => tooltipRow(item.seriesName || '指标', item.value ?? 0, item.color || '#67e8f9'))
        return tooltipShell(title, rows, '撤机月度趋势')
      },
    }),
    legend: icuLegend({ textStyle: { fontSize: 10 } }),
    grid: icuGrid({ left: 42, right: 18, top: 34, bottom: 34 }),
    xAxis: icuCategoryAxis(xs, { axisLabel: { fontSize: 10, margin: 10 } }),
    yAxis: icuValueAxis({ axisLabel: { fontSize: 10 } }),
    series: [
      {
        name: '脱机评估',
        type: 'bar',
        data: weaningTrendRows.value.map((row: any) => Number(row.assessed || 0)),
        itemStyle: { color: '#0ea5b7', borderRadius: [6, 6, 0, 0] },
        barMaxWidth: 14,
      },
      {
        name: '高风险',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2, color: '#f59e0b' },
        itemStyle: { color: '#f59e0b' },
        data: weaningTrendRows.value.map((row: any) => Number(row.high_risk || 0)),
      },
      {
        name: '拔管后风险',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2, color: '#fb5a7a' },
        itemStyle: { color: '#fb5a7a' },
        data: weaningTrendRows.value.map((row: any) => Number(row.reintubation_risk || 0)),
      },
    ],
  }
})

const weaningDeptCompareOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: icuTooltip({
    trigger: 'axis',
    axisPointer: { type: 'shadow' },
    formatter: (params: any[]) => {
      const list = Array.isArray(params) ? params : [params]
      const title = list[0]?.name || '科室'
      const rows = list.map((item: any) => tooltipRow(item.seriesName || '指标', `${item.value ?? 0}%`, item.color || '#67e8f9'))
      return tooltipShell(title, rows, 'Department Compare')
    },
  }),
  legend: icuLegend({ textStyle: { fontSize: 10 } }),
  grid: icuGrid({ left: 52, right: 18, top: 28, bottom: 34 }),
  xAxis: icuCategoryAxis(weaningDeptCompare.value.map((row: any) => row.dept || '未知科室'), {
    axisLabel: { color: '#b7ddec', fontSize: 10, interval: 0, rotate: 18 },
  }),
  yAxis: icuValueAxis({
    axisLabel: {
      fontSize: 10,
      formatter: (value: number) => `${value}%`,
    },
  }),
  series: [
    {
      name: '脱机高风险占比',
      type: 'bar',
      data: weaningDeptCompare.value.map((row: any) => Math.round(Number(row.high_risk_ratio || 0) * 1000) / 10),
      itemStyle: { color: '#f59e0b', borderRadius: [6, 6, 0, 0] },
      barMaxWidth: 18,
    },
    {
      name: '再插管风险占比',
      type: 'bar',
      data: weaningDeptCompare.value.map((row: any) => Math.round(Number(row.reintubation_risk_ratio || 0) * 1000) / 10),
      itemStyle: { color: '#fb5a7a', borderRadius: [6, 6, 0, 0] },
      barMaxWidth: 18,
    },
  ],
}))

const deptColumns = [
  { title: '科室', dataIndex: 'dept', key: 'dept' },
  { title: '总量', dataIndex: 'count', key: 'count', width: 72 },
  { title: '危急', dataIndex: 'critical', key: 'critical', width: 80 },
  { title: '高危', dataIndex: 'high', key: 'high', width: 70 },
  { title: '预警', dataIndex: 'warning', key: 'warning', width: 70 },
]

const bedColumns = [
  { title: '科室', dataIndex: 'dept', key: 'dept', width: 120 },
  { title: '床位', dataIndex: 'bed', key: 'bed', width: 90 },
  { title: '总量', dataIndex: 'count', key: 'count', width: 72 },
  { title: '危急', dataIndex: 'critical', key: 'critical', width: 80 },
  { title: '高危', dataIndex: 'high', key: 'high', width: 70 },
  { title: '预警', dataIndex: 'warning', key: 'warning', width: 70 },
]

const weaningDeptColumns = [
  { title: '科室', dataIndex: 'dept', key: 'dept' },
  { title: '脱机评估', dataIndex: 'weaning_assessed_patients', key: 'weaning_assessed_patients', width: 84 },
  { title: '高风险', dataIndex: 'high_risk_patients', key: 'high_risk_patients', width: 76 },
  {
    title: '高风险占比',
    dataIndex: 'high_risk_ratio_text',
    key: 'high_risk_ratio',
    width: 92,
  },
  { title: '拔管患者', dataIndex: 'extubated_patients', key: 'extubated_patients', width: 84 },
  { title: '再插管风险', dataIndex: 'reintubation_risk_patients', key: 'reintubation_risk_patients', width: 92 },
]

async function loadFrequency() {
  const res = await getAlertAnalyticsFrequency({
    ...commonParams(),
    bucket: bucket.value,
  })
  freqSeries.value = res.data.series || []
}

async function loadHeatmap() {
  const res = await getAlertAnalyticsHeatmap({
    ...commonParams(),
    top_n: topN.value,
  })
  heatmapX.value = res.data.x_labels || []
  heatmapY.value = (res.data.y_labels || []).map((item: any) => formatAlertTypeLabel(item))
  heatmapData.value = res.data.data || []
}

async function loadRankings() {
  const res = await getAlertAnalyticsRankings({
    ...commonParams(),
    top_n: topN.value,
  })
  deptRankings.value = res.data.dept_rankings || []
  bedRankings.value = (res.data.bed_rankings || []).map((r: any, idx: number) => ({
    ...r,
    bedKey: `${r.dept || ''}-${r.bed || ''}-${idx}`,
  }))
}

async function loadSepsisBundleCompliance() {
  const res = await getSepsisBundleCompliance({
    month: sepsisBundleMonth.value,
    ...(deptCode.value ? { dept_code: deptCode.value } : {}),
    ...(!deptCode.value && deptName.value ? { dept: deptName.value } : {}),
  })
  sepsisBundleCompliance.value = res.data.summary || null
  sepsisBundleAiInsight.value = res.data.ai_insight || null
}

async function loadScenarioCoverage() {
  const res = await getScenarioCoverageAnalytics({
    ...commonParams(),
    top_n: topN.value,
  })
  scenarioCoverageSummary.value = res.data.summary || null
  scenarioGroupRows.value = res.data.group_rows || []
  scenarioTopRows.value = (res.data.top_scenarios || []).map((item: any) => ({
    ...item,
    group: formatScenarioGroupLabel(item.group),
  }))
  scenarioHeatmapX.value = res.data.heatmap?.x_labels || []
  scenarioHeatmapY.value = (res.data.heatmap?.y_labels || []).map((item: any) => formatScenarioGroupLabel(item))
  scenarioHeatmapData.value = res.data.heatmap?.data || []
}

async function loadNursingWorkload() {
  const res = await getNursingWorkloadAnalytics({
    window: windowRange.value,
    ...(deptCode.value ? { dept_code: deptCode.value } : {}),
    ...(!deptCode.value && deptName.value ? { dept: deptName.value } : {}),
  })
  nursingWorkload.value = res.data || null
}

async function loadWeaningSummary() {
  const res = await getWeaningSummary({
    month: sepsisBundleMonth.value,
    ...(deptCode.value ? { dept_code: deptCode.value } : {}),
    ...(!deptCode.value && deptName.value ? { dept: deptName.value } : {}),
  })
  weaningSummary.value = res.data.summary || null
}

async function loadRecentRescueAlerts() {
  const res = await getRecentAlerts(200, {
    ...(deptCode.value ? { dept_code: deptCode.value } : {}),
    ...(!deptCode.value && deptName.value ? { dept: deptName.value } : {}),
  })
  recentAlerts.value = res.data.records || []
}

async function loadSection(name: string, task: () => Promise<void>) {
  try {
    await task()
  } catch (error) {
    console.error(`加载 Analytics 分区失败: ${name}`, error)
  }
}

async function loadAll() {
  if (loading.value) return
  loading.value = true
  try {
    await Promise.all([
      loadSection('frequency', loadFrequency),
      loadSection('heatmap', loadHeatmap),
      loadSection('rankings', loadRankings),
      loadSection('sepsis-bundle', loadSepsisBundleCompliance),
      loadSection('weaning-summary', loadWeaningSummary),
      loadSection('nursing-workload', loadNursingWorkload),
      loadSection('scenario-coverage', loadScenarioCoverage),
      loadSection('recent-alerts', loadRecentRescueAlerts),
    ])
  } finally {
    loading.value = false
  }
}

watch([windowRange, bucket, topN], () => {
  void loadAll()
})

watch(analyticsSection, (section) => {
  const nextQuery = { ...route.query, section }
  router.replace({ query: nextQuery })
})

watch(
  () => route.query.section,
  (section) => {
    const normalized = normalizeAnalyticsSection(section)
    if (normalized !== analyticsSection.value) {
      analyticsSection.value = normalized
    }
  }
)

watch(
  () => route.query,
  () => {
    void loadAll()
  },
  { deep: true }
)

onMounted(() => {
  void loadAll()
})
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&display=swap');

.analytics-page {
  position: relative;
  isolation: isolate;
  padding: 16px 22px 24px;
  background:
    radial-gradient(circle at top, rgba(34, 211, 238, 0.1), rgba(34, 211, 238, 0) 28%),
    linear-gradient(180deg, #06111d 0%, #040b14 100%);
  min-height: 100%;
  font-family: 'Rajdhani', 'Noto Sans SC', sans-serif;
}

.analytics-page::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(rgba(73, 196, 255, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(73, 196, 255, 0.04) 1px, transparent 1px);
  background-size: 28px 28px;
  opacity: 0.26;
  z-index: -1;
}

.filter-card {
  background:
    linear-gradient(180deg, rgba(9, 22, 36, 0.94) 0%, rgba(6, 15, 27, 0.92) 100%);
  border: 1px solid rgba(80, 199, 255, 0.16);
  margin-bottom: 16px;
  border-radius: 12px;
  box-shadow: inset 0 1px 0 rgba(145, 228, 255, 0.06), 0 12px 28px rgba(0, 0, 0, 0.2);
}

.filter-card :deep(.ant-card-body) {
  padding: 12px 14px;
}

.filter-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.left-tools .label {
  font-size: 12px;
  color: #7ccfe4;
  margin-right: 4px;
  font-weight: 600;
  letter-spacing: 0.08em;
}

.filter-card :deep(.ant-segmented) {
  background: rgba(8, 28, 44, 0.78);
  border: 1px solid rgba(80, 199, 255, 0.14);
}

.filter-card :deep(.ant-segmented-item) {
  color: #8bcfe1;
  font-weight: 600;
}

.filter-card :deep(.ant-segmented-item-selected) {
  background: linear-gradient(180deg, rgba(11, 107, 137, 0.96) 0%, rgba(7, 63, 86, 0.98) 100%);
  color: #effcff;
  box-shadow: 0 0 12px rgba(34, 211, 238, 0.08);
}

.filter-card :deep(.ant-input-number) {
  background: rgba(8, 28, 44, 0.78);
  border-color: rgba(80, 199, 255, 0.14);
}

.filter-card :deep(.ant-input-number input) {
  color: #e8fbff;
}

.filter-card :deep(.ant-btn) {
  background: linear-gradient(180deg, rgba(11, 107, 137, 0.96) 0%, rgba(7, 63, 86, 0.98) 100%);
  border-color: rgba(110, 231, 249, 0.28);
  color: #effcff;
  font-weight: 600;
}
.rescue-toggle {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid rgba(251, 113, 133, 0.22);
  background: linear-gradient(180deg, rgba(51, 15, 27, 0.9) 0%, rgba(27, 11, 18, 0.92) 100%);
  color: #ffcad5;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: all .18s ease;
}
.rescue-toggle:hover,
.rescue-toggle.active {
  color: #fff1f4;
  border-color: rgba(251, 113, 133, 0.38);
  box-shadow: 0 0 18px rgba(251, 113, 133, 0.14);
}

.analytics-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.section-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
  margin-bottom: 16px;
  border-radius: 14px;
  border: 1px solid rgba(80, 199, 255, 0.14);
  background:
    radial-gradient(circle at top right, rgba(34, 211, 238, 0.12), rgba(34, 211, 238, 0) 36%),
    linear-gradient(180deg, rgba(7, 20, 34, 0.96) 0%, rgba(4, 12, 22, 0.98) 100%);
  box-shadow: inset 0 1px 0 rgba(145, 228, 255, 0.05), 0 12px 28px rgba(0, 0, 0, 0.18);
}

.hero-copy {
  display: grid;
  gap: 6px;
  max-width: 760px;
}

.hero-kicker {
  color: #67e8f9;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.18em;
}

.hero-title {
  margin: 0;
  color: #effcff;
  font-size: 28px;
  line-height: 1.05;
}

.hero-desc {
  margin: 0;
  color: #8bbfd0;
  font-size: 13px;
  line-height: 1.6;
}

.hero-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: flex-end;
}

.hero-chip {
  min-width: 132px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(79, 182, 219, 0.16);
  background: rgba(8, 28, 44, 0.76);
}

.hero-chip__label {
  display: block;
  color: #77c9de;
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.hero-chip__value {
  display: block;
  margin-top: 4px;
  color: #effcff;
  font-size: 14px;
}

.kpi-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.action-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.action-tile {
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid rgba(79, 182, 219, 0.14);
  background:
    radial-gradient(circle at top right, rgba(34, 211, 238, 0.08), rgba(34, 211, 238, 0) 38%),
    linear-gradient(180deg, rgba(7, 20, 34, 0.96) 0%, rgba(4, 12, 22, 0.98) 100%);
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
}

.action-tile:hover {
  transform: translateY(-1px);
  border-color: rgba(103, 232, 249, 0.28);
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.2);
}

.action-tile__label {
  color: #77c9de;
  font-size: 11px;
  letter-spacing: 0.1em;
}

.action-tile__value {
  color: #effcff;
  font-size: 18px;
  line-height: 1.2;
}

.action-tile__meta {
  color: #8bbfd0;
  font-size: 11px;
  line-height: 1.5;
}

.kpi-tile {
  position: relative;
  overflow: hidden;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(80, 199, 255, 0.14);
  background:
    radial-gradient(circle at top right, rgba(34, 211, 238, 0.08), rgba(34, 211, 238, 0) 32%),
    linear-gradient(180deg, rgba(7, 20, 34, 0.96) 0%, rgba(4, 12, 22, 0.98) 100%);
  box-shadow: inset 0 1px 0 rgba(145, 228, 255, 0.05), 0 12px 28px rgba(0, 0, 0, 0.18);
}

.kpi-tile::after {
  content: '';
  position: absolute;
  inset: auto 0 0 0;
  height: 2px;
  background: linear-gradient(90deg, rgba(34, 211, 238, 0.08), rgba(34, 211, 238, 0.5), rgba(34, 211, 238, 0.08));
}

.kpi-tile--risk::after {
  background: linear-gradient(90deg, rgba(251, 90, 122, 0.08), rgba(251, 90, 122, 0.56), rgba(251, 90, 122, 0.08));
}

.kpi-tile--bundle::after {
  background: linear-gradient(90deg, rgba(45, 212, 191, 0.08), rgba(45, 212, 191, 0.56), rgba(45, 212, 191, 0.08));
}

.kpi-tile--weaning::after {
  background: linear-gradient(90deg, rgba(59, 130, 246, 0.08), rgba(59, 130, 246, 0.58), rgba(59, 130, 246, 0.08));
}

.kpi-tile--weaning-high::after {
  background: linear-gradient(90deg, rgba(245, 158, 11, 0.08), rgba(245, 158, 11, 0.58), rgba(245, 158, 11, 0.08));
}

.kpi-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.kpi-label {
  color: #7ed6eb;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.kpi-code {
  color: #4ec6de;
  font-size: 10px;
  letter-spacing: 0.12em;
  font-family: 'SF Mono', 'Consolas', monospace;
}

.kpi-value {
  color: #effcff;
  font-size: 24px;
  line-height: 1.1;
  font-weight: 700;
  font-family: 'Rajdhani', 'SF Mono', 'Consolas', monospace;
  letter-spacing: 0.03em;
}

.kpi-value--rule {
  font-size: 20px;
}

.kpi-sub {
  margin-top: 6px;
  color: #8bbfd0;
  font-size: 11px;
  line-height: 1.45;
}

.panel {
  background:
    radial-gradient(circle at top, rgba(34, 211, 238, 0.07), rgba(34, 211, 238, 0) 30%),
    linear-gradient(180deg, rgba(7, 20, 34, 0.96) 0%, rgba(4, 12, 22, 0.98) 100%);
  border: 1px solid rgba(80, 199, 255, 0.14);
  min-height: 420px;
  border-radius: 12px;
  box-shadow: inset 0 1px 0 rgba(145, 228, 255, 0.04), 0 12px 28px rgba(0, 0, 0, 0.2);
}

.panel :deep(.ant-card-head) {
  min-height: 50px;
  border-bottom: 1px solid rgba(80, 199, 255, 0.1);
  background: linear-gradient(90deg, rgba(9, 31, 48, 0.5), rgba(9, 31, 48, 0));
}

.panel :deep(.ant-card-head-title) {
  color: #67e8f9;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.panel :deep(.ant-card-body) {
  padding: 12px 14px 14px;
}

.panel-wide {
  grid-column: span 2;
}

.chart-wrap {
  width: 100%;
  position: relative;
  border-radius: 12px;
}

.chart-lg {
  height: 360px;
}

.chart-heatmap {
  padding-top: 4px;
}

.chart-md {
  height: 280px;
}

.panel-heatmap {
  background:
    radial-gradient(circle at top, rgba(34, 211, 238, 0.08), rgba(34, 211, 238, 0) 35%),
    var(--card-bg);
}

.heatmap-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 8px;
}

.summary-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(8, 28, 44, 0.78);
  border: 1px solid rgba(79, 182, 219, 0.18);
}

.summary-chip--wide {
  max-width: 100%;
}

.summary-k {
  font-size: 11px;
  color: #77c9de;
  letter-spacing: 0.08em;
}

.summary-v {
  font-size: 12px;
  color: #e8fbff;
  font-weight: 700;
}

.brief-board {
  display: grid;
  grid-template-columns: 1.8fr 1.2fr;
  gap: 16px;
  margin-bottom: 16px;
}

.brief-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.brief-card,
.focus-panel {
  border-radius: 14px;
  border: 1px solid rgba(79, 182, 219, 0.14);
  background:
    radial-gradient(circle at top right, rgba(34, 211, 238, 0.08), rgba(34, 211, 238, 0) 38%),
    linear-gradient(180deg, rgba(7, 20, 34, 0.96) 0%, rgba(4, 12, 22, 0.98) 100%);
  box-shadow: inset 0 1px 0 rgba(145, 228, 255, 0.05), 0 12px 28px rgba(0, 0, 0, 0.18);
}

.brief-card {
  display: grid;
  gap: 8px;
  padding: 14px 16px;
}

.brief-card__label {
  color: #77c9de;
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.brief-card__value {
  color: #effcff;
  font-size: 19px;
  font-weight: 700;
  line-height: 1.45;
}

.brief-card__meta {
  color: #8bbfd0;
  font-size: 11px;
  line-height: 1.6;
}

.focus-panel {
  display: grid;
  gap: 12px;
  padding: 14px 16px;
}

.focus-panel__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.focus-panel__kicker {
  color: #77c9de;
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.focus-panel__title {
  color: #effcff;
  font-size: 18px;
  font-weight: 700;
}

.focus-panel__badge {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba(103, 232, 249, 0.14);
  background: rgba(8, 28, 44, 0.82);
  color: #bdf7ff;
  font-size: 10px;
  letter-spacing: 0.08em;
}

.focus-list {
  display: grid;
  gap: 10px;
}

.focus-item {
  display: grid;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(79, 182, 219, 0.12);
  background: rgba(7, 28, 42, 0.68);
}

.focus-item__label {
  color: #77c9de;
  font-size: 11px;
  letter-spacing: 0.08em;
}

.focus-item__value {
  color: #effcff;
  font-size: 15px;
  font-weight: 700;
  line-height: 1.6;
}

.focus-item__meta {
  color: #8bbfd0;
  font-size: 11px;
  line-height: 1.55;
}
.insight-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}

.insight-tile {
  padding: 14px;
  border-radius: 12px;
  border: 1px solid rgba(79, 182, 219, 0.12);
  background: rgba(7, 28, 42, 0.68);
}

.insight-label {
  color: #77c9de;
  font-size: 11px;
  letter-spacing: 0.08em;
}

.insight-value {
  margin-top: 6px;
  color: #effcff;
  font-size: 24px;
  font-weight: 700;
  line-height: 1.1;
}

.insight-meta {
  margin-top: 6px;
  color: #8bbfd0;
  font-size: 11px;
  line-height: 1.5;
}

.bundle-status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}

.bundle-status-grid--compact {
  grid-template-columns: 1fr;
}

.status-card {
  padding: 14px;
  border-radius: 12px;
  border: 1px solid rgba(79, 182, 219, 0.14);
  background:
    radial-gradient(circle at top right, rgba(34, 211, 238, 0.08), rgba(34, 211, 238, 0) 38%),
    rgba(7, 28, 42, 0.72);
}

.status-card--risk {
  border-color: rgba(251, 113, 133, 0.18);
}

.status-card--bundle {
  border-color: rgba(45, 212, 191, 0.18);
}

.status-card--weaning,
.status-card--weaning-high {
  border-color: rgba(96, 165, 250, 0.18);
}

.status-card__label {
  color: #77c9de;
  font-size: 11px;
  letter-spacing: 0.08em;
}

.status-card__value {
  margin-top: 8px;
  color: #effcff;
  font-size: 26px;
  line-height: 1;
  font-weight: 700;
}

.status-card__meta {
  margin-top: 8px;
  color: #8bbfd0;
  font-size: 11px;
  line-height: 1.5;
}

.progress-list {
  display: grid;
  gap: 14px;
}

.progress-row {
  display: grid;
  gap: 8px;
}

.progress-row__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #dff8ff;
  font-size: 12px;
}

.progress-row__top strong {
  color: #effcff;
  font-size: 14px;
}

.progress-row__meta {
  color: #8bbfd0;
  font-size: 11px;
}

.progress-bar {
  height: 10px;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(8, 28, 44, 0.82);
  border: 1px solid rgba(79, 182, 219, 0.14);
}

.progress-bar__fill {
  height: 100%;
  border-radius: inherit;
  box-shadow: 0 0 18px rgba(34, 211, 238, 0.18);
}

.insight-list {
  display: grid;
  gap: 12px;
}

.insight-line {
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(79, 182, 219, 0.12);
  background: rgba(7, 28, 42, 0.68);
}

.insight-line__label {
  color: #77c9de;
  font-size: 11px;
  letter-spacing: 0.08em;
}

.insight-line__value {
  margin-top: 6px;
  color: #effcff;
  font-size: 20px;
  font-weight: 700;
}

.insight-line__value--sm {
  font-size: 15px;
  line-height: 1.6;
  font-weight: 600;
}

.insight-line__meta {
  margin-top: 6px;
  color: #8bbfd0;
  font-size: 11px;
  line-height: 1.5;
}

.summary-card {
  display: grid;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(79, 182, 219, 0.12);
  background: rgba(7, 28, 42, 0.68);
}

.summary-card--hero {
  border-color: rgba(103, 232, 249, 0.18);
  background:
    radial-gradient(circle at top right, rgba(34, 211, 238, 0.1), rgba(34, 211, 238, 0) 36%),
    rgba(7, 28, 42, 0.8);
}

.summary-card__label {
  color: #77c9de;
  font-size: 11px;
  letter-spacing: 0.08em;
}

.summary-card__value {
  color: #effcff;
  font-size: 18px;
  font-weight: 700;
  line-height: 1.6;
}

.summary-card__value--sm {
  font-size: 15px;
  font-weight: 600;
}

.summary-card__meta {
  color: #8bbfd0;
  font-size: 11px;
  line-height: 1.5;
}

.advice-list {
  display: grid;
  gap: 12px;
}

.advice-card {
  display: grid;
  grid-template-columns: 44px 1fr;
  gap: 12px;
  align-items: start;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(79, 182, 219, 0.12);
  background: rgba(7, 28, 42, 0.68);
}

.advice-card__index {
  display: grid;
  place-items: center;
  min-height: 40px;
  border-radius: 10px;
  background: rgba(8, 28, 44, 0.82);
  border: 1px solid rgba(103, 232, 249, 0.14);
  color: #67e8f9;
  font-size: 16px;
  font-weight: 700;
  font-family: 'Rajdhani', 'SF Mono', 'Consolas', monospace;
}

.advice-card__body {
  display: grid;
  gap: 6px;
}

.advice-card__label {
  color: #77c9de;
  font-size: 11px;
  letter-spacing: 0.08em;
}

.advice-card__text {
  color: #effcff;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.65;
}

.rank-table {
  margin-top: 12px;
}

.empty {
  color: #7ccfe4;
  font-size: 12px;
  padding: 16px 8px;
}

.analytics-page :deep(.analytics-tooltip) {
  min-width: 180px;
  display: grid;
  gap: 8px;
}

.analytics-page :deep(.analytics-tooltip__title) {
  color: #ecfeff;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.analytics-page :deep(.analytics-tooltip__body) {
  display: grid;
  gap: 6px;
}

.analytics-page :deep(.analytics-tooltip__row) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.analytics-page :deep(.analytics-tooltip__label) {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #9eddef;
  font-size: 11px;
}

.analytics-page :deep(.analytics-tooltip__dot) {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  box-shadow: 0 0 10px rgba(103, 232, 249, 0.24);
}

.analytics-page :deep(.analytics-tooltip__value) {
  color: #effcff;
  font-size: 11px;
  font-weight: 700;
}

.analytics-page :deep(.analytics-tooltip__footer) {
  padding-top: 6px;
  border-top: 1px solid rgba(80, 199, 255, 0.12);
  color: #6fdcf2;
  font-size: 10px;
  letter-spacing: 0.08em;
}

.rank-table :deep(.ant-table) {
  background: transparent;
  color: #dff8ff;
}

.rank-table :deep(.ant-table-container) {
  border: 1px solid rgba(80, 199, 255, 0.08);
  border-radius: 10px;
  overflow: hidden;
}

.rank-table :deep(.ant-table-thead > tr > th) {
  background: rgba(8, 28, 44, 0.82);
  color: #7ccfe4;
  border-bottom-color: rgba(80, 199, 255, 0.1);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
}

.rank-table :deep(.ant-table-tbody > tr > td) {
  background: transparent;
  color: #e3fbff;
  border-bottom-color: rgba(80, 199, 255, 0.08);
  font-size: 12px;
}

.rank-table :deep(.ant-table-tbody > tr:hover > td) {
  background: rgba(11, 42, 63, 0.42) !important;
}

.rank-table :deep(.ant-table-placeholder) {
  background: transparent;
}

.rank-table :deep(.ant-empty-description) {
  color: #7ccfe4;
}

.analytics-link {
  color: #7dd3fc;
  cursor: pointer;
}

.analytics-link:hover {
  color: #b5f3ff;
}

@media (max-width: 980px) {
  .analytics-page {
    padding: 10px;
  }

  .section-hero {
    flex-direction: column;
    align-items: stretch;
  }

  .hero-meta {
    justify-content: flex-start;
  }

  .brief-board,
  .analytics-grid {
    grid-template-columns: 1fr;
  }

  .brief-grid {
    grid-template-columns: 1fr;
  }

  .kpi-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .action-strip {
    grid-template-columns: 1fr;
  }

  .panel,
  .panel-wide {
    grid-column: auto;
    min-height: 0;
  }

  .chart-lg,
  .chart-md {
    height: 300px;
  }
}

@media (max-width: 680px) {
  .kpi-strip {
    grid-template-columns: 1fr;
  }

  .hero-title {
    font-size: 22px;
  }

  .kpi-value {
    font-size: 20px;
  }

  .kpi-value--rule {
    font-size: 17px;
  }
}
</style>
```







