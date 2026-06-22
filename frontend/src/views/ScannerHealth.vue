<template>
  <div class="scanner-health-page">
    <a-card :bordered="false" class="scanner-health-filter">
      <div class="scanner-health-toolbar">
        <a-space wrap>
          <span class="scanner-health-label">统计窗口</span>
          <a-segmented v-model:value="days" :options="dayOptions" size="small" />
        </a-space>
        <a-space>
          <a-button size="small" :loading="inferring" @click="inferOutcomes">补算结局</a-button>
          <a-button size="small" :loading="recalculating" @click="recalculate">生成建议</a-button>
          <a-button size="small" type="primary" :loading="loading" @click="loadRows">刷新</a-button>
        </a-space>
      </div>
    </a-card>

    <div v-if="source === 'alert_records_fallback'" class="scanner-health-notice">
      当前展示来自历史告警基础统计；点击“补算结局”后会写入告警结局表，并逐步补齐阳性预测值、覆盖率和24小时结局。
    </div>

    <section class="scanner-health-kpis">
      <div class="scanner-health-kpi">
        <span>规则数量</span>
        <strong>{{ rows.length }}</strong>
      </div>
      <div class="scanner-health-kpi is-red">
        <span>需人工复核</span>
        <strong>{{ reviewCount }}</strong>
      </div>
      <div class="scanner-health-kpi">
        <span>总触发</span>
        <strong>{{ totalFired }}</strong>
      </div>
      <div class="scanner-health-kpi">
        <span>平均阳性预测值</span>
        <strong>{{ percentText(avgPpv) }}</strong>
      </div>
      <div class="scanner-health-kpi">
        <span>运行异常</span>
        <strong>{{ runtimeErrorCount }}</strong>
      </div>
    </section>

    <section class="admin-quality-grid">
      <article class="scanner-command-card">
        <div class="scanner-command-head">
          <span>规则误报闭环</span>
          <strong>{{ quality.summary?.rules || 0 }} 条规则</strong>
        </div>
        <div class="quality-list">
          <button v-for="row in (quality.rule_false_positive_rows || []).slice(0, 5)" :key="row.rule" type="button">
            <strong>{{ scannerLabel(row.rule) }}</strong>
            <span>误报 {{ percentText(row.false_positive_rate) }} / 重复 {{ percentText(row.duplicate_rate) }} / 数据错 {{ percentText(row.data_error_rate) }}</span>
          </button>
        </div>
      </article>
      <article class="scanner-command-card">
        <div class="scanner-command-head">
          <span>科室响应</span>
          <strong>{{ quality.summary?.median_response_minutes ?? '—' }} 分钟</strong>
        </div>
        <div class="quality-list">
          <button v-for="row in (quality.department_response_rows || []).slice(0, 5)" :key="row.dept" type="button">
            <strong>{{ row.dept }}</strong>
            <span>确认率 {{ percentText(row.ack_rate) }} / 中位响应 {{ row.median_response_minutes ?? '—' }} 分钟</span>
          </button>
        </div>
      </article>
      <article class="scanner-command-card">
        <div class="scanner-command-head">
          <span>模块使用率</span>
          <strong>{{ quality.summary?.modules_used || 0 }} 个模块</strong>
        </div>
        <div class="quality-list">
          <button v-for="row in (quality.module_usage_rows || []).slice(0, 5)" :key="row.module" type="button">
            <strong>{{ moduleLabel(row.module) }}</strong>
            <span>{{ row.events }} 次 / {{ row.actor_count }} 人 / 最近 {{ fmtTime(row.last_used_at) }}</span>
          </button>
        </div>
      </article>
    </section>

    <section class="scanner-command-grid">
      <article class="scanner-command-card">
        <div class="scanner-command-head">
          <span>规则灯</span>
          <strong>{{ redCount }}红 / {{ yellowCount }}黄</strong>
        </div>
        <div class="scanner-light-wall">
          <button
            v-for="row in rows.slice(0, 36)"
            :key="`light-${row.scanner_name}`"
            type="button"
            :class="['scanner-light', `is-${row.drift_status || 'green'}`]"
            @click="focusScanner(row)"
          >
            <b>{{ shortScannerLabel(row.scanner_name) }}</b>
            <span>{{ row.fired_count || 0 }}</span>
          </button>
        </div>
      </article>
      <article class="scanner-command-card">
        <div class="scanner-command-head">
          <span>闭环任务</span>
          <strong>{{ closureTasks.length }}</strong>
        </div>
        <div v-if="closureTasks.length" class="scanner-task-list">
          <button
            v-for="task in closureTasks.slice(0, 6)"
            :key="`${task.scanner_name}-${task.title}`"
            type="button"
            :class="['scanner-task', `prio-${task.priority}`]"
            @click="focusScanner(task)"
          >
            <strong>{{ scannerLabel(task.scanner_name) }}</strong>
            <span>{{ task.title }}</span>
          </button>
        </div>
        <div v-else class="scanner-empty">当前没有规则闭环任务</div>
      </article>
      <article class="scanner-command-card">
        <div class="scanner-command-head">
          <span>当前聚焦</span>
          <strong>{{ focusedRow ? scannerLabel(focusedRow.scanner_name) : '未选择' }}</strong>
        </div>
        <div v-if="focusedRow" class="scanner-focus">
          <div><span>闭环</span><b>{{ focusedRow.closure?.percent ?? 0 }}%</b></div>
          <div><span>PPV</span><b>{{ percentText(focusedRow.ppv) }}</b></div>
          <div><span>覆盖</span><b>{{ percentText(focusedRow.override_rate) }}</b></div>
          <div><span>执行成功率</span><b>{{ percentText(focusedRow.runtime_health?.success_rate) }}</b></div>
          <div><span>P95耗时</span><b>{{ durationText(focusedRow.runtime_health?.p95_duration_ms) }}</b></div>
          <div><span>最近执行</span><b>{{ fmtTime(focusedRow.runtime_health?.last_run_at) }}</b></div>
          <p>{{ focusedRow.threshold_advice || focusedRow.closure?.label || '规则状态平稳，建议保留常规抽查。' }}</p>
          <p v-if="focusedRow.runtime_health?.last_error" class="runtime-error">最近异常：{{ focusedRow.runtime_health.last_error }}</p>
        </div>
        <div v-else class="scanner-empty">点击左侧规则灯查看</div>
      </article>
    </section>

    <a-card title="规则健康" :bordered="false" class="scanner-health-panel">
      <a-table
        size="small"
        :columns="columns"
        :data-source="rows"
        :loading="loading"
        :pagination="{ pageSize: 14, hideOnSinglePage: true }"
        :scroll="{ x: 1160 }"
        row-key="scanner_name"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'scanner_name'">
            <div class="scanner-name-cell">
              <strong>{{ scannerLabel(record.scanner_name) }}</strong>
              <span v-if="record.review_suggestion" class="review-tag">建议人工复核</span>
              <small>闭环 {{ record.closure?.percent ?? 0 }}%</small>
            </div>
          </template>
          <template v-else-if="column.key === 'ppv'">
            {{ percentText(record.ppv) }}
          </template>
          <template v-else-if="column.key === 'override_rate'">
            {{ percentText(record.override_rate) }}
          </template>
          <template v-else-if="column.key === 'drift_status'">
            <span :class="['drift-pill', `is-${record.drift_status || 'green'}`]">{{ driftText(record.drift_status) }}</span>
          </template>
          <template v-else-if="column.key === 'runtime_health'">
            <div class="runtime-cell">
              <span :class="['drift-pill', `is-${record.runtime_health?.tone || 'unknown'}`]">{{ runtimeText(record.runtime_health) }}</span>
              <small>P95 {{ durationText(record.runtime_health?.p95_duration_ms) }} / 最近 {{ fmtTime(record.runtime_health?.last_run_at) }}</small>
            </div>
          </template>
          <template v-else-if="column.key === 'recent_overrides'">
            <div v-if="record.recent_overrides?.length" class="override-list">
              <button
                v-for="item in record.recent_overrides.slice(0, 5)"
                :key="item.alert_id"
                type="button"
                class="override-chip"
                @click="openPatient(item.patient_id)"
              >
                {{ shortId(item.patient_id) }} · {{ reasonText(item.reason) }}
              </button>
            </div>
            <span v-else class="muted">暂无</span>
          </template>
        </template>
      </a-table>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button as AButton, Card as ACard, Segmented as ASegmented, Space as ASpace, Table as ATable, message } from 'ant-design-vue'
import { getAdminQualityClosedLoop, getScannerHealth, postScannerHealthInferOutcomes, postScannerHealthRecalculate } from '../api'
import { formatAlertTypeLabel } from '../utils/displayLabels'

const route = useRoute()
const router = useRouter()
const days = ref(30)
const rows = ref<any[]>([])
const focusedRow = ref<any>(null)
const loading = ref(false)
const recalculating = ref(false)
const inferring = ref(false)
const source = ref('')
const quality = ref<any>({ summary: {}, rule_false_positive_rows: [], department_response_rows: [], module_usage_rows: [] })
const dayOptions = [
  { label: '7天', value: 7 },
  { label: '30天', value: 30 },
]
const columns = [
  { title: '规则名称', dataIndex: 'scanner_name', key: 'scanner_name', width: 260 },
  { title: '触发数', dataIndex: 'fired_count', key: 'fired_count', width: 90 },
  { title: '阳性预测值', dataIndex: 'ppv', key: 'ppv', width: 110 },
  { title: '覆盖率', dataIndex: 'override_rate', key: 'override_rate', width: 100 },
  { title: '执行健康', dataIndex: 'runtime_health', key: 'runtime_health', width: 170 },
  { title: '响应中位时间(分钟)', dataIndex: 'median_time_to_action_minutes', key: 'median_time_to_action_minutes', width: 150 },
  { title: '24h事件率', dataIndex: 'event_24h_rate', key: 'event_24h_rate', width: 110 },
  { title: '需提醒人数', dataIndex: 'nnt', key: 'nnt', width: 110 },
  { title: '漂移', dataIndex: 'drift_status', key: 'drift_status', width: 100 },
  { title: '最近覆盖样例', dataIndex: 'recent_overrides', key: 'recent_overrides' },
]
const reviewCount = computed(() => rows.value.filter((row) => row.review_suggestion).length)
const redCount = computed(() => rows.value.filter((row) => String(row.drift_status || '').toLowerCase() === 'red').length)
const yellowCount = computed(() => rows.value.filter((row) => String(row.drift_status || '').toLowerCase() === 'yellow').length)
const runtimeErrorCount = computed(() => rows.value.filter((row) => ['red', 'yellow'].includes(String(row.runtime_health?.tone || '').toLowerCase())).length)
const totalFired = computed(() => rows.value.reduce((sum, row) => sum + Number(row.fired_count || 0), 0))
const avgPpv = computed(() => {
  if (!rows.value.length) return 0
  return rows.value.reduce((sum, row) => sum + Number(row.ppv || 0), 0) / rows.value.length
})
const closureTasks = computed(() => rows.value.flatMap((row) => (row.closure?.tasks || []).map((task: any) => ({ ...task, scanner_name: row.scanner_name }))))
const routeDeptCode = computed(() => String(route.query.dept_code || route.query.deptCode || '').trim())
const routeDept = computed(() => String(route.query.dept || route.query.department || '').trim())
const scopedParams = computed(() => {
  const params: { days: number; dept?: string; dept_code?: string } = { days: days.value }
  if (routeDeptCode.value) params.dept_code = routeDeptCode.value
  else if (routeDept.value) params.dept = routeDept.value
  return params
})

function percentText(value: any) {
  const num = Number(value)
  if (!Number.isFinite(num)) return '—'
  return `${Math.round(num * 100)}%`
}

function fmtTime(value: any) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function driftText(value: any) {
  return ({ green: '绿', yellow: '黄', red: '红' } as Record<string, string>)[String(value || '').toLowerCase()] || '绿'
}

function runtimeText(value: any) {
  if (!value || !value.run_count) return '未运行'
  const tone = String(value.tone || '').toLowerCase()
  const label = ({ green: '正常', yellow: '需关注', red: '异常' } as Record<string, string>)[tone] || '未知'
  return `${label} ${percentText(value.success_rate)}`
}

function durationText(value: any) {
  const num = Number(value)
  if (!Number.isFinite(num)) return '—'
  return num >= 1000 ? `${(num / 1000).toFixed(1)}秒` : `${Math.round(num)}毫秒`
}

function scannerLabel(value: any) {
  const key = String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_')
  const map: Record<string, string> = {
    sofa: '器官衰竭评分',
    qsofa: '快速脓毒症评分',
    septic_shock: '脓毒性休克',
    sepsis_bundle_overdue_3h: '脓毒症救治清单超时',
    liberation_bundle: '撤机与镇静唤醒评估',
    vap_bundle_missing: 'VAP 预防清单缺项',
    weaning: '撤机筛查',
    pupil: '瞳孔异常',
    delirium_risk: '谵妄风险',
    vte_immobility_no_prophylaxis: '制动无VTE预防',
    nutrition_start_delay: '营养启动延迟',
    nurse_reminder: '护理评估提醒',
    multi_organ_deterioration_trend: '多器官恶化趋势',
    integrated_risk_reasoning: '综合风险推理',
    lung_protective_ventilation: '肺保护通气',
    aki: '急性肾损伤',
    ards: '急性呼吸窘迫',
    dic: '弥散性血管内凝血',
    crrt_filter_clotting: 'CRRT滤器凝堵',
    renal_dose_adjustment: '肾功能剂量调整',
    glucose_variability: '血糖波动',
    hypoglycemia: '低血糖',
    glucose_drop_fast: '血糖快速下降',
    hyperglycemia_no_insulin: '高血糖未启胰岛素',
    abx_timeout: '抗菌药复核超时',
    abx_stop_recommendation: '抗菌药停药评估',
    abx_tdm_reminder: '抗菌药血药浓度提醒',
    abx_duration_exceeded: '抗菌药疗程超限',
    nutrition_calorie_not_reached: '热卡未达标',
    nutrition_feeding_intolerance: '喂养不耐受',
    nutrition_refeeding_risk: '再喂养风险',
    cvc_review: '中心静脉导管评估',
    foley_review: '导尿管评估',
    ett_extubation_delay: '拔管延迟',
    driving_pressure: '驱动压升高',
    pplat_high: '平台压升高',
    mechanical_power: '机械功率升高',
    fluid_responsiveness: '容量反应性',
    steroid_taper_after_vaso: '升压药后激素减停',
    steroid_long_term_taper: '长程激素减停',
    steroid_hyperglycemia: '激素相关高血糖',
  }
  if (map[key]) return map[key]
  return formatAlertTypeLabel(value)
}

function moduleLabel(value: any) {
  const key = String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_')
  const map: Record<string, string> = {
    clinical_trials: '临床试验',
    ai_confirmation: 'AI确认',
    respiratory: '呼吸治疗',
    clinical_workflow: '临床工作流',
    nutrition: '营养支持',
    rounding: '查房报告',
    research_support: '科研支持',
    research_export: '科研导出',
    research_analytics: '科研分析',
    runtime_config: '运行配置',
    mdt: 'MDT会诊',
    ai_consult: 'AI问诊',
    alerts: '预警处置',
    followup: '随访管理',
    scanner_health: '规则健康',
  }
  return map[key] || formatAlertTypeLabel(value)
}

function shortScannerLabel(value: any) {
  const text = scannerLabel(value)
  return text.length > 6 ? text.slice(0, 6) : text
}

function focusScanner(row: any) {
  const name = String(row?.scanner_name || '').trim()
  focusedRow.value = rows.value.find((item) => String(item.scanner_name || '') === name) || row
}

function reasonText(reason: any) {
  const code = String(reason?.code || '').trim()
  return ({
    not_clinically_relevant: '病情不相关',
    already_addressed: '已有处置',
    duplicate_or_noise: '重复噪声',
    monitoring_only: '仅观察',
  } as Record<string, string>)[code] || code || '未填原因'
}

function shortId(value: any) {
  const text = String(value || '')
  return text.length > 8 ? text.slice(-8) : text || '未知患者'
}

function openPatient(patientId: any) {
  const id = String(patientId || '').trim()
  if (!id) return
  router.push({ path: `/patient/${id}`, query: { ...route.query, tab: 'alerts' } })
}

async function loadRows() {
  loading.value = true
  try {
    const [res, qualityRes] = await Promise.all([
      getScannerHealth(scopedParams.value),
      getAdminQualityClosedLoop(scopedParams.value).catch(() => ({ data: {} })),
    ])
    rows.value = Array.isArray(res.data?.rows) ? res.data.rows : []
    focusedRow.value = rows.value.find((row) => row.review_suggestion) || rows.value[0] || null
    source.value = String(res.data?.source || '')
    quality.value = qualityRes.data || quality.value
  } finally {
    loading.value = false
  }
}

async function recalculate() {
  recalculating.value = true
  try {
    await postScannerHealthRecalculate({ days: days.value })
    message.success('已生成规则校准建议')
    await loadRows()
  } finally {
    recalculating.value = false
  }
}

async function inferOutcomes() {
  inferring.value = true
  try {
    const res = await postScannerHealthInferOutcomes({ limit: 500, min_age_minutes: 0 })
    const result = res.data?.result || {}
    message.success(`已补算 ${result.processed || 0} 条，新增占位 ${result.seeded || 0} 条`)
    await loadRows()
  } finally {
    inferring.value = false
  }
}

watch(() => [days.value, route.query.deptCode, route.query.dept_code, route.query.dept, route.query.department], () => { void loadRows() })
onMounted(() => { void loadRows() })
</script>

<style scoped>
.scanner-health-page { display: grid; gap: 16px; font-family: var(--app-display-font); }
.scanner-health-filter,.scanner-health-panel { border: 1px solid rgba(80,199,255,.12); background: var(--bg-surface) 0%, var(--bg-surface) 100%); }
.scanner-health-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.scanner-health-label,.muted { color: var(--text-secondary); font-size: 12px; }
.scanner-health-notice { padding: 10px 12px; border-radius: var(--card-radius); border: 1px solid rgba(251,191,36,.22); background: var(--bg-surface),.42); color: var(--warning-soft); font-size: 12px; }
.scanner-health-kpis { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; }
.admin-quality-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px; }
.quality-list { display: grid; gap: 8px; }
.quality-list button { display: grid; gap: 4px; width: 100%; text-align: left; border: 1px solid rgba(125,167,214,.14); border-radius: var(--card-radius); background: var(--bg-surface),.64); color: var(--text-primary); padding: 9px 10px; }
.quality-list strong { color: var(--text-primary); font-size: 12px; }
.quality-list span { color: var(--text-secondary); font-size: 11px; }
.scanner-health-kpi { padding: 16px; border-radius: var(--card-radius); border: 1px solid rgba(125,211,252,.14); background: var(--bg-surface), var(--bg-surface)); }
.scanner-health-kpi.is-red { border-color: rgba(251,113,133,.28); }
.scanner-health-kpi span { display: block; color: var(--text-secondary); font-size: 12px; }
.scanner-health-kpi strong { display: block; margin-top: 8px; color: var(--text-primary); font-size: 28px; }
.scanner-command-grid { display: grid; grid-template-columns: 1.1fr .9fr .8fr; gap: 12px; }
.scanner-command-card { min-width: 0; padding: 16px; border-radius: var(--card-radius); border: 1px solid rgba(125,211,252,.14); background: var(--bg-surface), transparent 32%), var(--bg-surface); }
.scanner-command-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 12px; }
.scanner-command-head span { color: var(--text-secondary); font-size: 12px; }
.scanner-command-head strong { color: var(--text-primary); font-size: 18px; }
.scanner-light-wall { display: grid; grid-template-columns: repeat(auto-fill, minmax(76px, 1fr)); gap: 8px; }
.scanner-light { display: grid; gap: 4px; min-height: 58px; padding: 8px; border: 1px solid rgba(52,211,153,.22); border-radius: var(--card-radius); color: #d1fae5; background: var(--bg-surface),.18); cursor: pointer; }
.scanner-light.is-yellow { border-color: rgba(251,191,36,.28); color: var(--warning-soft); background: var(--bg-surface),.22); }
.scanner-light.is-red { border-color: rgba(251,113,133,.34); color: var(--danger-soft); background: var(--bg-surface),.28); }
.scanner-light b,.scanner-light span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.scanner-light b { font-size: 12px; }
.scanner-light span { color: currentColor; opacity: .75; font-size: 11px; }
.scanner-task-list { display: grid; gap: 8px; }
.scanner-task { display: grid; gap: 4px; padding: 10px; border: 1px solid rgba(125,211,252,.14); border-radius: var(--card-radius); color: inherit; background: var(--bg-surface),.28); text-align: left; cursor: pointer; }
.scanner-task.prio-high { border-color: rgba(251,113,133,.34); }
.scanner-task strong { color: var(--text-primary); font-size: 13px; }
.scanner-task span,.scanner-empty { color: var(--text-secondary); font-size: 12px; }
.scanner-empty { min-height: 110px; display: grid; place-content: center; border: 1px dashed rgba(125,211,252,.16); border-radius: var(--card-radius); }
.scanner-focus { display: grid; gap: 10px; }
.scanner-focus div { display: flex; justify-content: space-between; gap: 12px; padding: 9px 10px; border-radius: var(--card-radius); background: var(--bg-surface),.28); }
.scanner-focus span { color: var(--text-secondary); }
.scanner-focus b { color: var(--text-primary); }
.scanner-focus p { margin: 0; color: var(--text-primary); line-height: 1.55; }
.runtime-error { color: var(--danger-soft) !important; }
.runtime-cell { display: grid; gap: 4px; }
.runtime-cell small { color: var(--text-secondary); font-size: 11px; }
.scanner-name-cell { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; color: var(--text-primary); }
.scanner-name-cell small { color: #6aa7bd; font-size: 11px; }
.review-tag { padding: 2px 8px; border-radius: var(--card-radius); color: var(--danger-soft); border: 1px solid rgba(251,113,133,.28); background: var(--bg-surface),.38); font-size: 11px; }
.drift-pill { display: inline-flex; min-width: 42px; justify-content: center; padding: 3px 10px; border-radius: var(--card-radius); border: 1px solid rgba(52,211,153,.24); color: var(--success); }
.drift-pill.is-yellow { border-color: rgba(251,191,36,.28); color: var(--warning-soft); }
.drift-pill.is-red { border-color: rgba(251,113,133,.28); color: var(--danger-soft); }
.drift-pill.is-unknown { border-color: rgba(148,163,184,.24); color: var(--text-secondary); }
.override-list { display: flex; gap: 6px; flex-wrap: wrap; }
.override-chip { border: 1px solid rgba(125,211,252,.14); background: var(--bg-surface),.82); color: var(--text-primary); border-radius: var(--card-radius); padding: 4px 8px; cursor: pointer; font-size: 12px; }
html[data-theme='light'] .scanner-health-page { color: var(--text-primary); }
html[data-theme='light'] .scanner-health-filter,
html[data-theme='light'] .scanner-health-panel,
html[data-theme='light'] .scanner-health-kpi,
html[data-theme='light'] .scanner-command-card {
  background:
    var(--bg-surface), transparent 36%),
    #ffffff;
  border-color: rgba(148, 163, 184, 0.24);
  box-shadow: var(--card-shadow);
}
html[data-theme='light'] .scanner-health-notice {
  border-color: rgba(245, 158, 11, 0.22);
  background: var(--warning-soft);
  color: var(--warning);
}
html[data-theme='light'] .quality-list button {
  background: var(--bg-surface);
  border-color: rgba(148, 163, 184, 0.22);
  color: var(--text-primary);
}
html[data-theme='light'] .quality-list strong { color: var(--text-secondary); }
html[data-theme='light'] .quality-list span { color: var(--text-secondary); }
html[data-theme='light'] .scanner-health-kpi strong,
html[data-theme='light'] .scanner-name-cell,
html[data-theme='light'] .scanner-command-head strong,
html[data-theme='light'] .scanner-task strong,
html[data-theme='light'] .scanner-focus b { color: #153554; }
html[data-theme='light'] .scanner-health-label,
html[data-theme='light'] .scanner-health-kpi span,
html[data-theme='light'] .scanner-command-head span,
html[data-theme='light'] .scanner-task span,
html[data-theme='light'] .scanner-empty,
html[data-theme='light'] .scanner-focus span,
html[data-theme='light'] .muted { color: #5f7690; }
html[data-theme='light'] .scanner-task,
html[data-theme='light'] .scanner-focus div,
html[data-theme='light'] .scanner-empty {
  background: var(--bg-surface);
  border-color: rgba(148, 163, 184, 0.22);
}
html[data-theme='light'] .scanner-focus p { color: var(--text-primary); }
html[data-theme='light'] .scanner-light {
  color: var(--success);
  background: var(--bg-surface);
  border-color: rgba(16, 185, 129, 0.24);
}
html[data-theme='light'] .scanner-light.is-yellow {
  color: var(--warning);
  background: var(--warning-soft);
  border-color: rgba(245, 158, 11, 0.24);
}
html[data-theme='light'] .scanner-light.is-red {
  color: var(--danger-strong);
  background: var(--danger-bg);
  border-color: rgba(244, 63, 94, 0.24);
}
html[data-theme='light'] .review-tag {
  color: var(--danger-strong);
  background: var(--danger-bg);
  border-color: rgba(244, 63, 94, 0.24);
}
html[data-theme='light'] .drift-pill { color: var(--success); background: var(--bg-surface); }
html[data-theme='light'] .drift-pill.is-yellow { color: var(--warning); background: var(--warning-soft); }
html[data-theme='light'] .drift-pill.is-red { color: var(--danger-strong); background: var(--danger-bg); }
html[data-theme='light'] .override-chip {
  background: var(--bg-surface);
  border-color: rgba(59, 130, 246, 0.22);
  color: var(--brand);
}
html[data-theme='light'] .scanner-health-panel :deep(.ant-table),
html[data-theme='light'] .scanner-health-panel :deep(.ant-table-container),
html[data-theme='light'] .scanner-health-panel :deep(.ant-table-cell) {
  background: var(--bg-surface);
  color: var(--text-primary);
}
html[data-theme='light'] .scanner-health-panel :deep(.ant-table-thead > tr > th) {
  background: var(--bg-surface-2);
  color: var(--text-secondary);
}
@media (max-width: 900px) {
  .scanner-health-kpis,
  .admin-quality-grid,
  .scanner-command-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 640px) {
  .scanner-health-kpis,
  .admin-quality-grid,
  .scanner-command-grid { grid-template-columns: 1fr; }
}
</style>
