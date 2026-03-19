<template>
  <div class="overview">
    <!-- ====== 顶部信息带 ====== -->
    <header class="top-bar">
      <div class="summary-row">
        <div class="sum-block">
          <span class="sum-val">{{ filteredPatients.length }}</span>
          <span class="sum-lbl">在院</span>
        </div>
        <div v-if="refreshing && !loading" class="sum-sync">
          <span class="sum-sync-dot"></span>
          <span>后台同步中</span>
        </div>
        <div class="sum-divider"></div>
        <div class="sum-block clickable" :class="{ chosen: alertFilter === 'critical' }"
             @click="toggleAlert('critical')">
          <span class="sum-dot dot-crit"></span>
          <span class="sum-val">{{ criticalCount }}</span>
          <span class="sum-lbl">危重</span>
        </div>
        <div class="sum-block clickable" :class="{ chosen: alertFilter === 'warning' }"
             @click="toggleAlert('warning')">
          <span class="sum-dot dot-warn"></span>
          <span class="sum-val">{{ warningCount }}</span>
          <span class="sum-lbl">警告</span>
        </div>
        <div class="sum-block clickable" :class="{ chosen: alertFilter === 'normal' }"
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
    </header>

    <!-- ====== 加载态 ====== -->
    <div v-if="loading" class="loader">
      <div class="loader-ring"></div>
      <p>正在加载患者数据…</p>
    </div>

    <!-- ====== 卡片网格 ====== -->
    <section v-else class="grid">
      <PatientOverviewCard
        v-for="p in showList"
        :key="p._id"
        :patient="p"
        @select="goDetail"
      />
    </section>
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
  if (routeDeptName.value) items.push({ key: 'dept', label: `科室 ${routeDeptName.value}` })
  if (routeDeptCode.value && !routeDeptName.value) items.push({ key: 'dept_code', label: `科室编码 ${routeDeptCode.value}` })
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
      ? { dept_code: deptCode }
      : deptName
        ? { dept: deptName }
        : undefined

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

    try {
      const statusRes = await getPatientBundleStatuses(ls.map((p: any) => p._id))
      const statuses = statusRes.data?.statuses || {}
      for (const item of [...done, ...tail]) {
        item.bundleStatus = statuses[String(item._id)] || { lights: {} }
      }
    } catch {
      for (const item of [...done, ...tail]) {
        item.bundleStatus = { lights: {} }
      }
    }

    const ord: Record<string, number> = { critical: 0, warning: 1, none: 2, normal: 3 }
    const all = [...done, ...tail].sort((a, b) => {
      const d = (ord[a.alertLevel] ?? 9) - (ord[b.alertLevel] ?? 9)
      return d || String(a.hisBed).localeCompare(String(b.hisBed), undefined, { numeric: true })
    })
    patients.value = all
    overviewCache.set(cacheKey, {
      ts: Date.now(),
      patients: all.map((p: any) => ({ ...p })),
      depts: depts.value.map((d: any) => ({ ...d })),
      curDept: curDept.value,
    })
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
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&display=swap');

.overview { 
  position: relative;
  isolation: isolate;
  background:
    radial-gradient(circle at top, rgba(34, 211, 238, 0.12) 0%, rgba(34, 211, 238, 0) 28%),
    linear-gradient(180deg, #06111d 0%, #040b14 100%);
  padding: 22px 24px 28px;
  min-height: 100%; 
  color: #d8f6ff;
  font-family: 'Rajdhani', 'Noto Sans SC', sans-serif;
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

.loader {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 50vh;
  color: #7ed6e8;
  gap: 14px;
  font-family: 'Rajdhani', 'Noto Sans SC', sans-serif;
}
.loader-ring {
  width: 36px; height: 36px; border: 3px solid rgba(72, 193, 255, 0.14);
  border-top-color: #3ee7c0; border-radius: 50%;
  animation: spin .7s linear infinite;
  box-shadow: 0 0 18px rgba(62, 231, 192, 0.14);
}
@keyframes spin { to { transform: rotate(360deg) } }

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 18px;
}

@media (max-width: 900px) {
  .overview {
    padding: 16px;
  }
  .top-bar {
    padding: 12px;
  }
}
</style>

