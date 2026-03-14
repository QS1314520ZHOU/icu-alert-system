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
  const raw = route.query.dept_code
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
.overview { padding: 14px 18px; min-height: 100%; }

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
.sum-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot-crit { background: #ef4444; box-shadow: 0 0 6px #ef4444; animation: blink 1.4s infinite; }
.dot-warn { background: #f59e0b; box-shadow: 0 0 5px #f59e0b88; }
.dot-ok   { background: #22c55e; }
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
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px;
}

/* ── 卡片 ── */
.card {
  position: relative;
  background: #111119;
  border: 1px solid #1a1a28;
  border-radius: 12px;
  padding: 14px 14px 10px;
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s, border-color 0.15s;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.card:hover {
  transform: translateY(-3px);
  box-shadow: 0 12px 32px rgba(0,0,0,0.45);
  border-color: #2a2a3c;
}

/* 级别 */
.card--critical {
  border-color: #ef444433;
  background: linear-gradient(170deg, #1a0a0e 0%, #111119 35%);
}
.card--warning {
  border-color: #f59e0b28;
  background: linear-gradient(170deg, #1a150a 0%, #111119 35%);
}
.card--high {
  border-color: #f9731628;
  background: linear-gradient(170deg, #1a120a 0%, #111119 35%);
}
.card--normal { border-color: #22c55e18; }
.card--flash {
  animation: flash-border 1.2s ease-in-out infinite;
}

/* 床号 + 灯 */
.card-head { display: flex; justify-content: space-between; align-items: center; }
.head-left { display: flex; align-items: center; gap: 8px; min-width: 0; }
.avatar-wrap {
  width: 38px;
  height: 38px;
  border-radius: 9px;
  background: color-mix(in srgb, var(--av) 18%, transparent);
  border: 1px solid color-mix(in srgb, var(--av) 60%, #1a1a28);
  box-shadow: 0 0 8px color-mix(in srgb, var(--av) 45%, transparent);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.avatar {
  width: 32px;
  height: 32px;
  border-radius: 7px;
  background: #0b0b14;
  border: 1px solid #1a1a28;
  padding: 3px;
  object-fit: contain;
}
.bed {
  font-size: 22px; font-weight: 900; color: #60a5fa;
  font-family: 'SF Mono','JetBrains Mono','Consolas',monospace;
  letter-spacing: -0.5px;
}
.bed small { font-size: 11px; font-weight: 400; color: #444; margin-left: 1px; }
.lamp {
  width: 9px; height: 9px; border-radius: 50%;
  flex-shrink: 0;
}
.lamp--critical { background: #ef4444; box-shadow: 0 0 8px #ef4444; animation: blink 1.4s infinite; }
.lamp--warning  { background: #f59e0b; box-shadow: 0 0 6px #f59e0b88; }
.lamp--high     { background: #f97316; box-shadow: 0 0 6px #f9731688; }
.lamp--normal   { background: #22c55e; }
.lamp--none     { background: #333; }

/* 姓名行 */
.card-id { display: flex; align-items: baseline; gap: 8px; }
.name { font-size: 15px; color: #e2e2e2; letter-spacing: 0.3px; }
.demo { display: flex; gap: 5px; font-size: 11px; color: #666; }
.demo em { font-style: normal; }
.demo .m { color: #60a5fa; }
.demo .f { color: #f472b6; }
.icu-d {
  font-family: monospace; font-weight: 700; font-size: 11px;
  color: #888; background: #1a1a28; padding: 0 4px; border-radius: 3px;
}
.icu-d.long { color: #f59e0b; background: #f59e0b15; }

/* 标签 */
.tags { display: flex; gap: 4px; flex-wrap: wrap; }
.tag {
  font-size: 10px; font-weight: 600; padding: 1px 7px;
  border: 1px solid; border-radius: 3px;
  line-height: 16px; letter-spacing: 0.3px;
}
.tag-more { color: #555; border-color: #333; }

/* 诊断 */
.diag { font-size: 12px; color: #666; line-height: 1.3; margin: 0; }

/* 饮食/隔离 */
.care-flags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.care-pill {
  display: inline-flex;
  align-items: center;
  font-size: 10px;
  font-weight: 600;
  line-height: 16px;
  border-radius: 4px;
  padding: 1px 7px;
  border: 1px solid;
  max-width: 100%;
  white-space: nowrap;
}
.care-pill--diet {
  color: #34d399;
  border-color: #34d39966;
  background: #34d39912;
}
.care-pill--iso {
  color: #f59e0b;
  border-color: #f59e0b66;
  background: #f59e0b12;
}

.bundle-lights {
  display: flex;
  gap: 4px;
  align-items: center;
  flex-wrap: wrap;
}
.bundle-dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 9px;
  font-weight: 800;
  color: #fff;
  border: 1px solid rgba(255,255,255,0.12);
}
.bundle-green { background: #22c55e; }
.bundle-yellow { background: #f59e0b; color: #111827; }
.bundle-red { background: #ef4444; }
.bundle-unknown { background: #475569; }

/* 医生 */
.doc { font-size: 10px; color: #444; margin-top: auto; padding-top: 2px; }

/* ── 生命体征 ── */
.vitals {
  background: #0b0b14;
  border-radius: 8px;
  padding: 8px;
  margin-top: 2px;
}
.vitals--empty {
  text-align: center; color: #333; font-size: 11px; padding: 12px;
}
.vg { display: flex; gap: 4px; margin-bottom: 4px; }
.vg:last-of-type { margin-bottom: 0; }
.vi {
  flex: 1;
  text-align: center;
  background: #0f0f1c;
  border-radius: 5px;
  padding: 5px 2px 4px;
}
.vi-bp { flex: 1.4; }
.vi label {
  display: block; font-size: 9px; font-weight: 600;
  color: #444; letter-spacing: 0.5px; margin-bottom: 1px;
}
.vi span {
  font-size: 17px; font-weight: 800;
  font-family: 'SF Mono','JetBrains Mono','Consolas',monospace;
  color: #ccc; line-height: 1;
}

/* 监护仪配色 */
.vi label { color: #555; }

/* HR = 绿 */
.vi:first-child label { color: #22c55e88; }
.vi:first-child.ok span { color: #22c55e; }
/* SpO2 = 青 */
.vi-spo2 label { color: #06b6d488; }
.vi-spo2.ok span { color: #06b6d4; }

/* 异常态 */
.vi.crit { background: #ef444412; }
.vi.crit span { color: #ef4444; }
.vi.crit label { color: #ef444488; }
.vi.warn { background: #f59e0b10; }
.vi.warn span { color: #f59e0b; }
.vi.warn label { color: #f59e0b88; }
.vi.ok span { color: #a3e635; }

/* BP 正常时红色系(监护仪传统) */
.vi-bp label { color: #ef444466; }
.vi-bp.ok span { color: #f87171; }

/* Temp */
.vi:last-child label { color: #fb923c66; }
.vi:last-child.ok span { color: #fb923c; }

.vt {
  display: block; text-align: right;
  font-size: 9px; color: #333; margin-top: 3px;
  font-family: monospace;
}

@media (max-width: 960px) {
  .overview { padding: 10px; }
  .grid {
    grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
    gap: 8px;
  }
}

@media (max-width: 640px) {
  .summary-row {
    flex-wrap: wrap;
    gap: 4px;
  }
  .sum-block {
    flex: 1 1 calc(50% - 4px);
    justify-content: center;
  }
  .sum-divider {
    display: none;
  }
  .grid {
    grid-template-columns: 1fr;
    gap: 8px;
  }
  .card {
    padding: 12px 12px 10px;
  }
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
:global(html[data-theme='light']) .card {
  background: #ffffff;
  border-color: #d8e2f0;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.06);
}
:global(html[data-theme='light']) .card:hover {
  border-color: #9bb1d1;
  box-shadow: 0 12px 24px rgba(15, 23, 42, 0.12);
}
:global(html[data-theme='light']) .card--critical {
  background: linear-gradient(170deg, #fff2f2 0%, #ffffff 45%);
}
:global(html[data-theme='light']) .card--warning,
:global(html[data-theme='light']) .card--high {
  background: linear-gradient(170deg, #fff8ed 0%, #ffffff 45%);
}
:global(html[data-theme='light']) .card--normal {
  background: linear-gradient(170deg, #f2fff7 0%, #ffffff 45%);
}
:global(html[data-theme='light']) .bed small,
:global(html[data-theme='light']) .demo,
:global(html[data-theme='light']) .diag,
:global(html[data-theme='light']) .doc,
:global(html[data-theme='light']) .vt {
  color: #6b7b94;
}
:global(html[data-theme='light']) .name { color: #0f172a; }
:global(html[data-theme='light']) .icu-d { background: #e9eef8; color: #51607a; }
:global(html[data-theme='light']) .tag-more { color: #677893; border-color: #bcc9dc; }
:global(html[data-theme='light']) .bundle-dot { border-color: rgba(15, 23, 42, 0.08); }
:global(html[data-theme='light']) .vitals {
  background: #f2f6fc;
  border: 1px solid #d9e2f1;
}
:global(html[data-theme='light']) .vitals--empty { color: #90a0b8; }
:global(html[data-theme='light']) .vi {
  background: #ffffff;
  border: 1px solid #dee6f4;
}
:global(html[data-theme='light']) .vi label { color: #5f6f8d; }
:global(html[data-theme='light']) .vi span { color: #22314d; }
</style>
