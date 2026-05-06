<template>
  <div class="nutrition-page">
    <section class="topbar">
      <div>
        <h1>营养支持工作台</h1>
        <p>按床位看 NRS2002、NUTRIC、EN/PN 与达标率。</p>
      </div>
      <a-space wrap>
        <a-input v-model:value="keyword" allow-clear placeholder="搜索床号 / 姓名 / 诊断" class="search-box" />
        <a-select v-model:value="riskFilter" :options="riskOptions" class="risk-select" />
        <a-button :loading="loading" @click="loadAll">刷新</a-button>
      </a-space>
    </section>

    <div class="scope-strip">当前范围：{{ scopeLabel }}</div>

    <section class="kpis">
      <button v-for="card in kpis" :key="card.key" type="button" :class="['kpi', `tone-${card.tone}`]" @click="riskFilter = card.filter">
        <span>{{ card.label }}</span>
        <strong>{{ card.value }}</strong>
      </button>
    </section>

    <section class="layout">
      <section class="patient-panel">
        <div class="panel-head">
          <div>
            <strong>营养床卡</strong>
            <span>{{ filteredPatients.length }} 人</span>
          </div>
          <em>点击床位看评分、化验和任务</em>
        </div>
        <div v-if="loading" class="soft-empty">正在加载床位...</div>
        <div v-else-if="filteredPatients.length" class="nutrition-grid">
          <button
            v-for="patient in filteredPatients"
            :key="patient.patient_id"
            type="button"
            :class="['nutrition-card', `tone-${patientTone(patient)}`]"
            @click="openPatient(patient)"
          >
            <div class="card-top">
              <span class="bed">{{ patient.bed_no || '--' }}床</span>
              <div class="identity">
                <strong>{{ patient.name || '患者' }}</strong>
                <small>{{ patient.route || '未开始' }}</small>
              </div>
              <b>{{ patient.nutrition_score ?? '评' }}</b>
            </div>

            <div class="score-strip">
              <span>
                <i>NRS2002</i>
                <strong>{{ patient.nrs2002 ?? '待评' }}</strong>
              </span>
              <span>
                <i>NUTRIC</i>
                <strong>{{ patient.nutric ?? '待评' }}</strong>
              </span>
            </div>

            <div class="progress-pair">
              <div>
                <label>热量 {{ patient.kcal_achieved_pct ?? '待评' }}{{ patient.kcal_achieved_pct == null ? '' : '%' }}</label>
                <meter min="0" max="100" :value="patient.kcal_achieved_pct || 0"></meter>
              </div>
              <div>
                <label>蛋白 {{ patient.protein_achieved_pct ?? '待评' }}{{ patient.protein_achieved_pct == null ? '' : '%' }}</label>
                <meter min="0" max="100" :value="patient.protein_achieved_pct || 0"></meter>
              </div>
            </div>

            <div class="chips">
              <span v-for="tag in compactTags(patient)" :key="tag">{{ tag }}</span>
              <span v-if="patient.open_task_count" class="task-chip">{{ patient.open_task_count }}项</span>
            </div>
          </button>
        </div>
        <div v-else class="soft-empty">当前范围暂无需要营养复核的床位。</div>
      </section>

      <aside class="visual-panel">
        <div class="panel-head compact">
          <div>
            <strong>路径与达标</strong>
            <span>图表点击筛选床卡</span>
          </div>
        </div>
        <div class="route-donut" :style="{ '--en': routePct('EN'), '--pn': routePct('PN'), '--mix': routePct('混合') }">
          <div>
            <strong>{{ stats.patient_count || 0 }}</strong>
            <span>在科</span>
          </div>
        </div>
        <div class="route-buttons">
          <button type="button" @click="riskFilter = 'EN'"><i class="dot en"></i>EN {{ routeCount('EN') }}</button>
          <button type="button" @click="riskFilter = 'PN'"><i class="dot pn"></i>PN {{ routeCount('PN') }}</button>
          <button type="button" @click="riskFilter = '混合'"><i class="dot mix"></i>混合 {{ routeCount('混合') }}</button>
          <button type="button" @click="riskFilter = '未开始'"><i class="dot none"></i>未开始 {{ routeCount('未开始') }}</button>
        </div>

        <div class="mini-chart">
          <div class="chart-head">
            <strong>真实7日达标</strong>
            <span>{{ avgTrend }}%</span>
          </div>
          <div class="bars">
            <span v-for="(bar, idx) in wardTrend" :key="idx" :style="{ height: `${Math.max(8, bar)}%` }"></span>
          </div>
        </div>

        <div class="priority-box">
          <div class="chart-head">
            <strong>今日先做</strong>
            <span>{{ stats.open_task_count || 0 }} 待办</span>
          </div>
          <button v-for="item in priorities" :key="`${item.patient_id}-${item.action}`" type="button" :class="`priority-item tone-${item.tone}`" @click="openById(item.patient_id)">
            <b>{{ item.bed_no }}床</b>
            <span>{{ item.action }}</span>
            <small>{{ item.reason }}</small>
          </button>
          <div v-if="!priorities.length" class="mini-empty">暂无优先事项</div>
        </div>

        <div class="role-strip">
          <button type="button" @click="riskFilter = 'EN不耐受'"><b>{{ roleActions.nurse?.length || 0 }}</b><span>护士</span></button>
          <button type="button" @click="riskFilter = '热量未达标'"><b>{{ roleActions.doctor?.length || 0 }}</b><span>医生</span></button>
          <button type="button" @click="riskFilter = 'high'"><b>{{ roleActions.director?.length || 0 }}</b><span>主任</span></button>
          <button type="button"><b>{{ stats.data_quality_avg || 0 }}%</b><span>质量</span></button>
        </div>
      </aside>
    </section>

    <a-drawer v-model:open="drawerOpen" width="720" :title="drawerPatient ? `${drawerPatient.bed_no}床 ${drawerPatient.name}` : '营养详情'">
      <section v-if="drawerPatient" class="drawer-kpis">
        <article>
          <span>NRS2002</span>
          <strong>{{ drawerPatient.nrs2002 ?? '待评' }}</strong>
        </article>
        <article>
          <span>NUTRIC</span>
          <strong>{{ drawerPatient.nutric ?? '待评' }}</strong>
        </article>
        <article>
          <span>路径</span>
          <strong>{{ drawerPatient.route }}</strong>
        </article>
      </section>

      <section v-if="drawerPatient" class="target-card">
        <div>
          <span>热量</span>
          <strong>{{ drawerPatient.kcal_delivered || 0 }} / {{ drawerPatient.kcal_goal || 0 }} kcal</strong>
          <meter min="0" max="100" :value="drawerPatient.kcal_achieved_pct || 0"></meter>
        </div>
        <div>
          <span>蛋白</span>
          <strong>{{ drawerPatient.protein_delivered || 0 }} / {{ drawerPatient.protein_goal || 0 }} g</strong>
          <meter min="0" max="100" :value="drawerPatient.protein_achieved_pct || 0"></meter>
        </div>
      </section>

      <section v-if="drawerPatient" class="closed-loop-grid">
        <article>
          <span>执行摄入</span>
          <strong>{{ deliverySourceLabel }}</strong>
          <small>{{ drawerPatient.volume_ml_24h || 0 }} ml / 24h</small>
        </article>
        <article :class="`level-${drawerPatient.tolerance?.level || 'unknown'}`">
          <span>EN耐受</span>
          <strong>{{ toleranceText }}</strong>
          <small>{{ drawerPatient.tolerance?.event_count || 0 }} 条记录</small>
        </article>
        <article :class="`level-${drawerPatient.pn_safety?.level || 'unknown'}`">
          <span>PN安全</span>
          <strong>{{ drawerPatient.pn_safety?.needs_review ? '需复核' : '平稳' }}</strong>
          <small>血糖 / TG / 肝胆</small>
        </article>
        <article :class="`level-${drawerPatient.refeeding?.level || 'unknown'}`">
          <span>再喂养</span>
          <strong>{{ levelText(drawerPatient.refeeding?.level) }}</strong>
          <small>P / K / Mg</small>
        </article>
        <article :class="`level-${drawerPatient.glucose_trend?.level || 'unknown'}`">
          <span>血糖</span>
          <strong>{{ glucoseRange }}</strong>
          <small>{{ drawerPatient.glucose_trend?.points?.length || 0 }} 次</small>
        </article>
        <article :class="`level-${drawerPatient.closed_loop?.level || 'unknown'}`">
          <span>闭环</span>
          <strong>{{ drawerPatient.closed_loop?.open || 0 }} 待办</strong>
          <small>{{ drawerPatient.closed_loop?.closed || 0 }} 已完成</small>
        </article>
        <article :class="`level-${drawerPatient.data_quality?.level || 'unknown'}`">
          <span>数据</span>
          <strong>{{ drawerPatient.data_quality?.completeness || 0 }}%</strong>
          <small>{{ qualityMissing }}</small>
        </article>
        <article :class="`level-${drawerPatient.completion?.level || 'unknown'}`">
          <span>完成度</span>
          <strong>{{ drawerPatient.completion?.percent || 0 }}%</strong>
          <small>闭环成熟度</small>
        </article>
      </section>

      <section v-if="drawerPatient" class="prescription-card" :class="`level-${drawerPatient.prescription?.level || 'unknown'}`">
        <div>
          <span>今日差额</span>
          <strong>{{ drawerPatient.prescription?.kcal_gap || 0 }} kcal</strong>
          <small>蛋白 {{ drawerPatient.prescription?.protein_gap || 0 }} g</small>
        </div>
        <div>
          <span>建议路径</span>
          <strong>{{ drawerPatient.prescription?.route || drawerPatient.route }}</strong>
          <small>{{ drawerPatient.prescription?.title || '维持当前' }}</small>
        </div>
        <button
          v-for="item in drawerPatient.prescription?.suggestions || []"
          :key="item.title"
          type="button"
          @click="createTask({ title: item.title, target: item.target, priority: item.priority, task_type: 'nutrition_prescription_gap', payload: item })"
        >
          {{ item.title }}
        </button>
      </section>

      <section v-if="drawerPatient" class="detail-chart-grid">
        <article>
          <div class="chart-head small"><strong>7日热量</strong><span>{{ drawerPatient.kcal_achieved_pct || 0 }}%</span></div>
          <div class="spark-bars">
            <span v-for="item in drawerPatient.trend_7d || []" :key="item.day" :style="{ height: `${Math.max(8, Number(item.pct || 0))}%` }"></span>
          </div>
        </article>
        <article>
          <div class="chart-head small"><strong>血糖波动</strong><span>{{ glucoseRange }}</span></div>
          <div class="glucose-line">
            <i v-for="(point, idx) in glucosePoints" :key="`${point.time}-${idx}`" :style="{ left: `${glucoseX(idx)}%`, bottom: `${glucoseY(Number(point.value || 0))}%` }"></i>
          </div>
        </article>
      </section>

      <a-divider>风险灯</a-divider>
      <div v-if="drawerPatient" class="risk-lights">
        <span v-for="tag in drawerPatient.risk_tags || []" :key="tag" :class="{ hot: isHotTag(tag) }">{{ tag }}</span>
      </div>

      <a-divider>关键化验</a-divider>
      <section v-if="drawerPatient" class="lab-grid">
        <article v-for="lab in labRows" :key="lab.key">
          <span>{{ lab.label }}</span>
          <strong>{{ lab.value }}</strong>
          <small>{{ lab.time }}</small>
        </article>
      </section>

      <a-divider>最近营养医嘱</a-divider>
      <div v-if="drawerPatient" class="order-list">
        <article v-for="order in drawerPatient.orders || []" :key="`${order.name}-${order.time}`">
          <b>{{ order.route }}</b>
          <span>{{ order.name }}</span>
          <small>{{ order.kcal ? `${order.kcal} kcal` : fmt(order.time) }}</small>
        </article>
        <div v-if="!(drawerPatient.orders || []).length" class="soft-empty small">近 72 小时未识别到营养医嘱</div>
      </div>

      <a-divider>任务闭环</a-divider>
      <div v-if="drawerPatient" class="task-list">
        <article v-for="task in drawerPatient.tasks || []" :key="task.task_id" :class="{ closed: task.status !== 'open' }">
          <div>
            <b>{{ task.title }}</b>
            <span>{{ task.payload?.target || task.outcome || '营养任务' }}</span>
          </div>
          <button v-if="task.status === 'open'" type="button" @click="closeTask(task)">完成</button>
          <small v-else>已完成</small>
        </article>
        <div v-if="!(drawerPatient.tasks || []).length" class="soft-empty small">暂无营养任务</div>
      </div>

      <a-divider>下一步</a-divider>
      <div v-if="drawerPatient" class="action-list">
        <button type="button" class="ai-action" :disabled="aiLoading" @click="loadAiAdvice(true)">
          <strong>{{ aiLoading ? 'AI分析中...' : 'AI营养建议' }}</strong>
          <span>1句总评 + 可执行动作</span>
        </button>
        <button v-for="action in drawerPatient.actions || []" :key="action.title" type="button" @click="createTask(action)">
          <strong>{{ action.title }}</strong>
          <span>{{ action.target }}</span>
        </button>
        <button type="button" @click="createTask({ title: '营养会诊复核', target: '营养师/主管医生' })">
          <strong>营养会诊复核</strong>
          <span>生成任务</span>
        </button>
      </div>

      <section v-if="aiAdvice" class="ai-card">
        <div class="ai-card__head">
          <strong>AI营养建议</strong>
          <span>{{ aiAdvice.degraded ? '规则兜底' : aiAdvice.model || 'AI' }}</span>
        </div>
        <p>{{ aiAdvice.summary || aiAdvice.text || '暂无建议' }}</p>
        <div v-if="aiAdvice.text && aiAdvice.text !== aiAdvice.summary" class="ai-text">{{ aiAdvice.text }}</div>
        <div class="ai-advice-list">
          <article v-for="item in aiAdvice.advice || []" :key="item.title">
            <b>{{ item.title }}</b>
            <span>{{ item.detail }}</span>
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
  Divider as ADivider,
  Drawer as ADrawer,
  Input as AInput,
  Select as ASelect,
  Space as ASpace,
  message,
} from 'ant-design-vue'
import { getClinicalAccount, getDepartments } from '../api'
import { closeNutritionTask, getNutritionDashboard, getNutritionPatient, postNutritionAiAdvice, postNutritionTask, type NutritionScopeParams } from '../api/nutrition'
import { formatBeijingTime } from '../utils/time'

const route = useRoute()
const loading = ref(false)
const detailLoading = ref(false)
const keyword = ref('')
const riskFilter = ref('all')
const patients = ref<any[]>([])
const stats = ref<any>({})
const priorities = ref<any[]>([])
const roleActions = ref<any>({})
const drawerOpen = ref(false)
const drawerPatient = ref<any>(null)
const scopeName = ref('')
const aiAdvice = ref<any>(null)
const aiLoading = ref(false)

const riskOptions = [
  { value: 'all', label: '全部床位' },
  { value: 'high', label: '高风险' },
  { value: '未启动', label: '未启动' },
  { value: '热量未达标', label: '热量未达标' },
  { value: '再喂养风险', label: '再喂养风险' },
  { value: 'EN不耐受', label: 'EN不耐受' },
  { value: '血糖风险', label: '血糖风险' },
  { value: 'NRS待评', label: '评分待补' },
  { value: 'EN', label: 'EN' },
  { value: 'PN', label: 'PN' },
  { value: '混合', label: '混合' },
  { value: '未开始', label: '未开始' },
]

const routeDeptCode = computed(() => String(route.query.dept_code || route.query.deptCode || '').trim())
const routeDeptName = computed(() => String(route.query.dept || route.query.department || '').trim())
const routeUserName = computed(() => String(route.query.userName || '').trim())
const scopeLabel = computed(() => scopeName.value || routeDeptName.value || '全部 ICU 在科患者')

const filteredPatients = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  return patients.value.filter((row) => {
    if (riskFilter.value === 'high' && row.risk_level !== 'high') return false
    if (['EN', 'PN', '混合', '未开始'].includes(riskFilter.value) && row.route !== riskFilter.value) return false
    if (!['all', 'high', 'EN', 'PN', '混合', '未开始'].includes(riskFilter.value) && !(row.risk_tags || []).includes(riskFilter.value)) return false
    if (!q) return true
    return [row.bed_no, row.name, row.diagnosis, row.route].some((item) => String(item || '').toLowerCase().includes(q))
  })
})

const kpis = computed(() => [
  { key: 'not-reached', label: '未达标', value: stats.value.not_reached_count || 0, tone: 'warn', filter: '热量未达标' },
  { key: 'refeeding', label: '再喂养', value: stats.value.refeeding_count || 0, tone: 'danger', filter: '再喂养风险' },
  { key: 'not-started', label: '未启动', value: stats.value.not_started_count || 0, tone: 'danger', filter: '未开始' },
  { key: 'pn', label: 'PN复核', value: stats.value.pn_review_count || 0, tone: 'info', filter: 'PN' },
  { key: 'avg', label: '平均达标', value: `${stats.value.avg_kcal_pct || 0}%`, tone: 'stable', filter: 'all' },
])

const wardTrend = computed(() => {
  const rows = patients.value.filter((row) => Array.isArray(row.trend_7d))
  if (!rows.length) return [0, 0, 0, 0, 0, 0, 0]
  return Array.from({ length: 7 }, (_, idx) => {
    const values = rows.map((row) => Number(row.trend_7d?.[idx]?.pct || 0))
    return Math.round(values.reduce((sum, item) => sum + item, 0) / Math.max(1, values.length))
  })
})
const avgTrend = computed(() => Math.round(wardTrend.value.reduce((sum, item) => sum + item, 0) / Math.max(1, wardTrend.value.length)))
const toleranceText = computed(() => {
  const level = drawerPatient.value?.tolerance?.level
  if (level === 'danger') return '中断'
  if (level === 'warn') return '观察'
  if (level === 'stable') return '平稳'
  return '待评'
})
const glucoseRange = computed(() => {
  const trend = drawerPatient.value?.glucose_trend || {}
  if (trend.min == null || trend.max == null) return '待评'
  return `${trend.min}-${trend.max}`
})
const glucosePoints = computed(() => drawerPatient.value?.glucose_trend?.points || [])
const qualityMissing = computed(() => {
  const missing = drawerPatient.value?.data_quality?.missing || []
  return missing.length ? missing.slice(0, 2).join(' / ') : '完整'
})
const deliverySourceLabel = computed(() => {
  const source = String(drawerPatient.value?.delivery_source || '')
  if (/drugExe/i.test(source)) return '实际执行'
  if (source.includes('医嘱')) return '医嘱估算'
  return source || '执行估算'
})

const labRows = computed(() => {
  const labs = drawerPatient.value?.labs || {}
  const map: Array<[string, string]> = [
    ['p', 'P'],
    ['k', 'K'],
    ['mg', 'Mg'],
    ['glucose', '血糖'],
    ['tg', 'TG'],
    ['albumin', '白蛋白'],
    ['prealbumin', '前白蛋白'],
    ['crp', 'CRP'],
  ]
  return map.map(([key, label]) => {
    const lab = labs[key] || {}
    return {
    key,
    label,
    value: lab.value != null ? `${lab.value}${lab.unit ? ` ${lab.unit}` : ''}` : '—',
    time: fmt(lab.time),
  }
  })
})

function fmt(v: any) { return formatBeijingTime(v, '—') }
function routeCount(name: string) { return stats.value.route_counts?.[name] || 0 }
function routePct(name: string) {
  const total = Number(stats.value.patient_count || 0)
  return total ? `${Math.round((routeCount(name) / total) * 100)}%` : '0%'
}
function compactTags(patient: any) {
  const tags = Array.isArray(patient?.risk_tags) ? patient.risk_tags.filter(Boolean) : []
  return tags.length ? tags.slice(0, 3) : ['稳定']
}
function patientTone(patient: any) {
  if (patient?.risk_level === 'high') return 'danger'
  if (patient?.risk_level === 'medium') return 'warn'
  return 'stable'
}
function isHotTag(tag: string) {
  return ['未启动', '再喂养风险', '热量未达标', '蛋白未达标', '血糖风险', '脂肪乳风险', 'EN不耐受'].includes(tag)
}
function levelText(level: string) {
  return ({ danger: '高危', warn: '关注', stable: '平稳', unknown: '待评' } as Record<string, string>)[level || 'unknown'] || '待评'
}
function glucoseX(idx: any) {
  const len = Math.max(1, glucosePoints.value.length - 1)
  return Math.round((Number(idx || 0) / len) * 100)
}
function glucoseY(value: any) {
  const num = Number(value || 0)
  return Math.max(6, Math.min(92, Math.round(((num - 3) / 12) * 100)))
}
function requestParams(): NutritionScopeParams {
  const params: NutritionScopeParams = { patient_scope: 'in_dept' }
  if (routeDeptCode.value) params.dept_code = routeDeptCode.value
  else if (routeDeptName.value) params.dept = routeDeptName.value
  return params
}
async function resolveScopeName() {
  if (routeDeptName.value && !/^\d+$/.test(routeDeptName.value)) {
    scopeName.value = routeDeptName.value
    return
  }
  try {
    if (routeUserName.value) {
      const { data } = await getClinicalAccount({
        userName: routeUserName.value,
        dept_code: routeDeptCode.value || undefined,
        dept: routeDeptName.value || undefined,
      })
      const dept = String(data?.account?.dept || '').trim()
      if (dept && dept !== routeDeptCode.value) {
        scopeName.value = dept
        return
      }
    }
    if (routeDeptCode.value) {
      const { data } = await getDepartments()
      const hit = (data?.departments || []).find((item: any) => String(item.deptCode || '').trim() === routeDeptCode.value)
      scopeName.value = String(hit?.dept || '').trim()
      return
    }
  } catch {
    scopeName.value = ''
  }
}
async function loadAll() {
  loading.value = true
  try {
    await resolveScopeName()
    const { data } = await getNutritionDashboard(requestParams())
    patients.value = data?.patients || []
    stats.value = data?.stats || {}
    priorities.value = data?.priorities || []
    roleActions.value = data?.role_actions || {}
  } finally {
    loading.value = false
  }
  detailLoading.value = true
  try {
    const { data } = await getNutritionDashboard({ ...requestParams(), detail: true })
    patients.value = data?.patients || patients.value
    stats.value = data?.stats || stats.value
    priorities.value = data?.priorities || priorities.value
    roleActions.value = data?.role_actions || roleActions.value
  } finally {
    detailLoading.value = false
  }
}
async function openPatient(row: any) {
  drawerPatient.value = row
  drawerOpen.value = true
  aiAdvice.value = null
  const { data } = await getNutritionPatient(row.patient_id)
  drawerPatient.value = data?.patient || row
}
async function openById(patientId: string) {
  const hit = patients.value.find((item) => item.patient_id === patientId)
  if (hit) {
    await openPatient(hit)
  }
}
async function loadAiAdvice(refresh = false) {
  if (!drawerPatient.value) return
  aiLoading.value = true
  try {
    const { data } = await postNutritionAiAdvice(drawerPatient.value.patient_id, { refresh })
    aiAdvice.value = data?.advice || null
  } finally {
    aiLoading.value = false
  }
}
async function createTask(action: any) {
  if (!drawerPatient.value) return
  const { data } = await postNutritionTask(drawerPatient.value.patient_id, {
    title: action.title,
    target: action.target,
    task_type: action.task_type,
    priority: action.priority || (isHotTag(action.title) ? 'high' : 'medium'),
    payload: action.payload,
    source: '营养支持工作台',
  })
  drawerPatient.value.tasks = [data?.task, ...(drawerPatient.value.tasks || [])].filter(Boolean)
  message.success('已生成营养任务')
}
async function closeTask(task: any) {
  if (!task?.task_id || !drawerPatient.value) return
  const { data } = await closeNutritionTask(task.task_id, { outcome: '已完成' })
  drawerPatient.value.tasks = (drawerPatient.value.tasks || []).map((item: any) => item.task_id === task.task_id ? data?.task || { ...item, status: 'closed' } : item)
  message.success('任务已闭环')
}

watch(() => [route.query.userName, route.query.deptCode, route.query.dept_code, route.query.dept, route.query.department], () => {
  void loadAll()
})

onMounted(loadAll)
</script>

<style scoped>
.nutrition-page {
  min-height: calc(100vh - 76px);
  padding: 18px;
  background:
    radial-gradient(circle at 10% 0%, rgba(34,197,94,.13), transparent 30%),
    radial-gradient(circle at 92% 10%, rgba(251,191,36,.1), transparent 32%);
}
.topbar { display: flex; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
h1 { margin: 0; font-size: 26px; color: #f6fff0; }
p { margin: 6px 0 0; color: #8fa896; }
.search-box { width: 240px; }
.risk-select { width: 150px; }
.scope-strip {
  display: inline-flex;
  margin: 0 0 14px;
  padding: 8px 12px;
  border: 1px solid rgba(134,239,172,.2);
  border-radius: 999px;
  color: #d9f99d;
  background: rgba(20,83,45,.22);
  font-size: 12px;
}
.kpis { display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); gap: 10px; margin-bottom: 14px; }
.kpi {
  border: 1px solid rgba(125,167,214,.16);
  border-radius: 16px;
  padding: 12px;
  background: rgba(10,25,42,.9);
  text-align: left;
  cursor: pointer;
}
.kpi span { color: #93a79b; display: block; }
.kpi strong { font-size: 28px; color: #f7fee7; }
.kpi.tone-danger { border-color: rgba(248,113,113,.32); }
.kpi.tone-warn { border-color: rgba(251,191,36,.3); }
.kpi.tone-info { border-color: rgba(56,189,248,.28); }
.kpi.tone-stable { border-color: rgba(74,222,128,.26); }
.layout {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(340px, .65fr);
  gap: 16px;
  align-items: start;
}
.patient-panel,
.visual-panel {
  border: 1px solid rgba(125,167,214,.16);
  border-radius: 20px;
  padding: 16px;
  background:
    radial-gradient(circle at 100% 0%, rgba(132,204,22,.09), transparent 30%),
    rgba(7,20,34,.92);
}
.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 12px;
  margin-bottom: 14px;
  border-bottom: 1px solid rgba(190,242,100,.12);
}
.panel-head.compact { margin-bottom: 18px; }
.panel-head strong { display: block; color: #f7fee7; font-size: 19px; }
.panel-head span,
.panel-head em { display: block; margin-top: 3px; color: #93a79b; font-size: 12px; font-style: normal; }
.nutrition-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(255px, 1fr)); gap: 12px; }
.nutrition-card {
  display: grid;
  gap: 12px;
  min-height: 178px;
  padding: 14px;
  border: 1px solid rgba(134,239,172,.16);
  border-radius: 18px;
  color: inherit;
  background:
    radial-gradient(circle at 92% 0%, rgba(190,242,100,.14), transparent 34%),
    linear-gradient(145deg, rgba(22,63,38,.82), rgba(7,20,34,.9));
  text-align: left;
  cursor: pointer;
  transition: transform .16s ease, border-color .16s ease;
}
.nutrition-card:hover { transform: translateY(-2px); border-color: rgba(190,242,100,.42); }
.nutrition-card.tone-danger { border-color: rgba(248,113,113,.36); }
.nutrition-card.tone-warn { border-color: rgba(251,191,36,.28); }
.nutrition-card.tone-stable { border-color: rgba(74,222,128,.22); }
.card-top { display: flex; align-items: center; gap: 8px; }
.bed {
  min-width: 58px;
  height: 42px;
  display: grid;
  place-items: center;
  border-radius: 14px;
  color: #10200f;
  background: linear-gradient(135deg, #bef264, #86efac);
  font-size: 16px;
  font-weight: 950;
}
.identity { min-width: 0; display: grid; gap: 2px; }
.identity strong { color: #f7fee7; font-size: 17px; line-height: 1.15; }
.identity small { color: #bbf7d0; font-size: 13px; font-weight: 800; }
.card-top b {
  margin-left: auto;
  min-width: 38px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  color: #d9f99d;
  background: rgba(2,8,20,.38);
  border: 1px solid rgba(190,242,100,.16);
}
.score-strip {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}
.score-strip span {
  padding: 9px;
  border-radius: 12px;
  background: rgba(2,8,20,.28);
  border: 1px solid rgba(190,242,100,.12);
}
.score-strip i,
.score-strip strong { display: block; text-align: center; }
.score-strip i { color: #93a79b; font-style: normal; font-size: 11px; }
.score-strip strong { margin-top: 3px; color: #f7fee7; font-size: 16px; }
.progress-pair { display: grid; gap: 8px; }
.progress-pair label { display: block; margin-bottom: 4px; color: #c9dfc5; font-size: 12px; }
meter {
  width: 100%;
  height: 9px;
  border: 0;
  border-radius: 999px;
  overflow: hidden;
}
meter::-webkit-meter-bar { background: rgba(2,8,20,.34); border: 0; }
meter::-webkit-meter-optimum-value { background: linear-gradient(90deg, #84cc16, #22c55e); }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chips span,
.risk-lights span {
  padding: 5px 8px;
  border: 1px solid rgba(190,242,100,.16);
  border-radius: 999px;
  color: #e7ffd2;
  background: rgba(2,8,20,.28);
  font-size: 12px;
  line-height: 1;
}
.chips .task-chip {
  color: #10200f;
  border-color: transparent;
  background: linear-gradient(135deg, #fef08a, #facc15);
  font-weight: 900;
}
.route-donut {
  width: 220px;
  height: 220px;
  margin: 4px auto 18px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background:
    radial-gradient(circle, rgba(7,20,34,1) 0 55%, transparent 56%),
    conic-gradient(#22c55e 0 var(--en), #38bdf8 var(--en) calc(var(--en) + var(--pn)), #f59e0b calc(var(--en) + var(--pn)) calc(var(--en) + var(--pn) + var(--mix)), rgba(148,163,184,.28) 0);
}
.route-donut strong,
.route-donut span { display: block; text-align: center; }
.route-donut strong { color: #f7fee7; font-size: 38px; }
.route-donut span { color: #93a79b; }
.route-buttons { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-bottom: 16px; }
.route-buttons button {
  padding: 10px;
  border: 1px solid rgba(190,242,100,.14);
  border-radius: 12px;
  color: #e7ffd2;
  background: rgba(2,8,20,.28);
  text-align: left;
  cursor: pointer;
}
.dot { display: inline-block; width: 8px; height: 8px; margin-right: 6px; border-radius: 999px; }
.dot.en { background: #22c55e; }
.dot.pn { background: #38bdf8; }
.dot.mix { background: #f59e0b; }
.dot.none { background: #94a3b8; }
.mini-chart {
  padding: 14px;
  border: 1px solid rgba(190,242,100,.14);
  border-radius: 16px;
  background: rgba(2,8,20,.25);
}
.priority-box {
  display: grid;
  gap: 8px;
  margin-top: 14px;
  padding: 14px;
  border: 1px solid rgba(190,242,100,.14);
  border-radius: 16px;
  background: rgba(2,8,20,.25);
}
.priority-item {
  display: grid;
  grid-template-columns: 54px 1fr auto;
  gap: 8px;
  align-items: center;
  width: 100%;
  border: 1px solid rgba(190,242,100,.12);
  border-radius: 12px;
  padding: 9px;
  color: #e7ffd2;
  background: rgba(7,20,34,.68);
  text-align: left;
  cursor: pointer;
}
.priority-item b {
  display: grid;
  place-items: center;
  height: 32px;
  border-radius: 10px;
  color: #10200f;
  background: #bef264;
}
.priority-item span { color: #f7fee7; font-weight: 900; }
.priority-item small { color: #93a79b; }
.priority-item.tone-danger { border-color: rgba(248,113,113,.34); }
.mini-empty {
  min-height: 58px;
  display: grid;
  place-items: center;
  color: #93a79b;
}
.role-strip {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-top: 12px;
}
.role-strip button {
  padding: 10px 6px;
  border: 1px solid rgba(190,242,100,.14);
  border-radius: 14px;
  color: #e7ffd2;
  background: rgba(2,8,20,.26);
  cursor: pointer;
}
.role-strip b,
.role-strip span { display: block; text-align: center; }
.role-strip b { font-size: 20px; color: #bef264; }
.role-strip span { margin-top: 2px; color: #93a79b; font-size: 12px; }
.chart-head { display: flex; justify-content: space-between; margin-bottom: 12px; color: #e7ffd2; }
.chart-head span { color: #bef264; font-weight: 900; }
.bars { height: 120px; display: flex; align-items: end; gap: 9px; }
.bars span {
  flex: 1;
  min-height: 8px;
  border-radius: 999px 999px 4px 4px;
  background: linear-gradient(180deg, #bef264, #16a34a);
}
.soft-empty {
  min-height: 160px;
  display: grid;
  place-content: center;
  border: 1px dashed rgba(190,242,100,.18);
  border-radius: 16px;
  color: #93a79b;
  text-align: center;
}
.soft-empty.small { min-height: 88px; }
.drawer-kpis,
.lab-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}
.drawer-kpis article,
.lab-grid article,
.target-card {
  padding: 12px;
  border: 1px solid rgba(125,167,214,.16);
  border-radius: 14px;
  background: rgba(2,8,20,.24);
}
.drawer-kpis span,
.lab-grid span,
.target-card span { display: block; color: #93a79b; }
.drawer-kpis strong { color: #f7fee7; font-size: 24px; }
.target-card { display: grid; gap: 12px; margin-top: 12px; }
.target-card strong { display: block; margin: 4px 0 6px; color: #f7fee7; }
.closed-loop-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-top: 12px;
}
.closed-loop-grid article {
  min-height: 96px;
  padding: 12px;
  border: 1px solid rgba(190,242,100,.14);
  border-radius: 16px;
  background: linear-gradient(145deg, rgba(15,45,35,.42), rgba(2,8,20,.22));
}
.closed-loop-grid span,
.closed-loop-grid small { display: block; color: #93a79b; }
.closed-loop-grid strong {
  display: block;
  margin: 7px 0 4px;
  color: #f7fee7;
  font-size: 19px;
}
.closed-loop-grid .level-danger { border-color: rgba(248,113,113,.36); background: rgba(127,29,29,.18); }
.closed-loop-grid .level-warn { border-color: rgba(251,191,36,.32); background: rgba(113,63,18,.18); }
.closed-loop-grid .level-stable { border-color: rgba(74,222,128,.25); }
.prescription-card {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: 10px;
  align-items: stretch;
  margin-top: 10px;
  padding: 12px;
  border: 1px solid rgba(190,242,100,.16);
  border-radius: 18px;
  background:
    radial-gradient(circle at 100% 0%, rgba(56,189,248,.14), transparent 35%),
    rgba(2,8,20,.24);
}
.prescription-card.level-danger { border-color: rgba(248,113,113,.36); background-color: rgba(127,29,29,.14); }
.prescription-card.level-warn { border-color: rgba(251,191,36,.32); background-color: rgba(113,63,18,.14); }
.prescription-card div {
  padding: 10px;
  border-radius: 14px;
  background: rgba(2,8,20,.22);
}
.prescription-card span,
.prescription-card small { display: block; color: #93a79b; }
.prescription-card strong {
  display: block;
  margin: 5px 0 3px;
  color: #f7fee7;
  font-size: 20px;
}
.prescription-card button {
  min-width: 92px;
  border: 0;
  border-radius: 14px;
  color: #10200f;
  background: linear-gradient(135deg, #bef264, #86efac);
  font-weight: 950;
  cursor: pointer;
}
.detail-chart-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-top: 10px;
}
.detail-chart-grid article {
  min-height: 130px;
  padding: 12px;
  border: 1px solid rgba(190,242,100,.14);
  border-radius: 16px;
  background: rgba(2,8,20,.24);
}
.chart-head.small {
  margin-bottom: 10px;
  font-size: 13px;
}
.spark-bars {
  height: 78px;
  display: flex;
  align-items: end;
  gap: 8px;
}
.spark-bars span {
  flex: 1;
  min-height: 8px;
  border-radius: 999px 999px 4px 4px;
  background: linear-gradient(180deg, #bef264, #22c55e);
}
.glucose-line {
  position: relative;
  height: 78px;
  border-radius: 12px;
  background:
    linear-gradient(180deg, transparent 30%, rgba(251,191,36,.18) 31% 60%, transparent 61%),
    rgba(2,8,20,.28);
  overflow: hidden;
}
.glucose-line i {
  position: absolute;
  width: 8px;
  height: 8px;
  margin-left: -4px;
  border-radius: 999px;
  background: #38bdf8;
  box-shadow: 0 0 0 4px rgba(56,189,248,.12);
}
.risk-lights { display: flex; flex-wrap: wrap; gap: 8px; }
.risk-lights span.hot { color: #fee2e2; border-color: rgba(248,113,113,.3); background: rgba(127,29,29,.24); }
.lab-grid { grid-template-columns: repeat(4, 1fr); }
.lab-grid strong { display: block; margin: 4px 0; color: #f7fee7; font-size: 18px; }
.lab-grid small { color: #93a79b; }
.order-list,
.action-list,
.task-list { display: grid; gap: 8px; }
.order-list article,
.action-list button {
  display: grid;
  grid-template-columns: 54px 1fr auto;
  gap: 10px;
  align-items: center;
  padding: 10px;
  border: 1px solid rgba(190,242,100,.14);
  border-radius: 12px;
  background: rgba(2,8,20,.24);
}
.action-list .ai-action {
  border-color: rgba(56,189,248,.28);
  background: linear-gradient(135deg, rgba(14,116,144,.24), rgba(2,8,20,.24));
}
.ai-card {
  display: grid;
  gap: 10px;
  margin-top: 16px;
  padding: 14px;
  border: 1px solid rgba(56,189,248,.22);
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(8,47,73,.22), rgba(2,8,20,.26));
}
.ai-card__head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}
.ai-card__head strong { color: #e0f2fe; }
.ai-card__head span,
.ai-card p,
.ai-text,
.ai-advice-list span { color: #9cc8d7; }
.ai-card p { margin: 0; }
.ai-text {
  white-space: pre-wrap;
  line-height: 1.55;
  font-size: 13px;
}
.ai-advice-list {
  display: grid;
  gap: 8px;
}
.ai-advice-list article {
  padding: 10px;
  border: 1px solid rgba(125,211,252,.14);
  border-radius: 12px;
  background: rgba(2,8,20,.22);
}
.ai-advice-list b {
  display: block;
  margin-bottom: 4px;
  color: #e0f2fe;
}
.order-list b { color: #bef264; }
.order-list span,
.action-list strong { color: #f7fee7; }
.order-list small,
.action-list span { color: #93a79b; }
.action-list button {
  grid-template-columns: 1fr auto;
  text-align: left;
  cursor: pointer;
}
.task-list article {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px;
  border: 1px solid rgba(190,242,100,.14);
  border-radius: 12px;
  background: rgba(2,8,20,.24);
}
.task-list b,
.task-list span { display: block; }
.task-list b { color: #f7fee7; }
.task-list span,
.task-list small { color: #93a79b; }
.task-list button {
  border: 0;
  border-radius: 999px;
  padding: 7px 12px;
  color: #10200f;
  background: linear-gradient(135deg, #bef264, #86efac);
  font-weight: 900;
  cursor: pointer;
}
.task-list article.closed {
  opacity: .68;
  border-color: rgba(148,163,184,.16);
}
@media (max-width: 1100px) {
  .layout,
  .kpis,
  .drawer-kpis,
  .lab-grid,
  .prescription-card,
  .closed-loop-grid { grid-template-columns: 1fr; }
  .topbar { flex-direction: column; }
}

html[data-theme='light'] .nutrition-page {
  background:
    radial-gradient(circle at 10% 0%, rgba(34, 197, 94, 0.08), transparent 30%),
    radial-gradient(circle at 92% 10%, rgba(245, 158, 11, 0.07), transparent 32%),
    #f5f7fa;
}
html[data-theme='light'] h1,
html[data-theme='light'] .kpi strong,
html[data-theme='light'] .panel-head strong,
html[data-theme='light'] .identity strong,
html[data-theme='light'] .score-strip strong,
html[data-theme='light'] .route-donut strong,
html[data-theme='light'] .priority-item span,
html[data-theme='light'] .chart-head,
html[data-theme='light'] .drawer-kpis strong,
html[data-theme='light'] .target-card strong,
html[data-theme='light'] .closed-loop-grid strong,
html[data-theme='light'] .prescription-card strong,
html[data-theme='light'] .lab-grid strong,
html[data-theme='light'] .ai-card__head strong,
html[data-theme='light'] .ai-advice-list b,
html[data-theme='light'] .action-list strong,
html[data-theme='light'] .task-list b,
html[data-theme='light'] .order-list span {
  color: #0f172a;
}
html[data-theme='light'] p,
html[data-theme='light'] .kpi span,
html[data-theme='light'] .panel-head span,
html[data-theme='light'] .panel-head em,
html[data-theme='light'] .identity small,
html[data-theme='light'] .score-strip i,
html[data-theme='light'] .progress-pair label,
html[data-theme='light'] .route-donut span,
html[data-theme='light'] .priority-item small,
html[data-theme='light'] .mini-empty,
html[data-theme='light'] .role-strip span,
html[data-theme='light'] .soft-empty,
html[data-theme='light'] .drawer-kpis span,
html[data-theme='light'] .lab-grid span,
html[data-theme='light'] .lab-grid small,
html[data-theme='light'] .target-card span,
html[data-theme='light'] .closed-loop-grid span,
html[data-theme='light'] .closed-loop-grid small,
html[data-theme='light'] .prescription-card span,
html[data-theme='light'] .prescription-card small,
html[data-theme='light'] .ai-card__head span,
html[data-theme='light'] .ai-card p,
html[data-theme='light'] .ai-text,
html[data-theme='light'] .ai-advice-list span,
html[data-theme='light'] .order-list small,
html[data-theme='light'] .action-list span,
html[data-theme='light'] .task-list span,
html[data-theme='light'] .task-list small {
  color: #64748b;
}
html[data-theme='light'] .scope-strip {
  color: #15803d;
  background: #f0fdf4;
  border-color: rgba(22, 163, 74, 0.18);
}
html[data-theme='light'] .kpi,
html[data-theme='light'] .patient-panel,
html[data-theme='light'] .visual-panel,
html[data-theme='light'] .nutrition-card,
html[data-theme='light'] .score-strip span,
html[data-theme='light'] .route-buttons button,
html[data-theme='light'] .mini-chart,
html[data-theme='light'] .priority-box,
html[data-theme='light'] .priority-item,
html[data-theme='light'] .role-strip button,
html[data-theme='light'] .soft-empty,
html[data-theme='light'] .drawer-kpis article,
html[data-theme='light'] .lab-grid article,
html[data-theme='light'] .target-card,
html[data-theme='light'] .closed-loop-grid article,
html[data-theme='light'] .prescription-card,
html[data-theme='light'] .prescription-card div,
html[data-theme='light'] .detail-chart-grid article,
html[data-theme='light'] .glucose-line,
html[data-theme='light'] .order-list article,
html[data-theme='light'] .action-list button,
html[data-theme='light'] .task-list article,
html[data-theme='light'] .ai-card,
html[data-theme='light'] .ai-advice-list article {
  background: rgba(255, 255, 255, 0.96);
  border-color: rgba(145, 176, 199, 0.32);
  box-shadow: 0 8px 20px rgba(22, 163, 74, 0.05), 0 1px 3px rgba(15, 23, 42, 0.04);
}
html[data-theme='light'] .patient-panel,
html[data-theme='light'] .visual-panel,
html[data-theme='light'] .nutrition-card {
  background:
    radial-gradient(circle at 100% 0%, rgba(34, 197, 94, 0.08), transparent 34%),
    #ffffff;
}
html[data-theme='light'] .route-donut {
  background:
    radial-gradient(circle, #ffffff 0 55%, transparent 56%),
    conic-gradient(#22c55e 0 var(--en), #38bdf8 var(--en) calc(var(--en) + var(--pn)), #f59e0b calc(var(--en) + var(--pn)) calc(var(--en) + var(--pn) + var(--mix)), rgba(148,163,184,.28) 0);
}
html[data-theme='light'] .chips span,
html[data-theme='light'] .risk-lights span {
  color: #15803d;
  background: #f0fdf4;
  border-color: rgba(22, 163, 74, 0.18);
}
html[data-theme='light'] .card-top b,
html[data-theme='light'] .role-strip b,
html[data-theme='light'] .chart-head span,
html[data-theme='light'] .order-list b {
  color: #16a34a;
}
html[data-theme='light'] .card-top b {
  background: #f0fdf4;
  border-color: rgba(22, 163, 74, 0.18);
}
html[data-theme='light'] meter::-webkit-meter-bar {
  background: #e2e8f0;
}
</style>
