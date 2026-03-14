<template>
  <div class="overview">
    <!-- ====== 顶部信息带 ====== -->
    <header class="top-bar">
      <div class="summary-row">
        <div class="sum-block">
          <span class="sum-val">{{ filteredPatients.length }}</span>
          <span class="sum-lbl">在院</span>
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
      <div class="tag-chips" v-if="tagStats.length">
        <span v-for="ts in tagStats" :key="ts.tag"
              :class="['chip', { chosen: tagFilter === ts.tag }]"
              :style="tagFilter === ts.tag ? { background: ts.color + '33', color: ts.color } : {}"
              @click="tagFilter = tagFilter === ts.tag ? '' : ts.tag">
          {{ ts.icon }} {{ ts.label }}
          <b>{{ ts.count }}</b>
        </span>
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
import { getDepartments, getPatients, getPatientVitals, getPatientBundleStatuses } from '../api'
import { onAlertMessage } from '../services/alertSocket'

const PatientOverviewCard = defineAsyncComponent(() => import('../components/overview/PatientOverviewCard.vue'))

const router = useRouter()
const route = useRoute()
const loading = ref(true)
const patients = ref<any[]>([])
const depts = ref<any[]>([])
const curDept = ref('全部')
const tagFilter = ref('')
const alertFilter = ref('')
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
const showDeptNav = computed(() => !routeDeptCode.value && !routeDeptName.value)

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

/* ── 最终列表 ── */
const showList = computed(() => {
  let ls = byDept.value
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
  if (showDeptNav.value) syncDeptQuery(dept)
}

function goDetail(id: string) {
  router.push({ path: `/patient/${id}`, query: route.query })
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
  target.alertHoldUntil = Date.now() + 30 * 60 * 1000
  target.alertFlash = true
  window.setTimeout(() => { target.alertFlash = false }, 15000)
}

/* ── fmt ── */
/* ── 数据加载 ── */
async function load() {
  loading.value = true
  try {
    const deptCode = routeDeptCode.value
    const deptName = routeDeptName.value
    const params = deptCode
      ? { dept_code: deptCode }
      : deptName
        ? { dept: deptName }
        : undefined

    const [dr, pr] = await Promise.all([getDepartments(), getPatients(params)])
    const allDepts = dr.data.departments || []
    const ls = pr.data.patients || []

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
    const tail = ls.slice(100).map((p: any) => ({ ...p, vitals: {}, alertLevel: 'none' }))

    const done = await Promise.all(head.map(async (p: any) => {
      try { p.vitals = (await getPatientVitals(p._id)).data.vitals || {} }
      catch { p.vitals = {} }
      p.alertLevel = mergeAlertLevel(p, calcLevel(p.vitals))
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
  } catch (e) { console.error(e) }
  finally { loading.value = false }
}

watch(
  () => [routeDeptCode.value, routeDeptName.value],
  () => {
    tagFilter.value = ''
    alertFilter.value = ''
    load()
  },
  { immediate: true }
)

onMounted(() => { iv = setInterval(load, 60000) })
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
/* ================================================================
   ICU Overview v3 — 精致医疗级暗色主题
   ================================================================ */
.overview { background: #0A0E17; padding: 14px 18px; min-height: 100%; }

/* ── 顶部 ── */
.top-bar {
  margin-bottom: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.summary-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.sum-block {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 12px;
  border-radius: 8px;
  background: rgba(255,255,255,0.03);
}
.sum-block.clickable { cursor: pointer; transition: background 0.15s; }
.sum-block.clickable:hover { background: rgba(255,255,255,0.06); }
.sum-block.chosen { background: rgba(255,255,255,0.08); outline: 1px solid rgba(255,255,255,0.1); }
.sum-val { font-size: 20px; font-weight: 800; color: #eee; font-variant-numeric: tabular-nums; }
.sum-lbl { font-size: 11px; color: #666; }
.sum-dot { width: 8px; height: 8px; border-radius: 50%; }
.dot-crit { background: #F87171; box-shadow: 0 0 8px rgba(248, 113, 113, 0.4); animation: blink 1.4s infinite; }
.dot-warn { background: #FBBF24; box-shadow: 0 0 8px rgba(251, 191, 36, 0.4); }
.dot-ok { background: #34D399; box-shadow: 0 0 8px rgba(52, 211, 153, 0.4); }
.sum-divider { width: 1px; height: 22px; background: #222; margin: 0 4px; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.25} }

/* 科室 */
.dept-nav { display: flex; gap: 5px; overflow-x: auto; padding-bottom: 2px; }
.dept-pill {
  background: none; border: 1px solid #1e1e30; border-radius: 14px;
  padding: 3px 12px; color: #777; font-size: 12px; cursor: pointer;
  white-space: nowrap; transition: all 0.15s;
}
.dept-pill i { font-style: normal; font-size: 10px; opacity: 0.5; margin-left: 3px; }
.dept-pill:hover { color: #aaa; border-color: #333; }
.dept-pill.active { background: #1d4ed8; border-color: #1d4ed8; color: #fff; }
.dept-pill.active i { opacity: 0.8; }

/* 标签 chip */
.tag-chips { display: flex; gap: 5px; flex-wrap: wrap; }
.chip {
  font-size: 11px; padding: 2px 9px; border-radius: 10px;
  background: rgba(255,255,255,0.03); color: #888; cursor: pointer;
  border: 1px solid transparent; transition: all 0.15s; white-space: nowrap;
}
.chip:hover { background: rgba(255,255,255,0.06); }
.chip.chosen { border-color: currentColor; }
.chip b { font-weight: 700; margin-left: 3px; }

/* ── 加载 ── */
.loader { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 50vh; color: #555; gap: 14px; }
.loader-ring {
  width: 32px; height: 32px; border: 3px solid #1a1a2e;
  border-top-color: #3b82f6; border-radius: 50%;
  animation: spin .7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg) } }
@keyframes flash-border {
  0%, 100% { box-shadow: 0 0 0 rgba(239,68,68,0); }
  50% { box-shadow: 0 0 18px rgba(239,68,68,0.35); }
}

/* ── 网格 ── */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 10px;
}

/* ===== Light Theme ===== */
:global(html[data-theme='light']) .overview {
  background: #f4f7fb;
}
:global(html[data-theme='light']) .sum-block {
  background: #ffffff;
  border: 1px solid #d9e2f1;
}
:global(html[data-theme='light']) .sum-lbl { color: #64748b; }
:global(html[data-theme='light']) .sum-val { color: #0f172a; }
:global(html[data-theme='light']) .sum-divider { background: #d6deea; }
:global(html[data-theme='light']) .dept-pill {
  border-color: #ccd8ea;
  color: #4c5f7f;
  background: #fff;
}
:global(html[data-theme='light']) .dept-pill:hover {
  border-color: #9db2d4;
  color: #1e3a8a;
}
:global(html[data-theme='light']) .chip {
  background: #ffffff;
  color: #4c5f7f;
  border-color: #d8e2f0;
}
:global(html[data-theme='light']) .loader { color: #5a6d89; }
</style>
