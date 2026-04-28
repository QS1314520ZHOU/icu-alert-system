<template>
  <div class="work-page">
    <section class="topbar">
      <div>
        <h1>Respiratory Dashboard / 呼吸治疗师工作面板</h1>
        <p>机械通气患者、SBT 候选、气道记录和困难气道预案统一管理，按安全评分和待办优先处理。</p>
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
    <section class="workbench-strip">
      <article v-for="item in topActions" :key="`${item.patient_id}-${item.title}`" class="action-card" @click="openPatient(item.patient)">
        <div>
          <a-tag :color="item.priority === 'high' ? 'red' : 'gold'">{{ item.priority === 'high' ? '优先' : '待办' }}</a-tag>
          <strong>{{ item.bed_no }}床 {{ item.name }} · {{ item.title }}</strong>
        </div>
        <p>{{ item.detail }}</p>
      </article>
      <article v-if="!topActions.length" class="action-card muted-card">
        <strong>暂无高优先级呼吸治疗待办</strong>
        <p>仍建议按班次复核气囊压、湿化、管路固定和 VAP bundle。</p>
      </article>
    </section>
    <section class="layout">
      <a-card title="呼吸机患者" class="panel" :bordered="false">
        <a-table row-key="patient_id" size="small" :loading="loading" :data-source="filteredPatients" :columns="columns" :pagination="{ pageSize: 8 }" :custom-row="rowProps">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'safety_score'">
              <a-tag :color="scoreColor(record.safety_score)">{{ record.safety_score ?? '—' }}</a-tag>
            </template>
            <template v-if="column.key === 'risk_tags'">
              <a-space wrap><a-tag v-for="tag in record.risk_tags" :key="tag" color="volcano">{{ tag }}</a-tag></a-space>
            </template>
            <template v-else-if="column.key === 'sbt'">
              <a-tag :color="record.sbt_candidate_status?.status === 'candidate' ? 'green' : 'gold'">
                {{ record.sbt_candidate_status?.status === 'candidate' ? '可评估' : '暂不适合' }}
              </a-tag>
            </template>
          </template>
        </a-table>
      </a-card>
      <a-card title="SBT 待办" class="panel" :bordered="false">
        <a-tabs>
          <a-tab-pane key="todo" :tab="`今日可评估 ${sbt.todo?.length || 0}`">
            <a-list :data-source="sbt.todo || []">
              <template #renderItem="{ item }">
                <a-list-item>
                  <div class="sbt-row">
                    <span>{{ item.bed_no }}床 {{ item.name }} · P/F {{ item.pf_ratio || '—' }}</span>
                    <a-space>
                      <a-button size="small" type="primary" @click.stop="recordSbt(item, 'completed')">记录完成</a-button>
                      <a-button size="small" danger @click.stop="recordSbt(item, 'failed')">记录失败</a-button>
                    </a-space>
                  </div>
                </a-list-item>
              </template>
            </a-list>
          </a-tab-pane>
          <a-tab-pane key="no" :tab="`暂不适合 ${sbt.not_suitable?.length || 0}`">
            <a-list :data-source="sbt.not_suitable || []">
              <template #renderItem="{ item }"><a-list-item>{{ item.patient?.bed_no }}床 {{ item.patient?.name }} · {{ (item.reasons || []).join('；') }}</a-list-item></template>
            </a-list>
          </a-tab-pane>
          <a-tab-pane key="fail" :tab="`失败 ${sbt.failed?.length || 0}`">
            <a-list :data-source="sbt.failed || []">
              <template #renderItem="{ item }"><a-list-item>{{ item.patient?.bed_no }}床 {{ item.patient?.name }} · {{ item.reason || '未记录原因' }}</a-list-item></template>
            </a-list>
          </a-tab-pane>
        </a-tabs>
      </a-card>
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
        <a-descriptions-item label="FiO2">{{ drawerPatient.fio2 ?? '—' }}</a-descriptions-item>
        <a-descriptions-item label="PEEP">{{ drawerPatient.peep ?? '—' }}</a-descriptions-item>
        <a-descriptions-item label="VT(set)">{{ drawerPatient.vt_set ?? '—' }}</a-descriptions-item>
        <a-descriptions-item label="峰流速">{{ drawerPatient.peak_flow ?? '—' }}</a-descriptions-item>
        <a-descriptions-item label="驱动压">{{ drawerPatient.driving_pressure ?? '—' }}</a-descriptions-item>
        <a-descriptions-item label="气道阻力">{{ drawerPatient.airway_resistance ?? '—' }}</a-descriptions-item>
        <a-descriptions-item label="P0.1">{{ drawerPatient.p01 ?? '—' }}</a-descriptions-item>
        <a-descriptions-item label="Pplat">{{ drawerPatient.pplat ?? '—' }}</a-descriptions-item>
        <a-descriptions-item label="C_STAT">{{ drawerPatient.c_stat ?? '—' }}</a-descriptions-item>
        <a-descriptions-item label="静态顺应性">{{ drawerPatient.static_compliance ?? '—' }}</a-descriptions-item>
        <a-descriptions-item label="P/F">{{ drawerPatient.pf_ratio ?? '—' }}</a-descriptions-item>
        <a-descriptions-item label="RASS">{{ drawerPatient.rass ?? '—' }}</a-descriptions-item>
      </a-descriptions>
      <a-divider>参数时间线</a-divider>
      <a-timeline>
        <a-timeline-item v-for="(item, idx) in timeline" :key="idx">
          {{ fmt(item.time) }} · {{ item.mode || '模式—' }} / FiO2 {{ item.fio2 ?? '—' }} / PEEP {{ item.peep ?? '—' }} / VT(set) {{ item.vt_set ?? '—' }} / Pplat {{ item.pplat ?? '—' }} / C_STAT {{ item.c_stat ?? '—' }} / DP {{ item.driving_pressure ?? '—' }}
        </a-timeline-item>
      </a-timeline>
      <a-divider>气道预案</a-divider>
      <div class="airway-tools">
        <a-button size="small" @click="recordAirway">补录气道记录</a-button>
        <a-button size="small" type="primary" ghost @click="saveDifficultAirwayPlan">标记困难气道预案</a-button>
      </div>
      <pre class="json">{{ airwayPlan }}</pre>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  Button as AButton,
  Card as ACard,
  Descriptions as ADescriptions,
  DescriptionsItem as ADescriptionsItem,
  Divider as ADivider,
  Drawer as ADrawer,
  Input as AInput,
  List as AList,
  ListItem as AListItem,
  Select as ASelect,
  Space as ASpace,
  Table as ATable,
  Tabs as ATabs,
  TabPane as ATabPane,
  Tag as ATag,
  Timeline as ATimeline,
  TimelineItem as ATimelineItem,
  message,
} from 'ant-design-vue'
import { getAirwayPlan, getSbtCandidates, getVentilatedPatients, getVentilatorTimeline, postAirwayPlan, postAirwayRecord, postSbtStatus, type RespiratoryScopeParams } from '../api/respiratory'

const route = useRoute()
const loading = ref(false)
const keyword = ref('')
const riskFilter = ref('all')
const patients = ref<any[]>([])
const stats = ref<any>({})
const sbt = ref<any>({})
const drawerOpen = ref(false)
const drawerPatient = ref<any>(null)
const timeline = ref<any[]>([])
const airwayPlan = ref('')
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
const columns = [
  { title: '床号', dataIndex: 'bed_no', width: 70 },
  { title: '患者', dataIndex: 'name', width: 100 },
  { title: '安全', key: 'safety_score', width: 70 },
  { title: '体位', dataIndex: 'position', width: 90 },
  { title: '模式', dataIndex: 'ventilator_mode', width: 100 },
  { title: 'FiO2', dataIndex: 'fio2', width: 70 },
  { title: 'PEEP', dataIndex: 'peep', width: 70 },
  { title: 'VT', dataIndex: 'vt', width: 70 },
  { title: 'VT(set)', dataIndex: 'vt_set', width: 85 },
  { title: '峰流速', dataIndex: 'peak_flow', width: 85 },
  { title: 'Pplat', dataIndex: 'pplat', width: 80 },
  { title: '气道阻力', dataIndex: 'airway_resistance', width: 90 },
  { title: 'P0.1', dataIndex: 'p01', width: 70 },
  { title: 'C_STAT', dataIndex: 'c_stat', width: 80 },
  { title: 'DP', dataIndex: 'driving_pressure', width: 70 },
  { title: 'P/F', dataIndex: 'pf_ratio', width: 80 },
  { title: 'SBT', key: 'sbt', width: 90 },
  { title: '风险标签', key: 'risk_tags' },
]
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
const topActions = computed(() => patients.value.flatMap((patient) => (patient.worklist_actions || []).map((action: any) => ({
  ...action,
  patient,
  patient_id: patient.patient_id,
  bed_no: patient.bed_no,
  name: patient.name,
}))).sort((a, b) => (a.priority === 'high' ? -1 : 1) - (b.priority === 'high' ? -1 : 1)).slice(0, 6))
function fmt(v: any) { return v ? new Date(v).toLocaleString('zh-CN') : '—' }
function scoreColor(score: number) { return Number(score || 0) >= 85 ? 'green' : Number(score || 0) >= 70 ? 'gold' : 'red' }
function rowProps(record: any) { return { onClick: () => openPatient(record) } }
function requestParams(): RespiratoryScopeParams {
  const params: RespiratoryScopeParams = { patient_scope: 'in_dept' }
  if (routeDeptCode.value) params.dept_code = routeDeptCode.value
  else if (routeDeptName.value) params.dept = routeDeptName.value
  return params
}
async function loadAll() {
  loading.value = true
  try {
    const [p, s] = await Promise.all([getVentilatedPatients(requestParams()), getSbtCandidates(requestParams())])
    patients.value = p.data?.patients || []
    stats.value = p.data?.stats || {}
    sbt.value = s.data || {}
  } finally {
    loading.value = false
  }
}
async function openPatient(row: any) {
  drawerPatient.value = row
  drawerOpen.value = true
  const [tl, plan] = await Promise.all([getVentilatorTimeline(row.patient_id), getAirwayPlan(row.patient_id)])
  timeline.value = tl.data?.timeline || []
  airwayPlan.value = JSON.stringify(plan.data?.plan || {}, null, 2)
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
  airwayPlan.value = JSON.stringify(plan.data?.plan || {}, null, 2)
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
    radial-gradient(circle at 12% 0%, rgba(56,189,248,.12), transparent 30%),
    radial-gradient(circle at 88% 14%, rgba(20,184,166,.1), transparent 32%);
}
.topbar { display: flex; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
h1 { margin: 0; font-size: 22px; letter-spacing: 0; }
p { margin: 4px 0 0; color: #8aa4b8; }
.search-box { width: 240px; }
.risk-select { width: 150px; }
.scope-strip {
  display: inline-flex;
  margin: 0 0 14px;
  padding: 8px 12px;
  border: 1px solid rgba(103,232,249,.18);
  border-radius: 999px;
  color: #bfefff;
  background: rgba(8,47,73,.24);
  font-size: 12px;
}
.kpis { display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); gap: 10px; margin-bottom: 14px; }
.kpis article { border: 1px solid rgba(125,167,214,.16); border-radius: 16px; padding: 12px; background: rgba(10,25,42,.9); }
.kpis span { color: #8aa4b8; display: block; }
.kpis strong { font-size: 28px; color: #e6f7ff; }
.workbench-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}
.action-card {
  display: grid;
  gap: 8px;
  padding: 13px;
  border: 1px solid rgba(125,167,214,.16);
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(8,42,62,.72), rgba(7,20,34,.78));
  cursor: pointer;
}
.action-card div {
  display: flex;
  gap: 8px;
  align-items: center;
}
.action-card strong { color: #e6f7ff; }
.action-card p { color: #b7ccda; }
.muted-card { cursor: default; }
.layout { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(360px, .8fr); gap: 14px; }
.panel { background: rgba(10,25,42,.92); border-radius: 16px; }
.sbt-row {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
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
  border-radius: 14px;
  background: rgba(2,8,20,.24);
}
.drawer-summary span { display: block; color: #8aa4b8; }
.drawer-summary strong { color: #e6f7ff; font-size: 22px; }
.airway-tools {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.json { white-space: pre-wrap; color: #b7ccda; background: rgba(2,8,20,.3); padding: 10px; border-radius: 8px; }
@media (max-width: 1100px) { .layout, .kpis, .drawer-summary { grid-template-columns: 1fr; } .topbar { flex-direction: column; } }
</style>
