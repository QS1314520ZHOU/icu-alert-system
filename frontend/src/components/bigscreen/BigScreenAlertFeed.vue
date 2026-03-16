<template>
  <div class="alert-list">
    <div v-for="a in alerts" :key="a._id" :class="['alert-row', `alert-row--${a.severity || 'warning'}`]">
      <div class="alert-rail">
        <span :class="['sev-dot', `sev-${a.severity || 'warning'}`]"></span>
        <span class="alert-time">{{ fmtTime(a.created_at) || '--:--' }}</span>
      </div>
      <div class="alert-main">
        <div class="alert-top">
          <div class="alert-name">{{ a.name || a.rule_id || '预警' }}</div>
          <div class="alert-code">{{ formatAlertValue(a) }}</div>
        </div>
        <div class="alert-pills">
          <span class="meta-pill meta-pill--bed">{{ a.bed || '--' }}床</span>
          <span class="meta-pill">{{ a.patient_name || '未知' }}</span>
          <span v-if="a.category" class="meta-pill">{{ labelCategory(a.category) }}</span>
          <span v-if="a.alert_type" class="meta-pill meta-pill--soft">{{ labelType(a.alert_type) }}</span>
        </div>
        <div v-if="hasExplanation(a)" class="alert-explanation">
          <div class="alert-explanation-tag">CLINICAL REASONING</div>
          <div class="alert-explanation-grid">
            <div v-if="explanationSummary(a)" class="alert-explanation-block">
              <div class="alert-explanation-label">Summary</div>
              <div class="alert-explanation-text">{{ explanationSummary(a) }}</div>
            </div>
            <div v-if="explanationEvidence(a).length" class="alert-explanation-block">
              <div class="alert-explanation-label">Evidence</div>
              <ul class="alert-explanation-list">
                <li v-for="(ev, idx) in explanationEvidence(a)" :key="`ev-${a._id || idx}-${idx}`">
                  {{ ev }}
                </li>
              </ul>
            </div>
            <div v-if="explanationSuggestion(a)" class="alert-explanation-block">
              <div class="alert-explanation-label">Suggestion</div>
              <div class="alert-explanation-text">{{ explanationSuggestion(a) }}</div>
            </div>
          </div>
        </div>
        <div class="alert-meta">
          MONITOR EVENT · {{ a.rule_id || a.alert_type || 'RULE' }}
        </div>
      </div>
      <div class="alert-side">
        <div :class="['sev-tag', `sev-tag--${a.severity || 'warning'}`]">{{ severityText(a.severity) }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import dayjs from 'dayjs'

defineProps<{
  alerts: any[]
}>()

function fmtTime(t: any) {
  if (!t) return ''
  try { return dayjs(t).format('HH:mm') } catch { return '' }
}

function explanationPayload(alert: any) {
  const exp = alert?.explanation
  if (typeof exp === 'string') {
    return {
      summary: exp,
      evidence: [] as string[],
      suggestion: '',
    }
  }
  if (exp && typeof exp === 'object') {
    return {
      summary: typeof exp.summary === 'string' ? exp.summary : (typeof exp.text === 'string' ? exp.text : ''),
      evidence: Array.isArray(exp.evidence) ? exp.evidence.filter((x: any) => String(x || '').trim()) : [],
      suggestion: typeof exp.suggestion === 'string' ? exp.suggestion : '',
    }
  }
  return {
    summary: typeof alert?.explanation_text === 'string' ? alert.explanation_text : '',
    evidence: [] as string[],
    suggestion: '',
  }
}

function hasExplanation(alert: any) {
  const p = explanationPayload(alert)
  return !!(p.summary || p.evidence.length || p.suggestion)
}

function explanationSummary(alert: any) {
  return explanationPayload(alert).summary || ''
}

function explanationEvidence(alert: any) {
  return explanationPayload(alert).evidence || []
}

function explanationSuggestion(alert: any) {
  return explanationPayload(alert).suggestion || ''
}

function labelCategory(v: any) {
  const k = String(v || '')
  const map: Record<string, string> = {
    vital_signs: '生命体征',
    lab_results: '检验',
    trend: '趋势',
    syndrome: '综合征',
    tbi: '颅脑',
    ventilator: '呼吸机',
    drug_safety: '药物安全',
    assessments: '护理评估',
    ai_analysis: 'AI',
    fluid_balance: '液体平衡',
    glycemic_control: '血糖管理',
    antibiotic_stewardship: '抗菌药管理',
    vte_prophylaxis: 'VTE预防',
    nutrition_monitor: '营养监测',
    composite_deterioration: '复合恶化',
    device_management: '装置管理',
    bundle: 'Bundle',
    hemodynamic: '血流动力学',
    crrt: 'CRRT',
    dose_adjustment: '剂量调整',
  }
  return map[k] || k
}

function labelType(v: any) {
  const k = String(v || '')
  const map: Record<string, string> = {
    pupil: '瞳孔异常',
    dic: 'DIC',
    ards: 'ARDS',
    aki: 'AKI',
    qsofa: 'qSOFA',
    sofa: 'SOFA',
    septic_shock: '脓毒性休克',
    icp: 'ICP',
    cpp: 'CPP',
    gi_bleeding: '消化道出血',
    weaning: '撤机筛查',
    hit: 'HIT',
    nephrotoxicity: '肾毒性',
    sedation: '过度镇静',
    qt_risk: 'QT风险',
    af_afl_new_onset: '新发房颤/房扑',
    brady_hypotension: '心动过缓合并低压',
    qtc_prolonged: 'QTc明显延长',
    opioid_high_dose_resp_risk: '阿片高剂量风险',
    opioid_respiratory_depression: '阿片呼吸抑制',
    opioid_withdrawal_risk: '阿片戒断风险',
    nurse_reminder: '评估超时',
    lab_threshold: '检验阈值',
    threshold: '阈值',
    trend_analysis: '趋势',
    ai_risk: 'AI风险',
    fluid_balance: '液体平衡',
    delirium_risk: '谵妄风险',
    sedation_delirium_conversion: '镇静转谵妄',
    glucose_variability: '血糖波动',
    hypoglycemia: '低血糖',
    glucose_drop_fast: '血糖快速下降',
    glucose_recheck_reminder: '血糖复查提醒',
    hyperglycemia_no_insulin: '高血糖未启胰岛素',
    abx_timeout: '抗生素time-out',
    abx_stop_recommendation: 'PCT停药评估',
    abx_tdm_reminder: '抗生素TDM提醒',
    abx_duration_exceeded: '抗生素疗程超限',
    vte_prophylaxis_omission: 'VTE预防遗漏',
    vte_bleeding_linkage: 'VTE出血风险联动',
    vte_immobility_no_prophylaxis: '制动无VTE预防',
    nutrition_start_delay: '营养启动延迟',
    nutrition_calorie_not_reached: '热卡未达标',
    nutrition_feeding_intolerance: '喂养不耐受',
    nutrition_refeeding_risk: '再喂养风险',
    multi_organ_deterioration_trend: '多器官恶化趋势',
    cvc_review: 'CVC评估',
    foley_review: '导尿管评估',
    ett_extubation_delay: '拔管延迟',
    liberation_bundle: 'ABCDEF Bundle',
    fluid_responsiveness: '容量反应性',
    crrt_filter_clotting: '滤器凝堵',
    crrt_citrate_ica: '枸橼酸iCa',
    crrt_heparin_act: '肝素ACT',
    crrt_dose_low: 'CRRT剂量不足',
    renal_dose_adjustment: '肾功能剂量调整',
    driving_pressure: '驱动压',
    pplat_high: '平台压',
    lung_protective_ventilation: '肺保护通气',
    mechanical_power: '机械功率',
    steroid_taper_after_vaso: '激素减停',
    steroid_long_term_taper: '长程激素减停',
    steroid_hyperglycemia: '激素相关高血糖',
  }
  return map[k] || k
}

function formatAlertValue(a: any) {
  if (!a) return '—'
  const t = String(a.alert_type || '')
  const p = String(a.parameter || '')
  const v = a.value
  const extra = a.extra || {}

  if (t === 'dic') return (extra?.score ?? v) != null ? `DIC=${extra?.score ?? v}` : '—'
  if (t === 'ards') return (v ?? extra?.pf_ratio) != null ? `P/F=${Math.round(Number(v ?? extra?.pf_ratio))}` : '—'
  if (t === 'aki') return v != null ? `AKI=${v}期` : '—'
  if (t === 'qsofa') return v != null ? `qSOFA=${v}` : '—'
  if (t === 'sofa' || t === 'septic_shock') return v != null ? `SOFA=${v}` : '—'
  if (t === 'nurse_reminder') return '—'

  if (t === 'fluid_balance') {
    const net = v ?? extra?.windows?.['24h']?.net_ml
    const pct = extra?.max_positive_pct_body_weight
    if (net != null && pct != null) return `Net=${net}mL(${pct}%)`
    if (net != null) return `Net=${net}mL`
    return '—'
  }

  if (t === 'delirium_risk') return v != null ? `Delirium=${v}` : '—'
  if (t === 'sedation_delirium_conversion') return extra?.deep_sedation_hours != null ? `RASS<-3 ${extra.deep_sedation_hours}h` : '—'
  if (t === 'glucose_variability') return (extra?.cv_percent ?? v) != null ? `CV=${extra?.cv_percent ?? v}%` : '—'
  if (t === 'hypoglycemia') return v != null ? `Glu=${v}` : '—'
  if (t === 'glucose_drop_fast') return (extra?.drop_rate_mmol_per_h ?? v) != null ? `dGlu=${extra?.drop_rate_mmol_per_h ?? v}/h` : '—'
  if (t === 'glucose_recheck_reminder') return (extra?.hours_since_last_check ?? v) != null ? `Recheck ${extra?.hours_since_last_check ?? v}h` : '—'

  if (t === 'hyperglycemia_no_insulin') {
    const c = extra?.consecutive_high_count
    const lv = extra?.latest_glucose ?? v
    if (c != null && lv != null) return `${c}x>${extra?.high_threshold_mmol || 10},${lv}`
    return lv != null ? `Glu=${lv}` : '—'
  }

  if (t === 'abx_timeout') return (extra?.broad_duration_hours ?? v) != null ? `Broad ${extra?.broad_duration_hours ?? v}h` : '—'
  if (t === 'abx_stop_recommendation') return (extra?.pct_latest ?? v) != null ? `PCT=${extra?.pct_latest ?? v}` : '—'
  if (t === 'abx_tdm_reminder') return extra?.drug_group || p ? `${extra?.drug_group || p} TDM` : 'TDM'
  if (t === 'abx_duration_exceeded') return (extra?.course_duration_days ?? v) != null ? `${extra?.course_duration_days ?? v}d no culture` : '—'
  if (t === 'af_afl_new_onset') return (extra?.hr_peak_in_segment ?? v) != null ? `AF/AFL HR${extra?.hr_peak_in_segment ?? v}` : 'AF/AFL'

  if (t === 'brady_hypotension') {
    const hr = extra?.latest_hr ?? v
    const d = extra?.drop_sbp
    if (hr != null && d != null) return `HR${hr},SBP↓${d}`
    return hr != null ? `HR${hr}` : 'Brady+BP'
  }

  if (t === 'qtc_prolonged') return (extra?.qtc_ms ?? v) != null ? `QTc${extra?.qtc_ms ?? v}` : 'QTc high'
  if (t === 'opioid_high_dose_resp_risk') return (extra?.opioid_med_24h_mg ?? v) != null ? `MED=${extra?.opioid_med_24h_mg ?? v}mg` : 'High opioid'

  if (t === 'opioid_respiratory_depression') {
    const rr = extra?.rr
    const spo2 = extra?.latest_spo2
    if (rr != null && spo2 != null) return `RR${rr}/SpO₂${spo2}`
    if (rr != null) return `RR${rr}`
    if (spo2 != null) return `SpO₂${spo2}`
    return 'Resp risk'
  }

  if (t === 'opioid_withdrawal_risk') return (extra?.since_last_opioid_hours ?? v) != null ? `Stop ${extra?.since_last_opioid_hours ?? v}h` : 'Withdrawal'
  if (t === 'vte_prophylaxis_omission') return (extra?.padua_score ?? v) != null ? `Padua=${extra?.padua_score ?? v}` : '—'
  if (t === 'vte_bleeding_linkage') return (extra?.padua_score ?? v) != null ? `Padua=${extra?.padua_score ?? v}, mech` : 'mech only'
  if (t === 'vte_immobility_no_prophylaxis') return (extra?.immobility_hours ?? v) != null ? `Bedrest ${extra?.immobility_hours ?? v}h` : '—'
  if (t === 'nutrition_start_delay') return (extra?.icu_stay_hours ?? v) != null ? `ICU ${extra?.icu_stay_hours ?? v}h no EN/PN` : 'No EN/PN'
  if (t === 'nutrition_calorie_not_reached') return (extra?.coverage_percent ?? v) != null ? `Calorie ${extra?.coverage_percent ?? v}%` : 'Calorie low'
  if (t === 'nutrition_feeding_intolerance') return (extra?.latest_grv_ml ?? v) != null ? `GRV=${extra?.latest_grv_ml ?? v}mL` : 'Intolerance'

  if (t === 'nutrition_refeeding_risk') {
    const items = extra?.triggered_electrolytes
    if (Array.isArray(items) && items.length > 0) return `Drop:${items.join('/')}`
    return v != null ? `Drop=${v}%` : 'Refeeding risk'
  }

  if (t === 'multi_organ_deterioration_trend') {
    const modi = extra?.modi ?? v
    const n = extra?.organ_count
    if (modi != null && n != null) return `MODI=${modi}/${n}sys`
    if (modi != null) return `MODI=${modi}`
    return 'MODI trend'
  }

  if (t === 'lab_threshold') {
    const unit = extra?.unit || ''
    const labelMap: Record<string, string> = {
      k: 'K⁺',
      na: 'Na⁺',
      ica: 'iCa',
      ca: 'Ca',
      lac: 'Lac',
      glu: 'Glu',
      hb: 'Hb',
      plt: 'PLT',
      cr: 'Cr',
      pct: 'PCT',
      inr: 'INR',
      pt: 'PT',
      fib: 'Fib',
      ddimer: 'D-Dimer',
      trop: 'TnI/TnT',
      bnp: 'BNP',
      bil: 'TBil',
      pao2: 'PaO₂',
    }
    const label = labelMap[p] || extra?.raw_name || ''
    if (v == null) return '—'
    return label ? `${label}=${v}${unit}` : `${v}${unit}`
  }

  const unitMap: Record<string, string> = {
    param_HR: ' bpm',
    param_PR: ' bpm',
    param_resp: ' 次/分',
    param_spo2: ' %',
    param_T: ' ℃',
    param_nibp_s: ' mmHg',
    param_nibp_d: ' mmHg',
    param_nibp_m: ' mmHg',
    param_ibp_s: ' mmHg',
    param_ibp_d: ' mmHg',
    param_ibp_m: ' mmHg',
    param_cvp: ' cmH2O',
    param_ETCO2: ' mmHg',
    icp: ' mmHg',
    cpp: ' mmHg',
  }
  if (p && unitMap[p]) return v != null ? `${v}${unitMap[p]}` : '—'
  return v ?? '—'
}

function severityText(v: any) {
  const map: Record<string, string> = {
    warning: 'WARN',
    high: 'HIGH',
    critical: 'CRIT',
    normal: 'OK',
  }
  return map[String(v || 'warning')] || 'WARN'
}
</script>

<style scoped>
.alert-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: calc(100vh - 210px);
  overflow: auto;
  padding-right: 2px;
}
.alert-row {
  display: grid;
  grid-template-columns: 54px 1fr 64px;
  gap: 10px;
  padding: 9px 10px;
  border-radius: 12px;
  background:
    radial-gradient(circle at top right, rgba(34, 211, 238, 0.08), rgba(34, 211, 238, 0) 26%),
    linear-gradient(180deg, rgba(7, 20, 34, 0.94) 0%, rgba(4, 12, 22, 0.96) 100%);
  border: 1px solid rgba(80, 199, 255, 0.12);
  box-shadow: inset 0 1px 0 rgba(145,228,255,.04);
}
.alert-row--critical {
  border-color: rgba(251,90,122,.24);
}
.alert-row--high {
  border-color: rgba(249,115,22,.22);
}
.alert-row--warning {
  border-color: rgba(245,158,11,.2);
}
.alert-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding-top: 4px;
}
.alert-time {
  font-size: 10px;
  color: #73cde0;
  letter-spacing: .08em;
  writing-mode: vertical-rl;
  transform: rotate(180deg);
}
.alert-main {
  min-width: 0;
  display: grid;
  gap: 6px;
}
.alert-top {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}
.alert-name {
  font-size: 12px;
  color: #ecfeff;
  font-weight: 700;
  letter-spacing: .04em;
  line-height: 1.35;
}
.alert-code {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  font-weight: 700;
  color: #dffbff;
  white-space: nowrap;
}
.alert-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.meta-pill {
  display: inline-flex;
  align-items: center;
  min-height: 18px;
  padding: 0 7px;
  border-radius: 999px;
  background: rgba(8, 30, 46, 0.88);
  border: 1px solid rgba(80,199,255,.12);
  color: #8fd4e6;
  font-size: 10px;
}
.meta-pill--bed {
  color: #dffbff;
}
.meta-pill--soft {
  color: #bfd8f1;
}
.alert-meta {
  font-size: 10px;
  color: #6ea9bc;
  line-height: 1.35;
  letter-spacing: .08em;
}
.alert-explanation {
  display: grid;
  gap: 6px;
  margin-top: 2px;
  padding: 8px 9px;
  border-radius: 10px;
  border: 1px solid rgba(80, 199, 255, 0.12);
  background:
    linear-gradient(180deg, rgba(6, 23, 37, 0.92) 0%, rgba(5, 18, 30, 0.94) 100%);
}
.alert-explanation-tag {
  color: #67dff2;
  font-size: 9px;
  letter-spacing: .14em;
}
.alert-explanation-grid {
  display: grid;
  gap: 6px;
}
.alert-explanation-block {
  padding: 7px 8px;
  border-radius: 8px;
  border: 1px solid rgba(80, 199, 255, 0.08);
  background: rgba(8, 27, 42, 0.62);
}
.alert-explanation-label {
  margin-bottom: 3px;
  color: #93ebff;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: .12em;
  text-transform: uppercase;
}
.alert-explanation-text {
  color: #d9ebff;
  font-size: 10px;
  line-height: 1.5;
  word-break: break-word;
}
.alert-explanation-list {
  margin: 0;
  padding-left: 14px;
  color: #d9ebff;
  font-size: 10px;
  line-height: 1.5;
}
.alert-explanation-list li + li {
  margin-top: 2px;
}
.alert-side {
  display: flex;
  justify-content: flex-end;
  align-items: flex-start;
}
.sev-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 46px;
  height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .12em;
  border: 1px solid transparent;
}
.sev-tag--warning { color: #fcd34d; background: #3f2d07; border-color: #6a4b0d; }
.sev-tag--high { color: #fdba74; background: #41210b; border-color: #7c3816; }
.sev-tag--critical { color: #fda4af; background: #47131d; border-color: #7f1d32; }
.sev-tag--normal { color: #6ee7b7; background: #10372b; border-color: #14532d; }
.sev-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 2px;
}
.sev-warning { background: #f59e0b; box-shadow: 0 0 6px #f59e0b88; }
.sev-high { background: #f97316; box-shadow: 0 0 6px #f9731688; }
.sev-critical { background: #fb5a7a; box-shadow: 0 0 8px rgba(251,90,122,.65); }
.sev-normal { background: #22c55e; box-shadow: 0 0 6px rgba(34,197,94,.5); }

@media (max-width: 1100px) {
  .alert-list {
    max-height: none;
  }
  .alert-time {
    writing-mode: initial;
    transform: none;
  }
}

@media (max-width: 640px) {
  .alert-row {
    grid-template-columns: 1fr;
    gap: 8px;
  }
  .alert-rail,
  .alert-side {
    display: flex;
    flex-direction: row;
    justify-content: space-between;
    align-items: center;
  }
  .alert-top {
    flex-direction: column;
    gap: 4px;
  }
  .alert-code {
    white-space: normal;
  }
}
</style>
