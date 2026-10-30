<template>
  <div class="decision-assistants">
    <div class="da-toolbar">
      <span class="da-toolbar__hint">逐条列出每个判断用到的数据、参考阈值与结果；数值缺失的条目标为“未采集”，不参与判断</span>
      <button class="da-btn" :disabled="loading" @click="loadAll">{{ loading ? '加载中…' : '刷新' }}</button>
    </div>

    <!-- ── 撤机 / 拔管 ── -->
    <section class="da-card">
      <header class="da-card__head">
        <h3 class="da-card__title">撤机与拔管评估</h3>
        <span v-if="weaning?.has_assessment" class="da-pill" :class="`da-pill--${levelTone(weaning.risk_level)}`">
          撤机失败风险 {{ LEVEL_LABELS[String(weaning.risk_level).toLowerCase()] || weaning.risk_level }}
          <template v-if="weaning.risk_score !== null && weaning.risk_score !== undefined">（{{ weaning.risk_score }} 分）</template>
        </span>
        <span class="da-card__time">评估时间 {{ fmt(weaning?.updated_at) }}</span>
      </header>
      <div v-if="errors.weaning" class="da-error">{{ errors.weaning }}</div>
      <template v-else-if="weaning">
        <p v-if="weaning.recommendation" class="da-conclusion"><b>结论：</b>{{ weaning.recommendation }}</p>
        <p v-if="!weaning.has_assessment" class="da-muted">暂无撤机评估记录（患者可能未上机，或评估扫描尚未运行）</p>

        <h4 class="da-h4">1. 撤机筛查条件逐项核对</h4>
        <table class="da-table">
          <thead><tr><th>指标</th><th>当前值</th><th>参考标准</th><th>判断</th></tr></thead>
          <tbody>
            <tr v-for="row in weaningRows" :key="row.key">
              <td>{{ row.label }}</td>
              <td class="da-mono">{{ row.display }}</td>
              <td class="da-muted">{{ row.ref }}</td>
              <td><span class="da-verdict" :class="`da-verdict--${row.verdict}`">{{ VERDICT_LABELS[row.verdict] }}</span></td>
            </tr>
          </tbody>
        </table>
        <p class="da-footnote">系统未采集、需床旁人工核对：导致呼吸衰竭的原发病已好转；pH &gt; 7.25；体温 ≤ 38.5 ℃；无新发感染/心肌缺血；能自主触发吸气；咳痰与气道保护能力；升压药为低剂量或已停用。</p>
        <p class="da-footnote">阈值参考 AARC 2024 SBT 临床实践指南与 ACCP/ATS 2017 撤机指南的常用筛查标准（AARC 指南不建议把 RSBI 作为进入 SBT 的必需条件），科室可按本院流程调整；最终是否 SBT 由主管医生决定。</p>

        <template v-if="gateFailures.length">
          <h4 class="da-h4">2. 未通过的门控条件（系统判定）</h4>
          <ul class="da-list da-list--warn">
            <li v-for="g in gateFailures" :key="g">{{ g }}</li>
          </ul>
        </template>
        <template v-if="factors.length">
          <h4 class="da-h4">{{ gateFailures.length ? 3 : 2 }}. 影响撤机风险的因素（权重越高影响越大）</h4>
          <div class="da-factors">
            <div v-for="f in factors" :key="f.name" class="da-factor">
              <span class="da-factor__name">{{ f.name }}</span>
              <span class="da-factor__bar"><i :style="{ width: `${Math.min(100, f.weight * 25)}%` }" /></span>
              <span class="da-mono da-muted">{{ f.weight ? `权重 ${f.weight}` : '' }}</span>
              <span class="da-factor__ev">{{ f.evidence }}</span>
            </div>
          </div>
        </template>

        <h4 class="da-h4">SBT 记录</h4>
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

        <div v-if="postExtub?.has_alert" class="da-alert">
          <b>拔管后失败风险告警</b>（{{ fmt(postExtub.created_at) }}）：
          拔管后 {{ num(postExtub.hours_since_extubation, ' h') }}，RR {{ num(postExtub.rr) }}，SpO₂ {{ num(postExtub.spo2, '%') }}
        </div>
      </template>
    </section>

    <!-- ── 脓毒症 1 小时集束 ── -->
    <section class="da-card">
      <header class="da-card__head">
        <h3 class="da-card__title">脓毒症 1 小时集束化治疗</h3>
        <span v-if="sepsis" class="da-pill" :class="`da-pill--${LIGHT_TONE[sepsis.light] || 'muted'}`">{{ sepsis.label }}</span>
        <span v-if="sepsis?.bundle_started_at" class="da-card__time">计时起点 {{ fmt(sepsis.bundle_clock_anchor || sepsis.bundle_started_at) }}</span>
      </header>
      <div v-if="errors.sepsis" class="da-error">{{ errors.sepsis }}</div>
      <template v-else-if="sepsis">
        <p v-if="sepsis.status === 'none'" class="da-muted">未触发脓毒症筛查，集束未进入计时。</p>
        <template v-else>
          <div class="da-clock">
            <div><span class="da-muted">已过时间</span><b>{{ num(sepsis.elapsed_minutes, ' min') }}</b></div>
            <div><span class="da-muted">1h 截止</span><b>{{ fmt(sepsis.deadline_1h) }}</b><em :class="remainClass(sepsis.remaining_seconds_to_1h)">{{ remainText(sepsis.remaining_seconds_to_1h) }}</em></div>
            <div><span class="da-muted">3h 截止</span><b>{{ fmt(sepsis.deadline_3h) }}</b><em :class="remainClass(sepsis.remaining_seconds_to_3h)">{{ remainText(sepsis.remaining_seconds_to_3h) }}</em></div>
            <div><span class="da-muted">首剂抗生素</span><b>{{ sepsis.first_antibiotic_time ? fmt(sepsis.first_antibiotic_time) : '未给药' }}</b><em>{{ sepsis.first_antibiotic_name || '' }}</em></div>
          </div>

          <h4 class="da-h4">1. 为什么进入集束：感染判断依据</h4>
          <div class="da-evidence">
            <div>
              <span class="da-muted">判断</span>
              <b>{{ INFECTION_LABELS[sepsis.infection_verdict] || sepsis.infection_verdict || '未判定' }}</b>
              <span v-if="sepsis.infection_confidence !== null && sepsis.infection_confidence !== undefined" class="da-muted">置信度 {{ pct(sepsis.infection_confidence) }}</span>
            </div>
            <div v-if="listOf(sepsis.infection_positive_evidence).length"><span class="da-tag da-tag--pos">支持</span>{{ listOf(sepsis.infection_positive_evidence).join('；') }}</div>
            <div v-if="listOf(sepsis.infection_negative_evidence).length"><span class="da-tag da-tag--neg">反对</span>{{ listOf(sepsis.infection_negative_evidence).join('；') }}</div>
            <div v-if="listOf(sepsis.infection_missing_data).length"><span class="da-tag">缺失</span>{{ listOf(sepsis.infection_missing_data).join('；') }}</div>
            <div v-if="listOf(sepsis.source_rules).length" class="da-muted">触发规则：{{ listOf(sepsis.source_rules).join('、') }}</div>
          </div>

          <h4 class="da-h4">2. 休克 / 低灌注评估</h4>
          <div class="da-evidence">
            <div>
              疑似脓毒性休克：<b :class="sepsis.shock_suspected ? 'da-c-critical' : ''">{{ sepsis.shock_suspected ? '是' : '否' }}</b>
              · 血管活性药：<b>{{ sepsis.vasopressor_active ? '使用中' : '未使用' }}</b>
            </div>
            <div v-if="listOf(sepsis.hypoperfusion_evidence).length"><span class="da-tag da-tag--pos">低灌注证据</span>{{ listOf(sepsis.hypoperfusion_evidence).join('；') }}</div>
          </div>

          <h4 class="da-h4">3. 集束元素逐项执行情况</h4>
          <table v-if="bundleRows.length" class="da-table">
            <thead><tr><th>项目</th><th>适用性</th><th>执行状态</th><th>完成时间 / 值</th><th>触发依据</th></tr></thead>
            <tbody>
              <tr v-for="row in bundleRows" :key="row.key">
                <td>{{ row.label }}</td>
                <td class="da-muted">{{ row.applicability }}</td>
                <td><span class="da-verdict" :class="`da-verdict--${row.tone}`">{{ row.status }}</span></td>
                <td class="da-mono">{{ row.done }}</td>
                <td class="da-muted">{{ row.trigger }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="da-muted">该集束记录未包含元素明细（旧版记录）</p>

          <template v-if="listOf(sepsis.fluid_risk_factors).length || listOf(sepsis.fluid_risk_cautions).length">
            <h4 class="da-h4">4. 液体复苏个体化提示</h4>
            <ul class="da-list da-list--warn">
              <li v-for="f in listOf(sepsis.fluid_risk_factors)" :key="'f' + f">风险因素：{{ f }}</li>
              <li v-for="c in listOf(sepsis.fluid_risk_cautions)" :key="'c' + c">注意：{{ c }}</li>
            </ul>
            <p v-if="sepsis.requires_individualization" class="da-footnote">存在容量过负荷风险，30 ml/kg 晶体液需由医生确认个体化目标。</p>
          </template>
        </template>
      </template>
    </section>

    <section class="da-card da-card--muted">
      <h3 class="da-card__title">尚未接入的专项</h3>
      <p class="da-muted">镇静镇痛、抗感染降阶梯、VTE 预防、血糖控制、压疮预防等专项决策后端尚未提供结构化评估数据，接入后将按相同“指标—阈值—判断”方式展示。营养方案请使用营养支持工作台。</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useEmbedBridge } from '../../../composables/useEmbedBridge'
import { getPatientWeaningStatus, getPatientSbtRecords, getPatientSepsisBundleStatus } from '../../../api'

type Verdict = 'pass' | 'fail' | 'na'

const LEVEL_LABELS: Record<string, string> = { low: '低', medium: '中', moderate: '中', high: '高', critical: '极高', unknown: '未知' }
const VERDICT_LABELS: Record<Verdict, string> = { pass: '达标', fail: '未达标', na: '未采集' }
const LIGHT_TONE: Record<string, string> = { green: 'ok', yellow: 'warn', orange: 'warn', red: 'critical', gray: 'muted' }
const INFECTION_LABELS: Record<string, string> = { confirmed: '确认感染', suspected: '疑似感染', unlikely: '感染可能性低', unknown: '未判定', excluded: '已排除' }
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
function levelTone(level: unknown) {
  const s = String(level || '').toLowerCase()
  if (s === 'high' || s === 'critical') return 'critical'
  if (s === 'medium' || s === 'moderate') return 'warn'
  if (s === 'low') return 'ok'
  return 'muted'
}
function remainText(sec: unknown) {
  const n = toNum(sec)
  if (n === null) return ''
  const m = Math.round(Math.abs(n) / 60)
  return n >= 0 ? `剩余 ${m} 分钟` : `已超时 ${m} 分钟`
}
function remainClass(sec: unknown) {
  const n = toNum(sec)
  if (n === null) return ''
  if (n < 0) return 'da-c-critical'
  if (n < 15 * 60) return 'da-c-warn'
  return ''
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
    return {
      key,
      label: ELEMENT_LABELS[key] || key,
      applicability: APPLICABILITY_LABELS[String(el?.applicability || '')] || el?.applicability || '—',
      status,
      tone,
      done: [exec?.completed_at ? fmt(exec.completed_at) : '', value].filter(Boolean).join(' · ') || '—',
      trigger: triggers.map((t: string) => TRIGGER_LABELS[t] || t).join('、') || '—',
    }
  })
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
.decision-assistants { display: flex; flex-direction: column; gap: 16px; padding: 4px }
.da-toolbar { display: flex; align-items: center; gap: 12px }
.da-toolbar__hint { flex: 1; font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF) }
.da-btn { padding: 5px 14px; border: 1px solid var(--color-border, #E5E7EB); border-radius: var(--radius-md, 6px); background: var(--color-bg-surface, #FFFFFF); cursor: pointer; font-size: var(--text-body, 13px) }
.da-btn:disabled { opacity: .6; cursor: default }
.da-card { background: var(--color-bg-surface, #FFFFFF); border: 1px solid var(--color-border, #E5E7EB); border-radius: var(--radius-lg, 10px); padding: 14px 18px }
.da-card--muted { background: var(--color-bg-surface-secondary, #F1F4F8) }
.da-card__head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px }
.da-card__title { margin: 0; font-size: var(--text-section-title, 15px); font-weight: 600; color: var(--color-text-primary, #111827) }
.da-card__time { margin-left: auto; font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF) }
.da-pill { font-size: var(--text-caption, 12px); padding: 2px 10px; border-radius: 999px; font-weight: 600 }
.da-pill--ok { background: var(--color-normal-bg, #E7F6EF); color: var(--color-normal, #12A66A) }
.da-pill--warn { background: var(--color-warning-soft-bg, #FFF9D8); color: var(--color-warning, #B54708) }
.da-pill--critical { background: var(--color-critical-bg, #FEECEB); color: var(--color-critical, #D92D20) }
.da-pill--muted { background: var(--color-bg-inset, #E9EEF5); color: var(--color-text-secondary, #4B5563) }
.da-conclusion { margin: 0 0 8px; font-size: var(--text-body, 13px); color: var(--color-text-primary, #111827); line-height: 1.6 }
.da-h4 { margin: 14px 0 6px; font-size: var(--text-body, 13px); font-weight: 600; color: var(--color-text-secondary, #4B5563) }
.da-table { width: 100%; border-collapse: collapse; font-size: var(--text-caption, 12px) }
.da-table th { text-align: left; font-weight: 500; color: var(--color-text-tertiary, #9CA3AF); background: var(--color-bg-surface-secondary, #F1F4F8); padding: 6px 8px }
.da-table td { padding: 6px 8px; border-bottom: 1px solid var(--color-border, #E5E7EB); color: var(--color-text-primary, #111827) }
.da-mono { font-family: 'SF Mono', Consolas, monospace }
.da-muted { color: var(--color-text-tertiary, #9CA3AF); font-size: var(--text-caption, 12px) }
.da-footnote { margin: 6px 0 0; font-size: 11px; color: var(--color-text-tertiary, #9CA3AF) }
.da-verdict { font-size: 11px; padding: 1px 6px; border-radius: var(--radius-tag, 4px) }
.da-verdict--pass { background: var(--color-normal-bg, #E7F6EF); color: var(--color-normal, #12A66A) }
.da-verdict--fail { background: var(--color-critical-bg, #FEECEB); color: var(--color-critical, #D92D20) }
.da-verdict--na { background: var(--color-bg-inset, #E9EEF5); color: var(--color-text-tertiary, #9CA3AF) }
.da-list { margin: 0; padding-left: 18px; font-size: var(--text-body, 13px); line-height: 1.7 }
.da-list--warn { color: var(--color-warning, #B54708) }
.da-factors { display: flex; flex-direction: column; gap: 6px }
.da-factor { display: grid; grid-template-columns: 140px 120px 60px 1fr; gap: 8px; align-items: center; font-size: var(--text-caption, 12px) }
.da-factor__name { font-weight: 600 }
.da-factor__bar { height: 6px; background: var(--color-bg-inset, #E9EEF5); border-radius: 3px; overflow: hidden }
.da-factor__bar i { display: block; height: 100%; background: var(--color-warning, #B54708) }
.da-factor__ev { color: var(--color-text-secondary, #4B5563) }
.da-alert { margin-top: 10px; padding: 8px 12px; border-radius: var(--radius-md, 6px); background: var(--color-critical-bg, #FEECEB); color: var(--color-critical, #D92D20); font-size: var(--text-body, 13px) }
.da-error { padding: 8px 12px; border-radius: var(--radius-md, 6px); background: var(--color-critical-bg, #FEECEB); color: var(--color-critical, #D92D20); font-size: var(--text-body, 13px) }
.da-clock { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 4px 0 }
.da-clock > div { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; background: var(--color-bg-surface-secondary, #F1F4F8); border-radius: var(--radius-md, 6px) }
.da-clock b { font-size: 15px; color: var(--color-text-primary, #111827) }
.da-clock em { font-style: normal; font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563) }
.da-evidence { display: flex; flex-direction: column; gap: 4px; font-size: var(--text-body, 13px); color: var(--color-text-primary, #111827); line-height: 1.6 }
.da-tag { display: inline-block; margin-right: 6px; font-size: 11px; padding: 0 6px; border-radius: var(--radius-tag, 4px); background: var(--color-bg-inset, #E9EEF5); color: var(--color-text-secondary, #4B5563) }
.da-tag--pos { background: var(--color-critical-bg, #FEECEB); color: var(--color-critical, #D92D20) }
.da-tag--neg { background: var(--color-normal-bg, #E7F6EF); color: var(--color-normal, #12A66A) }
.da-c-critical { color: var(--color-critical, #D92D20) !important }
.da-c-warn { color: var(--color-warning, #B54708) !important }
@media (max-width: 768px) { .da-clock { grid-template-columns: repeat(2, 1fr) } .da-factor { grid-template-columns: 1fr 80px } }
</style>
