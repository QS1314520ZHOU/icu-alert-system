<template>
  <div class="work-page">
    <section class="topbar">
      <div>
        <h1>呼吸治疗工作台</h1>
        <p>{{ completion.label || '按床位处理机械通气、撤机与气道安全。' }}</p>
      </div>
      <a-space wrap>
        <a-input v-model:value="keyword" allow-clear placeholder="搜索床号 / 姓名 / 诊断" class="search-box" />
        <a-select v-model:value="riskFilter" :options="riskOptions" class="risk-select" />
        <a-button :loading="loading" @click="loadAll">刷新</a-button>
      </a-space>
    </section>
    <div class="scope-strip">当前范围：{{ scopeLabel }} · 仅统计在科机械通气与 SBT 待办</div>
    <section class="kpis">
      <article v-for="card in kpis" :key="card.label"><span>{{ card.label }}</span><strong>{{ card.value }}</strong></article>
    </section>
    <section class="closure-strip">
      <article>
        <span>闭环完成</span>
        <strong>{{ completion.percent ?? 100 }}%</strong>
        <i><b :style="{ width: `${completion.percent ?? 100}%` }"></b></i>
      </article>
      <article>
        <span>数据质量</span>
        <strong>{{ completion.data_quality?.percent ?? 100 }}%</strong>
        <i><b :style="{ width: `${completion.data_quality?.percent ?? 100}%` }"></b></i>
      </article>
      <article>
        <span>待办任务</span>
        <strong>{{ completion.tasks?.length || 0 }}</strong>
        <small>{{ topMissingText }}</small>
      </article>
    </section>
    <section class="bedside-command">
      <article v-for="item in bedsideCommand" :key="item.key" :class="['bedside-tile', `tone-${item.tone}`]">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <small>{{ item.hint }}</small>
      </article>
    </section>
    <section class="rt-worklist">
      <div class="panel-head">
        <div>
          <strong>今日工作清单</strong>
          <span>{{ respiratoryWorklist.length }} 项</span>
        </div>
      </div>
      <div class="rt-worklist-grid">
        <article v-for="(item, idx) in respiratoryWorklist" :key="`${item.patient_id}-${item.title}-${idx}`" :class="['rt-task', `tone-${item.tone}`]">
          <b>{{ Number(idx) + 1 }}</b>
          <div>
            <strong>{{ item.title }}</strong>
            <span>{{ item.reason }}</span>
          </div>
          <a-button size="small" @click="openTaskPatient(item)">查看</a-button>
        </article>
        <div v-if="!respiratoryWorklist.length" class="soft-empty small">暂无待处理呼吸治疗任务。</div>
      </div>
    </section>
    <section class="command-layout">
      <section class="patient-panel">
        <div class="panel-head">
          <div>
            <strong>呼吸患者</strong>
            <span>{{ filteredPatients.length }} 人</span>
          </div>
          <em>点击床位查看完整参数</em>
        </div>
        <div v-if="loading" class="soft-empty">正在整理呼吸机患者...</div>
        <div v-else-if="filteredPatients.length" class="vent-card-grid">
          <button
            v-for="patient in filteredPatients"
            :key="patient.patient_id"
            type="button"
            :class="['vent-patient-card', `tone-${patientTone(patient)}`]"
            @click="openPatient(patient)"
          >
            <div class="vent-card-top">
              <span class="bed-badge">{{ patient.bed_no || '--' }}床</span>
              <div class="vent-card-name">
                <strong>{{ patient.name || '患者' }}</strong>
                <small>{{ patient.ventilator_mode || '模式未记载' }}</small>
              </div>
              <b>{{ patient.safety_score ?? '—' }}</b>
            </div>
            <div class="vent-meter-row">
              <span><i>FiO2</i><strong>{{ fmtVentParam('fio2', patient.fio2) }}</strong></span>
              <span><i>PEEP</i><strong>{{ fmtVentParam('peep', patient.peep) }}</strong></span>
              <span><i>DP</i><strong>{{ fmtVentParam('driving_pressure', patient.driving_pressure) }}</strong></span>
              <span><i>P/F</i><strong>{{ fmtVentParam('pf_ratio', patient.pf_ratio) }}</strong></span>
              <span><i>EtCO2</i><strong>{{ fmtVentParam('etco2', patient.etco2) }}</strong></span>
              <span><i>EE</i><strong>{{ fmtVentParam('energy_expenditure', patient.energy_expenditure) }}</strong></span>
            </div>
            <div class="vent-chip-row">
              <span v-for="tag in compactRiskTags(patient)" :key="tag">{{ tag }}</span>
              <span v-if="patient.sbt_candidate_status?.status === 'candidate'" class="is-ok">SBT可评估</span>
            </div>
          </button>
        </div>
        <div v-else class="soft-empty">当前范围暂无机械通气患者。</div>
      </section>

      <section class="sbt-panel">
        <div class="panel-head">
          <div>
            <strong>SBT 待办</strong>
            <span>{{ (sbt.todo?.length || 0) + (sbt.not_suitable?.length || 0) }} 人</span>
          </div>
        </div>
        <a-tabs>
          <a-tab-pane key="deterioration" :tab="`呼吸恶化预警 ${respiratoryDeteriorationRows.length}`">
            <div class="sbt-list">
              <article v-for="item in respiratoryDeteriorationRows" :key="`deterioration-${item.patient_id}`" :class="['deterioration-card', item.tone === 'danger' ? 'danger' : '']">
                <div class="deterioration-main">
                  <div class="deterioration-title">
                    <strong>{{ item.bed_no || '--' }}床 {{ item.name || '患者' }}</strong>
                    <a-tag :color="item.tone === 'danger' ? 'red' : 'gold'">{{ item.tone === 'danger' ? '优先复核' : '趋势关注' }}</a-tag>
                  </div>
                  <span>{{ item.actionText }}</span>
                  <div class="deterioration-metrics">
                    <b v-for="metric in item.metrics" :key="metric.label"><i>{{ metric.label }}</i>{{ metric.value }}</b>
                    <em>试验性</em>
                  </div>
                </div>
                <div class="sbt-actions">
                  <a-button size="small" @click="openPatient(item)">查看</a-button>
                </div>
              </article>
              <div v-if="!respiratoryDeteriorationRows.length" class="soft-empty small">暂无呼吸恶化预警候选</div>
            </div>
          </a-tab-pane>
          <a-tab-pane key="tasks" :tab="`闭环任务 ${completion.tasks?.length || 0}`">
            <div class="sbt-list">
              <article v-for="item in completion.tasks || []" :key="`${item.patient_id}-${item.title}`" :class="['sbt-card', item.priority === 'high' ? 'danger' : '']">
                <div>
                  <strong>{{ item.bed_no || '--' }}床 {{ item.name || '患者' }}</strong>
                  <span>{{ item.title }}</span>
                </div>
                <div class="sbt-actions">
                  <a-button size="small" @click="openTaskPatient(item)">查看</a-button>
                  <a-button size="small" type="primary" @click="closeRespTask(item)">完成</a-button>
                </div>
              </article>
              <div v-if="!(completion.tasks || []).length" class="soft-empty small">呼吸任务已清空</div>
            </div>
          </a-tab-pane>
          <a-tab-pane key="todo" :tab="`今日可评估 ${sbt.todo?.length || 0}`">
            <div class="sbt-list">
              <article v-for="item in sbt.todo || []" :key="`todo-${item.patient_id}`" class="sbt-card">
                <div>
                  <strong>{{ item.bed_no }}床 {{ item.name }}</strong>
                  <span>P/F {{ item.pf_ratio || '—' }}</span>
                  <span>SBT 候选评分：{{ item.sbt_candidate_status?.score ?? sbtCandidateScore(item) }}/100 · {{ item.sbt_candidate_status?.recommendation || sbtCandidateReason(item) }}</span>
                </div>
                <div class="sbt-actions">
                  <a-button size="small" type="primary" @click.stop="recordSbt(item, 'completed')">完成</a-button>
                  <a-button size="small" danger @click.stop="recordSbt(item, 'failed')">失败</a-button>
                </div>
              </article>
              <div v-if="!(sbt.todo || []).length" class="soft-empty small">暂无今日可评估患者</div>
            </div>
          </a-tab-pane>
          <a-tab-pane key="no" :tab="`暂不适合 ${sbt.not_suitable?.length || 0}`">
            <div class="sbt-list">
              <article v-for="item in sbt.not_suitable || []" :key="`no-${item.patient?.patient_id || item.patient?.bed_no}`" class="sbt-card muted">
                <div>
                  <strong>{{ item.patient?.bed_no }}床 {{ item.patient?.name }}</strong>
                  <span>{{ (item.reasons || []).slice(0, 2).join(' / ') || '原因待核' }}</span>
                </div>
              </article>
              <div v-if="!(sbt.not_suitable || []).length" class="soft-empty small">暂无暂不适合患者</div>
            </div>
          </a-tab-pane>
          <a-tab-pane key="fail" :tab="`失败 ${sbt.failed?.length || 0}`">
            <div class="sbt-list">
              <article v-for="item in sbt.failed || []" :key="`fail-${item.patient?.patient_id || item.patient?.bed_no}`" class="sbt-card danger">
                <div>
                  <strong>{{ item.patient?.bed_no }}床 {{ item.patient?.name }}</strong>
                  <span>{{ item.reason || '未记录原因' }}</span>
                </div>
              </article>
              <div v-if="!(sbt.failed || []).length" class="soft-empty small">暂无失败记录</div>
            </div>
          </a-tab-pane>
        </a-tabs>
      </section>
    </section>

    <a-drawer v-model:open="drawerOpen" width="720" :title="drawerPatient ? `${drawerPatient.bed_no}床 ${drawerPatient.name}` : '患者详情'">
      <section v-if="drawerPatient" class="drawer-summary">
        <article>
          <span>安全评分</span>
          <strong>{{ drawerPatient.safety_score ?? '—' }}</strong>
        </article>
        <article>
          <span>参数完整度</span>
          <strong>{{ Math.round((drawerPatient.parameter_completeness?.score || 0) * 100) }}%</strong>
        </article>
        <article>
          <span>SBT 状态</span>
          <strong>{{ drawerPatient.sbt_candidate_status?.status === 'candidate' ? '可评估' : '暂不适合' }}</strong>
        </article>
      </section>
      <a-descriptions bordered size="small" :column="2" v-if="drawerPatient">
        <a-descriptions-item label="体位">{{ drawerPatient.position ?? '—' }}</a-descriptions-item>
        <a-descriptions-item label="模式">{{ drawerPatient.ventilator_mode }}</a-descriptions-item>
        <a-descriptions-item label="FiO2">{{ fmtVentParam('fio2', drawerPatient.fio2) }}</a-descriptions-item>
        <a-descriptions-item label="PEEP">{{ fmtVentParam('peep', drawerPatient.peep) }}</a-descriptions-item>
        <a-descriptions-item label="VT(set)">{{ fmtVentParam('vt_set', drawerPatient.vt_set) }}</a-descriptions-item>
        <a-descriptions-item label="峰流速">{{ fmtVentParam('peak_flow', drawerPatient.peak_flow) }}</a-descriptions-item>
        <a-descriptions-item label="驱动压">{{ fmtVentParam('driving_pressure', drawerPatient.driving_pressure) }}</a-descriptions-item>
        <a-descriptions-item label="气道阻力">{{ fmtVentParam('airway_resistance', drawerPatient.airway_resistance) }}</a-descriptions-item>
        <a-descriptions-item label="P0.1">{{ fmtVentParam('p01', drawerPatient.p01) }}</a-descriptions-item>
        <a-descriptions-item label="Pplat">{{ fmtVentParam('pplat', drawerPatient.pplat) }}</a-descriptions-item>
        <a-descriptions-item label="C_STAT">{{ fmtVentParam('c_stat', drawerPatient.c_stat) }}</a-descriptions-item>
        <a-descriptions-item label="静态顺应性">{{ fmtVentParam('static_compliance', drawerPatient.static_compliance) }}</a-descriptions-item>
        <a-descriptions-item label="P/F">{{ fmtVentParam('pf_ratio', drawerPatient.pf_ratio) }}</a-descriptions-item>
        <a-descriptions-item label="EtCO2">{{ fmtVentParam('etco2', drawerPatient.etco2) }}</a-descriptions-item>
        <a-descriptions-item label="间接测热 EE">{{ fmtVentParam('energy_expenditure', drawerPatient.energy_expenditure) }}</a-descriptions-item>
        <a-descriptions-item label="RASS">{{ fmtVentParam('rass', drawerPatient.rass) }}</a-descriptions-item>
      </a-descriptions>
      <a-divider>参数时间线</a-divider>
      <section class="forecast-card">
        <div class="forecast-card__head">
          <div>
            <span>呼吸恶化预警</span>
            <strong>{{ forecastView.title }}</strong>
          </div>
          <a-tag :color="forecastView.color">experimental</a-tag>
        </div>
        <div class="forecast-grid">
          <article><span>S/F</span><strong>{{ forecastView.sfRatio }}</strong></article>
          <article><span>6h预测</span><strong>{{ forecastView.projected }}</strong></article>
          <article><span>完整度</span><strong>{{ forecastView.completeness }}</strong></article>
        </div>
        <p>{{ forecastView.note }}</p>
      </section>
      <a-timeline>
        <a-timeline-item v-for="(item, idx) in timeline" :key="idx">
          {{ fmt(item.time) }} · {{ item.mode || '模式—' }} / FiO2 {{ fmtVentParam('fio2', item.fio2) }} / PEEP {{ fmtVentParam('peep', item.peep) }} / VT(set) {{ fmtVentParam('vt_set', item.vt_set) }} / Pplat {{ fmtVentParam('pplat', item.pplat) }} / C_STAT {{ fmtVentParam('c_stat', item.c_stat) }} / DP {{ fmtVentParam('driving_pressure', item.driving_pressure) }} / EtCO2 {{ fmtVentParam('etco2', item.etco2) }} / EE {{ fmtVentParam('energy_expenditure', item.energy_expenditure) }}
        </a-timeline-item>
      </a-timeline>
      <a-divider>气道预案</a-divider>
      <div class="airway-tools">
        <a-button size="small" @click="recordAirway">补录气道记录</a-button>
        <a-button size="small" type="primary" ghost @click="saveDifficultAirwayPlan">标记困难气道预案</a-button>
      </div>
      <section class="airway-plan-card">
        <div class="airway-plan-card__head">
          <div>
            <span>预案状态</span>
            <strong>{{ airwayPlanView.statusText }}</strong>
          </div>
          <a-tag :color="airwayPlanView.tagColor">{{ airwayPlanView.riskText }}</a-tag>
        </div>
        <p>{{ airwayPlanView.note }}</p>
        <div class="airway-plan-grid">
          <article>
            <span>困难气道</span>
            <strong>{{ airwayPlanView.difficultAirway ? '已标记' : '未标记' }}</strong>
          </article>
          <article>
            <span>备选设备</span>
            <strong>{{ airwayPlanView.equipment }}</strong>
          </article>
          <article>
            <span>联络团队</span>
            <strong>{{ airwayPlanView.contacts }}</strong>
          </article>
        </div>
      </section>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  Button as AButton,
  Descriptions as ADescriptions,
  DescriptionsItem as ADescriptionsItem,
  Divider as ADivider,
  Drawer as ADrawer,
  Input as AInput,
  Select as ASelect,
  Space as ASpace,
  Tabs as ATabs,
  TabPane as ATabPane,
  Timeline as ATimeline,
  TimelineItem as ATimelineItem,
  message,
} from 'ant-design-vue'
import {
  closeRespiratoryWorklistTask,
  getAirwayPlan,
  getRespiratoryDashboard,
  getRespiratoryDeteriorationForecast,
  getVentilatorTimeline,
  postAirwayPlan,
  postAirwayRecord,
  postRespiratoryTaskDone,
  postSbtStatus,
  type RespiratoryScopeParams,
} from '../api/respiratory'
import { formatBeijingTime } from '../utils/time'

const route = useRoute()
const loading = ref(false)
const keyword = ref('')
const riskFilter = ref('all')
const patients = ref<any[]>([])
const stats = ref<any>({})
const sbt = ref<any>({})
const completion = ref<any>({})
const worklist = ref<any>({ tasks: [], summary: {} })
const drawerOpen = ref(false)
const drawerPatient = ref<any>(null)
const timeline = ref<any[]>([])
const airwayPlan = ref<any>({})
const deteriorationForecast = ref<any>({})
const riskOptions = [
  { value: 'all', label: '全部风险' },
  { value: '高驱动压', label: '高驱动压' },
  { value: '低氧合', label: '低氧合' },
  { value: '气囊压待测', label: '气囊压待测' },
  { value: '困难气道', label: '困难气道' },
  { value: 'sbt', label: 'SBT候选' },
]
const routeDeptCode = computed(() => String(route.query.dept_code || route.query.deptCode || '').trim())
const routeDeptName = computed(() => String(route.query.dept || route.query.department || '').trim())
const scopeLabel = computed(() => routeDeptName.value || routeDeptCode.value || '全部 ICU 在科患者')
const filteredPatients = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  return patients.value.filter((row) => {
    if (riskFilter.value === 'sbt' && row.sbt_candidate_status?.status !== 'candidate') return false
    if (riskFilter.value !== 'all' && riskFilter.value !== 'sbt' && !(row.risk_tags || []).includes(riskFilter.value)) return false
    if (!q) return true
    return [row.bed_no, row.name, row.diagnosis, row.ventilator_mode].some((item) => String(item || '').toLowerCase().includes(q))
  })
})
const kpis = computed(() => [
  { label: '机械通气', value: stats.value.ventilated_count || 0 },
  { label: 'SBT 候选', value: stats.value.sbt_candidate_count || 0 },
  { label: '高驱动压', value: stats.value.high_driving_pressure_count || 0 },
  { label: '低氧合', value: stats.value.low_oxygenation_count || 0 },
  { label: '平均安全分', value: stats.value.avg_safety_score || 0 },
])
const topMissingText = computed(() => {
  const gaps = completion.value?.data_quality?.missing || []
  if (!gaps.length) return '关键字段齐全'
  return gaps.slice(0, 2).map((item: any) => `${item.label}${item.count}`).join(' / ')
})
const bedsideCommand = computed(() => {
  const rows = patients.value || []
  const highDp = rows.filter((row: any) => (row.risk_tags || []).includes('高驱动压')).length
  const lowOxy = rows.filter((row: any) => (row.risk_tags || []).includes('低氧合')).length
  const cuffTodo = rows.filter((row: any) => (row.risk_tags || []).includes('气囊压待测')).length
  const sbtReady = rows.filter((row: any) => row.sbt_candidate_status?.status === 'candidate').length
  return [
    { key: 'oxygen', label: '氧合优先', value: lowOxy, hint: '先看 P/F 与 FiO2', tone: lowOxy ? 'danger' : 'stable' },
    { key: 'protect', label: '肺保护', value: highDp, hint: '复核 DP/Pplat/VT', tone: highDp ? 'warning' : 'stable' },
    { key: 'sbt', label: '今日 SBT', value: sbtReady, hint: '可床旁评估', tone: sbtReady ? 'info' : 'stable' },
    { key: 'airway', label: '气道补录', value: cuffTodo, hint: '气囊压/湿化/固定', tone: cuffTodo ? 'warning' : 'stable' },
  ]
})
const respiratoryWorklist = computed(() => {
  if (Array.isArray(worklist.value?.tasks) && worklist.value.tasks.length) {
    return worklist.value.tasks.map((item: any) => ({
      ...item,
      tone: item.priority === 'high' ? 'danger' : item.priority === 'medium' ? 'warning' : 'info',
    })).slice(0, 8)
  }
  const rows: any[] = []
  for (const item of sbt.value?.todo || []) {
    rows.push({ ...item, title: `评估 ${item.bed_no || '--'}床 SBT 候选`, reason: sbtCandidateReason(item), tone: 'info' })
  }
  for (const item of patients.value.filter((row: any) => (row.risk_tags || []).includes('气囊压待测')).slice(0, 4)) {
    rows.push({ ...item, title: `复查 ${item.bed_no || '--'}床 气囊压`, reason: '近8小时缺失或异常需补录', tone: 'warning' })
  }
  for (const item of patients.value.filter((row: any) => (row.risk_tags || []).includes('高驱动压')).slice(0, 4)) {
    rows.push({ ...item, title: `复核 ${item.bed_no || '--'}床 肺保护通气参数`, reason: '关注 VT/Pplat/Driving Pressure', tone: 'danger' })
  }
  return rows.slice(0, 8)
})
const respiratoryDeteriorationRows = computed(() => {
  return (patients.value || [])
    .map((row: any) => {
      const tags = Array.isArray(row?.risk_tags) ? row.risk_tags : []
      const fio2Raw = Number(row?.fio2)
      const fio2Percent = Number.isFinite(fio2Raw) ? (fio2Raw > 0 && fio2Raw <= 1 ? fio2Raw * 100 : fio2Raw) : null
      const pf = Number(row?.pf_ratio)
      const score = Number(row?.safety_score)
      const reasons: string[] = []
      let priority = 0
      if (tags.some((tag: string) => String(tag).includes('低氧合'))) {
        reasons.push('低氧合标签')
        priority += 4
      }
      if (Number.isFinite(pf) && pf > 0 && pf < 200) {
        reasons.push(`P/F ${Math.round(pf)}`)
        priority += pf < 150 ? 4 : 2
      }
      if (Number.isFinite(fio2Percent) && Number(fio2Percent) >= 60) {
        reasons.push(`FiO2 ${Math.round(Number(fio2Percent))}%`)
        priority += Number(fio2Percent) >= 80 ? 3 : 2
      }
      if (Number.isFinite(score) && score < 75) {
        reasons.push(`安全评分 ${Math.round(score)}`)
        priority += score < 60 ? 3 : 1
      }
      const metrics = [
        { label: 'P/F', value: Number.isFinite(pf) && pf > 0 ? Math.round(pf) : '—' },
        { label: 'FiO2', value: Number.isFinite(fio2Percent) ? `${Math.round(Number(fio2Percent))}%` : '—' },
        { label: '评分', value: Number.isFinite(score) ? Math.round(score) : '—' },
      ]
      return {
        ...row,
        priority,
        tone: priority >= 5 ? 'danger' : 'warning',
        reason: reasons.join(' / '),
        actionText: reasons.length ? `建议床旁复核：${reasons.slice(0, 3).join('、')}` : '建议床旁复核氧合趋势',
        metrics,
      }
    })
    .filter((row: any) => row.priority > 0)
    .sort((a: any, b: any) => b.priority - a.priority)
    .slice(0, 8)
})
const airwayPlanView = computed(() => {
  const plan = airwayPlan.value || {}
  const risk = String(plan.risk_level || 'unknown').toLowerCase()
  const isDefault = Boolean(plan.is_default || plan.is_mock)
  const equipment = Array.isArray(plan.backup_equipment) ? plan.backup_equipment.filter(Boolean) : []
  const contacts = Array.isArray(plan.contacts) ? plan.contacts.filter(Boolean) : []
  return {
    statusText: isDefault ? '默认流程提醒' : '已维护预案',
    riskText: risk === 'high' ? '高风险' : risk === 'medium' ? '中风险' : '待评估',
    tagColor: risk === 'high' ? 'red' : risk === 'medium' ? 'gold' : 'blue',
    difficultAirway: Boolean(plan.difficult_airway),
    equipment: equipment.length ? equipment.join(' / ') : '待补充',
    contacts: contacts.length ? contacts.join(' / ') : '待补充',
    note: plan.note || '暂无预案说明，建议由呼吸治疗师与麻醉团队补充。',
  }
})

const forecastView = computed(() => {
  const row = deteriorationForecast.value || {}
  const features = row.features || {}
  const forecast = row.forecast || {}
  const completeness = row.data_completeness || {}
  const severity = String(row.severity || row.risk_level || 'none').toLowerCase()
  const ratio = Number(completeness.completeness_ratio)
  return {
    title: row.available ? (severity === 'high' ? '需优先复核' : severity === 'warning' ? '趋势需关注' : '暂无明显恶化') : '数据不足',
    color: severity === 'high' ? 'red' : severity === 'warning' ? 'gold' : 'blue',
    sfRatio: features.latest_sf_ratio != null ? Math.round(Number(features.latest_sf_ratio)) : '—',
    projected: forecast.projected_sf_ratio != null ? Math.round(Number(forecast.projected_sf_ratio)) : '—',
    completeness: Number.isFinite(ratio) ? `${Math.round(ratio * 100)}%` : '—',
    note: row.available ? `特征版本 ${row.feature_schema_version || features.feature_schema_version || '—'}，仅作实验性趋势提示。` : (row.unavailable_reason || '缺少可配对的 SpO2/FiO2 数据。'),
  }
})
function fmt(v: any) { return formatBeijingTime(v, '—') }
function fmtVentParam(key: string, value: any) {
  if (value === null || value === undefined || value === '') return '—'
  const num = Number(value)
  if (!Number.isFinite(num)) return String(value)
  if (key === 'fio2') {
    const fio2 = num > 0 && num <= 1 ? num * 100 : num
    return `${Math.round(fio2)}`
  }
  const decimals: Record<string, number> = {
    peep: 0,
    vt_set: 0,
    peak_flow: 0,
    driving_pressure: 1,
    airway_resistance: 1,
    p01: 1,
    pplat: 0,
    c_stat: 0,
    static_compliance: 0,
    pf_ratio: 0,
    etco2: 0,
    energy_expenditure: 0,
    rass: 0,
  }
  const digits = decimals[key] ?? 1
  const rounded = Number(num.toFixed(digits))
  return digits === 0 || Number.isInteger(rounded) ? String(Math.round(rounded)) : rounded.toFixed(digits)
}
function compactRiskTags(patient: any) {
  const tags = Array.isArray(patient?.risk_tags) ? patient.risk_tags.filter(Boolean) : []
  if (tags.length) return tags.slice(0, 3)
  return ['常规复核']
}
function patientTone(patient: any) {
  const score = Number(patient?.safety_score || 0)
  const tags = Array.isArray(patient?.risk_tags) ? patient.risk_tags : []
  if (tags.includes('低氧合') || tags.includes('高驱动压') || score < 60) return 'danger'
  if (tags.length || score < 80) return 'warn'
  return 'stable'
}
function sbtCandidateScore(row: any) {
  let score = 50
  if (Number(row?.pf_ratio || 0) >= 150) score += 15
  if (Number(row?.peep || 99) <= 8) score += 10
  if (Number(row?.fio2 || 1) <= 0.5) score += 10
  const rass = Number(row?.rass)
  if (Number.isFinite(rass) && rass >= -2 && rass <= 1) score += 10
  if (!(row?.risk_tags || []).includes('低氧合')) score += 5
  return Math.min(100, score)
}
function sbtCandidateReason(row: any) {
  const blockers = []
  if (row?.rass == null) blockers.push('RASS缺失')
  if (Number(row?.fio2 || 0) > 0.5) blockers.push('FiO2偏高')
  if (Number(row?.peep || 0) > 8) blockers.push('PEEP偏高')
  if ((row?.risk_tags || []).includes('低氧合')) blockers.push('氧合不稳')
  return blockers.length ? `阻碍因素：${blockers.slice(0, 2).join('、')}` : '建议评估 SBT'
}
function requestParams(): RespiratoryScopeParams {
  const params: RespiratoryScopeParams = { patient_scope: 'in_dept' }
  if (routeDeptCode.value) params.dept_code = routeDeptCode.value
  else if (routeDeptName.value) params.dept = routeDeptName.value
  return params
}
async function loadAll() {
  loading.value = true
  try {
    const res = await getRespiratoryDashboard(requestParams())
    const d = res.data || {}
    patients.value = d.dashboard?.patients || []
    stats.value = d.dashboard?.stats || {}
    completion.value = d.dashboard?.completion || {}
    sbt.value = d.sbt || {}
    worklist.value = d.worklist || { tasks: [], summary: {} }
  } finally {
    loading.value = false
  }
}
async function openTaskPatient(item: any) {
  const row = patients.value.find((patient) => patient.patient_id === item.patient_id)
  if (row) await openPatient(row)
}
async function closeRespTask(item: any) {
  if (item.task_id) {
    await closeRespiratoryWorklistTask(item.task_id, {
      patient_id: item.patient_id,
      status: 'completed',
      result: '床旁已复核',
      note: `闭环：${item.title || '呼吸治疗任务'}。${item.reason || item.detail || ''}`,
    })
  }
  await postRespiratoryTaskDone(item.patient_id, {
    airway_type: '床旁已复核',
    humidification_status: '已复核',
    note: `闭环：${item.title || '呼吸治疗任务'}。${item.detail || ''}`,
  })
  message.success('已记录闭环')
  await loadAll()
}
async function openPatient(row: any) {
  drawerPatient.value = row
  drawerOpen.value = true
  const [tl, plan, forecast] = await Promise.all([
    getVentilatorTimeline(row.patient_id),
    getAirwayPlan(row.patient_id),
    getRespiratoryDeteriorationForecast(row.patient_id).catch(() => ({ data: {} })),
  ])
  timeline.value = tl.data?.timeline || []
  airwayPlan.value = plan.data?.plan || {}
  deteriorationForecast.value = forecast.data || {}
}
async function recordSbt(row: any, status: 'completed' | 'failed') {
  await postSbtStatus(row.patient_id, { status, note: status === 'completed' ? '呼吸治疗师工作台记录 SBT 已完成' : '呼吸治疗师工作台记录 SBT 失败，原因待补充' })
  message.success(status === 'completed' ? '已记录 SBT 完成' : '已记录 SBT 失败')
  await loadAll()
}
async function recordAirway() {
  if (!drawerPatient.value) return
  await postAirwayRecord(drawerPatient.value.patient_id, {
    airway_type: drawerPatient.value.airway_type,
    cuff_pressure: drawerPatient.value.latest_cuff_pressure || '',
    humidification_status: '待床旁确认',
    note: '呼吸治疗师工作台快速补录，请完善痰液性状、固定深度和 VAP bundle。',
  })
  message.success('已创建气道记录草稿')
}
async function saveDifficultAirwayPlan() {
  if (!drawerPatient.value) return
  await postAirwayPlan(drawerPatient.value.patient_id, {
    risk_level: 'high',
    difficult_airway: true,
    backup_equipment: ['视频喉镜', '纤支镜', '环甲膜穿刺包'],
    contacts: ['麻醉科', '耳鼻喉科'],
    note: '呼吸治疗师工作台快速标记，需临床团队复核完善。',
  })
  message.success('已标记困难气道预案')
  const plan = await getAirwayPlan(drawerPatient.value.patient_id)
  airwayPlan.value = plan.data?.plan || {}
}
watch(() => [route.query.deptCode, route.query.dept_code, route.query.dept, route.query.department], () => {
  void loadAll()
})

onMounted(loadAll)
</script>

<style scoped>
.work-page {
  min-height: calc(100vh - 76px);
  padding: 18px;
  background:
    var(--bg-surface), transparent 30%),
    var(--bg-surface), transparent 32%);
}
.topbar { display: flex; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
h1 { margin: 0; font-size: 26px; letter-spacing: 0; color: var(--text-primary); }
p { margin: 6px 0 0; color: var(--text-secondary); }
.search-box { width: 240px; }
.risk-select { width: 150px; }
.scope-strip {
  display: inline-flex;
  margin: 0 0 14px;
  padding: 8px 12px;
  border: 1px solid rgba(103,232,249,.18);
  border-radius: var(--card-radius);
  color: var(--text-primary);
  background: var(--bg-surface),.24);
  font-size: 12px;
}
.kpis { display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); gap: 10px; margin-bottom: 14px; }
.kpis article { border: 1px solid rgba(125,167,214,.16); border-radius: var(--card-radius); padding: 12px; background: var(--bg-surface),.9); }
.kpis span { color: var(--text-secondary); display: block; }
.kpis strong { font-size: 28px; color: var(--text-primary); }
.closure-strip {
  display: grid;
  grid-template-columns: 1fr 1fr minmax(180px, .7fr);
  gap: 10px;
  margin-bottom: 14px;
}
.rt-worklist {
  display: grid;
  gap: 10px;
  margin-bottom: 14px;
  padding: 12px;
  border: 1px solid rgba(125,167,214,.16);
  border-radius: var(--card-radius);
  background: var(--bg-surface),.82);
}
.rt-worklist-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 10px;
}
.rt-task {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 10px;
  border-radius: var(--card-radius);
  border: 1px solid rgba(125,211,252,.14);
  background: var(--bg-surface),.72);
}
.rt-task b {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: var(--card-radius);
  background: rgba(59,130,246,.24);
  color: var(--text-primary);
}
.rt-task strong,
.rt-task span {
  display: block;
}
.rt-task strong {
  color: var(--text-primary);
}
.rt-task span {
  color: var(--text-secondary);
  font-size: 12px;
}
.rt-task.tone-danger {
  border-color: rgba(248,113,113,.26);
}
.rt-task.tone-warning {
  border-color: rgba(245,158,11,.24);
}
.closure-strip article {
  min-width: 0;
  padding: 12px 14px;
  border: 1px solid rgba(45,212,191,.16);
  border-radius: var(--card-radius);
  background: var(--bg-surface), var(--bg-surface));
}
.closure-strip span,
.closure-strip small {
  display: block;
  color: var(--text-secondary);
  font-size: 12px;
}
.closure-strip strong {
  display: block;
  margin-top: 2px;
  color: var(--text-primary);
  font-size: 24px;
}
.closure-strip i {
  display: block;
  height: 8px;
  margin-top: 8px;
  overflow: hidden;
  border-radius: var(--card-radius);
  background: var(--bg-surface),.38);
}
.closure-strip b {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--bg-surface);
}
.bedside-command {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}
.bedside-tile {
  min-height: 106px;
  padding: 14px;
  border: 1px solid rgba(125,211,252,.14);
  border-radius: var(--card-radius);
  background: var(--bg-surface), var(--bg-surface));
}
.bedside-tile span,
.bedside-tile small {
  display: block;
  color: var(--text-secondary);
  font-size: 12px;
}
.bedside-tile strong {
  display: block;
  margin: 4px 0;
  color: var(--text-primary);
  font-size: 34px;
  line-height: 1;
}
.bedside-tile.tone-danger { border-color: rgba(251,113,133,.36); background: var(--bg-surface), var(--bg-surface)); }
.bedside-tile.tone-warning { border-color: rgba(251,191,36,.32); background: var(--bg-surface), var(--bg-surface)); }
.bedside-tile.tone-info { border-color: rgba(103,232,249,.28); }
.bedside-tile.tone-stable { border-color: rgba(52,211,153,.22); }
.command-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(360px, .65fr);
  gap: 16px;
  align-items: start;
}
.patient-panel,
.sbt-panel {
  border: 1px solid rgba(125,167,214,.16);
  border-radius: var(--card-radius);
  padding: 16px;
  background:
    var(--bg-surface), transparent 30%),
    rgba(7,20,34,.92);
}
.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding-bottom: 12px;
  margin-bottom: 14px;
  border-bottom: 1px solid rgba(125,211,252,.12);
}
.panel-head strong {
  display: block;
  color: var(--text-primary);
  font-size: 19px;
}
.panel-head span,
.panel-head em {
  display: block;
  margin-top: 3px;
  color: var(--text-secondary);
  font-size: 12px;
  font-style: normal;
}
.vent-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 12px;
}
.vent-patient-card {
  display: grid;
  gap: 12px;
  min-height: 154px;
  padding: 14px;
  border: 1px solid rgba(103,232,249,.16);
  border-radius: var(--card-radius);
  color: inherit;
  background:
    var(--bg-surface), transparent 34%),
    var(--bg-surface), rgba(7,20,34,.9));
  text-align: left;
  cursor: pointer;
  transition: transform .16s ease, border-color .16s ease, background .16s ease;
}
.vent-patient-card:hover {
  transform: translateY(-2px);
  border-color: rgba(103,232,249,.42);
}
.vent-patient-card.tone-danger { border-color: rgba(251,113,133,.34); }
.vent-patient-card.tone-warn { border-color: rgba(251,191,36,.26); }
.vent-patient-card.tone-stable { border-color: rgba(52,211,153,.22); }
.vent-card-top {
  display: flex;
  gap: 8px;
  align-items: center;
}
.bed-badge {
  min-width: 58px;
  height: 42px;
  display: grid;
  place-items: center;
  border-radius: var(--card-radius);
  color: var(--text-primary);
  background: var(--bg-surface);
  font-size: 16px;
  font-weight: 950;
  box-shadow: var(--card-shadow);
}
.vent-card-name {
  min-width: 0;
  display: grid;
  gap: 2px;
}
.vent-card-name strong {
  color: var(--text-primary);
  font-size: 17px;
  line-height: 1.15;
}
.vent-card-name small {
  color: #8bdcf1;
  font-size: 13px;
  font-weight: 800;
}
.vent-card-top b {
  margin-left: auto;
  min-width: 38px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: var(--card-radius);
  color: var(--success);
  background: var(--bg-surface),.38);
  border: 1px solid rgba(125,211,252,.16);
}
.vent-meter-row {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 7px;
}
.vent-meter-row span {
  min-width: 0;
  padding: 8px 6px;
  border-radius: var(--card-radius);
  background: var(--bg-surface),.28);
  border: 1px solid rgba(125,211,252,.12);
}
.vent-meter-row i,
.vent-meter-row strong {
  display: block;
  text-align: center;
}
.vent-meter-row i {
  color: var(--text-secondary);
  font-style: normal;
  font-size: 11px;
}
.vent-meter-row strong {
  margin-top: 3px;
  color: var(--text-primary);
  font-size: 15px;
}
.vent-chip-row {
  display: flex;
  align-content: flex-start;
  gap: 6px;
  flex-wrap: wrap;
}
.vent-chip-row span {
  padding: 5px 8px;
  border: 1px solid rgba(125,211,252,.16);
  border-radius: var(--card-radius);
  color: var(--text-primary);
  background: var(--bg-surface),.28);
  font-size: 12px;
  line-height: 1;
}
.vent-chip-row .is-ok {
  color: var(--success);
  border-color: rgba(52,211,153,.24);
}
.sbt-list {
  display: grid;
  gap: 10px;
}
.sbt-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  border: 1px solid rgba(125,211,252,.14);
  border-radius: var(--card-radius);
  background: var(--bg-surface),.28);
}
.sbt-card strong,
.sbt-card span {
  display: block;
}
.sbt-card strong { color: var(--text-primary); }
.sbt-card span {
  margin-top: 4px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.35;
}
.sbt-card.muted { border-color: rgba(251,191,36,.2); }
.sbt-card.danger { border-color: rgba(251,113,133,.24); }
.deterioration-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  border: 1px solid rgba(245,158,11,.22);
  border-radius: var(--card-radius);
  background: var(--bg-surface),.28);
}
.deterioration-card.danger {
  border-color: rgba(248,113,113,.3);
}
.deterioration-main {
  min-width: 0;
  display: grid;
  gap: 8px;
}
.deterioration-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.deterioration-title strong {
  color: var(--text-primary);
  font-size: 15px;
}
.deterioration-main > span {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.35;
}
.deterioration-metrics {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
}
.deterioration-metrics b,
.deterioration-metrics em {
  padding: 5px 8px;
  border-radius: var(--card-radius);
  background: rgba(125, 211, 252, .08);
  border: 1px solid rgba(125,211,252,.14);
  color: var(--text-primary);
  font-size: 12px;
  font-style: normal;
  line-height: 1;
}
.deterioration-metrics i {
  margin-right: 4px;
  color: var(--text-secondary);
  font-style: normal;
}
.deterioration-metrics em {
  color: var(--text-secondary);
  background: transparent;
}
.sbt-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.soft-empty {
  min-height: 160px;
  display: grid;
  place-content: center;
  border: 1px dashed rgba(125,211,252,.18);
  border-radius: var(--card-radius);
  color: var(--text-secondary);
  text-align: center;
}
.soft-empty.small {
  min-height: 96px;
}
.drawer-summary {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-bottom: 14px;
}
.drawer-summary article {
  padding: 12px;
  border: 1px solid rgba(125,167,214,.16);
  border-radius: var(--card-radius);
  background: var(--bg-surface),.24);
}
.drawer-summary span { display: block; color: var(--text-secondary); }
.drawer-summary strong { color: var(--text-primary); font-size: 22px; }
.airway-tools {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.forecast-card {
  display: grid;
  gap: 10px;
  margin: 12px 0;
  padding: 12px;
  border: 1px solid rgba(125, 211, 252, .16);
  border-radius: var(--card-radius);
  background: var(--bg-surface);
}
.forecast-card__head,
.forecast-grid {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}
.forecast-card__head span,
.forecast-grid span {
  display: block;
  color: var(--text-secondary);
  font-size: 12px;
}
.forecast-card__head strong,
.forecast-grid strong {
  color: var(--text-primary);
}
.forecast-grid article {
  flex: 1;
  min-width: 0;
  padding: 8px 10px;
  border-radius: var(--card-radius);
  background: rgba(125, 211, 252, .08);
}
.forecast-card p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
}
.airway-plan-card {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid rgba(45,212,191,.18);
  border-radius: var(--card-radius);
  background: var(--bg-surface), var(--bg-surface));
}
.airway-plan-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.airway-plan-card span,
.airway-plan-grid span {
  display: block;
  color: var(--text-secondary);
  font-size: 12px;
}
.airway-plan-card strong,
.airway-plan-grid strong {
  color: var(--text-primary);
}
.airway-plan-card p {
  margin: 0;
  color: #b7ccda;
}
.airway-plan-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}
.airway-plan-grid article {
  min-width: 0;
  padding: 10px;
  border-radius: var(--card-radius);
  background: var(--bg-surface-2);
}
@media (max-width: 1100px) { .command-layout, .kpis, .closure-strip, .bedside-command, .drawer-summary { grid-template-columns: 1fr; } .topbar { flex-direction: column; } }

html[data-theme='light'] .work-page {
  background:
    var(--bg-surface), transparent 30%),
    var(--bg-surface), transparent 32%),
    #f5f7fa;
}
html[data-theme='light'] h1,
html[data-theme='light'] .kpis strong,
html[data-theme='light'] .rt-task strong,
html[data-theme='light'] .closure-strip strong,
html[data-theme='light'] .bedside-tile strong,
html[data-theme='light'] .panel-head strong,
html[data-theme='light'] .vent-card-name strong,
html[data-theme='light'] .vent-meter-row strong,
html[data-theme='light'] .sbt-card strong,
html[data-theme='light'] .drawer-summary strong,
html[data-theme='light'] .airway-plan-card strong,
html[data-theme='light'] .airway-plan-grid strong {
  color: var(--text-primary);
}
html[data-theme='light'] p,
html[data-theme='light'] .kpis span,
html[data-theme='light'] .rt-task span,
html[data-theme='light'] .closure-strip span,
html[data-theme='light'] .closure-strip small,
html[data-theme='light'] .bedside-tile span,
html[data-theme='light'] .bedside-tile small,
html[data-theme='light'] .panel-head span,
html[data-theme='light'] .panel-head em,
html[data-theme='light'] .vent-meter-row i,
html[data-theme='light'] .sbt-card span,
html[data-theme='light'] .soft-empty,
html[data-theme='light'] .drawer-summary span,
html[data-theme='light'] .airway-plan-card span,
html[data-theme='light'] .airway-plan-grid span,
html[data-theme='light'] .airway-plan-card p {
  color: var(--text-secondary);
}
html[data-theme='light'] .scope-strip {
  color: var(--brand);
  background: var(--bg-surface);
  border-color: rgba(37, 99, 235, 0.18);
}
html[data-theme='light'] .kpis article,
html[data-theme='light'] .rt-worklist,
html[data-theme='light'] .rt-task,
html[data-theme='light'] .closure-strip article,
html[data-theme='light'] .bedside-tile,
html[data-theme='light'] .patient-panel,
html[data-theme='light'] .sbt-panel,
html[data-theme='light'] .vent-patient-card,
html[data-theme='light'] .vent-meter-row span,
html[data-theme='light'] .sbt-card,
html[data-theme='light'] .drawer-summary article,
html[data-theme='light'] .airway-plan-card,
html[data-theme='light'] .airway-plan-grid article {
  background: rgba(255, 255, 255, 0.96);
  border-color: rgba(145, 176, 199, 0.32);
  box-shadow: var(--card-shadow);
}
html[data-theme='light'] .vent-patient-card,
html[data-theme='light'] .bedside-tile,
html[data-theme='light'] .patient-panel,
html[data-theme='light'] .sbt-panel {
  background:
    var(--bg-surface), transparent 34%),
    #ffffff;
}
html[data-theme='light'] .closure-strip article,
html[data-theme='light'] .airway-plan-card {
  background: var(--bg-surface), rgba(239, 246, 255, 0.98));
}
html[data-theme='light'] .vent-card-name small,
html[data-theme='light'] .vent-chip-row span,
html[data-theme='light'] .vent-chip-row .is-ok {
  color: var(--brand);
}
html[data-theme='light'] .vent-card-top b {
  color: var(--chart-2);
  background: var(--bg-surface);
  border-color: rgba(16, 185, 129, 0.22);
}
html[data-theme='light'] .vent-chip-row span {
  background: var(--bg-surface);
  border-color: rgba(145, 176, 199, 0.3);
}
html[data-theme='light'] .soft-empty {
  background: var(--bg-surface);
  border-color: rgba(145, 176, 199, 0.32);
}
</style>
