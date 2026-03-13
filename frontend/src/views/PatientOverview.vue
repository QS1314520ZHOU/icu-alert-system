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
      <article v-for="p in showList" :key="p._id"
               :class="['card', `card--${p.alertLevel || 'none'}`]"
               @click="goDetail(p._id)">

        <!-- 行1: 床号 + 状态灯 -->
        <div class="card-head">
          <div class="head-left">
            <span class="avatar-wrap" :style="{ '--av': avatarAccent(p) }">
              <img class="avatar" :src="avatarFor(p)" :alt="avatarAlt(p)" />
            </span>
            <span class="bed">{{ p.hisBed }}<small>床</small></span>
          </div>
          <span :class="['lamp', `lamp--${p.alertLevel || 'none'}`]"></span>
        </div>

        <!-- 行2: 姓名 性别年龄 ICU天数 -->
        <div class="card-id">
          <strong class="name">{{ p.name || '—' }}</strong>
          <span class="demo">
            <em :class="p.gender === 'Male' ? 'm' : 'f'">{{ p.genderText }}</em>
            <em v-if="p.age">{{ p.age }}</em>
            <em v-if="p.icuDays != null && p.icuDays >= 0"
                :class="['icu-d', { long: p.icuDays > 14 }]">D{{ p.icuDays }}</em>
          </span>
        </div>

        <!-- 行3: 临床标签（最多3个） -->
        <div class="tags" v-if="p.clinicalTags?.length">
          <span v-for="t in p.clinicalTags.slice(0, 3)" :key="t.tag"
                class="tag" :style="{ color: t.color, borderColor: t.color + '66' }">
            {{ t.label }}
          </span>
          <span v-if="p.clinicalTags.length > 3" class="tag tag-more">
            +{{ p.clinicalTags.length - 3 }}
          </span>
        </div>

        <!-- 行4: 诊断 -->
        <p class="diag" :title="p.clinicalDiagnosis || p.admissionDiagnosis">
          {{ shortDiag(p.clinicalDiagnosis || p.admissionDiagnosis) }}
        </p>

        <!-- 行5: 生命体征 -->
        <div class="vitals" v-if="p.vitals?.source">
          <div class="vg">
            <div :class="['vi', vc('hr', p.vitals.hr)]">
              <label>HR</label>
              <span>{{ p.vitals.hr ?? '–' }}</span>
            </div>
            <div :class="['vi vi-spo2', vc('spo2', p.vitals.spo2)]">
              <label>SpO₂</label>
              <span>{{ p.vitals.spo2 != null ? p.vitals.spo2 + '%' : '–' }}</span>
            </div>
            <div :class="['vi', vc('rr', p.vitals.rr)]">
              <label>RR</label>
              <span>{{ p.vitals.rr ?? '–' }}</span>
            </div>
          </div>
          <div class="vg">
            <div :class="['vi vi-bp', vc('sys', p.vitals.nibp_sys)]">
              <label>BP</label>
              <span>{{ bp(p.vitals) }}</span>
            </div>
            <div :class="['vi', vc('temp', p.vitals.temp)]">
              <label>T</label>
              <span>{{ temp(p.vitals.temp) }}</span>
            </div>
          </div>
          <time class="vt">{{ clock(p.vitals.time) }}</time>
        </div>
        <div class="vitals vitals--empty" v-else>无监护数据</div>

        <!-- 主管医生小字 -->
        <div class="doc" v-if="p.bedDoctor">{{ p.bedDoctor }}</div>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getDepartments, getPatients, getPatientVitals } from '../api'
import maleChild from '../assets/avatars/male-child.svg'
import maleAdult from '../assets/avatars/male-adult.svg'
import maleElder from '../assets/avatars/male-elder.svg'
import femaleChild from '../assets/avatars/female-child.svg'
import femaleAdult from '../assets/avatars/female-adult.svg'
import femaleElder from '../assets/avatars/female-elder.svg'

const router = useRouter()
const route = useRoute()
const loading = ref(true)
const patients = ref<any[]>([])
const depts = ref<any[]>([])
const curDept = ref('全部')
const tagFilter = ref('')
const alertFilter = ref('')
let iv: any = null

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

const avatarMap = {
  male: { child: maleChild, adult: maleAdult, elder: maleElder },
  female: { child: femaleChild, adult: femaleAdult, elder: femaleElder },
  neutral: { child: maleChild, adult: maleAdult, elder: maleElder },
} as const

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
  if (alertFilter.value) ls = ls.filter(p => p.alertLevel === alertFilter.value)
  return ls
})

/* ── 统计 ── */
const criticalCount = computed(() => byDept.value.filter(p => p.alertLevel === 'critical').length)
const warningCount = computed(() => byDept.value.filter(p => p.alertLevel === 'warning').length)
const normalCount = computed(() => byDept.value.filter(p => p.alertLevel === 'normal').length)

/* ── toggle ── */
function toggleAlert(a: string) { alertFilter.value = alertFilter.value === a ? '' : a }

function ageGroup(age: any): 'child' | 'adult' | 'elder' {
  const s = String(age ?? '').trim()
  if (!s) return 'adult'
  if (s.endsWith('天') || s.endsWith('月')) return 'child'
  const m = s.match(/(\d+)/)
  if (m) {
    const n = Number(m[1])
    if (Number.isFinite(n)) {
      if (n < 14) return 'child'
      if (n >= 60) return 'elder'
      return 'adult'
    }
  }
  return 'adult'
}

function avatarFor(p: any) {
  const gender =
    p?.gender === 'Female' ? 'female' :
    p?.gender === 'Male' ? 'male' : 'neutral'
  return avatarMap[gender][ageGroup(p?.age)]
}

function avatarAlt(p: any) {
  const genderText = p?.gender === 'Female' ? '女性' : p?.gender === 'Male' ? '男性' : '未知性别'
  const group = ageGroup(p?.age)
  const groupText = group === 'child' ? '儿童' : group === 'elder' ? '老年' : '成人'
  return `${genderText}${groupText}头像`
}

function avatarAccent(p: any) {
  const level = String(p?.alertLevel || 'none')
  if (level === 'critical') return '#f5222d'
  if (level === 'warning') return '#faad14'
  if (level === 'normal') return '#52c41a'
  return '#1890ff'
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
  const T: Record<string, number[]> = {
    hr: [40, 50, 110, 130], spo2: [85, 92, 999, 999],
    sys: [70, 85, 160, 200], temp: [34, 35.5, 38.5, 40],
    rr: [6, 10, 25, 35],
  }
  const t = T[k]; if (!t) return ''
  if (n < t[0] || n > t[3]) return 'crit'
  if (n < t[1] || n > t[2]) return 'warn'
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

/* ── fmt ── */
function bp(v: any) {
  const s = v?.nibp_sys, d = v?.nibp_dia
  return s != null || d != null ? `${s ?? '–'}/${d ?? '–'}` : '–'
}
function temp(v: any) {
  if (v == null) return '–'
  const n = Number(v)
  return isNaN(n) ? '–' : n.toFixed(1)
}
function clock(t: any) {
  if (!t) return ''
  try { const d = new Date(t); return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}` }
  catch { return '' }
}
function shortDiag(s: string) {
  if (!s) return '—'
  const f = s.split('|')[0]
  return f.length > 16 ? f.slice(0, 16) + '…' : f
}

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
      p.alertLevel = calcLevel(p.vitals)
      return p
    }))

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
onUnmounted(() => clearInterval(iv))
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
.card--normal { border-color: #22c55e18; }

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
</style>
