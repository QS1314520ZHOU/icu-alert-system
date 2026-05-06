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
            <strong>{{ row.module }}</strong>
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
          <p>{{ focusedRow.threshold_advice || focusedRow.closure?.label || '规则状态平稳，建议保留常规抽查。' }}</p>
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
import { useRouter } from 'vue-router'
import { Button as AButton, Card as ACard, Segmented as ASegmented, Space as ASpace, Table as ATable, message } from 'ant-design-vue'
import { getAdminQualityClosedLoop, getScannerHealth, postScannerHealthInferOutcomes, postScannerHealthRecalculate } from '../api'

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
  { title: '响应中位时间(分钟)', dataIndex: 'median_time_to_action_minutes', key: 'median_time_to_action_minutes', width: 150 },
  { title: '24h事件率', dataIndex: 'event_24h_rate', key: 'event_24h_rate', width: 110 },
  { title: '需提醒人数', dataIndex: 'nnt', key: 'nnt', width: 110 },
  { title: '漂移', dataIndex: 'drift_status', key: 'drift_status', width: 100 },
  { title: '最近覆盖样例', dataIndex: 'recent_overrides', key: 'recent_overrides' },
]
const reviewCount = computed(() => rows.value.filter((row) => row.review_suggestion).length)
const redCount = computed(() => rows.value.filter((row) => String(row.drift_status || '').toLowerCase() === 'red').length)
const yellowCount = computed(() => rows.value.filter((row) => String(row.drift_status || '').toLowerCase() === 'yellow').length)
const totalFired = computed(() => rows.value.reduce((sum, row) => sum + Number(row.fired_count || 0), 0))
const avgPpv = computed(() => {
  if (!rows.value.length) return 0
  return rows.value.reduce((sum, row) => sum + Number(row.ppv || 0), 0) / rows.value.length
})
const closureTasks = computed(() => rows.value.flatMap((row) => (row.closure?.tasks || []).map((task: any) => ({ ...task, scanner_name: row.scanner_name }))))

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

function scannerLabel(value: any) {
  const key = String(value || '').trim()
  const map: Record<string, string> = {
    sofa: '器官衰竭评分',
    qsofa: '快速脓毒症评分',
    septic_shock: '脓毒性休克',
    sepsis_bundle_overdue_3h: '脓毒症Bundle超时3小时',
    liberation_bundle: '撤机与镇静唤醒Bundle',
    vap_bundle_missing: '呼吸机相关肺炎Bundle缺项',
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
  return key
    .replace(/_/g, ' ')
    .replace(/\b[a-z]/g, (letter) => letter.toUpperCase())
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
  router.push({ path: `/patient/${id}`, query: { tab: 'alerts' } })
}

async function loadRows() {
  loading.value = true
  try {
    const [res, qualityRes] = await Promise.all([
      getScannerHealth({ days: days.value }),
      getAdminQualityClosedLoop({ days: days.value }).catch(() => ({ data: {} })),
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

watch(days, () => { void loadRows() })
onMounted(() => { void loadRows() })
</script>

<style scoped>
.scanner-health-page { display: grid; gap: 16px; font-family: var(--app-display-font); }
.scanner-health-filter,.scanner-health-panel { border: 1px solid rgba(80,199,255,.12); background: linear-gradient(180deg, rgba(7,20,34,.94) 0%, rgba(4,12,22,.97) 100%); }
.scanner-health-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.scanner-health-label,.muted { color: #8cb7c9; font-size: 12px; }
.scanner-health-notice { padding: 10px 12px; border-radius: 10px; border: 1px solid rgba(251,191,36,.22); background: rgba(66,46,9,.42); color: #fde68a; font-size: 12px; }
.scanner-health-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.admin-quality-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px; }
.quality-list { display: grid; gap: 8px; }
.quality-list button { display: grid; gap: 4px; width: 100%; text-align: left; border: 1px solid rgba(125,167,214,.14); border-radius: 12px; background: rgba(8,28,44,.64); color: #dff8ff; padding: 9px 10px; }
.quality-list strong { color: #eafcff; font-size: 12px; }
.quality-list span { color: #8aa4b8; font-size: 11px; }
.scanner-health-kpi { padding: 16px; border-radius: 14px; border: 1px solid rgba(125,211,252,.14); background: linear-gradient(180deg, rgba(11,31,50,.92), rgba(8,20,34,.98)); }
.scanner-health-kpi.is-red { border-color: rgba(251,113,133,.28); }
.scanner-health-kpi span { display: block; color: #8cb7c9; font-size: 12px; }
.scanner-health-kpi strong { display: block; margin-top: 8px; color: #ecfeff; font-size: 28px; }
.scanner-command-grid { display: grid; grid-template-columns: 1.1fr .9fr .8fr; gap: 12px; }
.scanner-command-card { min-width: 0; padding: 16px; border-radius: 16px; border: 1px solid rgba(125,211,252,.14); background: radial-gradient(circle at 100% 0%, rgba(34,211,238,.1), transparent 32%), rgba(7,20,34,.92); }
.scanner-command-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 12px; }
.scanner-command-head span { color: #8cb7c9; font-size: 12px; }
.scanner-command-head strong { color: #ecfeff; font-size: 18px; }
.scanner-light-wall { display: grid; grid-template-columns: repeat(auto-fill, minmax(76px, 1fr)); gap: 8px; }
.scanner-light { display: grid; gap: 4px; min-height: 58px; padding: 8px; border: 1px solid rgba(52,211,153,.22); border-radius: 12px; color: #d1fae5; background: rgba(20,83,45,.18); cursor: pointer; }
.scanner-light.is-yellow { border-color: rgba(251,191,36,.28); color: #fde68a; background: rgba(82,48,12,.22); }
.scanner-light.is-red { border-color: rgba(251,113,133,.34); color: #fecaca; background: rgba(69,10,10,.28); }
.scanner-light b,.scanner-light span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.scanner-light b { font-size: 12px; }
.scanner-light span { color: currentColor; opacity: .75; font-size: 11px; }
.scanner-task-list { display: grid; gap: 8px; }
.scanner-task { display: grid; gap: 4px; padding: 10px; border: 1px solid rgba(125,211,252,.14); border-radius: 12px; color: inherit; background: rgba(2,8,20,.28); text-align: left; cursor: pointer; }
.scanner-task.prio-high { border-color: rgba(251,113,133,.34); }
.scanner-task strong { color: #ecfeff; font-size: 13px; }
.scanner-task span,.scanner-empty { color: #8cb7c9; font-size: 12px; }
.scanner-empty { min-height: 110px; display: grid; place-content: center; border: 1px dashed rgba(125,211,252,.16); border-radius: 12px; }
.scanner-focus { display: grid; gap: 10px; }
.scanner-focus div { display: flex; justify-content: space-between; gap: 12px; padding: 9px 10px; border-radius: 12px; background: rgba(2,8,20,.28); }
.scanner-focus span { color: #8cb7c9; }
.scanner-focus b { color: #ecfeff; }
.scanner-focus p { margin: 0; color: #bfefff; line-height: 1.55; }
.scanner-name-cell { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; color: #ecfeff; }
.scanner-name-cell small { color: #6aa7bd; font-size: 11px; }
.review-tag { padding: 2px 8px; border-radius: 999px; color: #fecaca; border: 1px solid rgba(251,113,133,.28); background: rgba(69,10,10,.38); font-size: 11px; }
.drift-pill { display: inline-flex; min-width: 42px; justify-content: center; padding: 3px 10px; border-radius: 999px; border: 1px solid rgba(52,211,153,.24); color: #86efac; }
.drift-pill.is-yellow { border-color: rgba(251,191,36,.28); color: #fde68a; }
.drift-pill.is-red { border-color: rgba(251,113,133,.28); color: #fecaca; }
.override-list { display: flex; gap: 6px; flex-wrap: wrap; }
.override-chip { border: 1px solid rgba(125,211,252,.14); background: rgba(10,36,54,.82); color: #d7f3ff; border-radius: 999px; padding: 4px 8px; cursor: pointer; font-size: 12px; }
html[data-theme='light'] .scanner-health-filter,
html[data-theme='light'] .scanner-health-panel,
html[data-theme='light'] .scanner-health-kpi,
html[data-theme='light'] .scanner-command-card { background: #fff; border-color: rgba(145,176,199,.36); }
html[data-theme='light'] .quality-list button { background: #fff; border-color: rgba(145,176,199,.28); }
html[data-theme='light'] .quality-list strong { color: #16324f; }
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
