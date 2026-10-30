<template>
  <section class="sbc" :class="{ 'sbc--embedded': embedded }" aria-label="脓毒症集束化">
    <header v-if="!embedded" class="sbc-head">
      <span class="sbc-title">脓毒症集束化</span>
      <span class="sbc-head-meta">
        <span v-if="t0">T0 {{ t0 }}</span>
        <span class="sbc-status">{{ status?.label || '未进入计时' }}</span>
      </span>
    </header>
    <div class="sbc-body">
      <div class="sbc-headline" :class="`t-${headline.tone}`">
        <span v-if="embedded" class="sbc-inline-status">{{ status?.label || '未进入计时' }}</span>
        {{ headline.text }}<small v-if="embedded && t0" class="sbc-t0">T0 {{ t0 }}</small>
      </div>

      <div v-if="gateGroups.length" class="sbc-gate">
        <span v-for="g in gateGroups" :key="g.label" class="sbc-gate-group">
          <em>{{ g.label }}</em>
          <i v-for="(e, i) in g.items" :key="i" :class="`g-${g.tone}`">{{ e }}</i>
        </span>
      </div>

      <div class="sbc-windows">
        <div v-for="w in windows" :key="w.key" class="sbc-window" :class="`t-${w.tone}`">
          <span class="sbc-wkey">{{ w.key }}</span>
          <b>{{ w.label }}</b>
          <small v-if="w.deadline">截止 {{ fmtHm(w.deadline) }}</small>
        </div>
      </div>

      <table v-if="rows.length" class="sbc-table">
        <thead><tr><th>要素</th><th>时窗</th><th>状态</th><th>完成时间</th><th>说明</th></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.key">
            <th scope="row">{{ r.name }}</th>
            <td class="sbc-win">{{ r.window }}</td>
            <td><span class="sbc-mark" :class="`t-${r.tone}`">{{ r.mark }}</span></td>
            <td class="sbc-time">{{ fmtHm(r.time) || '—' }}</td>
            <td class="sbc-note">{{ r.note }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="sbc-empty">后端未返回集束化要素明细，仅显示计时状态。</p>

      <p v-if="cautions.length" class="sbc-caution">补液注意：{{ cautions.join('；') }}</p>

      <details class="sbc-rules">
        <summary>判定规则与数据来源</summary>
        <ul>
          <li>“✓”按时完成；“✓ 超时”超过时窗后补做；“待”时窗未结束，不判未达标；“×”时窗已过仍未见执行记录；“—”未取到记录，不按未完成计。</li>
          <li>1h：乳酸、抗菌药前血培养、广谱抗菌药、低血压时血管活性药；3h：低血压或乳酸≥4 时晶体液 30 ml/kg，初始乳酸≥2 时复测乳酸（SSC 2021）。</li>
          <li>T0 取后端计时锚点（{{ status?.bundle_clock_anchor ? '临床确认/筛查锚点' : '集束化开始时间' }}）。仅为质控提示，不替代医生判断。</li>
        </ul>
      </details>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { buildBundleRows, buildWindows, bundleHeadline, fmtHm } from './sepsisBundleModel'

const props = defineProps<{ status: any; embedded?: boolean }>()
const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | null = null
onMounted(() => { timer = setInterval(() => { now.value = Date.now() }, 30_000) })
onBeforeUnmount(() => { if (timer) clearInterval(timer) })

const t0 = computed(() => fmtHm(props.status?.bundle_clock_anchor || props.status?.bundle_started_at))
const rows = computed(() => buildBundleRows(props.status, now.value))
const windows = computed(() => buildWindows(props.status, now.value))
const headline = computed(() => bundleHeadline(props.status, rows.value, now.value))
const cautions = computed<string[]>(() => (Array.isArray(props.status?.fluid_risk_cautions) ? props.status.fluid_risk_cautions.map(String) : []))
const INFECTION: Record<string, string> = { likely: '很可能', possible: '可能', confirmed: '确认', supported: '支持', suspected: '疑似', unlikely: '可能性低', not_supported: '无证据', unknown: '不明' }
const gateGroups = computed(() => {
  const s = props.status || {}
  const out: { label: string; items: string[]; tone: string }[] = []
  const inf: string[] = []
  if (s.infection_verdict) inf.push(`感染${INFECTION[s.infection_verdict] || s.infection_verdict}`)
  if (Array.isArray(s.infection_positive_evidence)) inf.push(...s.infection_positive_evidence.map(String))
  if (inf.length) out.push({ label: '感染', items: inf, tone: 'warn' })
  const shock: string[] = []
  if (s.shock_suspected) shock.push('疑似休克')
  if (s.vasopressor_active) shock.push('升压药使用中')
  if (Array.isArray(s.hypoperfusion_evidence)) shock.push(...s.hypoperfusion_evidence.map(String))
  if (shock.length) out.push({ label: '休克/灌注', items: shock, tone: 'crit' })
  if (Array.isArray(s.infection_missing_data) && s.infection_missing_data.length) out.push({ label: '缺项', items: s.infection_missing_data.map(String), tone: 'none' })
  return out
})
</script>

<style scoped>
.sbc { background: #fff; border: 1px solid #E6E5E3; border-radius: 10px; overflow: hidden; }
.sbc-head { height: 38px; background: #5392FF; color: #fff; display: flex; align-items: center; justify-content: space-between; padding: 0 16px; }
.sbc-title { font-size: 15px; font-weight: 600; }
.sbc-head-meta { display: flex; gap: 10px; align-items: center; font-size: 12px; }
.sbc-status { background: rgba(255,255,255,.2); border-radius: 4px; padding: 1px 8px; }
.sbc-body { padding: 12px 16px 14px; }
.sbc-headline { font-size: 16px; font-weight: 700; line-height: 1.5; color: #1F2329; }
.sbc-headline.t-fail { color: #B91C1C; }
.sbc-headline.t-late, .sbc-headline.t-wait { color: #B45309; }
.sbc-headline.t-done { color: #2F7D55; }
.sbc-gate { display: flex; flex-wrap: wrap; gap: 6px 14px; margin-top: 8px; font-size: 12px; }
.sbc-gate-group { display: inline-flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.sbc-gate-group em { font-style: normal; color: #646A73; margin-right: 2px; }
.sbc-gate-group i { font-style: normal; padding: 1px 6px; border-radius: 4px; border: 1px solid #E6E5E3; background: #F7F8FA; color: #1F2329; }
.sbc-gate-group i.g-crit { background: #FEF2F2; border-color: #FCA5A5; color: #B91C1C; }
.sbc-gate-group i.g-warn { background: #FFFBEB; border-color: #FCD34D; color: #B45309; }
.sbc-windows { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin: 10px 0; }
.sbc-window { display: flex; align-items: baseline; gap: 8px; padding: 8px 12px; border-radius: 8px; background: #F7F8FA; border: 1px solid #E6E5E3; }
.sbc-wkey { font-size: 12px; font-weight: 600; color: #5392FF; }
.sbc-window b { font-size: 16px; }
.sbc-window small { margin-left: auto; color: #8F959E; font-size: 12px; }
.sbc-window.t-fail { background: #FEF2F2; border-color: #FCA5A5; } .sbc-window.t-fail b { color: #B91C1C; }
.sbc-window.t-late { background: #FFFBEB; border-color: #FCD34D; } .sbc-window.t-late b { color: #B45309; }
.sbc-window.t-done { background: #E7F5EE; border-color: #A7D9BF; } .sbc-window.t-done b { color: #2F7D55; }
.sbc-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.sbc-table th, .sbc-table td { border-bottom: 1px solid #EFF0F1; padding: 6px 8px; text-align: left; vertical-align: top; }
.sbc-table thead th { background: #F7F8FA; color: #646A73; font-weight: 500; font-size: 12px; }
.sbc-table tbody th { font-weight: 500; color: #1F2329; white-space: nowrap; }
.sbc-win, .sbc-time { color: #646A73; white-space: nowrap; font-variant-numeric: tabular-nums; }
.sbc-note { color: #646A73; font-size: 12px; }
.sbc-mark { display: inline-block; min-width: 40px; text-align: center; padding: 1px 6px; border-radius: 4px; font-weight: 600; font-size: 12px; white-space: nowrap; }
.sbc-mark.t-done { background: #E7F5EE; color: #2F7D55; }
.sbc-mark.t-late { background: #FFFBEB; color: #B45309; }
.sbc-mark.t-fail { background: #FEF2F2; color: #B91C1C; }
.sbc-mark.t-wait { background: #EEF4FF; color: #2F6FED; }
.sbc-mark.t-none, .sbc-mark.t-quiet { background: #F2F3F5; color: #8F959E; }
.sbc-empty { color: #8F959E; font-size: 12px; margin: 4px 0; }
.sbc-caution { margin: 8px 0 0; font-size: 12px; color: #B45309; }
.sbc-rules { margin-top: 8px; font-size: 12px; color: #646A73; }
.sbc-rules summary { cursor: pointer; color: #5392FF; }
.sbc-rules ul { margin: 6px 0 0; padding-left: 18px; line-height: 1.6; }
.sbc--embedded { border: 0; border-radius: 0; }
.sbc--embedded .sbc-body { padding: 0; }
.sbc-inline-status { display: inline-block; font-size: 12px; font-weight: 600; padding: 1px 8px; border-radius: 4px; background: #EEF4FF; color: #2F6FED; margin-right: 6px; vertical-align: 2px; }
.sbc-t0 { font-size: 12px; font-weight: 400; color: #8F959E; margin-left: 8px; }
</style>
