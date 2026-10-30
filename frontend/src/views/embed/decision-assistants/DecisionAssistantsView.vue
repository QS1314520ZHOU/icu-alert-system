<template>
  <div class="decision-assistants">
    <!-- ① 结论先行：两张结论卡，一眼看到“能不能做 / 还剩多久 / 下一步做什么” -->
    <div class="da-summary">
      <article class="da-sum" :class="`da-sum--${weaningTone}`">
        <header class="da-sum__head">
          <span class="da-sum__title">撤机 / SBT</span>
          <span v-if="weaning?.has_assessment && weaning.risk_score != null" class="da-sum__score">失败风险 {{ LEVEL_LABELS[String(weaning.risk_level).toLowerCase()] || weaning.risk_level }} · {{ weaning.risk_score }} 分</span>
        </header>
        <div v-if="errors.weaning" class="da-error">{{ errors.weaning }}</div>
        <template v-else>
          <div class="da-sum__big">{{ weaningHeadline }}</div>
          <div class="da-sum__counts">
            <span class="c-fail">未达标 <b>{{ weaningCount.fail }}</b></span>
            <span class="c-pass">达标 <b>{{ weaningCount.pass }}</b></span>
            <span class="c-na">未采集 <b>{{ weaningCount.na }}</b></span>
          </div>
          <div v-if="weaningFails.length" class="da-sum__chips">
            <span v-for="r in weaningFails" :key="r.key" class="da-chip da-chip--fail">{{ r.short }} {{ r.display }}</span>
          </div>
          <div class="da-sum__foot">评估 {{ fmt(weaning?.updated_at) }}<template v-if="weaning?.recommendation && weaning.recommendation !== '-'"> · {{ weaning.recommendation }}</template></div>
        </template>
      </article>

      <article class="da-sum" :class="`da-sum--${sepsisTone}`">
        <header class="da-sum__head">
          <span class="da-sum__title">脓毒症 1h 集束</span>
          <span v-if="sepsis?.label" class="da-sum__score">{{ sepsis.label }}</span>
        </header>
        <div v-if="errors.sepsis" class="da-error">{{ errors.sepsis }}</div>
        <template v-else-if="!sepsis || sepsis.status === 'none'">
          <div class="da-sum__big da-sum__big--muted">未触发</div>
          <div class="da-sum__foot">未触发脓毒症筛查，集束未计时</div>
        </template>
        <template v-else>
          <div class="da-sum__big">{{ sepsisHeadline }}</div>
          <div class="da-progress"><i :style="{ width: `${bundleDonePct}%` }" /></div>
          <div class="da-sum__counts">
            <span class="c-pass">已完成 <b>{{ bundleCount.done }}</b> / {{ bundleCount.total }}</span>
            <span>已过 <b>{{ num(sepsis.elapsed_minutes) }}</b> 分钟</span>
            <span>首剂抗生素 <b :class="sepsis.first_antibiotic_time ? '' : 'c-fail'">{{ sepsis.first_antibiotic_time ? fmt(sepsis.first_antibiotic_time) : '未给药' }}</b></span>
          </div>
          <div v-if="bundleTodo.length" class="da-sum__chips">
            <span class="da-sum__label">下一步</span>
            <span v-for="r in bundleTodo" :key="r.key" class="da-chip da-chip--todo">{{ r.short }}</span>
          </div>
        </template>
      </article>
    </div>

    <!-- ② 撤机：逐项指标用色块呈现，未达标排在前面 -->
    <section class="da-card">
      <header class="da-card__head">
        <h3 class="da-card__title">撤机筛查逐项</h3>
        <span class="da-card__hint">红=未达标 · 绿=达标 · 灰=未采集（不参与判断）</span>
        <button class="da-btn" :disabled="loading" @click="loadAll">{{ loading ? '加载中…' : '刷新' }}</button>
      </header>
      <div v-if="weaning" class="da-tiles">
        <div v-for="row in sortedWeaningRows" :key="row.key" class="da-tile" :class="`da-tile--${row.verdict}`">
          <span class="da-tile__label">{{ row.label }}</span>
          <span class="da-tile__value">{{ row.display }}</span>
          <span class="da-tile__ref">{{ row.ref }}</span>
          <span class="da-tile__verdict">{{ VERDICT_LABELS[row.verdict] }}</span>
        </div>
      </div>
      <div class="da-two">
        <div v-if="factors.length" class="da-block">
          <h4 class="da-h4">影响撤机风险的因素</h4>
          <div v-for="f in factors" :key="f.name" class="da-factor">
            <span class="da-factor__name">{{ f.name }}</span>
            <span class="da-factor__bar"><i :style="{ width: `${Math.min(100, f.weight * 25)}%` }" /></span>
            <span class="da-factor__ev">{{ f.evidence }}</span>
          </div>
        </div>
        <div class="da-block">
          <h4 class="da-h4">需床旁人工核对（系统未采集）</h4>
          <div class="da-checks">
            <span v-for="m in MANUAL_CHECKS" :key="m" class="da-check">{{ m }}</span>
          </div>
        </div>
      </div>
      <div v-if="postExtub?.has_alert" class="da-alert">
        <b>拔管后失败风险告警</b>（{{ fmt(postExtub.created_at) }}）：拔管后 {{ num(postExtub.hours_since_extubation, ' h') }}，RR {{ num(postExtub.rr) }}，SpO₂ {{ num(postExtub.spo2, '%') }}
      </div>
      <details class="da-more">
        <summary>SBT 记录（{{ sbtRecords.length }}）<template v-if="gateFailures.length"> · 系统门控未通过 {{ gateFailures.length }} 项</template> · 阈值来源</summary>
        <ul v-if="gateFailures.length" class="da-list da-list--warn"><li v-for="g in gateFailures" :key="g">{{ g }}</li></ul>
        <table v-if="sbtRecords.length" class="da-table">
          <thead><tr><th>时间</th><th>结果</th><th>时长</th><th>RR</th><th>VT</th><th>RSBI</th><th>FiO₂ / PEEP</th></tr></thead>
          <tbody>
            <tr v-for="(r, i) in sbtRecords" :key="i">
              <td class="da-mono">{{ fmt(r.trial_time) }}</td>
              <td><span class="da-verdict" :class="`da-verdict--${r.result === 'passed' ? 'pass' : r.result === 'failed' ? 'fail' : 'na'}`">{{ r.label || r.result }}</span></td>
              <td class="da-mono">{{ num(r.duration_minutes, ' min') }}</td>
              <td class="da-mono">{{ num(r.rr) }}</td>
              <td class="da-mono">{{ num(r.vte_ml, ' ml') }}</td>
              <td class="da-mono">{{ num(r.rsbi) }}</td>
              <td class="da-mono">{{ fio2Text(r.fio2) }} / {{ num(r.peep) }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="da-muted">近期无 SBT 记录</p>
        <p class="da-footnote">阈值参考 AARC 2024 SBT 临床实践指南与 ACCP/ATS 2017 撤机指南的常用筛查标准（AARC 指南不建议把 RSBI 作为进入 SBT 的必需条件），科室可按本院流程调整；最终是否 SBT 由主管医生决定。</p>
      </details>
    </section>

    <!-- ③ 脓毒症：集束元素做成执行清单，依据放在两侧小卡 -->
    <section v-if="sepsis && sepsis.status !== 'none'" class="da-card">
      <header class="da-card__head">
        <h3 class="da-card__title">集束执行清单</h3>
        <span class="da-card__hint">计时起点 {{ fmt(sepsis.bundle_clock_anchor || sepsis.bundle_started_at) }} · 1h 截止 {{ fmt(sepsis.deadline_1h) }} · 3h 截止 {{ fmt(sepsis.deadline_3h) }}</span>
      </header>
      <div class="da-sepsis">
        <ol class="da-steps">
          <li v-for="row in bundleRows" :key="row.key" class="da-step" :class="`da-step--${row.stepTone}`">
            <span class="da-step__dot">{{ row.stepTone === 'done' ? '✓' : row.stepTone === 'late' ? '!' : '' }}</span>
            <div class="da-step__main">
              <div class="da-step__title">{{ row.label }}</div>
              <div class="da-step__sub">{{ row.applicability }}<template v-if="row.trigger !== '—'"> · 触发：{{ row.trigger }}</template></div>
            </div>
            <div class="da-step__state">
              <b>{{ row.status }}</b>
              <span v-if="row.done !== '—'" class="da-mono">{{ row.done }}</span>
            </div>
          </li>
        </ol>
        <div class="da-side">
          <div class="da-block">
            <h4 class="da-h4">为什么进入集束</h4>
            <div class="da-kv"><span>感染判断</span><b>{{ INFECTION_LABELS[sepsis.infection_verdict] || sepsis.infection_verdict || '未判定' }}</b><em v-if="sepsis.infection_confidence != null">置信度 {{ pct(sepsis.infection_confidence) }}</em></div>
            <div v-if="listOf(sepsis.infection_positive_evidence).length" class="da-sum__chips"><span v-for="e in listOf(sepsis.infection_positive_evidence)" :key="e" class="da-chip da-chip--fail">{{ e }}</span></div>
            <div v-if="listOf(sepsis.infection_negative_evidence).length" class="da-sum__chips"><span class="da-sum__label">反对</span><span v-for="e in listOf(sepsis.infection_negative_evidence)" :key="e" class="da-chip">{{ e }}</span></div>
            <div v-if="listOf(sepsis.infection_missing_data).length" class="da-sum__chips"><span class="da-sum__label">缺失</span><span v-for="e in listOf(sepsis.infection_missing_data)" :key="e" class="da-chip da-chip--na">{{ e }}</span></div>
          </div>
          <div class="da-block">
            <h4 class="da-h4">休克 / 低灌注</h4>
            <div class="da-kv"><span>疑似脓毒性休克</span><b :class="sepsis.shock_suspected ? 'c-fail' : ''">{{ sepsis.shock_suspected ? '是' : '否' }}</b></div>
            <div class="da-kv"><span>血管活性药</span><b>{{ sepsis.vasopressor_active ? '使用中' : '未使用' }}</b></div>
            <div v-if="listOf(sepsis.hypoperfusion_evidence).length" class="da-sum__chips"><span v-for="e in listOf(sepsis.hypoperfusion_evidence)" :key="e" class="da-chip da-chip--fail">{{ e }}</span></div>
          </div>
          <div v-if="listOf(sepsis.fluid_risk_factors).length || listOf(sepsis.fluid_risk_cautions).length" class="da-block da-block--warn">
            <h4 class="da-h4">液体复苏需个体化</h4>
            <div v-for="f in listOf(sepsis.fluid_risk_factors)" :key="'f' + f">风险因素：{{ f }}</div>
            <div v-for="c in listOf(sepsis.fluid_risk_cautions)" :key="'c' + c">建议：{{ c }}</div>
          </div>
        </div>
      </div>
    </section>

    <p class="da-footnote da-footnote--end">镇静镇痛、抗感染降阶梯、VTE 预防、血糖控制等专项暂无结构化评估数据，接入后按相同方式展示；营养方案见营养支持工作台。仅供临床决策支持，不替代医生判断。</p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useEmbedBridge } from '../../../composables/useEmbedBridge'
import { getPatientWeaningStatus, getPatientSbtRecords, getPatientSepsisBundleStatus } from '../../../api'

type Verdict = 'pass' | 'fail' | 'na'

const MANUAL_CHECKS = ['原发病已好转', 'pH > 7.25', '体温 ≤ 38.5 ℃', '无新发感染/心肌缺血', '能自主触发吸气', '咳痰与气道保护能力', '升压药低剂量或已停（NE ≤0.1）']
const SHORT_LABELS: Record<string, string> = { pf: 'P/F', fio2: 'FiO₂', peep: 'PEEP', rsbi: 'RSBI', rr: 'RR', vte: 'VT', map: 'MAP', rass: 'RASS', gcs: 'GCS', fo: '液体超负荷' }
const ELEMENT_SHORT: Record<string, string> = { lactate: '测乳酸', lactate_repeat: '复查乳酸', blood_culture: '血培养', antibiotic_assessment: '抗生素评估', first_antibiotic: '首剂抗生素', infection_source: '感染源控制', clinician_path_confirmation: '医生确认路径', fluid_resuscitation: '晶体液复苏', vasopressor: '升压药' }

const LEVEL_LABELS: Record<string, string> = { low: '低', medium: '中', moderate: '中', high: '高', critical: '极高', unknown: '未知' }
const VERDICT_LABELS: Record<Verdict, string> = { pass: '达标', fail: '未达标', na: '未采集' }
const INFECTION_LABELS: Record<string, string> = { likely: '很可能感染', possible: '可能感染', confirmed: '确认感染', suspected: '疑似感染', unlikely: '感染可能性低', unknown: '未判定', excluded: '已排除' }
const APPLICABILITY_LABELS: Record<string, string> = {
  required: '必做', conditional: '条件触发', not_applicable: '不适用', contraindicated: '禁忌', individualized: '个体化', review_pending: '待医生确认',
}
const EXEC_LABELS: Record<string, [string, Verdict]> = {
  met: ['按时完成', 'pass'], completed_before: ['此前已完成', 'pass'], met_late: ['超时完成', 'fail'],
  pending: ['待完成', 'na'], not_started: ['未开始', 'na'], data_missing: ['无数据', 'na'], cancelled: ['已取消', 'na'],
}
const ELEMENT_LABELS: Record<string, string> = {
  lactate: '血乳酸测定', lactate_repeat: '乳酸复查（初值≥2 mmol/L）', blood_culture: '抗生素前血培养',
  antibiotic_assessment: '广谱抗生素评估', first_antibiotic: '首剂广谱抗生素（休克/高度可能脓毒症 1h 内；可能脓毒症无休克 3h 内评估后）', infection_source: '感染源评估与控制',
  clinician_path_confirmation: '医生确认诊疗路径', fluid_resuscitation: '晶体液复苏 ≥30 ml/kg（低灌注/休克，3h 内，SSC 弱推荐）', vasopressor: '血管活性药（液体复苏后 MAP<65，首选去甲肾上腺素）',
}
const TRIGGER_LABELS: Record<string, string> = {
  suspected_sepsis_screening: '脓毒症筛查阳性', 'initial_lactate>=2': '初始乳酸≥2', 'lactate>=4': '乳酸≥4', hypotension: '低血压',
}

const route = useRoute()
const patientId = computed(() => String(route.params.patientId || ''))
const { sendUpdateTitle, sendReportError } = useEmbedBridge({
  moduleKey: 'decision-assistants',
  targetOrigin: window.location.origin,
  onPatientContextChanged: () => loadAll(),
  onRefresh: () => loadAll(),
})

const loading = ref(false)
const errors = reactive<{ weaning: string; sepsis: string }>({ weaning: '', sepsis: '' })
const weaningStatus = ref<any>(null)
const sbtRecords = ref<any[]>([])
const sepsis = ref<any>(null)

const weaning = computed(() => weaningStatus.value?.weaning || null)
const postExtub = computed(() => weaningStatus.value?.post_extubation_risk || null)

function isNum(v: unknown): v is number { return typeof v === 'number' && Number.isFinite(v) }
function toNum(v: unknown): number | null {
  const n = typeof v === 'string' ? Number(v) : v
  return isNum(n) ? n : null
}
function num(v: unknown, unit = ''): string {
  const n = toNum(v)
  if (n === null) return '—'
  return `${Number.isInteger(n) ? n : n.toFixed(1)}${unit}`
}
/** FiO2 可能以 0.4 或 40 两种形式存储，统一按百分比显示 */
function fio2Pct(v: unknown): number | null {
  const n = toNum(v)
  if (n === null) return null
  return n <= 1 ? n * 100 : n
}
function fio2Text(v: unknown) {
  const n = fio2Pct(v)
  return n === null ? '—' : `${Math.round(n)}%`
}
function pct(v: unknown) {
  const n = toNum(v)
  if (n === null) return '—'
  return n <= 1 ? `${Math.round(n * 100)}%` : `${Math.round(n)}%`
}
function listOf(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v.map((x: any) => (typeof x === 'string' ? x : x?.label || x?.description || x?.evidence || x?.name || JSON.stringify(x))).filter(Boolean)
}
function fmt(t: unknown) {
  if (!t) return '—'
  const d = new Date(String(t))
  if (Number.isNaN(d.getTime())) return String(t)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
function remainText(sec: unknown) {
  const n = toNum(sec)
  if (n === null) return ''
  const m = Math.round(Math.abs(n) / 60)
  return n >= 0 ? `剩余 ${m} 分钟` : `已超时 ${m} 分钟`
}

const weaningRows = computed(() => {
  const w = weaning.value || {}
  const rows: { key: string; label: string; value: number | null; display: string; ref: string; test: (v: number) => boolean }[] = [
    { key: 'pf', label: '氧合指数 P/F', value: toNum(w.pf_ratio), display: num(w.pf_ratio, ' mmHg'), ref: '≥ 150 mmHg（或 FiO₂≤40% 时 SpO₂≥90%）', test: (v) => v >= 150 },
    { key: 'fio2', label: 'FiO₂', value: fio2Pct(w.fio2), display: fio2Text(w.fio2), ref: '≤ 40%', test: (v) => v <= 40 },
    { key: 'peep', label: 'PEEP', value: toNum(w.peep), display: num(w.peep, ' cmH₂O'), ref: '≤ 8 cmH₂O（部分方案 ≤10）', test: (v) => v <= 8 },
    { key: 'rsbi', label: '浅快呼吸指数 RSBI（仅参考，不作为必需门槛）', value: toNum(w.rsbi), display: num(w.rsbi), ref: '< 105 次/(min·L)', test: (v) => v < 105 },
    { key: 'rr', label: '呼吸频率', value: toNum(w.rr), display: num(w.rr, ' 次/分'), ref: '< 35 次/分', test: (v) => v < 35 },
    { key: 'vte', label: '潮气量 VT', value: toNum(w.vte_ml), display: num(w.vte_ml, ' ml'), ref: '≥ 5 ml/kg PBW（无体重时按 300 ml 判断）', test: (v) => v >= 300 },
    { key: 'map', label: '平均动脉压 MAP', value: toNum(w.map), display: num(w.map, ' mmHg'), ref: '≥ 65 mmHg；升压药剂量需人工核对（NE ≤0.1 μg/kg/min）', test: (v) => v >= 65 },
    { key: 'rass', label: 'RASS', value: toNum(w.rass), display: num(w.rass), ref: '-2 ~ +1', test: (v) => v >= -2 && v <= 1 },
    { key: 'gcs', label: 'GCS（拔管气道保护参考）', value: toNum(w.gcs), display: num(w.gcs), ref: '≥ 8', test: (v) => v >= 8 },
    { key: 'fo', label: '液体超负荷', value: toNum(w.fluid_overload_pct), display: num(w.fluid_overload_pct, '%'), ref: '< 10%', test: (v) => v < 10 },
  ]
  return rows.map((r) => ({ ...r, verdict: (r.value === null ? 'na' : r.test(r.value) ? 'pass' : 'fail') as Verdict }))
    .concat(toNum(w.ventilation_days) !== null
      ? [{ key: 'days', label: '机械通气天数', value: toNum(w.ventilation_days), display: num(w.ventilation_days, ' 天'), ref: '供参考', test: () => true, verdict: 'na' as Verdict }]
      : [])
})
const gateFailures = computed(() => listOf(weaning.value?.gate_failures))
const factors = computed(() =>
  (Array.isArray(weaning.value?.factors) ? weaning.value.factors : []).map((f: any) =>
    typeof f === 'string'
      ? { name: f, weight: 0, evidence: '' }
      : { name: String(f?.label || f?.factor || f?.name || '—'), weight: Number(f?.weight || 0), evidence: String(f?.evidence || f?.detail || '') },
  ),
)

const bundleRows = computed(() => {
  const els = sepsis.value?.bundle_elements
  if (!els || typeof els !== 'object') return []
  return Object.entries(els as Record<string, any>).map(([key, el]) => {
    const exec = el?.execution && typeof el.execution === 'object' ? el.execution : { status: el?.execution ?? el?.status }
    const [status, tone] = EXEC_LABELS[String(exec?.status || '')] || [String(exec?.status || '—'), 'na' as Verdict]
    const value = exec?.value !== undefined && exec?.value !== null ? String(exec.value) : ''
    const triggers = Array.isArray(el?.condition?.trigger_evidence) ? el.condition.trigger_evidence : []
    const stepTone = tone === 'pass' ? 'done' : tone === 'fail' ? 'late' : ['pending', 'not_started'].includes(String(exec?.status || '')) ? 'todo' : 'na'
    return {
      key,
      stepTone,
      applicabilityKey: String(el?.applicability || ''),
      label: ELEMENT_LABELS[key] || key,
      applicability: APPLICABILITY_LABELS[String(el?.applicability || '')] || el?.applicability || '—',
      status,
      tone,
      done: [exec?.completed_at ? fmt(exec.completed_at) : '', value].filter(Boolean).join(' · ') || '—',
      trigger: triggers.map((t: string) => TRIGGER_LABELS[t] || t).join('、') || '—',
    }
  })
})

const sortedWeaningRows = computed(() => {
  const order: Record<Verdict, number> = { fail: 0, pass: 1, na: 2 }
  return [...weaningRows.value].sort((a, b) => order[a.verdict] - order[b.verdict])
})
const weaningCount = computed(() => {
  const rows = weaningRows.value.filter((r) => r.key !== 'days')
  return { fail: rows.filter((r) => r.verdict === 'fail').length, pass: rows.filter((r) => r.verdict === 'pass').length, na: rows.filter((r) => r.verdict === 'na').length }
})
const weaningFails = computed(() => weaningRows.value.filter((r) => r.verdict === 'fail' && r.key !== 'rsbi').map((r) => ({ ...r, short: SHORT_LABELS[r.key] || r.label })))
const weaningHeadline = computed(() => {
  if (!weaning.value?.has_assessment) return '暂无撤机评估'
  if (weaningFails.value.length) return `暂不满足 SBT 条件（${weaningFails.value.length} 项未达标）`
  if (weaningCount.value.na) return `已采集项均达标，另有 ${weaningCount.value.na} 项未采集`
  return '筛查达标，可考虑 SBT'
})
const weaningTone = computed(() => {
  if (errors.weaning || !weaning.value?.has_assessment) return 'muted'
  return weaningFails.value.length ? 'critical' : weaningCount.value.na ? 'warn' : 'ok'
})
const bundleCount = computed(() => {
  const rows = bundleRows.value.filter((r) => r.applicabilityKey !== 'not_applicable')
  return { done: rows.filter((r) => r.stepTone === 'done').length, total: rows.length }
})
const bundleDonePct = computed(() => (bundleCount.value.total ? Math.round((bundleCount.value.done / bundleCount.value.total) * 100) : 0))
const bundleTodo = computed(() => bundleRows.value.filter((r) => r.stepTone === 'todo' && r.applicabilityKey !== 'not_applicable').map((r) => ({ ...r, short: ELEMENT_SHORT[r.key] || r.label })))
const sepsisHeadline = computed(() => {
  const s = sepsis.value
  if (!s) return ''
  const r1 = toNum(s.remaining_seconds_to_1h)
  if (r1 !== null && r1 >= 0 && bundleTodo.value.length) return `1h 内还剩 ${Math.round(r1 / 60)} 分钟`
  if (r1 !== null && r1 < 0 && bundleTodo.value.length) return `1h 已超时 ${Math.round(-r1 / 60)} 分钟`
  if (!bundleTodo.value.length) return '集束要素已完成'
  return remainText(s.remaining_seconds_to_3h) || '计时中'
})
const sepsisTone = computed(() => {
  const s = sepsis.value
  if (errors.sepsis || !s || s.status === 'none') return 'muted'
  const r1 = toNum(s.remaining_seconds_to_1h)
  if (!bundleTodo.value.length) return 'ok'
  if (r1 !== null && r1 < 15 * 60) return 'critical'
  return 'warn'
})

function errText(e: any, fallback: string) {
  const status = e?.response?.status
  if (status === 401) return '登录状态已失效，请重新登录'
  if (status === 403) return '当前账号无权访问该患者数据'
  return e?.response?.data?.detail || e?.response?.data?.message || e?.message || fallback
}

async function loadAll() {
  if (!patientId.value) return
  loading.value = true
  errors.weaning = ''
  errors.sepsis = ''
  const [w, s, b] = await Promise.allSettled([
    getPatientWeaningStatus(patientId.value),
    getPatientSbtRecords(patientId.value, 5),
    getPatientSepsisBundleStatus(patientId.value),
  ])
  if (w.status === 'fulfilled' && (w.value as any)?.data?.code === 0) {
    weaningStatus.value = (w.value as any).data.status || null
  } else {
    weaningStatus.value = null
    errors.weaning = w.status === 'rejected' ? errText(w.reason, '撤机评估加载失败') : ((w.value as any)?.data?.message || '撤机评估加载失败')
  }
  sbtRecords.value = s.status === 'fulfilled' ? ((s.value as any)?.data?.records || []) : []
  if (b.status === 'fulfilled' && (b.value as any)?.data?.code === 0) {
    sepsis.value = (b.value as any).data.status || null
  } else {
    sepsis.value = null
    errors.sepsis = b.status === 'rejected' ? errText(b.reason, '集束状态加载失败') : ((b.value as any)?.data?.message || '集束状态加载失败')
  }
  if (errors.weaning && errors.sepsis) sendReportError('LOAD_FAILED', errors.weaning)
  loading.value = false
}

onMounted(() => {
  sendUpdateTitle('专项决策')
  loadAll()
})
watch(patientId, (id, prev) => {
  if (id && id !== prev) loadAll()
})
</script>

<style scoped>
.decision-assistants { display: flex; flex-direction: column; gap: 12px; padding: 4px; color: #2C2C2B }
.da-summary { display: grid; grid-template-columns: 1fr 1fr; gap: 12px }
.da-sum { background: #fff; border: 1px solid #E6E5E3; border-radius: 8px; overflow: hidden; display: flex; flex-direction: column }
.da-sum__head { display: flex; align-items: center; gap: 8px; height: 38px; padding: 0 14px; background: #5392FF; color: #fff }
.da-sum__title { font-size: 14px; font-weight: 700 }
.da-sum__score { margin-left: auto; font-size: 12px; padding: 1px 8px; border-radius: 4px; background: rgba(255,255,255,.22) }
.da-sum__big { padding: 12px 14px 4px; font-size: 20px; font-weight: 700; line-height: 1.3 }
.da-sum__big--muted { color: #94A3B8 }
.da-sum--critical .da-sum__big { color: #D95C58 }
.da-sum--warn .da-sum__big { color: #C47B1A }
.da-sum--ok .da-sum__big { color: #3A9A6A }
.da-sum__counts { display: flex; flex-wrap: wrap; gap: 14px; padding: 4px 14px; font-size: 12px; color: #7D7A75 }
.da-sum__counts b { font-size: 15px; color: #2C2C2B; margin: 0 2px }
.c-fail, .da-sum__counts .c-fail b, b.c-fail { color: #D95C58 !important }
.c-pass b { color: #3A9A6A !important }
.c-na b { color: #94A3B8 !important }
.da-sum__chips { display: flex; flex-wrap: wrap; align-items: center; gap: 5px; padding: 6px 14px 0 }
.da-block .da-sum__chips { padding: 4px 0 0 }
.da-sum__label { font-size: 12px; color: #7D7A75 }
.da-sum__foot { margin-top: auto; padding: 8px 14px 10px; font-size: 12px; color: #7D7A75; border-top: 1px solid #F5F3F1; margin-top: 10px }
.da-chip { display: inline-flex; align-items: center; height: 22px; padding: 0 7px; border-radius: 4px; font-size: 12px; border: 1px solid #E2E8F0; background: #F1F5F9; color: #64748B; white-space: nowrap }
.da-chip--fail { background: #FEE2E2; color: #B91C1C; border-color: #FCA5A5; font-weight: 600 }
.da-chip--todo { background: #FEF3C7; color: #B45309; border-color: #FCD34D; font-weight: 600 }
.da-chip--na { background: #F1F5F9; color: #94A3B8 }
.da-progress { margin: 6px 14px 2px; height: 6px; border-radius: 3px; background: #EEF1F5; overflow: hidden }
.da-progress i { display: block; height: 100%; background: #5392FF }
.da-card { background: #fff; border: 1px solid #E6E5E3; border-radius: 8px; padding: 12px 14px }
.da-card__head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px }
.da-card__title { margin: 0; font-size: 14px; font-weight: 700; padding-left: 8px; border-left: 3px solid #5392FF; line-height: 1.1 }
.da-card__hint { font-size: 12px; color: #9A978F }
.da-btn { margin-left: auto; padding: 4px 12px; border: 1px solid #E6E5E3; border-radius: 6px; background: #fff; cursor: pointer; font-size: 12px; color: #4A4A48 }
.da-btn:hover { border-color: #2F6FED; color: #2F6FED }
.da-btn:disabled { opacity: .6; cursor: default }
.da-tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px }
.da-tile { position: relative; display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; border-radius: 6px; border: 1px solid #E6E5E3; background: #FAFAF9 }
.da-tile__label { font-size: 12px; color: #7D7A75; padding-right: 40px }
.da-tile__value { font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums }
.da-tile__ref { font-size: 11px; color: #9A978F; line-height: 1.35 }
.da-tile__verdict { position: absolute; top: 7px; right: 8px; font-size: 11px; font-weight: 700 }
.da-tile--fail { background: #FEF2F2; border-color: #FCA5A5 }
.da-tile--fail .da-tile__value, .da-tile--fail .da-tile__verdict { color: #D95C58 }
.da-tile--pass .da-tile__verdict { color: #3A9A6A }
.da-tile--na { opacity: .7 }
.da-tile--na .da-tile__value, .da-tile--na .da-tile__verdict { color: #94A3B8 }
.da-two { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px }
.da-block { padding: 10px 12px; border-radius: 6px; background: #F7F8FA; font-size: 13px }
.da-block--warn { background: #FFFBEB; border: 1px solid #FDE68A; color: #92400E }
.da-h4 { margin: 0 0 6px; font-size: 13px; font-weight: 700; color: #4A4A48 }
.da-factor { display: grid; grid-template-columns: 90px 1fr auto; align-items: center; gap: 8px; padding: 3px 0; font-size: 12px }
.da-factor__name { font-weight: 600 }
.da-factor__bar { height: 6px; border-radius: 3px; background: #E8EBF0; overflow: hidden }
.da-factor__bar i { display: block; height: 100%; background: #C47B1A }
.da-factor__ev { color: #7D7A75 }
.da-checks { display: flex; flex-wrap: wrap; gap: 6px }
.da-check { font-size: 12px; padding: 2px 8px 2px 22px; border-radius: 4px; background: #fff; border: 1px solid #E6E5E3; position: relative }
.da-check::before { content: ''; position: absolute; left: 7px; top: 50%; width: 9px; height: 9px; margin-top: -5px; border: 1.5px solid #94A3B8; border-radius: 2px }
.da-more { margin-top: 10px; font-size: 13px }
.da-more summary { cursor: pointer; color: #2F6FED; font-size: 12px }
.da-sepsis { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr); gap: 12px }
.da-steps { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column }
.da-step { display: grid; grid-template-columns: 24px 1fr auto; gap: 10px; align-items: center; padding: 8px 4px; border-bottom: 1px solid #F0EFED; position: relative }
.da-step__dot { width: 20px; height: 20px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; border: 2px solid #CBD5E1; color: #fff; background: #fff }
.da-step--done .da-step__dot { background: #3A9A6A; border-color: #3A9A6A }
.da-step--late .da-step__dot { background: #D95C58; border-color: #D95C58 }
.da-step--todo .da-step__dot { border-color: #C47B1A; background: #FEF3C7 }
.da-step__title { font-size: 13px; font-weight: 600 }
.da-step__sub { font-size: 12px; color: #9A978F }
.da-step__state { text-align: right; display: flex; flex-direction: column; font-size: 12px }
.da-step__state b { font-size: 12px }
.da-step--done .da-step__state b { color: #3A9A6A }
.da-step--late .da-step__state b { color: #D95C58 }
.da-step--todo .da-step__state b { color: #C47B1A }
.da-step--na .da-step__state b { color: #94A3B8 }
.da-side { display: flex; flex-direction: column; gap: 8px }
.da-kv { display: flex; gap: 8px; align-items: baseline; font-size: 13px; padding: 2px 0 }
.da-kv span { color: #7D7A75; min-width: 84px }
.da-kv em { font-style: normal; font-size: 12px; color: #9A978F }
.da-table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 6px }
.da-table th { text-align: left; font-weight: 600; color: #7D7A75; background: #F7F8FA; padding: 6px 8px }
.da-table td { padding: 6px 8px; border-bottom: 1px solid #F0EFED }
.da-mono { font-variant-numeric: tabular-nums }
.da-verdict { font-size: 11px; padding: 1px 6px; border-radius: 4px; font-weight: 600 }
.da-verdict--pass { background: #E7F6EE; color: #3A9A6A }
.da-verdict--fail { background: #FEE2E2; color: #D95C58 }
.da-verdict--na { background: #F1F5F9; color: #94A3B8 }
.da-list { margin: 6px 0; padding-left: 18px; font-size: 12px }
.da-list--warn { color: #B45309 }
.da-muted { color: #9A978F; font-size: 12px }
.da-footnote { margin: 6px 0 0; font-size: 12px; color: #9A978F; line-height: 1.6 }
.da-footnote--end { margin: 0; padding: 0 2px }
.da-error { margin: 10px 14px; padding: 8px 10px; border-radius: 6px; background: #FEF2F2; color: #B91C1C; font-size: 12px }
.da-alert { margin-top: 10px; padding: 8px 10px; border-radius: 6px; background: #FEF2F2; border: 1px solid #FCA5A5; color: #B91C1C; font-size: 13px }
@media (max-width: 1100px) { .da-summary, .da-two, .da-sepsis { grid-template-columns: 1fr } }
</style>
