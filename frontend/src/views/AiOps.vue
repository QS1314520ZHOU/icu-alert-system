<template>
  <div class="ops-page">
    <a-card :bordered="false" class="ops-filter-card">
      <div class="ops-filter-row">
        <div class="ops-left-tools">
          <a-space wrap>
            <span class="ops-label">反馈窗口</span>
            <a-segmented v-model:value="days" :options="dayOptions" size="small" />
            <span class="ops-label">审核状态</span>
            <a-segmented v-model:value="thresholdStatus" :options="thresholdOptions" size="small" />
          </a-space>
        </div>
        <div class="ops-right-tools">
          <a-button size="small" :loading="loading" @click="loadAll">刷新运营视图</a-button>
        </div>
      </div>
    </a-card>

    <section class="ops-kpi-strip">
      <div class="ops-kpi">
        <span class="ops-kpi-label">工具模块</span>
        <strong class="ops-kpi-value">{{ monitorStats.length }}</strong>
        <small>{{ activeMonitorAlerts.length }} 条活跃监控告警</small>
      </div>
      <div class="ops-kpi">
        <span class="ops-kpi-label">反馈总数</span>
        <strong class="ops-kpi-value">{{ feedbackSummary.total || 0 }}</strong>
        <small>已确认占比 {{ percentText(feedbackSummary.confirmed_ratio) }}</small>
      </div>
      <div class="ops-kpi ops-kpi--warn">
        <span class="ops-kpi-label">不准确占比</span>
        <strong class="ops-kpi-value">{{ percentText(feedbackSummary.inaccurate_ratio) }}</strong>
        <small>{{ feedbackSummary.by_outcome?.inaccurate || 0 }} 条判定不准确</small>
      </div>
      <div class="ops-kpi ops-kpi--review">
        <span class="ops-kpi-label">待审核阈值</span>
        <strong class="ops-kpi-value">{{ thresholdSummary.pending_review || 0 }}</strong>
        <small>已批准 {{ thresholdSummary.approved || 0 }} / 已拒绝 {{ thresholdSummary.rejected || 0 }}</small>
      </div>
      <div class="ops-kpi ops-kpi--runtime">
        <span class="ops-kpi-label">模型服务</span>
        <strong class="ops-kpi-value">{{ runtimeStatusText }}</strong>
        <small>缓存 {{ runtimeCacheSize }} 条 / 并发上限 {{ runtimeConcurrencyLimit }}</small>
      </div>
    </section>

    <section class="ops-action-strip">
      <button
        v-for="item in opsActions"
        :key="item.label"
        type="button"
        class="ops-action-tile"
        @click="item.action()"
      >
        <span class="ops-action-label">{{ item.label }}</span>
        <strong class="ops-action-value">{{ item.value }}</strong>
        <small class="ops-action-meta">{{ item.meta }}</small>
      </button>
    </section>

    <section class="ops-grid">
      <a-card title="模型服务运行态" :bordered="false" class="ops-panel">
        <div class="ops-runtime-grid">
          <div class="ops-runtime-item">
            <span>缓存条目</span>
            <strong>{{ runtimeCacheSize }}</strong>
          </div>
          <div class="ops-runtime-item">
            <span>并发上限</span>
            <strong>{{ runtimeConcurrencyLimit }}</strong>
          </div>
          <div class="ops-runtime-item">
            <span>降级状态</span>
            <strong>{{ runtimeDegradedText }}</strong>
          </div>
          <div class="ops-runtime-item">
            <span>最近异常</span>
            <strong>{{ runtimeLastErrorText }}</strong>
          </div>
        </div>
        <div class="ops-runtime-note">
          用于观察大模型调用的缓存、限流和自动降级状态，帮助判断响应慢是模型侧、缓存未命中还是并发拥塞。
        </div>
      </a-card>

      <a-card title="运行监控" :bordered="false" class="ops-panel">
        <div v-if="monitorStats.length" class="ops-table-wrap">
          <a-table
            size="small"
            :columns="monitorColumns"
            :data-source="monitorStats"
            :pagination="false"
            row-key="module"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'module'">
                <a class="ops-link" @click.prevent="openAnalyticsByModule(record.module)">{{ moduleLabel(record.module) }}</a>
              </template>
            </template>
          </a-table>
        </div>
        <div v-else class="ops-empty">暂无运行监控统计</div>
        <div v-if="activeMonitorAlerts.length" class="ops-alert-row">
          <button
            v-for="(item, idx) in activeMonitorAlerts.slice(0, 6)"
            :key="`ma-${idx}`"
            type="button"
            class="ops-alert-pill"
            @click="openAnalyticsByModule(item.module)"
          >
            {{ moduleLabel(item.module) }} · {{ alertCodeLabel(item.alert_code) }}
          </button>
        </div>
      </a-card>

      <a-card title="反馈闭环" :bordered="false" class="ops-panel">
        <div class="ops-chip-row">
          <span class="ops-chip">已确认 {{ feedbackSummary.by_outcome?.confirmed || 0 }}</span>
          <span class="ops-chip">已忽略 {{ feedbackSummary.by_outcome?.dismissed || 0 }}</span>
          <span class="ops-chip">不准确 {{ feedbackSummary.by_outcome?.inaccurate || 0 }}</span>
        </div>
        <div v-if="feedbackModuleRows.length" class="ops-module-list">
          <button
            v-for="row in feedbackModuleRows"
            :key="row.module"
            type="button"
            class="ops-module-row"
            @click="openAnalyticsByModule(row.module)"
          >
            <span>{{ moduleLabel(row.module) }}</span>
            <strong>{{ row.count }}</strong>
          </button>
        </div>
        <div v-else class="ops-empty">暂无反馈模块统计</div>
        <a-table
          size="small"
          class="ops-feedback-table"
          :columns="feedbackColumns"
          :data-source="feedbackRows"
          :pagination="{ pageSize: 6, hideOnSinglePage: true }"
          :scroll="{ x: 860 }"
          row-key="prediction_id"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'patient'">
              <a class="ops-link" @click.prevent="openPatient(record)">{{ record.patient_name || '未知患者' }}</a>
            </template>
            <template v-else-if="column.key === 'outcome'">
              <span :class="['ops-outcome', `is-${record.outcome || 'unknown'}`]">{{ outcomeText(record.outcome) }}</span>
            </template>
            <template v-else-if="column.key === 'created_at'">
              {{ fmtTime(record.created_at) }}
            </template>
            <template v-else-if="column.key === 'module'">
              <a class="ops-link" @click.prevent="openAnalyticsByModule(record.module)">{{ moduleLabel(record.module) }}</a>
            </template>
          </template>
        </a-table>
      </a-card>

      <a-card title="个性化阈值审核中心" :bordered="false" class="ops-panel ops-panel--wide">
        <div class="ops-threshold-head">
          <div class="ops-threshold-note">支持在全局运营页直接完成“待审核 -> 已批准 / 已拒绝”的闭环处理。</div>
        </div>
        <a-table
          size="small"
          :columns="thresholdColumns"
          :data-source="thresholdRows"
          :pagination="{ pageSize: 8, hideOnSinglePage: true }"
          :scroll="{ x: 1080 }"
          row-key="_id"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'patient'">
              <a class="ops-link" @click.prevent="openPatient(record, 'alerts')">{{ record.patient_name || '未知患者' }}</a>
            </template>
            <template v-else-if="column.key === 'status'">
              <span :class="['ops-outcome', `is-${record.status || 'pending_review'}`]">{{ thresholdStatusText(record.status) }}</span>
            </template>
            <template v-else-if="column.key === 'reviewed_at'">
              {{ fmtTime(record.reviewed_at || record.updated_at || record.calc_time) }}
            </template>
            <template v-else-if="column.key === 'actions'">
              <div class="ops-action-row">
                <a-button size="small" type="primary" :disabled="record.status !== 'pending_review'" @click="openThresholdReview(record, 'approved')">批准</a-button>
                <a-button size="small" danger ghost :disabled="record.status !== 'pending_review'" @click="openThresholdReview(record, 'rejected')">拒绝</a-button>
              </div>
            </template>
          </template>
        </a-table>
      </a-card>
    </section>

    <a-modal
      v-model:open="reviewDialogOpen"
      :title="reviewStatus === 'approved' ? '批准个性化阈值建议' : '拒绝个性化阈值建议'"
      :confirm-loading="reviewSubmitting"
      ok-text="提交审核"
      cancel-text="取消"
      @ok="submitThresholdReview"
    >
      <div class="ops-review-dialog">
        <div class="ops-review-row">
          <label class="ops-review-label">审核人</label>
          <input v-model="reviewer" class="ops-review-input" type="text" maxlength="32" placeholder="请输入审核人姓名" />
        </div>
        <div class="ops-review-row">
          <label class="ops-review-label">审核备注</label>
          <textarea v-model="reviewComment" class="ops-review-textarea" rows="4" maxlength="240" placeholder="请输入审核备注" />
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import dayjs from 'dayjs'
import {
  Button as AButton,
  Card as ACard,
  Modal as AModal,
  Segmented as ASegmented,
  Space as ASpace,
  Table as ATable,
  message,
} from 'ant-design-vue'
import {
  getAiFeedbackSummary,
  getAiMonitorSummary,
  getThresholdReviewCenter,
  reviewPatientPersonalizedThreshold,
} from '../api'

const router = useRouter()
const loading = ref(false)
const days = ref(7)
const thresholdStatus = ref<'all' | 'pending_review' | 'approved' | 'rejected'>('all')
const monitorStats = ref<any[]>([])
const activeMonitorAlerts = ref<any[]>([])
const runtimeSummary = ref<any>({})
const feedbackSummary = ref<any>({ total: 0, by_outcome: {}, by_module: {}, confirmed_ratio: 0, inaccurate_ratio: 0 })
const feedbackRows = ref<any[]>([])
const thresholdSummary = ref<any>({ pending_review: 0, approved: 0, rejected: 0 })
const thresholdRows = ref<any[]>([])
const reviewDialogOpen = ref(false)
const reviewSubmitting = ref(false)
const reviewTarget = ref<any>(null)
const reviewStatus = ref<'approved' | 'rejected'>('approved')
const reviewer = ref('')
const reviewComment = ref('')

const dayOptions = [
  { label: '7天', value: 7 },
  { label: '14天', value: 14 },
  { label: '30天', value: 30 },
]
const thresholdOptions = [
  { label: '全部', value: 'all' },
  { label: '待审核', value: 'pending_review' },
  { label: '已批准', value: 'approved' },
  { label: '已拒绝', value: 'rejected' },
]

const monitorColumns = [
  { title: '模块', dataIndex: 'module', key: 'module', width: 140 },
  { title: '调用量', dataIndex: 'calls', key: 'calls', width: 96 },
  { title: '成功率', dataIndex: 'success_rate', key: 'success_rate', width: 110 },
  { title: 'P95延迟(ms)', dataIndex: 'p95_latency_ms', key: 'p95_latency_ms', width: 120 },
  { title: '错误数', dataIndex: 'error_count', key: 'error_count', width: 96 },
]
const feedbackColumns = [
  { title: '患者', dataIndex: 'patient_name', key: 'patient', width: 140 },
  { title: '床位', dataIndex: 'bed', key: 'bed', width: 90 },
  { title: '模块', dataIndex: 'module', key: 'module', width: 120 },
  { title: '告警', dataIndex: 'alert_name', key: 'alert_name', width: 180 },
  { title: '结果', dataIndex: 'outcome', key: 'outcome', width: 110 },
  { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 160 },
]
const thresholdColumns = [
  { title: '患者', dataIndex: 'patient_name', key: 'patient', width: 160 },
  { title: '床位', dataIndex: 'bed', key: 'bed', width: 90 },
  { title: '科室', dataIndex: 'dept', key: 'dept', width: 140 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 110 },
  { title: '审核人', dataIndex: 'reviewer', key: 'reviewer', width: 120 },
  { title: '时间', dataIndex: 'reviewed_at', key: 'reviewed_at', width: 170 },
  { title: '备注', dataIndex: 'review_comment', key: 'review_comment' },
  { title: '操作', key: 'actions', width: 160, fixed: 'right' as const },
]

const feedbackModuleRows = computed(() => {
  const src = feedbackSummary.value?.by_module || {}
  return Object.keys(src).map((key) => ({ module: key, count: Number(src[key] || 0) })).sort((a, b) => b.count - a.count)
})

const runtimeCacheSize = computed(() => {
  const value = Number(runtimeSummary.value?.cache_size)
  return Number.isFinite(value) ? Math.max(0, Math.round(value)) : 0
})

const runtimeConcurrencyLimit = computed(() => {
  const value = Number(runtimeSummary.value?.concurrency_limit)
  return Number.isFinite(value) && value > 0 ? Math.round(value) : '未初始化'
})

const runtimeStatusText = computed(() => {
  if (runtimeSummary.value?.open) return '熔断中'
  if (runtimeSummary.value?.last_error) return '需关注'
  return '正常'
})

const runtimeDegradedText = computed(() => {
  if (runtimeSummary.value?.open) return '已熔断'
  if (runtimeSummary.value?.failure_count) return `连续异常 ${runtimeSummary.value.failure_count} 次`
  return '未降级'
})

const runtimeLastErrorText = computed(() => {
  const text = String(runtimeSummary.value?.last_error || '').trim()
  return text ? text.slice(0, 46) : '无'
})

const opsActions = computed(() => [
  {
    label: '查看告警运营',
    value: '质控分析 / 告警运营',
    meta: '进入规则热区、高频时段和床位排名视图。',
    action: () => openAnalyticsSection('alerts'),
  },
  {
    label: '查看脓毒症质控',
    value: '质控分析 / 脓毒症质控',
    meta: '进入解放束达标、超时病例和进行中病例拆解。',
    action: () => openAnalyticsSection('sepsis'),
  },
  {
    label: '查看撤机分析',
    value: '质控分析 / 撤机分析',
    meta: '进入脱机高风险、再插管风险和科室对比。',
    action: () => openAnalyticsSection('weaning'),
  },
  {
    label: '进入抢救期总览',
    value: '患者总览 / 抢救期',
    meta: '回到患者总览并只看抢救期高风险患者。',
    action: () => router.push({ path: '/', query: { rescue_only: '1' } }),
  },
])

function fmtTime(value: any) {
  if (!value) return '—'
  const d = dayjs(value)
  return d.isValid() ? d.format('MM-DD HH:mm') : '—'
}

function percentText(value: any) {
  const num = Number(value)
  if (!Number.isFinite(num)) return '—'
  return `${Math.round(num * 100)}%`
}

function moduleLabel(value: any) {
  const key = String(value || '').trim().toLowerCase()
  if (!key) return '未知模块'
  const map: Record<string, string> = {
    ai_risk: '风险预测',
    similar_case_review: '相似病例复盘',
    api_llm: '大模型接口服务',
    alert_reasoning: '告警归因',
    sepsis_bundle: '脓毒症解放束',
    weaning_assistant: '撤机助手',
  }
  return map[key] || key.replace(/[_-]+/g, ' ').replace(/\b\w/g, (s) => s.toUpperCase())
}

function outcomeText(value: any) {
  const key = String(value || '').trim().toLowerCase()
  return ({
    confirmed: '已确认',
    dismissed: '已忽略',
    inaccurate: '不准确',
  } as Record<string, string>)[key] || '待判定'
}

function alertCodeLabel(value: any) {
  const key = String(value || '').trim().toLowerCase()
  if (!key) return '监控提醒'
  const map: Record<string, string> = {
    success_rate_low: '成功率偏低',
    p95_latency_high: '延迟过高',
    error_rate_high: '错误率升高',
    sample_count_low: '样本量不足',
  }
  return map[key] || key.replace(/[_-]+/g, ' ')
}

function thresholdStatusText(v: any) {
  return ({ pending_review: '待审核', approved: '已批准', rejected: '已拒绝' } as Record<string, string>)[String(v || '').toLowerCase()] || '待审核'
}

function openThresholdReview(record: any, status: 'approved' | 'rejected') {
  reviewTarget.value = record
  reviewStatus.value = status
  reviewer.value = ''
  reviewComment.value = status === 'approved'
    ? '同意采用该个性化阈值建议。'
    : '暂不采用该个性化阈值建议。'
  reviewDialogOpen.value = true
}

async function submitThresholdReview() {
  const record = reviewTarget.value
  const patientId = String(record?.patient_id || '').trim()
  const recordId = String(record?._id || '').trim()
  if (!patientId || !recordId) {
    message.error('缺少审核记录信息')
    return
  }
  reviewSubmitting.value = true
  try {
    await reviewPatientPersonalizedThreshold(patientId, recordId, {
      status: reviewStatus.value,
      reviewer: reviewer.value.trim(),
      review_comment: reviewComment.value.trim(),
    })
    message.success(reviewStatus.value === 'approved' ? '已批准个性化阈值建议' : '已拒绝个性化阈值建议')
    reviewDialogOpen.value = false
    await loadAll()
  } catch (e: any) {
    message.error(e?.response?.data?.message || '审核失败')
  } finally {
    reviewSubmitting.value = false
  }
}

function openPatient(record: any, tab = 'ai') {
  const patientId = String(record?.patient_id || '').trim()
  if (!patientId) return
  router.push({ path: `/patient/${patientId}`, query: { tab } })
}

function analyticsSectionForModule(module: any): 'alerts' | 'sepsis' | 'weaning' {
  const key = String(module || '').toLowerCase()
  if (key.includes('sepsis') || key.includes('bundle')) return 'sepsis'
  if (key.includes('wean') || key.includes('extubat') || key.includes('sbt') || key.includes('vent')) return 'weaning'
  return 'alerts'
}

function openAnalyticsSection(section: 'alerts' | 'sepsis' | 'weaning') {
  router.push({ path: '/analytics', query: { section } })
}

function openAnalyticsByModule(module: any) {
  openAnalyticsSection(analyticsSectionForModule(module))
}

async function loadAll() {
  loading.value = true
  try {
    const [monitorRes, feedbackRes, thresholdRes] = await Promise.all([
      getAiMonitorSummary(),
      getAiFeedbackSummary({ days: days.value, limit: 30 }),
      getThresholdReviewCenter({
        status: thresholdStatus.value === 'all' ? undefined : thresholdStatus.value,
        limit: 60,
      }),
    ])
    monitorStats.value = Array.isArray(monitorRes.data?.stats) ? monitorRes.data.stats : []
    activeMonitorAlerts.value = Array.isArray(monitorRes.data?.active_alerts) ? monitorRes.data.active_alerts : []
    runtimeSummary.value = monitorRes.data?.runtime || {}
    feedbackSummary.value = feedbackRes.data?.summary || { total: 0, by_outcome: {}, by_module: {}, confirmed_ratio: 0, inaccurate_ratio: 0 }
    feedbackRows.value = Array.isArray(feedbackRes.data?.recent) ? feedbackRes.data.recent : []
    thresholdSummary.value = thresholdRes.data?.summary || { pending_review: 0, approved: 0, rejected: 0 }
    thresholdRows.value = Array.isArray(thresholdRes.data?.rows) ? thresholdRes.data.rows : []
  } finally {
    loading.value = false
  }
}

watch(days, () => { void loadAll() })
watch(thresholdStatus, () => { void loadAll() })
onMounted(() => { void loadAll() })
</script>

<style scoped>
.ops-page { display: grid; gap: 16px; font-family: var(--app-display-font); }
.ops-filter-card,.ops-panel { border: 1px solid rgba(80,199,255,.12); background: #FFFFFF; }
.ops-filter-row,.ops-kpi-strip,.ops-chip-row,.ops-alert-row { display: flex; gap: 12px; flex-wrap: wrap; }
.ops-filter-row { justify-content: space-between; align-items: center; }
.ops-label { color: #8cb7c9; font-size: 12px; }
.ops-kpi-strip { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; }
.ops-kpi { padding: 16px; border-radius: 4px; border: 1px solid rgba(125,211,252,.14); background: #FFFFFF; }
.ops-kpi--warn { border-color: rgba(251,191,36,.2); }
.ops-kpi--review { border-color: rgba(52,211,153,.2); }
.ops-kpi--runtime { border-color: rgba(96,165,250,.22); }
.ops-kpi-label { color: #8cb7c9; font-size: 12px; }
.ops-kpi-value { display: block; margin-top: 8px; color: #ecfeff; font-size: 28px; }
.ops-kpi small { color: #86aabd; }
.ops-action-strip { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.ops-action-tile { display: grid; gap: 6px; padding: 14px 16px; border-radius: 4px; border: 1px solid rgba(125,211,252,.14); background: #FFFFFF; color: inherit; text-align: left; cursor: pointer; transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease; }
.ops-action-tile:hover { transform: translateY(-1px); border-color: rgba(125,211,252,.28); box-shadow: 0 1px 2px rgba(0,0,0,.06); }
.ops-action-label { color: #8cb7c9; font-size: 11px; letter-spacing: .08em; }
.ops-action-value { color: #ecfeff; font-size: 18px; line-height: 1.2; }
.ops-action-meta { color: #86aabd; font-size: 11px; line-height: 1.5; }
.ops-grid { display: grid; grid-template-columns: 1.1fr 1.2fr; gap: 14px; }
.ops-panel--wide { grid-column: 1 / -1; }
.ops-runtime-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.ops-runtime-item { min-height: 74px; padding: 12px; border-radius: 4px; border: 1px solid rgba(125,211,252,.12); background: rgba(9,26,42,.72); display: grid; align-content: center; gap: 6px; }
.ops-runtime-item span { color: #8cb7c9; font-size: 12px; }
.ops-runtime-item strong { color: #ecfeff; font-size: 18px; line-height: 1.2; word-break: break-word; }
.ops-runtime-note { margin-top: 12px; color: #86aabd; font-size: 12px; line-height: 1.7; }
.ops-empty { color: #8cb7c9; padding: 18px 0; }
.ops-chip,.ops-alert-pill { padding: 6px 10px; border-radius: 999px; background: rgba(10,36,54,.92); color: #d7f3ff; border: 1px solid rgba(125,211,252,.14); font-size: 12px; }
.ops-module-list { display: grid; gap: 8px; margin: 14px 0; }
.ops-module-row { display: flex; justify-content: space-between; gap: 12px; padding: 10px 12px; border-radius: 4px; background: rgba(9,26,42,.72); color: #dffbff; border: 1px solid rgba(125,211,252,.08); cursor: pointer; text-align: left; transition: border-color .18s ease, transform .18s ease; }
.ops-module-row:hover { border-color: rgba(125,211,252,.22); transform: translateY(-1px); }
.ops-feedback-table { margin-top: 14px; }
.ops-link { color: #7dd3fc; cursor: pointer; }
.ops-threshold-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; }
.ops-threshold-note { color: #8cb7c9; font-size: 12px; }
.ops-action-row { display: flex; gap: 8px; flex-wrap: wrap; }
.ops-review-dialog { display: grid; gap: 12px; }
.ops-review-row { display: grid; gap: 6px; }
.ops-review-label { color: #8cb7c9; font-size: 12px; }
.ops-review-input,.ops-review-textarea { width: 100%; border-radius: 4px; border: 1px solid rgba(125,211,252,.16); background: rgba(8, 20, 34, 0.96); color: #ecfeff; padding: 10px 12px; }
.ops-outcome { display: inline-flex; padding: 4px 10px; border-radius: 999px; font-size: 12px; border: 1px solid rgba(125,211,252,.12); }
.ops-outcome.is-confirmed,.ops-outcome.is-approved { color: #34d399; border-color: rgba(52,211,153,.22); }
.ops-outcome.is-dismissed { color: #fbbf24; border-color: rgba(251,191,36,.22); }
.ops-outcome.is-inaccurate,.ops-outcome.is-rejected { color: #fb7185; border-color: rgba(251,113,133,.24); }
.ops-outcome.is-pending_review { color: #7dd3fc; border-color: rgba(125,211,252,.22); }
html[data-theme='light'] .ops-page {
  --ops-text-main: #153554;
  --ops-text-sub: #5f7690;
  --ops-line: rgba(145, 176, 199, 0.36);
  --ops-card-bg: #FFFFFF;
  --ops-card-shadow: 0 14px 34px rgba(21, 53, 84, 0.1), 0 2px 0 rgba(255, 255, 255, 0.7) inset;
  color: var(--ops-text-main);
  position: relative;
  padding: 4px;
}
html[data-theme='light'] .ops-page::before {
  content: '';
  position: absolute;
  inset: -8px -6px;
  z-index: -1;
  pointer-events: none;
  border-radius: 4px;
  background: #FFFFFF;
}
html[data-theme='light'] .ops-filter-card,
html[data-theme='light'] .ops-panel,
html[data-theme='light'] .ops-kpi,
html[data-theme='light'] .ops-action-tile,
html[data-theme='light'] .ops-chip,
html[data-theme='light'] .ops-alert-pill,
html[data-theme='light'] .ops-module-row,
html[data-theme='light'] .ops-runtime-item,
html[data-theme='light'] .ops-review-input,
html[data-theme='light'] .ops-review-textarea,
html[data-theme='light'] .ops-outcome {
  border-color: var(--ops-line);
  background: var(--ops-card-bg);
  box-shadow: var(--ops-card-shadow);
}
html[data-theme='light'] .ops-filter-card,
html[data-theme='light'] .ops-panel {
  backdrop-filter: blur(8px);
}
html[data-theme='light'] .ops-kpi {
  position: relative;
  overflow: hidden;
}
html[data-theme='light'] .ops-kpi::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
  background: #FFFFFF;
}
html[data-theme='light'] .ops-label,
html[data-theme='light'] .ops-kpi-label,
html[data-theme='light'] .ops-action-label,
html[data-theme='light'] .ops-action-meta,
html[data-theme='light'] .ops-threshold-note,
html[data-theme='light'] .ops-review-label,
html[data-theme='light'] .ops-runtime-item span,
html[data-theme='light'] .ops-runtime-note,
html[data-theme='light'] .ops-empty {
  color: var(--ops-text-sub);
}
html[data-theme='light'] .ops-kpi-value,
html[data-theme='light'] .ops-action-value,
html[data-theme='light'] .ops-runtime-item strong {
  color: var(--ops-text-main);
}
html[data-theme='light'] .ops-link { color: #165ec9; }
html[data-theme='light'] .ops-module-row { color: var(--ops-text-main); }
html[data-theme='light'] .ops-chip,
html[data-theme='light'] .ops-alert-pill {
  color: #355a7c;
}
html[data-theme='light'] .ops-module-row:hover {
  border-color: rgba(34, 119, 214, 0.42);
  box-shadow: 0 1px 2px rgba(0,0,0,.06);
  transform: translateY(-2px);
}
html[data-theme='light'] .ops-action-tile:hover {
  border-color: rgba(34, 119, 214, 0.4);
  box-shadow: 0 1px 2px rgba(0,0,0,.06);
}
html[data-theme='light'] .ops-alert-pill:hover,
html[data-theme='light'] .ops-chip:hover {
  border-color: rgba(34, 119, 214, 0.4);
  transform: translateY(-1px);
}
html[data-theme='light'] .ops-action-tile,
html[data-theme='light'] .ops-alert-pill,
html[data-theme='light'] .ops-chip,
html[data-theme='light'] .ops-module-row {
  transition: transform .18s ease, box-shadow .2s ease, border-color .2s ease;
}
html[data-theme='light'] .ops-kpi--warn {
  border-color: rgba(245, 158, 11, 0.34);
}
html[data-theme='light'] .ops-kpi--review {
  border-color: rgba(16, 185, 129, 0.34);
}
html[data-theme='light'] .ops-kpi--runtime {
  border-color: rgba(59, 130, 246, 0.34);
}
html[data-theme='light'] .ops-kpi--warn::after {
  background: #FFFFFF;
}
html[data-theme='light'] .ops-kpi--review::after {
  background: #FFFFFF;
}
html[data-theme='light'] .ops-kpi--runtime::after {
  background: #FFFFFF;
}
html[data-theme='light'] :deep(.ant-card-head-title) {
  color: #1d4f7a;
  font-weight: 700;
  letter-spacing: 0.02em;
}
html[data-theme='light'] :deep(.ant-table-wrapper .ant-table-thead > tr > th) {
  color: #215580;
  background: #FFFFFF;
  border-bottom: 1px solid rgba(145, 176, 199, 0.44);
}
html[data-theme='light'] :deep(.ant-table-wrapper .ant-table-tbody > tr > td) {
  border-bottom: 1px solid rgba(167, 194, 214, 0.34);
}
html[data-theme='light'] :deep(.ant-table-wrapper .ant-table-tbody > tr:hover > td) {
  background: rgba(208, 232, 250, 0.46);
}
html[data-theme='light'] :deep(.ant-empty-description) {
  color: #7991aa;
}
html[data-theme='light'] .ops-outcome.is-confirmed,
html[data-theme='light'] .ops-outcome.is-approved { color: #047857; border-color: rgba(16,185,129,.28); background: rgba(220,252,231,.98); }
html[data-theme='light'] .ops-outcome.is-dismissed { color: #b45309; border-color: rgba(245,158,11,.28); background: rgba(254,243,199,.98); }
html[data-theme='light'] .ops-outcome.is-inaccurate,
html[data-theme='light'] .ops-outcome.is-rejected { color: #be123c; border-color: rgba(251,113,133,.3); background: rgba(255,241,242,.98); }
html[data-theme='light'] .ops-outcome.is-pending_review { color: #15558D; border-color: rgba(59,130,246,.28); background: rgba(219,234,254,.98); }
@media (max-width: 1080px) { .ops-kpi-strip,.ops-action-strip,.ops-grid { grid-template-columns: 1fr 1fr; } .ops-panel--wide { grid-column: auto; } }
@media (max-width: 760px) { .ops-kpi-strip,.ops-action-strip,.ops-grid { grid-template-columns: 1fr; } }
</style>


