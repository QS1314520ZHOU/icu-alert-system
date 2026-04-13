<template>
  <div class="overview">
    <!-- ====== 顶部信息带 ====== -->
    <header class="top-bar">
      <div class="summary-row">
        <div class="sum-block sum-block--total">
          <span class="sum-val">{{ filteredPatients.length }}</span>
          <span class="sum-lbl">在科</span>
        </div>
        <div v-if="refreshing && !loading" class="sum-sync">
          <span class="sum-sync-dot"></span>
          <span>后台同步中</span>
        </div>
        <div class="sum-divider"></div>
        <div class="sum-block sum-block--critical clickable" :class="{ chosen: alertFilter === 'critical' }"
             @click="toggleAlert('critical')">
          <span class="sum-dot dot-crit"></span>
          <span class="sum-val">{{ criticalCount }}</span>
          <span class="sum-lbl">危重</span>
        </div>
        <div class="sum-block sum-block--warning clickable" :class="{ chosen: alertFilter === 'warning' }"
             @click="toggleAlert('warning')">
          <span class="sum-dot dot-warn"></span>
          <span class="sum-val">{{ warningCount }}</span>
          <span class="sum-lbl">警告</span>
        </div>
        <div class="sum-block sum-block--normal clickable" :class="{ chosen: alertFilter === 'normal' }"
             @click="toggleAlert('normal')">
          <span class="sum-dot dot-ok"></span>
          <span class="sum-val">{{ normalCount }}</span>
          <span class="sum-lbl">正常</span>
        </div>
      </div>

      <!-- 科室 -->
      <nav class="dept-nav" v-if="showDeptNav">
        <button v-for="d in deptTabs" :key="d.dept"
                :class="['dept-pill', { active: curDept === d.dept }]"
                @click="selectDept(d.dept)">
          {{ d.label }}
          <i>{{ d.count }}</i>
        </button>
      </nav>

      <!-- 标签快筛 -->
      <div class="tag-chips" v-if="tagStats.length || rescueRiskCount">
        <span
          :class="['chip', 'chip--rescue', { chosen: rescueOnly }]"
          @click="rescueOnly = !rescueOnly"
        >
          🚨 抢救期风险
          <b>{{ rescueRiskCount }}</b>
        </span>
        <span v-for="ts in tagStats" :key="ts.tag"
              :class="['chip', { chosen: tagFilter === ts.tag }]"
              :style="tagFilter === ts.tag ? { background: ts.color + '33', color: ts.color } : {}"
              @click="tagFilter = tagFilter === ts.tag ? '' : ts.tag">
          {{ ts.icon }} {{ ts.label }}
          <b>{{ ts.count }}</b>
        </span>
      </div>

      <div v-if="activeOverviewFilters.length" class="filter-summary">
        <span class="filter-summary__label">当前筛选</span>
        <span v-for="item in activeOverviewFilters" :key="item.key" class="filter-summary__chip">
          {{ item.label }}
        </span>
        <button type="button" class="filter-summary__clear" @click="clearOverviewFilters">
          清空筛选
        </button>
      </div>

      <div class="command-strip">
        <div class="command-pill">
          <span class="command-pill__label">监护范围</span>
          <strong class="command-pill__value">{{ routeDeptDisplayName || curDept || '全科' }}</strong>
        </div>
        <div class="command-pill">
          <span class="command-pill__label">视图模式</span>
          <strong class="command-pill__value">{{ rescueOnly ? '抢救期快筛' : '全量监护' }}</strong>
        </div>
        <div class="command-pill">
          <span class="command-pill__label">活跃筛选</span>
          <strong class="command-pill__value">{{ activeOverviewFilters.length }}</strong>
        </div>
        <div class="command-pill">
          <span class="command-pill__label">刷新节奏</span>
          <strong class="command-pill__value">60s</strong>
        </div>
      </div>
    </header>

    <!-- ====== 加载态 ====== -->
    <div v-if="loading" class="loader">
      <div class="loader-ring"></div>
      <p>正在加载患者数据…</p>
    </div>

    <!-- ====== 风险分区 ====== -->
    <section v-else-if="severitySections.length" class="lane-stack">
      <article
        v-for="lane in severitySections"
        :key="lane.key"
        :class="['lane-panel', `lane-panel--${lane.tone}`]"
      >
        <div class="lane-head">
          <div class="lane-copy">
            <div class="lane-kicker">风险分区</div>
            <div class="lane-title">{{ lane.title }}</div>
            <div class="lane-meta">{{ lane.meta }}</div>
            <div v-if="lane.stats?.length" class="lane-stat-row">
              <span v-for="(item, idx) in lane.stats" :key="`${lane.key}-stat-${idx}`" class="lane-stat-chip">
                {{ item }}
              </span>
            </div>
          </div>
          <div :class="['lane-count', `lane-count--${lane.tone}`]">
            {{ lane.rows.length }} 床
          </div>
        </div>
        <div v-if="lane.featuredRows?.length" :class="['lane-brief', `lane-brief--${lane.tone}`]">
          <span class="lane-brief__label">当前重点</span>
          <div class="lane-brief__list">
            <span v-for="row in lane.featuredRows" :key="`${lane.key}-${row.patient_id}`" class="lane-brief__chip">
              <strong>{{ row.bed || '--' }}床</strong>
              <span>{{ row.name || '未知患者' }}</span>
            </span>
          </div>
        </div>
        <div class="lane-grid">
          <div
            v-for="p in lane.rows"
            :key="p._id"
            class="lane-card-shell"
          >
            <PatientOverviewCard
              :patient="p"
              @select="goDetail"
            />
          </div>
        </div>
      </article>
    </section>

    <div v-else class="overview-empty">
      当前筛选下暂无患者
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getDepartments, getPatients, getPatientVitals, getPatientBundleStatuses, getRecentAlerts } from '../api'
import { onAlertMessage } from '../services/alertSocket'

const OVERVIEW_CACHE_TTL_MS = 60 * 1000
const overviewCache = new Map<string, {
  ts: number
  patients: any[]
  depts: any[]
  curDept: string
}>()

const PatientOverviewCard = defineAsyncComponent(() => import('../components/overview/PatientOverviewCard.vue'))

const router = useRouter()
const route = useRoute()
const loading = ref(true)
const refreshing = ref(false)
const patients = ref<any[]>([])
const depts = ref<any[]>([])
const curDept = ref('全部')
const tagFilter = ref('')
const alertFilter = ref('')
const rescueOnly = ref(false)
let iv: any = null
let offAlert: any = null
let bundleRequestToken = 0

const routeDeptCode = computed(() => {
  const raw = route.query.dept_code || route.query.deptCode
  if (Array.isArray(raw)) return raw[0]?.trim() ?? ''
  if (typeof raw === 'string') return raw.trim()
  return ''
})
const routeDeptName = computed(() => {
  const raw = route.query.dept
  if (Array.isArray(raw)) return raw[0]?.trim() ?? ''
  if (typeof raw === 'string') return raw.trim()
  return ''
})
const routeDeptDisplayName = computed(() => {
  if (routeDeptName.value) return routeDeptName.value
  if (!routeDeptCode.value) return ''
  const hit = depts.value.find((item: any) => String(item?.deptCode || '').trim() === routeDeptCode.value)
  return String(hit?.dept || '').trim()
})
const routeAlertLevel = computed(() => {
  const raw = route.query.alert_level || route.query.alertLevel
  if (Array.isArray(raw)) return raw[0]?.trim() ?? ''
  if (typeof raw === 'string') return raw.trim()
  return ''
})
const routeTag = computed(() => {
  const raw = route.query.tag
  if (Array.isArray(raw)) return raw[0]?.trim() ?? ''
  if (typeof raw === 'string') return raw.trim()
  return ''
})
const routeRescueOnly = computed(() => {
  const raw = route.query.rescue_only || route.query.rescueOnly
  const value = Array.isArray(raw) ? raw[0] : raw
  return String(value || '').toLowerCase() === '1' || String(value || '').toLowerCase() === 'true'
})
const showDeptNav = computed(() => !routeDeptCode.value && !routeDeptName.value)
const overviewCacheKey = computed(() => JSON.stringify({
  dept_code: routeDeptCode.value || '',
  dept: routeDeptName.value || '',
}))

/* ── 科室标签 ── */
const deptTabs = computed(() => {
  const r: Array<{ dept: string; label: string; count: number }> = []
  if (showDeptNav.value) {
    r.push({ dept: '全部', label: '全部', count: patients.value.length })
  }
  depts.value.forEach(d => r.push({
    dept: d.dept,
    label: d.dept.replace('病区', ''),
    count: d.patientCount,
  }))
  return r
})

/* ── 按科室 ── */
const byDept = computed(() =>
  curDept.value === '全部'
    ? patients.value
    : patients.value.filter(p => p.dept === curDept.value)
)

const filteredPatients = computed(() => byDept.value)

/* ── 标签统计 ── */
const tagStats = computed(() => {
  const m: Record<string, any> = {}
  byDept.value.forEach(p =>
    (p.clinicalTags || []).forEach((t: any) => {
      if (!m[t.tag]) m[t.tag] = { ...t, count: 0 }
      m[t.tag].count++
    })
  )
  return Object.values(m).sort((a: any, b: any) => b.count - a.count)
})

const rescueRiskCount = computed(() => byDept.value.filter(p => p.hasRescueRisk).length)
const activeOverviewFilters = computed(() => {
  const items: Array<{ key: string; label: string }> = []
  if (routeDeptDisplayName.value) items.push({ key: 'dept', label: `科室 ${routeDeptDisplayName.value}` })
  else if (routeDeptCode.value) items.push({ key: 'dept', label: '当前科室' })
  if (alertFilter.value === 'critical') items.push({ key: 'alert', label: '危重患者' })
  else if (alertFilter.value === 'warning') items.push({ key: 'alert', label: '警告 / 高危患者' })
  else if (alertFilter.value === 'normal') items.push({ key: 'alert', label: '正常患者' })
  if (tagFilter.value) {
    const hit = tagStats.value.find((t: any) => t.tag === tagFilter.value)
    items.push({ key: 'tag', label: hit?.label ? `标签 ${hit.label}` : `标签 ${tagFilter.value}` })
  }
  if (rescueOnly.value) items.push({ key: 'rescue', label: '抢救期风险' })
  return items
})

/* ── 最终列表 ── */
const showList = computed(() => {
  let ls = byDept.value
  if (rescueOnly.value) ls = ls.filter(p => p.hasRescueRisk)
  if (tagFilter.value) ls = ls.filter(p => (p.clinicalTags || []).some((t: any) => t.tag === tagFilter.value))
  if (alertFilter.value) {
    if (alertFilter.value === 'warning') {
      ls = ls.filter(p => ['warning', 'high'].includes(p.alertLevel))
    } else {
      ls = ls.filter(p => p.alertLevel === alertFilter.value)
    }
  }
  return ls
})

const severitySections = computed(() => {
  const rows = showList.value
  const criticalRows = rows.filter((p: any) => p.alertLevel === 'critical')
  const warningRows = rows.filter((p: any) => ['warning', 'high'].includes(String(p.alertLevel || '')))
  const normalRows = rows.filter((p: any) => !['warning', 'high', 'critical'].includes(String(p.alertLevel || '')))
  const focusRows = (items: any[]) => items
    .slice(0, 3)
    .map((row: any) => ({
      patient_id: String(row?._id || ''),
      bed: String(row?.hisBed || '').trim(),
      name: String(row?.name || '').trim(),
    }))
  return [
    {
      key: 'critical',
      tone: 'critical',
      title: '危急监护区',
      meta: rescueOnly.value ? '优先处理抢救期高危与危急床位。' : '先看最需要立即干预的床位与抢救期风险。',
      stats: [
        `抢救期 ${criticalRows.filter((row: any) => row?.hasRescueRisk).length} 床`,
        '立即处置优先',
      ],
      featuredRows: focusRows(criticalRows),
      rows: criticalRows,
    },
    {
      key: 'warning',
      tone: 'warning',
      title: '预警观察区',
      meta: '聚焦正在恶化或需要尽快复评的患者，便于持续巡查。',
      stats: [
        `待复评 ${warningRows.length} 床`,
        `抢救期 ${warningRows.filter((row: any) => row?.hasRescueRisk).length} 床`,
      ],
      featuredRows: focusRows(warningRows),
      rows: warningRows,
    },
    {
      key: 'normal',
      tone: 'normal',
      title: '稳定监护区',
      meta: '保留基础监护视图，便于快速确认稳定患者的整体负荷。',
      stats: [
        `基础监护 ${normalRows.length} 床`,
        '适合批量巡检',
      ],
      featuredRows: focusRows(normalRows),
      rows: normalRows,
    },
  ].filter((section) => section.rows.length > 0)
})

/* ── 统计 ── */
const criticalCount = computed(() => byDept.value.filter(p => p.alertLevel === 'critical').length)
const warningCount = computed(() => byDept.value.filter(p => ['warning', 'high'].includes(p.alertLevel)).length)
// 没有预警的也算“正常”，避免全部为0
const normalCount = computed(() =>
  byDept.value.filter(p => !['warning', 'high', 'critical'].includes(p.alertLevel)).length
)

/* ── toggle ── */
function toggleAlert(a: string) { alertFilter.value = alertFilter.value === a ? '' : a }

function syncOverviewQuery() {
  const nextQuery: Record<string, any> = { ...route.query }
  if (alertFilter.value) nextQuery.alert_level = alertFilter.value
  else delete nextQuery.alert_level
  if (tagFilter.value) nextQuery.tag = tagFilter.value
  else delete nextQuery.tag
  if (rescueOnly.value) nextQuery.rescue_only = '1'
  else delete nextQuery.rescue_only
  router.replace({ query: nextQuery })
}

function syncDeptQuery(dept: string) {
  const nextQuery: Record<string, any> = { ...route.query }
  if (!dept || dept === '全部') {
    delete nextQuery.dept_code
    delete nextQuery.dept
  } else {
    const hit = depts.value.find((d: any) => d.dept === dept)
    if (hit?.deptCode) {
      nextQuery.dept_code = hit.deptCode
      delete nextQuery.dept
    } else {
      nextQuery.dept = dept
      delete nextQuery.dept_code
    }
  }
  router.replace({ query: nextQuery })
}

function selectDept(dept: string) {
  curDept.value = dept
  alertFilter.value = ''
  tagFilter.value = ''
  rescueOnly.value = false
  if (showDeptNav.value) syncDeptQuery(dept)
}

function goDetail(id: string) {
  router.push({ path: `/patient/${id}`, query: route.query })
}

function clearOverviewFilters() {
  tagFilter.value = ''
  alertFilter.value = ''
  rescueOnly.value = false
  router.replace({
    query: {
      ...(routeDeptCode.value ? { dept_code: routeDeptCode.value } : {}),
      ...(!routeDeptCode.value && routeDeptName.value ? { dept: routeDeptName.value } : {}),
    },
  })
}

/* ── 阈值 ── */
function vc(k: string, v: any): string {
  if (v == null || v === '') return ''
  const n = Number(v)
  if (isNaN(n)) return ''
  const T: Record<string, [number, number, number, number]> = {
    hr: [40, 50, 110, 130], spo2: [85, 92, 999, 999],
    sys: [70, 85, 160, 200], temp: [34, 35.5, 38.5, 40],
    rr: [6, 10, 25, 35],
  }
  const t = T[k]; if (!t) return ''
  const [critLow, warnLow, warnHigh, critHigh] = t
  if (n < critLow || n > critHigh) return 'crit'
  if (n < warnLow || n > warnHigh) return 'warn'
  return 'ok'
}

function calcLevel(v: any): string {
  if (!v?.source) return 'none'
  const cs = ['hr', 'spo2', 'sys', 'temp', 'rr'].map(k =>
    vc(k, k === 'sys' ? v.nibp_sys : v[k])
  )
  if (cs.includes('crit')) return 'critical'
  if (cs.includes('warn')) return 'warning'
  return 'normal'
}

function severityPriority(level: string) {
  const p: Record<string, number> = { none: 0, normal: 1, warning: 2, high: 3, critical: 4 }
  return p[level] ?? 0
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

function mergeAlertLevel(p: any, computed: string) {
  const holdUntil = p.alertHoldUntil || 0
  if (holdUntil > Date.now()) {
    if (severityPriority(p.alertLevel || 'none') >= severityPriority(computed)) {
      return p.alertLevel
    }
  }
  return computed
}

function applyAlert(alert: any) {
  const pid = String(alert?.patient_id || '')
  if (!pid) return
  const target = patients.value.find(p => String(p._id) === pid)
  if (!target) return
  const sev = String(alert?.severity || 'warning')
  if (severityPriority(sev) >= severityPriority(target.alertLevel || 'none')) {
    target.alertLevel = sev
  }
  if (isRescueRiskAlert(alert)) {
    target.hasRescueRisk = true
    target.rescueRiskSeverity = sev
  }
  target.alertHoldUntil = Date.now() + 30 * 60 * 1000
  target.alertFlash = true
  window.setTimeout(() => { target.alertFlash = false }, 15000)
}

function chunkItems<T>(items: T[], size: number): T[][] {
  const chunks: T[][] = []
  for (let i = 0; i < items.length; i += size) {
    chunks.push(items.slice(i, i + size))
  }
  return chunks
}

function syncOverviewCacheSnapshot() {
  overviewCache.set(overviewCacheKey.value, {
    ts: Date.now(),
    patients: patients.value.map((p: any) => ({ ...p })),
    depts: depts.value.map((d: any) => ({ ...d })),
    curDept: curDept.value,
  })
}

async function hydrateBundleStatuses(items: any[]) {
  const token = ++bundleRequestToken
  const targetItems = items
    .filter((item: any) => item && item._id)
    .slice(0, 120)

  for (const item of targetItems) {
    item.bundleStatus = item.bundleStatus || { lights: {} }
  }

  for (const batch of chunkItems(targetItems, 24)) {
    if (token !== bundleRequestToken) return
    try {
      const statusRes = await getPatientBundleStatuses(batch.map((item: any) => item._id))
      if (token !== bundleRequestToken) return
      const statuses = statusRes.data?.statuses || {}
      for (const item of batch) {
        item.bundleStatus = statuses[String(item._id)] || item.bundleStatus || { lights: {} }
      }
      syncOverviewCacheSnapshot()
    } catch {
      for (const item of batch) {
        item.bundleStatus = item.bundleStatus || { lights: {} }
      }
    }
  }
}

/* ── fmt ── */
/* ── 数据加载 ── */
async function load(options?: { silent?: boolean }) {
  const silent = !!options?.silent
  const cacheKey = overviewCacheKey.value
  const cached = overviewCache.get(cacheKey)
  const cacheFresh = !!cached && (Date.now() - cached.ts < OVERVIEW_CACHE_TTL_MS)
  if (!silent && cacheFresh) {
    patients.value = cached!.patients.map((p: any) => ({ ...p }))
    depts.value = cached!.depts.map((d: any) => ({ ...d }))
    curDept.value = cached!.curDept
    loading.value = false
    refreshing.value = true
  } else if (silent) {
    refreshing.value = true
  } else {
    loading.value = true
  }
  try {
    const deptCode = routeDeptCode.value
    const deptName = routeDeptName.value
    const params = deptCode
      ? { dept_code: deptCode, patient_scope: 'in_dept' as const }
      : deptName
        ? { dept: deptName, patient_scope: 'in_dept' as const }
        : { patient_scope: 'in_dept' as const }

    const [dr, pr, recentAlertRes] = await Promise.all([
      getDepartments(),
      getPatients(params),
      getRecentAlerts(200, params).catch(() => ({ data: { records: [] } })),
    ])
    const allDepts = dr.data.departments || []
    const ls = pr.data.patients || []
    const recentAlerts = recentAlertRes.data?.records || []
    const rescueSeverityMap = new Map<string, string>()
    const rescuePidSet = new Set(
      recentAlerts
        .filter((alert: any) => isRescueRiskAlert(alert))
        .map((alert: any) => {
          const pid = String(alert?.patient_id || '')
          const sev = String(alert?.severity || 'warning').toLowerCase()
          if (pid && severityPriority(sev) > severityPriority(rescueSeverityMap.get(pid) || 'none')) {
            rescueSeverityMap.set(pid, sev)
          }
          return pid
        })
        .filter(Boolean)
    )

    if (deptCode) {
      depts.value = allDepts.filter((d: any) => d.deptCode === deptCode)
      if (depts.value.length) curDept.value = depts.value[0].dept
      else if (ls.length) curDept.value = ls[0].dept
      else curDept.value = '全部'
    } else if (deptName) {
      depts.value = allDepts.filter((d: any) => d.dept === deptName)
      if (depts.value.length) curDept.value = deptName
      else if (ls.length) curDept.value = ls[0].dept
      else curDept.value = '全部'
    } else {
      depts.value = allDepts
      if (!depts.value.some((d: any) => d.dept === curDept.value)) {
        curDept.value = '全部'
      }
    }

    const head = ls.slice(0, 100)
    const tail = ls.slice(100).map((p: any) => ({
      ...p,
      vitals: {},
      alertLevel: rescueSeverityMap.get(String(p._id)) || 'none',
      hasRescueRisk: rescuePidSet.has(String(p._id)),
      rescueRiskSeverity: rescueSeverityMap.get(String(p._id)) || 'none',
    }))

    const done = await Promise.all(head.map(async (p: any) => {
      try { p.vitals = (await getPatientVitals(p._id)).data.vitals || {} }
      catch { p.vitals = {} }
      p.alertLevel = mergeAlertLevel(p, calcLevel(p.vitals))
      const rescueSeverity = rescueSeverityMap.get(String(p._id)) || 'none'
      if (severityPriority(rescueSeverity) > severityPriority(p.alertLevel || 'none')) {
        p.alertLevel = rescueSeverity
      }
      p.hasRescueRisk = rescuePidSet.has(String(p._id))
      p.rescueRiskSeverity = rescueSeverity
      return p
    }))

    const ord: Record<string, number> = { critical: 0, warning: 1, none: 2, normal: 3 }
    const all = [...done, ...tail].sort((a, b) => {
      const d = (ord[a.alertLevel] ?? 9) - (ord[b.alertLevel] ?? 9)
      return d || String(a.hisBed).localeCompare(String(b.hisBed), undefined, { numeric: true })
    })
    for (const item of all) {
      item.bundleStatus = item.bundleStatus || { lights: {} }
    }
    patients.value = all
    syncOverviewCacheSnapshot()
    void hydrateBundleStatuses(all)
  } catch (e) { console.error(e) }
  finally {
    refreshing.value = false
    loading.value = false
  }
}

watch(
  () => [routeDeptCode.value, routeDeptName.value],
  () => {
    tagFilter.value = routeTag.value
    alertFilter.value = routeAlertLevel.value
    rescueOnly.value = routeRescueOnly.value
    load()
  },
  { immediate: true }
)

watch([alertFilter, tagFilter, rescueOnly], () => {
  syncOverviewQuery()
})

onMounted(() => { iv = setInterval(() => load({ silent: true }), 60000) })
onMounted(() => {
  offAlert = onAlertMessage(msg => {
    if (msg?.type === 'alert') applyAlert(msg.data)
  })
})
onUnmounted(() => {
  clearInterval(iv)
  if (offAlert) offAlert()
})
</script>

<style scoped>
@import url('../assets/fonts/rajdhani/rajdhani.css');

.overview { 
  position: relative;
  isolation: isolate;
  background:
    radial-gradient(circle at top, rgba(34, 211, 238, 0.12) 0%, rgba(34, 211, 238, 0) 28%),
    linear-gradient(180deg, #06111d 0%, #040b14 100%);
  padding: 22px 24px 28px;
  min-height: 100%; 
  color: #d8f6ff;
  font-family: var(--app-display-font);
}
.overview::before,
.overview::after {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.overview::before {
  background:
    linear-gradient(rgba(73, 196, 255, 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(73, 196, 255, 0.05) 1px, transparent 1px);
  background-size: 28px 28px;
  opacity: 0.28;
  z-index: -2;
}
.overview::after {
  background: linear-gradient(180deg, rgba(19, 41, 64, 0.16), rgba(19, 41, 64, 0));
  z-index: -1;
}

.top-bar {
  margin-bottom: 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid rgba(80, 199, 255, 0.18);
  background: linear-gradient(180deg, rgba(9, 22, 36, 0.92) 0%, rgba(6, 15, 27, 0.9) 100%);
  box-shadow: inset 0 1px 0 rgba(145, 228, 255, 0.08), 0 10px 28px rgba(0, 0, 0, 0.22);
  clip-path: polygon(0 12px, 12px 0, calc(100% - 12px) 0, 100% 12px, 100% calc(100% - 12px), calc(100% - 12px) 100%, 12px 100%, 0 calc(100% - 12px));
}
.summary-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}
.sum-block {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 46px;
  padding: 10px 14px;
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(10, 29, 47, 0.94) 0%, rgba(8, 21, 34, 0.94) 100%);
  border: 1px solid rgba(70, 193, 255, 0.16);
  box-shadow: inset 0 1px 0 rgba(145, 228, 255, 0.06), 0 8px 18px rgba(0, 0, 0, 0.18);
  transition: all 0.2s;
  clip-path: polygon(0 8px, 8px 0, calc(100% - 8px) 0, 100% 8px, 100% calc(100% - 8px), calc(100% - 8px) 100%, 8px 100%, 0 calc(100% - 8px));
}
.sum-block.clickable { cursor: pointer; }
.sum-block.clickable:hover {
  transform: translateY(-2px);
  border-color: rgba(72, 225, 255, 0.28);
  box-shadow: inset 0 1px 0 rgba(145, 228, 255, 0.08), 0 0 18px rgba(34, 211, 238, 0.12);
}
.sum-block.chosen {
  background: linear-gradient(180deg, rgba(15, 54, 80, 0.96) 0%, rgba(8, 29, 48, 0.94) 100%);
  border-color: rgba(86, 229, 255, 0.34);
}
.sum-val {
  font-size: 24px;
  font-weight: 700;
  color: #e0fbff;
  font-variant-numeric: tabular-nums;
  text-shadow: 0 0 10px rgba(34, 211, 238, 0.18);
}
.sum-lbl {
  font-size: 12px;
  color: #6ee7f9;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.sum-dot { width: 10px; height: 10px; border-radius: 50%; }
.dot-crit { background: #fb5a7a; box-shadow: 0 0 12px rgba(251, 90, 122, 0.52); animation: blink 1.2s infinite; }
.dot-warn { background: #ffbf3c; box-shadow: 0 0 12px rgba(255, 191, 60, 0.44); }
.dot-ok { background: #3ee7c0; box-shadow: 0 0 12px rgba(62, 231, 192, 0.44); }
.sum-divider { width: 1px; height: 28px; background: rgba(72, 193, 255, 0.16); margin: 0 2px; }
.sum-sync {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba(80, 199, 255, 0.14);
  background: rgba(8, 28, 44, 0.72);
  color: #8fe0f2;
  font-size: 12px;
  font-weight: 600;
}
.sum-sync-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #3ee7c0;
  box-shadow: 0 0 12px rgba(62, 231, 192, 0.46);
  animation: blink 1.1s infinite;
}
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.25} }

.dept-nav { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 2px; }
.dept-pill {
  background: rgba(8, 25, 40, 0.82);
  border: 1px solid rgba(72, 193, 255, 0.14);
  border-radius: 999px;
  padding: 6px 14px;
  color: #8dd9ee;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap; transition: all 0.2s;
  font-weight: 600;
}
.dept-pill i { font-style: normal; font-size: 11px; opacity: 0.8; margin-left: 6px; font-weight: 700; color: #d9fbff; }
.dept-pill:hover {
  color: #d9fbff;
  border-color: rgba(86, 229, 255, 0.28);
  background: rgba(11, 36, 56, 0.94);
}
.dept-pill.active {
  background: linear-gradient(180deg, rgba(9, 129, 170, 0.94) 0%, rgba(10, 79, 124, 0.98) 100%);
  border-color: rgba(129, 248, 255, 0.38);
  color: #ecfeff;
  box-shadow: 0 0 18px rgba(34, 211, 238, 0.14);
}
.dept-pill.active i { opacity: 0.8; }

.tag-chips { display: flex; gap: 8px; flex-wrap: wrap; }
.chip {
  font-size: 12px; padding: 6px 10px; border-radius: 10px;
  background: rgba(9, 24, 39, 0.82);
  color: #8dcde0;
  cursor: pointer;
  border: 1px solid rgba(72, 193, 255, 0.14);
  transition: all 0.15s;
  white-space: nowrap;
  font-weight: 600;
}
.chip:hover { background: rgba(11, 36, 56, 0.94); border-color: rgba(86, 229, 255, 0.24); }
.chip.chosen {
  border-color: currentColor;
  box-shadow: 0 0 16px rgba(34, 211, 238, 0.08) inset;
}
.chip b { font-weight: 700; margin-left: 3px; }
.chip--rescue {
  color: #ffb4c1;
  border-color: rgba(251, 113, 133, 0.2);
  background: linear-gradient(180deg, rgba(53, 15, 28, 0.9) 0%, rgba(31, 11, 18, 0.92) 100%);
}
.chip--rescue:hover {
  background: linear-gradient(180deg, rgba(76, 19, 37, 0.94) 0%, rgba(41, 12, 22, 0.96) 100%);
  border-color: rgba(251, 113, 133, 0.28);
}
.chip--rescue.chosen {
  color: #ffe6eb;
  border-color: rgba(251, 113, 133, 0.4);
  box-shadow: inset 0 0 18px rgba(251, 113, 133, 0.16), 0 0 18px rgba(251, 113, 133, 0.08);
}

.filter-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.filter-summary__label {
  color: #7fd7eb;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.filter-summary__chip {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba(86, 229, 255, 0.18);
  background: rgba(8, 28, 44, 0.74);
  color: #dffbff;
  font-size: 12px;
}

.filter-summary__clear {
  min-height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba(251, 113, 133, 0.24);
  background: rgba(45, 14, 24, 0.82);
  color: #ffc8d4;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.18s ease;
}

.filter-summary__clear:hover {
  border-color: rgba(251, 113, 133, 0.34);
  color: #ffe8ee;
}
.command-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.command-pill {
  display: grid;
  gap: 3px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(80, 199, 255, 0.14);
  background: rgba(8, 28, 44, 0.66);
}
.command-pill__label {
  color: #7fd7eb;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.command-pill__value {
  color: #ecfeff;
  font-size: 14px;
  line-height: 1.35;
  font-weight: 800;
}

.loader {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 50vh;
  color: #7ed6e8;
  gap: 14px;
  font-family: var(--app-display-font);
}
.loader-ring {
  width: 36px; height: 36px; border: 3px solid rgba(72, 193, 255, 0.14);
  border-top-color: #3ee7c0; border-radius: 50%;
  animation: spin .7s linear infinite;
  box-shadow: 0 0 18px rgba(62, 231, 192, 0.14);
}
@keyframes spin { to { transform: rotate(360deg) } }

.lane-stack {
  display: grid;
  gap: 18px;
}
.lane-panel {
  position: relative;
  display: grid;
  gap: 12px;
  padding: 14px 16px 16px;
  border-radius: 16px;
  border: 1px solid rgba(80, 199, 255, 0.14);
  background:
    radial-gradient(circle at top right, rgba(34, 211, 238, 0.05), rgba(34, 211, 238, 0) 24%),
    linear-gradient(180deg, rgba(9, 22, 36, 0.88) 0%, rgba(6, 15, 27, 0.9) 100%);
  box-shadow: inset 0 1px 0 rgba(145, 228, 255, 0.05), 0 10px 24px rgba(0, 0, 0, 0.18);
}
.lane-panel::before {
  content: '';
  position: absolute;
  inset: 0 0 auto 0;
  height: 3px;
  border-radius: 16px 16px 0 0;
  background: linear-gradient(180deg, #38bdf8 0%, #0ea5e9 100%);
}
.lane-panel--critical::before { background: linear-gradient(180deg, #fb7185 0%, #ef4444 100%); }
.lane-panel--warning::before { background: linear-gradient(180deg, #fbbf24 0%, #f59e0b 100%); }
.lane-panel--normal::before { background: linear-gradient(180deg, #34d399 0%, #10b981 100%); }
.lane-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.lane-copy {
  display: grid;
  gap: 4px;
}
.lane-kicker {
  color: #7fd7eb;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}
.lane-title {
  color: #eafcff;
  font-size: 18px;
  font-weight: 800;
  letter-spacing: 0.02em;
}
.lane-meta {
  color: #8eb3bc;
  font-size: 12px;
  line-height: 1.55;
}
.lane-stat-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 2px;
}
.lane-stat-chip {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 9px;
  border-radius: 999px;
  border: 1px solid rgba(80, 199, 255, 0.12);
  background: rgba(8, 28, 44, 0.64);
  color: #cfefff;
  font-size: 10px;
  font-weight: 700;
}
.lane-count {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(8, 28, 44, 0.72);
  border: 1px solid rgba(80, 199, 255, 0.14);
  color: #dffbff;
  font-size: 12px;
  font-weight: 800;
}
.lane-count--critical {
  background: rgba(71, 16, 28, 0.16);
  border-color: rgba(248, 113, 113, 0.24);
  color: #fecdd3;
}
.lane-count--warning {
  background: rgba(76, 43, 12, 0.16);
  border-color: rgba(251, 191, 36, 0.22);
  color: #fde68a;
}
.lane-count--normal {
  background: rgba(7, 63, 55, 0.14);
  border-color: rgba(74, 222, 128, 0.2);
  color: #a7f3d0;
}
.lane-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
}
.lane-card-shell {
  position: relative;
}
.lane-brief {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 9px 12px;
  border-radius: 12px;
  border: 1px solid rgba(80, 199, 255, 0.12);
  background: rgba(8, 28, 44, 0.5);
}
.lane-brief__label {
  color: #7fd7eb;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  flex: 0 0 auto;
}
.lane-brief__text {
  color: #ecfeff;
  font-size: 13px;
  line-height: 1.45;
}
.lane-brief__list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.lane-brief__chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba(80, 199, 255, 0.12);
  background: rgba(8, 28, 44, 0.76);
  color: #dffbff;
  font-size: 12px;
}
.lane-brief__chip strong {
  color: #ecfeff;
  font-size: 12px;
}
.overview-empty {
  min-height: 220px;
  display: grid;
  place-items: center;
  border: 1px dashed rgba(80, 199, 255, 0.18);
  border-radius: 18px;
  color: #8eb3bc;
  background: rgba(8, 28, 44, 0.32);
  font-size: 14px;
  font-weight: 600;
}
html[data-theme='light'] .overview {
  background:
    radial-gradient(circle at top left, rgba(59, 130, 246, 0.16) 0%, rgba(59, 130, 246, 0) 24%),
    radial-gradient(circle at top right, rgba(14, 165, 233, 0.08) 0%, rgba(14, 165, 233, 0) 22%),
    linear-gradient(180deg, #f4f8fd 0%, #eef4fb 100%);
  color: #0F172A;
}
html[data-theme='light'] .overview::before {
  display: block;
  background:
    linear-gradient(rgba(37, 99, 235, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(37, 99, 235, 0.035) 1px, transparent 1px);
  background-size: 30px 30px;
  opacity: 0.35;
}
html[data-theme='light'] .overview::after {
  display: block;
  background: linear-gradient(180deg, rgba(148, 163, 184, 0.04), rgba(148, 163, 184, 0));
}
html[data-theme='light'] .top-bar {
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 16px;
  clip-path: none;
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.1), rgba(59, 130, 246, 0) 26%),
    linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(247,250,255,.98) 100%);
  box-shadow: 0 12px 28px rgba(37, 99, 235, 0.08);
}
html[data-theme='light'] .top-bar::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 5px;
  background: linear-gradient(180deg, #2563EB 0%, #38BDF8 100%);
}
html[data-theme='light'] .sum-block {
  clip-path: none;
  background:
    linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(248,250,253,.98) 100%);
  border-color: rgba(148, 163, 184, 0.2);
  border-radius: 12px;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.05);
}
html[data-theme='light'] .sum-block--total {
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.12), rgba(59, 130, 246, 0) 34%),
    linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(239,246,255,.98) 100%);
  border-color: rgba(59, 130, 246, 0.2);
}
html[data-theme='light'] .sum-block--critical {
  background:
    radial-gradient(circle at top right, rgba(248, 113, 113, 0.14), rgba(248, 113, 113, 0) 34%),
    linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(255,241,242,.98) 100%);
  border-color: rgba(248, 113, 113, 0.22);
}
html[data-theme='light'] .sum-block--warning {
  background:
    radial-gradient(circle at top right, rgba(245, 158, 11, 0.14), rgba(245, 158, 11, 0) 34%),
    linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(255,247,237,.98) 100%);
  border-color: rgba(245, 158, 11, 0.2);
}
html[data-theme='light'] .sum-block--normal {
  background:
    radial-gradient(circle at top right, rgba(16, 185, 129, 0.12), rgba(16, 185, 129, 0) 34%),
    linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(240,253,244,.98) 100%);
  border-color: rgba(74, 222, 128, 0.2);
}
html[data-theme='light'] .sum-block.clickable:hover {
  border-color: rgba(37, 99, 235, 0.24);
  background: linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(239,246,255,.98) 100%);
  box-shadow: 0 12px 24px rgba(37, 99, 235, 0.1);
}
html[data-theme='light'] .sum-block.chosen {
  background: linear-gradient(180deg, rgba(239,246,255,.98) 0%, rgba(219,234,254,.98) 100%);
  border-color: rgba(37, 99, 235, 0.28);
  box-shadow: 0 12px 24px rgba(37, 99, 235, 0.12);
}
html[data-theme='light'] .sum-val { color: #16324f; text-shadow: none; }
html[data-theme='light'] .sum-lbl { color: #556b86; letter-spacing: .02em; text-transform: none; }
html[data-theme='light'] .sum-block--total .sum-val,
html[data-theme='light'] .sum-block--total .sum-lbl {
  color: #1d4ed8;
}
html[data-theme='light'] .sum-block--critical .sum-val,
html[data-theme='light'] .sum-block--critical .sum-lbl {
  color: #dc2626;
}
html[data-theme='light'] .sum-block--warning .sum-val,
html[data-theme='light'] .sum-block--warning .sum-lbl {
  color: #d97706;
}
html[data-theme='light'] .sum-block--normal .sum-val,
html[data-theme='light'] .sum-block--normal .sum-lbl {
  color: #059669;
}
html[data-theme='light'] .sum-divider { background: rgba(0,0,0,0.06); }
html[data-theme='light'] .sum-sync {
  border-color: rgba(59, 130, 246, 0.16);
  background: rgba(239, 246, 255, 0.98);
  color: #1d4ed8;
}
html[data-theme='light'] .dept-pill {
  background: rgba(255,255,255,.98);
  border-color: rgba(148, 163, 184, 0.18);
  color: #556b86;
}
html[data-theme='light'] .dept-pill i { color: #16324f; }
html[data-theme='light'] .dept-pill:hover {
  color: #16324f;
  border-color: rgba(37, 99, 235, 0.2);
  background: rgba(239,246,255,.98);
}
html[data-theme='light'] .dept-pill.active {
  background: linear-gradient(180deg, rgba(239,246,255,.98) 0%, rgba(219,234,254,.98) 100%);
  color: #2563EB;
  border-color: rgba(37, 99, 235, 0.28);
  box-shadow: 0 10px 20px rgba(37, 99, 235, 0.12);
}
html[data-theme='light'] .chip {
  background: rgba(255,255,255,.98);
  border-color: rgba(148, 163, 184, 0.16);
  color: #556b86;
}
html[data-theme='light'] .chip:hover {
  background: rgba(239,246,255,.98);
  border-color: rgba(59, 130, 246, 0.18);
}
html[data-theme='light'] .chip.chosen {
  background: linear-gradient(180deg, rgba(239,246,255,.98) 0%, rgba(219,234,254,.98) 100%) !important;
  border-color: rgba(37, 99, 235, 0.28);
  color: #2563EB !important;
  box-shadow: 0 10px 18px rgba(37, 99, 235, 0.12);
}
html[data-theme='light'] .chip--rescue {
  color: #dc2626;
  border-color: rgba(248, 113, 113, 0.28);
  background: linear-gradient(180deg, rgba(254,242,242,.98) 0%, rgba(255,241,242,.98) 100%);
}
html[data-theme='light'] .chip--rescue.chosen {
  color: #be123c !important;
  border-color: rgba(244, 63, 94, 0.3);
  background: linear-gradient(180deg, rgba(255,241,242,.99) 0%, rgba(254,226,226,.99) 100%) !important;
  box-shadow: 0 10px 18px rgba(244, 63, 94, 0.1);
}
html[data-theme='light'] .filter-summary__label { color: #4f6782; }
html[data-theme='light'] .filter-summary__chip {
  border-color: rgba(148, 163, 184, 0.18);
  background: rgba(248,250,252,.98);
  color: #425a74;
}
html[data-theme='light'] .filter-summary__clear {
  border-color: rgba(37, 99, 235, 0.24);
  background: linear-gradient(180deg, rgba(239,246,255,.98) 0%, rgba(219,234,254,.98) 100%);
  color: #2563EB;
}
html[data-theme='light'] .command-pill {
  border-color: rgba(148, 163, 184, 0.18);
  background: linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(244,248,253,.98) 100%);
}
html[data-theme='light'] .command-pill__label {
  color: #5f738b;
}
html[data-theme='light'] .command-pill__value {
  color: #16324f;
}
html[data-theme='light'] .loader { color: #64748B; }
html[data-theme='light'] .loader-ring {
  border-color: rgba(0,0,0,0.06);
  border-top-color: #2563EB;
  box-shadow: none;
}
html[data-theme='light'] .lane-panel {
  border-color: rgba(148, 163, 184, 0.2);
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.06), rgba(59, 130, 246, 0) 24%),
    linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(246,249,253,.99) 100%);
  box-shadow: 0 12px 24px rgba(37, 99, 235, 0.06);
}
html[data-theme='light'] .lane-panel--critical {
  border-color: rgba(248, 113, 113, 0.24);
  background:
    radial-gradient(circle at top right, rgba(248, 113, 113, 0.08), rgba(248, 113, 113, 0) 24%),
    linear-gradient(180deg, rgba(255,255,255,.99) 0%, rgba(255,248,249,.99) 100%);
}
html[data-theme='light'] .lane-panel--warning {
  border-color: rgba(245, 158, 11, 0.22);
  background:
    radial-gradient(circle at top right, rgba(245, 158, 11, 0.08), rgba(245, 158, 11, 0) 24%),
    linear-gradient(180deg, rgba(255,255,255,.99) 0%, rgba(255,251,243,.99) 100%);
}
html[data-theme='light'] .lane-panel--normal {
  border-color: rgba(74, 222, 128, 0.22);
  background:
    radial-gradient(circle at top right, rgba(34, 197, 94, 0.08), rgba(34, 197, 94, 0) 24%),
    linear-gradient(180deg, rgba(255,255,255,.99) 0%, rgba(247,252,249,.99) 100%);
}
html[data-theme='light'] .lane-kicker {
  color: #5f738b;
}
html[data-theme='light'] .lane-title {
  color: #16324f;
}
html[data-theme='light'] .lane-meta {
  color: #556b86;
}
html[data-theme='light'] .lane-stat-chip {
  background: rgba(255,255,255,.98);
  border-color: rgba(148, 163, 184, 0.18);
  color: #425a74;
}
html[data-theme='light'] .lane-count {
  background: linear-gradient(180deg, rgba(239,246,255,.98) 0%, rgba(219,234,254,.98) 100%);
  border-color: rgba(59,130,246,.22);
  color: #1d4ed8;
  box-shadow: 0 10px 18px rgba(37,99,235,.1);
}
html[data-theme='light'] .lane-count--critical {
  background: linear-gradient(180deg, rgba(254,242,242,.99) 0%, rgba(255,226,226,.99) 100%);
  border-color: rgba(248,113,113,.26);
  color: #dc2626;
  box-shadow: 0 10px 18px rgba(239,68,68,.08);
}
html[data-theme='light'] .lane-count--warning {
  background: linear-gradient(180deg, rgba(255,247,237,.99) 0%, rgba(255,237,213,.99) 100%);
  border-color: rgba(251,191,36,.24);
  color: #d97706;
  box-shadow: 0 10px 18px rgba(245,158,11,.08);
}
html[data-theme='light'] .lane-count--normal {
  background: linear-gradient(180deg, rgba(240,253,244,.99) 0%, rgba(220,252,231,.99) 100%);
  border-color: rgba(74,222,128,.24);
  color: #059669;
  box-shadow: 0 10px 18px rgba(34,197,94,.08);
}
html[data-theme='light'] .lane-brief {
  background: rgba(255,255,255,.9);
  border-color: rgba(148, 163, 184, 0.18);
}
html[data-theme='light'] .lane-brief--critical {
  background: rgba(255,245,246,.94);
  border-color: rgba(248, 113, 113, 0.22);
}
html[data-theme='light'] .lane-brief--warning {
  background: rgba(255,249,239,.94);
  border-color: rgba(245, 158, 11, 0.22);
}
html[data-theme='light'] .lane-brief--normal {
  background: rgba(244,252,247,.94);
  border-color: rgba(74, 222, 128, 0.2);
}
html[data-theme='light'] .lane-brief__label {
  color: #5f738b;
}
html[data-theme='light'] .lane-brief__text,
html[data-theme='light'] .lane-brief__chip strong {
  color: #16324f;
}
html[data-theme='light'] .lane-brief__chip {
  border-color: rgba(148, 163, 184, 0.18);
  background: rgba(255,255,255,.98);
  color: #556b86;
}
html[data-theme='light'] .overview-empty {
  border-color: rgba(148, 163, 184, 0.18);
  background: linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(246,249,253,.99) 100%);
  color: #556b86;
}

@media (max-width: 900px) {
  .overview {
    padding: 16px;
  }
  .top-bar {
    padding: 12px;
  }
  .command-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 720px) {
  .lane-panel {
    padding: 14px;
  }
  .lane-title {
    font-size: 16px;
  }
  .lane-grid {
    grid-template-columns: 1fr;
  }
  .command-strip {
    grid-template-columns: 1fr;
  }
  .lane-brief {
    flex-direction: column;
  }
}
</style>

