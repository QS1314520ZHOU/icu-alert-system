<template>
  <section class="hl-card">
    <header class="hl-head">
      <span>出入量与血管活性药负荷</span>
      <div class="hl-head-actions">
        <button v-for="h in [12, 24, 48]" :key="h" :class="['hl-win', { on: hours === h }]" @click="setHours(h)">{{ h }}h</button>
        <button class="hl-win" :disabled="loading" @click="load">{{ loading ? '加载中' : '刷新' }}</button>
      </div>
    </header>
    <div v-if="error" class="hl-state hl-state--err">{{ error }}</div>
    <div v-else-if="!data && loading" class="hl-state">加载中…</div>
    <div v-else-if="data" class="hl-body">
      <div class="hl-findings">
        <span class="hl-label">结论</span>
        <template v-if="data.findings.length">
          <span v-for="(f, i) in data.findings" :key="i" :class="['hl-chip', `hl-chip--${f.level}`]">{{ f.text }}</span>
        </template>
        <span v-else class="hl-chip hl-chip--ok">窗口内出入量与血管活性药未见异常提示</span>
      </div>
      <div v-if="data.data_gaps.length" class="hl-gaps">{{ data.data_gaps.join('；') }}</div>

      <div class="hl-tiles">
        <div class="hl-tile">
          <span>{{ data.window_hours }}h 入 / 出</span>
          <b>{{ fmt(fluid.totals.intake_ml) }} / {{ fmt(fluid.totals.output_ml) }}</b><small>ml</small>
        </div>
        <div :class="['hl-tile', balanceTone]">
          <span>{{ data.window_hours }}h 净平衡</span>
          <b>{{ signed(fluid.totals.net_ml) }}</b><small>ml</small>
          <em v-if="fluid.fluid_overload_pct != null">约占体重 {{ fluid.fluid_overload_pct }}%</em>
        </div>
        <div :class="['hl-tile', urineTone]">
          <span>近6h 尿量</span>
          <template v-if="w6 && w6.urine_ml != null">
            <b>{{ w6.urine_ml_kg_h ?? '—' }}</b><small>ml/kg/h</small>
            <em>{{ fmt(w6.urine_ml) }} ml · {{ w6.urine_hours_recorded }}/6 小时有记录</em>
          </template>
          <template v-else><b class="hl-unknown">未知</b><em>无尿量记录（不按 0 计）</em></template>
        </div>
        <div :class="['hl-tile', neeTone]">
          <span>去甲肾上腺素当量 NEE</span>
          <template v-if="vaso.nee != null"><b>{{ vaso.nee_complete ? '' : '≥' }}{{ vaso.nee }}</b><small>μg/kg/min</small></template>
          <template v-else><b class="hl-unknown">未知</b></template>
          <em>{{ runningAgents.length ? runningAgents.map((a: any) => a.label).join('、') + ' 在用' : '无在用升压药' }}</em>
        </div>
        <div class="hl-tile">
          <span>血管活性-正性肌力评分 VIS</span>
          <template v-if="vaso.vis != null"><b>{{ vaso.vis_complete ? '' : '≥' }}{{ vaso.vis }}</b></template>
          <template v-else><b class="hl-unknown">未知</b></template>
          <em>{{ visHint }}</em>
        </div>
      </div>

      <div class="hl-grid">
        <div class="hl-panel">
          <h4>逐小时出入量与累计平衡</h4>
          <ClinicalChart :option="fluidOption" :height="220" aria-label="逐小时出入量" empty-text="窗口内无出入量记录" />
          <div class="hl-split">
            <div><span class="hl-sub">入量构成</span>
              <span v-for="x in fluid.intake_by" :key="x.key" class="hl-kv">{{ x.label }} {{ fmt(x.ml) }}</span>
              <span v-if="!fluid.intake_by.length" class="hl-kv hl-muted">无</span></div>
            <div><span class="hl-sub">出量构成</span>
              <span v-for="x in fluid.output_by" :key="x.key" class="hl-kv">{{ x.label }} {{ fmt(x.ml) }}</span>
              <span v-if="!fluid.output_by.length" class="hl-kv hl-muted">无</span></div>
          </div>
        </div>
        <div class="hl-panel">
          <h4>血管活性药剂量（{{ vasoUnitText }}）</h4>
          <ClinicalChart :option="vasoOption" :height="220" aria-label="血管活性药剂量" empty-text="窗口内无血管活性药执行记录" />
          <table v-if="vaso.agents.length" class="hl-table">
            <thead><tr><th>药物</th><th>状态</th><th>当前剂量</th><th>开始</th></tr></thead>
            <tbody>
              <tr v-for="a in vaso.agents" :key="a.agent">
                <td>{{ a.label }}<small v-if="!a.in_nee" class="hl-muted">（不计入 NEE）</small></td>
                <td><span :class="['hl-state-tag', a.state]">{{ stateText(a.state) }}</span></td>
                <td>
                  <template v-if="a.current_dose != null">{{ a.current_dose }} {{ a.unit }}</template>
                  <span v-else-if="a.state === 'running'" class="hl-warn">无法换算：{{ a.dose_unknown_reason || '数据不足' }}</span>
                  <span v-else class="hl-muted">—</span>
                </td>
                <td>{{ fmtTime(a.started_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="hl-resus">
        <span class="hl-sub">复苏液体（晶体+胶体，{{ data.window_hours }}h）</span>
        <b>{{ fmt(fluid.resuscitation.total_ml) }} ml</b>
        <span class="hl-muted">晶体 {{ fmt(fluid.resuscitation.crystalloid_ml) }} · 胶体 {{ fmt(fluid.resuscitation.colloid_ml) }}</span>
        <template v-if="fluid.resuscitation.target_30ml_kg">
          <span class="hl-muted">脓毒症 30 ml/kg 参考 {{ fmt(fluid.resuscitation.target_30ml_kg) }} ml</span>
          <span :class="['hl-chip', fluid.resuscitation.met === true ? 'hl-chip--ok' : fluid.resuscitation.met === false ? 'hl-chip--info' : 'hl-chip--warning']">
            {{ fluid.resuscitation.met === true ? '已达到' : fluid.resuscitation.met === false ? '未达到（是否需要由医生结合容量反应性判断）' : '部分记录无量，无法判定' }}
          </span>
        </template>
      </div>

      <details class="hl-method">
        <summary>计算方法与数据来源</summary>
        <p>{{ fluid.method }}</p>
        <p>{{ vaso.method }}</p>
        <p>体重：{{ data.weight_kg ? data.weight_kg + ' kg' : '缺失' }}；判定原则参照 ICU-05 脓毒症规则：缺失即未知，不补零；无执行动作的泵入记录不判定为"在用"。</p>
      </details>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { EChartsOption } from 'echarts'
import ClinicalChart from '../charts/base/ClinicalChart.vue'
import { getPatientHemodynamicLoad } from '../../api'

const props = defineProps<{ patientId: string }>()
const hours = ref(24)
const loading = ref(false)
const error = ref('')
const data = ref<any>(null)

async function load() {
  if (!props.patientId) return
  loading.value = true
  error.value = ''
  try {
    const res: any = await getPatientHemodynamicLoad(props.patientId, hours.value)
    const body = res?.data ?? res
    if (body?.code && body.code !== 0) throw new Error(body.message || '加载失败')
    data.value = body?.data ?? null
    if (!data.value) error.value = '接口未返回数据'
  } catch (e: any) {
    error.value = `出入量数据加载失败：${e?.message || e}`
  } finally {
    loading.value = false
  }
}
function setHours(h: number) { if (hours.value !== h) { hours.value = h; load() } }
onMounted(load)
watch(() => props.patientId, load)

const fluid = computed(() => data.value?.fluid || {})
const vaso = computed(() => data.value?.vasoactive || { agents: [] })
const w6 = computed(() => fluid.value?.windows?.['6h'])
const runningAgents = computed(() => (vaso.value.agents || []).filter((a: any) => a.state === 'running'))
const vasoUnitText = computed(() => (vaso.value.agents || []).some((a: any) => a.unit === 'U/min') ? 'μg/kg/min；加压素 U/min' : 'μg/kg/min')

const fmt = (v: any) => (v == null ? '—' : Math.round(Number(v)).toLocaleString())
const signed = (v: any) => (v == null ? '—' : `${v > 0 ? '+' : ''}${Math.round(v).toLocaleString()}`)
const fmtTime = (s: any) => { if (!s) return '—'; const d = new Date(s); return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}` }
const stateText = (s: string) => ({ running: '在用', stopped: '已停', unknown: '无法判断' } as any)[s] || s

const balanceTone = computed(() => { const p = fluid.value.fluid_overload_pct; return p == null ? '' : p >= 10 ? 'is-crit' : p >= 5 ? 'is-warn' : '' })
const urineTone = computed(() => { const r = w6.value?.urine_ml_kg_h; return r == null ? (w6.value?.urine_ml == null ? 'is-warn' : '') : r < 0.3 ? 'is-crit' : r < 0.5 ? 'is-warn' : 'is-ok' })
const neeTone = computed(() => { const n = vaso.value.nee; return n == null ? 'is-warn' : n >= 0.5 ? 'is-crit' : n >= 0.25 ? 'is-warn' : '' })
const visHint = computed(() => { const v = vaso.value.vis; if (v == null) return '剂量不全'; if (v >= 30) return '≥30 高负荷'; if (v >= 15) return '15–30 中等'; return v > 0 ? '<15 低' : '无' })

const hourLabel = (iso: string) => { const d = new Date(iso); return `${String(d.getHours()).padStart(2, '0')}:00` }
const fluidOption = computed<EChartsOption | null>(() => {
  const rows = fluid.value.rows || []
  if (!rows.some((r: any) => r.intake_ml || r.output_ml)) return null
  return {
    animation: false,
    grid: { left: 48, right: 48, top: 26, bottom: 24 },
    legend: { top: 0, itemWidth: 10, itemHeight: 8, textStyle: { fontSize: 11 } },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: rows.map((r: any) => hourLabel(r.hour)), axisLabel: { fontSize: 10, color: '#7A7975' } },
    yAxis: [
      { type: 'value', name: 'ml/h', nameTextStyle: { fontSize: 10 }, axisLabel: { fontSize: 10, color: '#7A7975' }, splitLine: { lineStyle: { color: '#F1F0EE' } } },
      { type: 'value', name: '累计', nameTextStyle: { fontSize: 10 }, axisLabel: { fontSize: 10, color: '#7A7975' }, splitLine: { show: false } },
    ],
    series: [
      { name: '入量', type: 'bar', stack: 'io', data: rows.map((r: any) => r.intake_ml), itemStyle: { color: '#5392FF' }, barMaxWidth: 12 },
      { name: '出量', type: 'bar', stack: 'io', data: rows.map((r: any) => -r.output_ml), itemStyle: { color: '#F59E0B' }, barMaxWidth: 12 },
      { name: '尿量', type: 'line', data: rows.map((r: any) => (r.urine_ml == null ? null : -r.urine_ml)), connectNulls: false, symbolSize: 4, lineStyle: { width: 1, type: 'dashed', color: '#B45309' }, itemStyle: { color: '#B45309' } },
      { name: '累计平衡', type: 'line', yAxisIndex: 1, data: rows.map((r: any) => r.cumulative_ml), showSymbol: false, lineStyle: { width: 2, color: '#37352F' }, itemStyle: { color: '#37352F' } },
    ],
  }
})
const AGENT_COLORS = ['#B91C1C', '#5392FF', '#7C3AED', '#2F7D55', '#B45309', '#0891B2']
const vasoOption = computed<EChartsOption | null>(() => {
  const agents = (vaso.value.agents || []).filter((a: any) => a.series?.some((p: any) => p.dose != null))
  if (!agents.length) return null
  const nee = (vaso.value.nee_series || []).map((p: any) => [new Date(p.time).getTime(), p.nee])
  return {
    animation: false,
    grid: { left: 48, right: 16, top: 26, bottom: 24 },
    legend: { top: 0, itemWidth: 10, itemHeight: 8, textStyle: { fontSize: 11 } },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'time', axisLabel: { fontSize: 10, color: '#7A7975', formatter: '{HH}:{mm}' } },
    yAxis: { type: 'value', axisLabel: { fontSize: 10, color: '#7A7975' }, splitLine: { lineStyle: { color: '#F1F0EE' } } },
    series: [
      { name: 'NEE', type: 'line', step: 'end', data: nee, showSymbol: false, lineStyle: { width: 2.5, color: '#37352F' }, itemStyle: { color: '#37352F' },
        markLine: { silent: true, symbol: 'none', lineStyle: { color: '#B45309', type: 'dashed' }, label: { formatter: '0.25', fontSize: 10 }, data: [{ yAxis: 0.25 }] } },
      ...agents.map((a: any, i: number) => ({
        name: a.label, type: 'line' as const, step: 'end' as const, showSymbol: false,
        data: a.series.map((p: any) => [new Date(p.time).getTime(), p.dose]),
        lineStyle: { width: 1.5, color: AGENT_COLORS[i % AGENT_COLORS.length] }, itemStyle: { color: AGENT_COLORS[i % AGENT_COLORS.length] },
      })),
    ],
  }
})
</script>

<style scoped>
.hl-card { border: 1px solid #E6E5E3; border-radius: 10px; overflow: hidden; background: #fff; margin-bottom: 16px; }
.hl-head { height: 38px; background: #5392FF; color: #fff; display: flex; align-items: center; justify-content: space-between; padding: 0 14px; font-weight: 600; font-size: 14px; }
.hl-head-actions { display: flex; gap: 4px; }
.hl-win { border: 0; background: rgba(255,255,255,.2); color: #fff; font-size: 12px; padding: 2px 10px; border-radius: 4px; cursor: pointer; }
.hl-win.on { background: #fff; color: #2B6DE0; font-weight: 600; }
.hl-state { padding: 24px; text-align: center; color: #7A7975; font-size: 13px; }
.hl-state--err { color: #B91C1C; }
.hl-body { padding: 12px 14px 14px; }
.hl-findings { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.hl-label, .hl-panel h4 { font-size: 13px; font-weight: 600; color: #37352F; padding-left: 8px; border-left: 3px solid #5392FF; margin: 0 4px 0 0; }
.hl-chip { font-size: 12px; padding: 2px 8px; border-radius: 10px; border: 1px solid; }
.hl-chip--critical { background: #FEF2F2; color: #B91C1C; border-color: #FCA5A5; }
.hl-chip--warning { background: #FFFBEB; color: #B45309; border-color: #FCD34D; }
.hl-chip--ok { background: #E7F5EE; color: #2F7D55; border-color: #A7D9BF; }
.hl-chip--info { background: #F1F5FB; color: #37527A; border-color: #C9D6E8; }
.hl-gaps { margin-top: 8px; font-size: 12px; color: #B45309; background: #FFFBEB; border: 1px solid #FCD34D; border-radius: 8px; padding: 6px 10px; }
.hl-tiles { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
.hl-tile { border: 1px solid #E6E5E3; border-radius: 10px; padding: 8px 10px; display: flex; flex-wrap: wrap; align-items: baseline; gap: 3px; }
.hl-tile span { width: 100%; font-size: 12px; color: #55534E; }
.hl-tile b { font-size: 20px; color: #37352F; font-variant-numeric: tabular-nums; }
.hl-tile small { font-size: 11px; color: #7A7975; }
.hl-tile em { width: 100%; font-style: normal; font-size: 11px; color: #7A7975; }
.hl-tile.is-crit { border-color: #FCA5A5; background: #FEF2F2; } .hl-tile.is-crit b { color: #B91C1C; }
.hl-tile.is-warn { border-color: #FCD34D; background: #FFFBEB; } .hl-tile.is-warn b { color: #B45309; }
.hl-tile.is-ok b { color: #2F7D55; }
.hl-unknown { color: #B45309 !important; font-size: 16px !important; }
.hl-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px; }
.hl-panel { border: 1px solid #E6E5E3; border-radius: 10px; padding: 10px 12px; }
.hl-panel h4 { margin-bottom: 6px; }
.hl-split { display: flex; flex-direction: column; gap: 4px; font-size: 12px; margin-top: 4px; }
.hl-sub { font-size: 12px; color: #55534E; font-weight: 600; margin-right: 6px; }
.hl-kv { margin-right: 10px; color: #37352F; font-variant-numeric: tabular-nums; }
.hl-muted { color: #7A7975; }
.hl-warn { color: #B45309; }
.hl-table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 6px; }
.hl-table th { text-align: left; color: #7A7975; font-weight: 500; border-bottom: 1px solid #E6E5E3; padding: 4px; }
.hl-table td { padding: 5px 4px; border-bottom: 1px dashed #EEE; }
.hl-state-tag { font-size: 11px; padding: 1px 6px; border-radius: 8px; border: 1px solid #C9D6E8; color: #37527A; }
.hl-state-tag.running { background: #FEF2F2; color: #B91C1C; border-color: #FCA5A5; }
.hl-state-tag.unknown { background: #FFFBEB; color: #B45309; border-color: #FCD34D; }
.hl-resus { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 12px; font-size: 12px; }
.hl-resus b { font-size: 14px; }
.hl-method { margin-top: 10px; font-size: 12px; color: #55534E; }
.hl-method summary { cursor: pointer; color: #2B6DE0; }
.hl-method p { margin: 4px 0; line-height: 1.6; }
@media (max-width: 1280px) { .hl-tiles { grid-template-columns: repeat(3, minmax(0, 1fr)); } .hl-grid { grid-template-columns: 1fr; } }
</style>
