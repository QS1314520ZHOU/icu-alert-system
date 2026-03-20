<template>
  <div class="alert-list">
    <div
      v-for="a in alerts"
      :key="a._id"
      :class="['alert-row', `alert-row--${a.severity || 'warning'}`, { 'alert-row--rescue': isRescueRiskAlert(a) }]"
    >
      <div class="alert-head">
        <div class="alert-head-main">
          <div class="alert-identity">
            <span class="alert-bed">{{ a.bed || '--' }}床</span>
            <div class="alert-patient-wrap">
              <div class="alert-patient">{{ a.patient_name || '未知患者' }}</div>
              <div class="alert-time">
                <span :class="['sev-dot', `sev-${a.severity || 'warning'}`]"></span>
                {{ fmtTime(a.created_at) || '--:--' }}
              </div>
            </div>
          </div>
          <div class="alert-head-copy">
            <div class="alert-name">{{ a.name || a.rule_id || '预警' }}</div>
            <div class="alert-code">{{ formatAlertValue(a) }}</div>
          </div>
        </div>
        <div class="alert-head-side">
          <div :class="['sev-tag', `sev-tag--${a.severity || 'warning'}`]">{{ severityText(a.severity) }}</div>
          <div class="alert-rule">{{ a.rule_id || a.alert_type || '规则' }}</div>
        </div>
      </div>

      <div class="alert-main">
        <div class="alert-pills">
          <span class="meta-pill">{{ a.patient_name || '未知' }}</span>
          <span v-if="a.category" class="meta-pill">{{ labelCategory(a.category) }}</span>
          <span v-if="a.alert_type" class="meta-pill meta-pill--soft">{{ labelType(a.alert_type) }}</span>
        </div>
        <div v-if="explanationSummary(a) && !isPostExtubationAlert(a)" class="alert-summary">
          <span class="alert-summary-tag">{{ isRescueRiskAlert(a) ? '当前判断' : '核心提示' }}</span>
          <div class="alert-summary-text">{{ explanationSummary(a) }}</div>
        </div>
        <div v-if="isPostExtubationAlert(a)" class="post-extub-panel">
          <div class="post-extub-head">
            <span class="post-extub-tag">再插管风险卡</span>
            <span :class="['post-extub-pill', `post-extub-pill--${severityClass(a.severity)}`]">{{ severityText(a.severity) }}</span>
          </div>
          <div class="post-extub-main">{{ postExtubationTitle(a) }}</div>
          <div class="post-extub-chip-row">
            <span class="post-extub-chip">RR {{ postExtubationMetric(a, 'rr') }}</span>
            <span class="post-extub-chip">SpO₂ {{ postExtubationMetric(a, 'spo2', '%') }}</span>
            <span class="post-extub-chip">拔管后 {{ postExtubationHours(a) }}</span>
            <span v-if="postExtubationAccessory(a)" class="post-extub-chip post-extub-chip--warn">辅助呼吸肌动用</span>
          </div>
        </div>
        <div class="alert-body-grid">
          <div v-if="hasExplanation(a)" :class="['alert-explanation', { 'alert-explanation--rescue': isRescueRiskAlert(a) }]">
            <div v-if="isRescueRiskAlert(a)" class="alert-rescue-head">
              <span class="alert-rescue-tag">抢救期风险卡</span>
              <span class="alert-rescue-main">{{ rescuePanelTitle(a) }}</span>
            </div>
            <div class="alert-explanation-tag">{{ isRescueRiskAlert(a) ? '三段式评估' : '临床推理' }}</div>
            <div :class="['alert-explanation-grid', { 'alert-explanation-grid--rescue': isRescueRiskAlert(a) }]">
              <div
                v-if="explanationSummary(a) && isRescueRiskAlert(a)"
                :class="['alert-explanation-block', 'alert-explanation-block--summary']"
              >
                <div class="alert-explanation-label">当前判断</div>
                <div class="alert-explanation-text alert-explanation-text--summary">{{ explanationSummary(a) }}</div>
              </div>
              <div v-if="explanationEvidence(a).length" :class="['alert-explanation-block', { 'alert-explanation-block--evidence': isRescueRiskAlert(a) }]">
                <div class="alert-explanation-label">{{ isRescueRiskAlert(a) ? '主要依据' : '证据' }}</div>
                <div v-if="isRescueRiskAlert(a)" class="alert-rescue-evidence-row">
                  <span
                    v-for="(ev, idx) in rescueEvidenceChips(a)"
                    :key="`ev-chip-${a._id || idx}-${idx}`"
                    class="alert-rescue-evidence-chip"
                  >
                    {{ ev }}
                  </span>
                </div>
                <ul v-else class="alert-explanation-list">
                  <li v-for="(ev, idx) in explanationEvidence(a)" :key="`ev-${a._id || idx}-${idx}`">
                    {{ ev }}
                  </li>
                </ul>
              </div>
              <div v-if="explanationSuggestion(a)" :class="['alert-explanation-block', { 'alert-explanation-block--suggestion': isRescueRiskAlert(a) }]">
                <div class="alert-explanation-label">{{ isRescueRiskAlert(a) ? '处置建议' : '建议' }}</div>
                <div :class="['alert-explanation-text', { 'alert-explanation-text--suggestion': isRescueRiskAlert(a) }]">{{ explanationSuggestion(a) }}</div>
              </div>
            </div>
          </div>
          <div v-if="hasContextSnapshot(a)" :class="['alert-snapshot', { 'alert-snapshot--rescue': isRescueRiskAlert(a) }]">
            <div class="alert-snapshot-head">
              <span class="alert-snapshot-tag">{{ isRescueRiskAlert(a) ? '风险快照' : '微型快照' }}</span>
              <span class="alert-snapshot-time">{{ snapshotTime(a) }}</span>
            </div>
            <div v-if="snapshotVitals(a).length" class="alert-snapshot-row">
              <span class="alert-snapshot-label">生命体征</span>
              <div class="alert-snapshot-chip-row">
                <span v-for="(chip, idx) in snapshotVitals(a)" :key="`sv-${a._id || idx}-${idx}`" class="alert-snapshot-chip">
                  <span class="alert-snapshot-chip-label">{{ chip.label }}</span>
                  <strong class="alert-snapshot-chip-value">{{ chip.value }}</strong>
                </span>
              </div>
            </div>
            <div v-if="snapshotLabs(a).length" class="alert-snapshot-row">
              <span class="alert-snapshot-label">关键检验</span>
              <div class="alert-snapshot-chip-row">
                <span v-for="(chip, idx) in snapshotLabs(a)" :key="`sl-${a._id || idx}-${idx}`" class="alert-snapshot-chip alert-snapshot-chip--lab">
                  <span class="alert-snapshot-chip-label">{{ chip.label }}</span>
                  <strong class="alert-snapshot-chip-value">{{ chip.value }}</strong>
                </span>
              </div>
            </div>
            <div v-if="snapshotVasopressors(a).length" class="alert-snapshot-row">
              <span class="alert-snapshot-label">血管活性药</span>
              <div class="alert-snapshot-badge-row">
                <span v-for="(badge, idx) in snapshotVasopressors(a)" :key="`sp-${a._id || idx}-${idx}`" class="alert-snapshot-badge">
                  <span class="alert-snapshot-badge-name">{{ badge.drug }}</span>
                  <span class="alert-snapshot-badge-dose">{{ badge.dose }}</span>
                </span>
              </div>
            </div>
          </div>
        </div>
        <div v-if="compositeClinicalChain(a) || compositeGroups(a).length" :class="['alert-composite', { 'alert-composite--rescue': isRescueRiskAlert(a) }]">
          <div v-if="compositeClinicalChain(a)" :class="['alert-chain', { 'alert-chain--rescue': isRescueRiskAlert(a) }]">
            <div class="alert-composite-head">
              <span class="alert-composite-tag">{{ isRescueRiskAlert(a) ? '病理生理链' : '临床链' }}</span>
              <span class="alert-composite-code">{{ compositeChainLabel(compositeClinicalChain(a)?.chain_type) }}</span>
            </div>
            <div class="alert-chain-summary">{{ compositeClinicalChain(a)?.summary }}</div>
            <div v-if="compositeClinicalChain(a)?.evidence?.length" class="alert-chain-chips">
              <span
                v-for="(ev, idx) in compositeClinicalChain(a)?.evidence?.slice(0, 3) || []"
                :key="`chain-${a._id || idx}-${idx}`"
                class="alert-chain-chip"
              >
                {{ ev }}
              </span>
            </div>
          </div>
          <div v-if="compositeGroups(a).length" :class="['alert-group-row', { 'alert-group-row--rescue': isRescueRiskAlert(a) }]">
            <span
              v-for="(group, idx) in compositeGroups(a).slice(0, 3)"
              :key="`group-${a._id || idx}-${idx}`"
              :class="['alert-group-chip', `alert-group-chip--${severityClass(group.severity)}`]"
            >
              {{ compositeGroupLabel(group.group) }} · {{ group.count || 0 }}
            </span>
          </div>
        </div>
        <div class="alert-meta-bar">
          <div class="alert-meta">监护事件 · {{ a.rule_id || a.alert_type || '规则' }}</div>
          <div class="alert-meta alert-meta--dim">{{ a.category ? labelCategory(a.category) : '综合监测' }}</div>
        </div>
      </div>
    </div>
    <div v-if="!alerts.length" class="alert-empty">
      <div class="alert-empty-title">当前无实时预警</div>
      <div class="alert-empty-copy">预警流为空时，这里会自动展示最新床位风险。</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import dayjs from 'dayjs'
import { formatCompositeChainLabel, formatCompositeGroupLabel } from '../../utils/displayLabels'

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
      evidence: Array.isArray(exp.evidence) ? exp.evidence.map((x: any) => (x != null && typeof x === 'object' ? JSON.stringify(x) : String(x || '')).trim()).filter(Boolean) : [],
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

function isRescueRiskAlert(alert: any) {
  const sev = severityClass(alert?.severity)
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
  return rescueKeywords.some((key) => haystack.includes(key)) || hasContextSnapshot(alert) || !!compositeClinicalChain(alert)
}

function isPostExtubationAlert(alert: any) {
  const alertType = String(alert?.alert_type || '').toLowerCase()
  const ruleId = String(alert?.rule_id || '').toLowerCase()
  return alertType.includes('post_extubation') || ruleId.includes('post_extubation')
}

function rescuePanelTitle(alert: any) {
  const haystack = `${String(alert?.alert_type || '').toLowerCase()} ${String(alert?.rule_id || '').toLowerCase()}`
  if (haystack.includes('cardiac_arrest')) return '心脏骤停前高风险'
  if (haystack.includes('shock') || haystack.includes('sepsis') || haystack.includes('septic')) return '循环衰竭 / 脓毒症抢救风险'
  if (haystack.includes('pe_') || haystack.includes('embol')) return '急性肺栓塞高风险'
  if (haystack.includes('bleed')) return '活动性出血风险'
  if (haystack.includes('post_extubation')) return '拔管后再插管高风险'
  if (haystack.includes('resp') || haystack.includes('hypoxia')) return '呼吸衰竭风险'
  return String(alert?.name || alert?.rule_id || '抢救期预警')
}

function postExtubationExtra(alert: any) {
  return alert?.extra && typeof alert.extra === 'object' ? alert.extra : {}
}

function postExtubationMetric(alert: any, key: string, suffix = '') {
  const value = postExtubationExtra(alert)?.[key]
  if (value == null || value === '') return '—'
  const num = Number(value)
  if (!Number.isFinite(num)) return `${value}${suffix}`
  const text = Math.abs(num - Math.round(num)) < 0.05 ? String(Math.round(num)) : num.toFixed(1)
  return `${text}${suffix}`
}

function postExtubationHours(alert: any) {
  const value = postExtubationExtra(alert)?.hours_since_extubation
  if (value == null || value === '') return '—'
  const num = Number(value)
  if (!Number.isFinite(num)) return String(value)
  if (num < 1) return `${Math.max(1, Math.round(num * 60))}min`
  return `${num.toFixed(num >= 10 ? 0 : 1)}h`
}

function postExtubationAccessory(alert: any) {
  return !!postExtubationExtra(alert)?.accessory_muscle_use
}

function postExtubationTitle(alert: any) {
  const rr = postExtubationMetric(alert, 'rr')
  const spo2 = postExtubationMetric(alert, 'spo2', '%')
  const hours = postExtubationHours(alert)
  return `拔管后 ${hours} 出现呼吸恶化信号 · RR ${rr} / SpO₂ ${spo2}`
}

function rescueEvidenceChips(alert: any) {
  const evidence = explanationEvidence(alert)
  if (evidence.length) return evidence.slice(0, 3)
  const chainEvidence = compositeClinicalChain(alert)?.evidence
  if (Array.isArray(chainEvidence) && chainEvidence.length) {
    return chainEvidence.map((x: any) => String(x || '').trim()).filter(Boolean).slice(0, 3)
  }
  return []
}

function compositeExtra(alert: any) {
  return alert?.extra && typeof alert.extra === 'object' ? alert.extra : {}
}

function compositeClinicalChain(alert: any) {
  const chain = compositeExtra(alert)?.clinical_chain
  return chain && typeof chain === 'object' ? chain : null
}

function compositeGroups(alert: any) {
  const rows = compositeExtra(alert)?.aggregated_groups
  return Array.isArray(rows) ? rows.filter((x: any) => x && typeof x === 'object') : []
}

function compositeGroupLabel(raw: any) {
  return formatCompositeGroupLabel(raw)
}

function compositeChainLabel(raw: any) {
  return formatCompositeChainLabel(raw)
}

function severityClass(raw: any) {
  const s = String(raw || '').toLowerCase()
  if (s === 'critical' || s.includes('crit')) return 'critical'
  if (s === 'high' || s.includes('high')) return 'high'
  return 'warning'
}

function contextSnapshot(alert: any) {
  const ctx = compositeExtra(alert)?.context_snapshot
  return ctx && typeof ctx === 'object' ? ctx : null
}

function hasContextSnapshot(alert: any) {
  return snapshotVitals(alert).length > 0 || snapshotLabs(alert).length > 0 || snapshotVasopressors(alert).length > 0
}

function snapshotValue(entry: any, digits = 0) {
  let current = entry
  let raw = entry?.value
  let unit = String(entry?.unit || '').trim()

  // Some snapshot payloads may wrap the actual lab payload in an extra { value } layer.
  while (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    current = raw
    raw = raw?.value
    if (!unit) unit = String(current?.unit || '').trim()
  }

  if (raw == null || raw === '') return ''
  const num = Number(raw)
  if (Number.isFinite(num)) {
    const valueText = digits > 0 ? num.toFixed(digits) : (Math.abs(num - Math.round(num)) < 0.05 ? String(Math.round(num)) : num.toFixed(1))
    return unit ? `${valueText}${unit}` : valueText
  }
  return unit ? `${raw}${unit}` : String(raw)
}

function snapshotVitals(alert: any) {
  const vitals = contextSnapshot(alert)?.vitals || {}
  const defs = [
    { key: 'hr', label: 'HR', digits: 0 },
    { key: 'rr', label: 'RR', digits: 0 },
    { key: 'map', label: 'MAP', digits: 0 },
    { key: 'spo2', label: 'SpO₂', digits: 0 },
    { key: 'temp', label: 'T', digits: 1 },
  ]
  return defs.map((def) => {
    const value = snapshotValue(vitals?.[def.key], def.digits)
    return value ? { label: def.label, value } : null
  }).filter(Boolean) as Array<{ label: string; value: string }>
}

function snapshotLabs(alert: any) {
  const labs = contextSnapshot(alert)?.labs || {}
  const defs = [
    { key: 'lac', label: 'Lac', digits: 1 },
    { key: 'cr', label: 'Cr', digits: 0 },
    { key: 'pct', label: 'PCT', digits: 2 },
  ]
  return defs.map((def) => {
    const value = snapshotValue(labs?.[def.key], def.digits)
    return value ? { label: def.label, value } : null
  }).filter(Boolean) as Array<{ label: string; value: string }>
}

function snapshotVasopressors(alert: any) {
  const rows = contextSnapshot(alert)?.vasopressors
  if (!Array.isArray(rows)) return []
  return rows.map((row: any) => {
    const drug = String(row?.drug || row?.raw_name || '').trim()
    if (!drug) return null
    return {
      drug,
      dose: String(row?.dose_display || row?.route || '在用').trim(),
    }
  }).filter(Boolean) as Array<{ drug: string; dose: string }>
}

function snapshotTime(alert: any) {
  return fmtTime(contextSnapshot(alert)?.snapshot_time) || '时间未知'
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
  if (t === 'glucose_recheck_reminder') return (extra?.hours_since_last_check ?? v) != null ? `${extra?.hours_since_last_check ?? v}h后复查` : '—'

  if (t === 'hyperglycemia_no_insulin') {
    const c = extra?.consecutive_high_count
    const lv = extra?.latest_glucose ?? v
    if (c != null && lv != null) return `${c}x>${extra?.high_threshold_mmol || 10},${lv}`
    return lv != null ? `Glu=${lv}` : '—'
  }

  if (t === 'abx_timeout') return (extra?.broad_duration_hours ?? v) != null ? `${extra?.broad_duration_hours ?? v}h广谱用药` : '—'
  if (t === 'abx_stop_recommendation') return (extra?.pct_latest ?? v) != null ? `PCT=${extra?.pct_latest ?? v}` : '—'
  if (t === 'abx_tdm_reminder') return extra?.drug_group || p ? `${extra?.drug_group || p} 治疗药物监测` : '治疗药物监测'
  if (t === 'abx_duration_exceeded') return (extra?.course_duration_days ?? v) != null ? `${extra?.course_duration_days ?? v}天未见培养` : '—'
  if (t === 'af_afl_new_onset') return (extra?.hr_peak_in_segment ?? v) != null ? `房颤/房扑 HR${extra?.hr_peak_in_segment ?? v}` : '房颤/房扑'

  if (t === 'brady_hypotension') {
    const hr = extra?.latest_hr ?? v
    const d = extra?.drop_sbp
    if (hr != null && d != null) return `HR${hr},SBP↓${d}`
    return hr != null ? `HR${hr}` : '心动过缓+血压异常'
  }

  if (t === 'qtc_prolonged') return (extra?.qtc_ms ?? v) != null ? `QTc${extra?.qtc_ms ?? v}` : 'QTc偏高'
  if (t === 'opioid_high_dose_resp_risk') return (extra?.opioid_med_24h_mg ?? v) != null ? `MED=${extra?.opioid_med_24h_mg ?? v}mg` : '阿片剂量偏高'

  if (t === 'opioid_respiratory_depression') {
    const rr = extra?.rr
    const spo2 = extra?.latest_spo2
    if (rr != null && spo2 != null) return `RR${rr}/SpO₂${spo2}`
    if (rr != null) return `RR${rr}`
    if (spo2 != null) return `SpO₂${spo2}`
    return '呼吸风险'
  }

  if (t === 'opioid_withdrawal_risk') return (extra?.since_last_opioid_hours ?? v) != null ? `停药 ${extra?.since_last_opioid_hours ?? v}h` : '戒断风险'
  if (t === 'vte_prophylaxis_omission') return (extra?.padua_score ?? v) != null ? `Padua=${extra?.padua_score ?? v}` : '—'
  if (t === 'vte_bleeding_linkage') return (extra?.padua_score ?? v) != null ? `Padua=${extra?.padua_score ?? v}, 机械预防` : '仅机械预防'
  if (t === 'vte_immobility_no_prophylaxis') return (extra?.immobility_hours ?? v) != null ? `卧床 ${extra?.immobility_hours ?? v}h` : '—'
  if (t === 'nutrition_start_delay') return (extra?.icu_stay_hours ?? v) != null ? `ICU ${extra?.icu_stay_hours ?? v}h 未启EN/PN` : '未启EN/PN'
  if (t === 'nutrition_calorie_not_reached') return (extra?.coverage_percent ?? v) != null ? `热卡达标 ${extra?.coverage_percent ?? v}%` : '热卡不足'
  if (t === 'nutrition_feeding_intolerance') return (extra?.latest_grv_ml ?? v) != null ? `GRV=${extra?.latest_grv_ml ?? v}mL` : '喂养不耐受'

  if (t === 'nutrition_refeeding_risk') {
    const items = extra?.triggered_electrolytes
    if (Array.isArray(items) && items.length > 0) return `Drop:${items.join('/')}`
    return v != null ? `下降=${v}%` : '再喂养风险'
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
  if (p && unitMap[p]) {
    if (v == null) return '—'
    const vs = typeof v === 'object' ? JSON.stringify(v) : String(v)
    return `${vs}${unitMap[p]}`
  }
  if (v == null) return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

function severityText(v: any) {
  const map: Record<string, string> = {
    warning: '关注',
    high: '高危',
    critical: '危急',
    normal: '平稳',
  }
  return map[String(v || 'warning')] || '关注'
}
</script>

<style scoped>
.alert-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: calc(100vh - 210px);
  overflow: auto;
  padding-right: 4px;
}
.alert-row {
  position: relative;
  display: grid;
  gap: 10px;
  padding: 12px;
  border-radius: 16px;
  background:
    radial-gradient(circle at top right, rgba(56, 189, 248, 0.14), rgba(56, 189, 248, 0) 28%),
    linear-gradient(180deg, rgba(8, 23, 38, 0.96) 0%, rgba(4, 12, 22, 0.98) 100%);
  border: 1px solid rgba(94, 234, 212, 0.08);
  box-shadow:
    inset 0 1px 0 rgba(145, 228, 255, 0.05),
    0 18px 32px rgba(0, 0, 0, 0.22);
}
.alert-row::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 4px;
  border-radius: 16px 0 0 16px;
  background: rgba(245, 158, 11, 0.7);
}
.alert-row--critical {
  border-color: rgba(251, 90, 122, 0.24);
}
.alert-row--critical::before {
  background: linear-gradient(180deg, #fb5a7a 0%, #be123c 100%);
}
.alert-row--high {
  border-color: rgba(249, 115, 22, 0.22);
}
.alert-row--high::before {
  background: linear-gradient(180deg, #fb923c 0%, #ea580c 100%);
}
.alert-row--warning {
  border-color: rgba(245, 158, 11, 0.2);
}
.alert-row--warning::before {
  background: linear-gradient(180deg, #fbbf24 0%, #f59e0b 100%);
}
.alert-row--rescue {
  background:
    radial-gradient(circle at top right, rgba(251, 113, 133, 0.16), rgba(251, 113, 133, 0) 28%),
    linear-gradient(180deg, rgba(15, 22, 37, 0.98) 0%, rgba(5, 11, 21, 0.99) 100%);
}
.alert-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: start;
}
.alert-head-main {
  display: grid;
  gap: 8px;
  min-width: 0;
}
.alert-identity {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.alert-bed {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 54px;
  height: 54px;
  padding: 0 10px;
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(15, 49, 73, 0.98) 0%, rgba(8, 29, 45, 0.98) 100%);
  border: 1px solid rgba(125, 211, 252, 0.18);
  color: #ecfeff;
  font-size: 18px;
  font-weight: 800;
  letter-spacing: 0.04em;
  font-family: 'Rajdhani', 'JetBrains Mono', monospace;
}
.alert-patient-wrap {
  display: grid;
  gap: 4px;
  min-width: 0;
}
.alert-patient {
  color: #f0fdff;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.2;
}
.alert-head-copy {
  display: grid;
  gap: 6px;
  min-width: 0;
}
.alert-time {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  width: fit-content;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(8, 31, 46, 0.82);
  border: 1px solid rgba(80, 199, 255, 0.1);
  font-size: 10px;
  color: #73cde0;
  letter-spacing: .08em;
}
.alert-main {
  min-width: 0;
  display: grid;
  gap: 8px;
}
.alert-head-side {
  display: grid;
  justify-items: end;
  gap: 8px;
}
.alert-name {
  font-size: 13px;
  color: #ecfeff;
  font-weight: 700;
  letter-spacing: .04em;
  line-height: 1.35;
}
.alert-code {
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  font-weight: 700;
  color: #8df5da;
  white-space: nowrap;
}
.alert-rule {
  color: #7ab8ca;
  font-size: 10px;
  line-height: 1.2;
  max-width: 140px;
  text-align: right;
  word-break: break-word;
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
  border: 1px solid rgba(80, 199, 255, 0.12);
  color: #8fd4e6;
  font-size: 10px;
}
.meta-pill--soft {
  color: #bfd8f1;
}
.alert-summary {
  display: grid;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(80, 199, 255, 0.12);
  background: linear-gradient(180deg, rgba(6, 30, 44, 0.96) 0%, rgba(5, 22, 36, 0.94) 100%);
}
.alert-summary-tag {
  color: #74e5f7;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: .08em;
}
.alert-summary-text {
  color: #ecfeff;
  font-size: 12px;
  line-height: 1.55;
  font-weight: 600;
}
.alert-meta {
  font-size: 10px;
  color: #6ea9bc;
  line-height: 1.35;
  letter-spacing: .08em;
}
.alert-meta--dim {
  color: #4d8aa0;
}
.alert-meta-bar {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  padding-top: 2px;
}
.alert-body-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, .95fr);
  gap: 8px;
}
.post-extub-panel {
  display: grid;
  gap: 6px;
  padding: 10px 11px;
  border-radius: 12px;
  border: 1px solid rgba(251, 113, 133, 0.16);
  background: linear-gradient(180deg, rgba(55, 16, 28, 0.54) 0%, rgba(18, 17, 30, 0.78) 100%);
}
.post-extub-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}
.post-extub-tag {
  display: inline-flex;
  align-items: center;
  min-height: 18px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(74, 19, 31, 0.86);
  border: 1px solid rgba(251, 113, 133, 0.18);
  color: #fda4af;
  font-size: 9px;
  letter-spacing: .06em;
}
.post-extub-pill {
  display: inline-flex;
  align-items: center;
  min-height: 18px;
  padding: 0 8px;
  border-radius: 999px;
  border: 1px solid transparent;
  font-size: 9px;
  font-weight: 700;
}
.post-extub-pill--warning { color: #fcd34d; background: #3f2d07; border-color: #6a4b0d; }
.post-extub-pill--high { color: #fdba74; background: #41210b; border-color: #7c3816; }
.post-extub-pill--critical { color: #fda4af; background: #47131d; border-color: #7f1d32; }
.post-extub-main {
  color: #fff1f3;
  font-size: 12px;
  line-height: 1.45;
  font-weight: 700;
}
.post-extub-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.post-extub-chip {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  border: 1px solid rgba(96, 165, 250, 0.18);
  background: rgba(12, 31, 50, 0.9);
  color: #e8f5ff;
  font-size: 10px;
}
.post-extub-chip--warn {
  border-color: rgba(251, 146, 60, 0.2);
  background: rgba(72, 30, 11, 0.76);
  color: #ffd8b4;
}
.alert-explanation {
  display: grid;
  gap: 6px;
  padding: 10px 11px;
  border-radius: 12px;
  border: 1px solid rgba(80, 199, 255, 0.12);
  background: linear-gradient(180deg, rgba(6, 23, 37, 0.92) 0%, rgba(5, 18, 30, 0.94) 100%);
}
.alert-explanation--rescue {
  border-color: rgba(251, 113, 133, 0.16);
  background: linear-gradient(180deg, rgba(54, 16, 28, 0.26) 0%, rgba(9, 23, 38, 0.94) 24%, rgba(5, 18, 30, 0.96) 100%);
}
.alert-rescue-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  padding-bottom: 6px;
  border-bottom: 1px solid rgba(251, 113, 133, 0.12);
}
.alert-rescue-tag {
  display: inline-flex;
  align-items: center;
  min-height: 18px;
  padding: 0 7px;
  border-radius: 999px;
  background: rgba(74, 19, 31, 0.86);
  border: 1px solid rgba(251, 113, 133, 0.18);
  color: #fda4af;
  font-size: 9px;
  letter-spacing: .06em;
}
.alert-rescue-main {
  color: #ffe4ea;
  font-size: 10px;
  font-weight: 700;
}
.alert-explanation-tag {
  color: #67dff2;
  font-size: 9px;
  letter-spacing: .08em;
}
.alert-explanation-grid {
  display: grid;
  gap: 6px;
}
.alert-explanation-grid--rescue {
  gap: 8px;
}
.alert-explanation-block {
  padding: 7px 8px;
  border-radius: 8px;
  border: 1px solid rgba(80, 199, 255, 0.08);
  background: rgba(8, 27, 42, 0.62);
}
.alert-explanation-block--summary {
  background: linear-gradient(180deg, rgba(59, 17, 30, 0.72) 0%, rgba(24, 20, 34, 0.78) 100%);
  border-color: rgba(251, 113, 133, 0.18);
}
.alert-explanation-block--suggestion {
  background: linear-gradient(180deg, rgba(8, 38, 30, 0.7) 0%, rgba(6, 27, 22, 0.82) 100%);
  border-color: rgba(55, 199, 147, 0.16);
}
.alert-explanation-label {
  margin-bottom: 3px;
  color: #93ebff;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: .06em;
}
.alert-explanation-text {
  color: #d9ebff;
  font-size: 10px;
  line-height: 1.5;
  word-break: break-word;
}
.alert-explanation-text--summary {
  color: #fff1f3;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.5;
}
.alert-explanation-text--suggestion {
  color: #baf2cb;
  font-weight: 600;
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
.alert-rescue-evidence-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.alert-rescue-evidence-chip {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  border: 1px solid rgba(96, 165, 250, 0.18);
  background: rgba(12, 31, 50, 0.9);
  color: #e8f5ff;
  font-size: 10px;
}
.alert-snapshot {
  display: grid;
  gap: 6px;
  padding: 10px 11px;
  border-radius: 12px;
  border: 1px solid rgba(80, 199, 255, 0.12);
  background: linear-gradient(180deg, rgba(7, 24, 39, 0.88) 0%, rgba(7, 18, 30, 0.94) 100%);
}
.alert-snapshot--rescue {
  border-color: rgba(96, 165, 250, 0.18);
  background: linear-gradient(180deg, rgba(9, 29, 46, 0.94) 0%, rgba(7, 19, 34, 0.96) 100%);
}
.alert-snapshot-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.alert-snapshot-tag {
  color: #72e4f7;
  font-size: 9px;
  letter-spacing: .06em;
}
.alert-snapshot-time {
  color: #83abc4;
  font-size: 9px;
}
.alert-snapshot-row {
  display: grid;
  grid-template-columns: 44px 1fr;
  gap: 8px;
  align-items: flex-start;
}
.alert-snapshot-label {
  color: #8ed8ee;
  font-size: 9px;
  letter-spacing: .04em;
  padding-top: 4px;
}
.alert-snapshot-chip-row,
.alert-snapshot-badge-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.alert-snapshot-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  border: 1px solid rgba(80, 199, 255, 0.12);
  background: rgba(11, 35, 54, 0.84);
}
.alert-snapshot-chip--lab {
  border-color: rgba(96, 165, 250, 0.18);
  background: rgba(12, 31, 50, 0.9);
}
.alert-snapshot-chip-label {
  color: #84bfd7;
  font-size: 9px;
}
.alert-snapshot-chip-value {
  color: #effbff;
  font-size: 10px;
  font-family: 'Rajdhani', 'JetBrains Mono', monospace;
  font-weight: 700;
}
.alert-snapshot-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  border: 1px solid rgba(245, 158, 11, 0.2);
  background: rgba(51, 27, 7, 0.66);
}
.alert-snapshot-badge-name {
  color: #fde68a;
  font-size: 10px;
  font-weight: 700;
}
.alert-snapshot-badge-dose {
  color: #ffe9b2;
  font-size: 10px;
  font-family: 'Rajdhani', 'JetBrains Mono', monospace;
}
.alert-composite {
  display: grid;
  gap: 6px;
}
.alert-composite--rescue {
  gap: 8px;
}
.alert-chain {
  padding: 10px 11px;
  border-radius: 12px;
  border: 1px solid rgba(80, 199, 255, 0.12);
  background: linear-gradient(180deg, rgba(7, 24, 39, 0.86) 0%, rgba(7, 18, 30, 0.92) 100%);
}
.alert-chain--rescue {
  border-color: rgba(56, 189, 248, 0.16);
  background: linear-gradient(180deg, rgba(11, 31, 49, 0.94) 0%, rgba(6, 21, 36, 0.96) 100%);
}
.alert-composite-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}
.alert-composite-tag {
  color: #72e4f7;
  font-size: 9px;
  letter-spacing: .06em;
}
.alert-composite-code {
  color: #9dd8ff;
  font-size: 9px;
  padding: 2px 7px;
  border-radius: 999px;
  border: 1px solid rgba(80, 199, 255, 0.12);
  background: rgba(8, 28, 44, 0.78);
}
.alert-chain-summary {
  color: #e9fbff;
  font-size: 10px;
  line-height: 1.5;
  font-weight: 600;
}
.alert-chain-chips,
.alert-group-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 7px;
}
.alert-group-row--rescue {
  margin-top: 2px;
}
.alert-chain-chip,
.alert-group-chip {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 10px;
  border: 1px solid rgba(80, 199, 255, 0.12);
  background: rgba(11, 35, 54, 0.84);
  color: #dffbff;
}
.alert-group-chip--warning { color: #fcd34d; border-color: rgba(245, 158, 11, 0.2); }
.alert-group-chip--high { color: #fdba74; border-color: rgba(249, 115, 22, 0.24); }
.alert-group-chip--critical { color: #fda4af; border-color: rgba(244, 63, 94, 0.24); }
.sev-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 58px;
  height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .08em;
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
}
.sev-warning { background: #f59e0b; box-shadow: 0 0 6px #f59e0b88; }
.sev-high { background: #f97316; box-shadow: 0 0 6px #f9731688; }
.sev-critical { background: #fb5a7a; box-shadow: 0 0 8px rgba(251, 90, 122, 0.65); }
.sev-normal { background: #22c55e; box-shadow: 0 0 6px rgba(34, 197, 94, 0.5); }
.alert-empty {
  display: grid;
  place-items: center;
  gap: 8px;
  min-height: 180px;
  border-radius: 16px;
  border: 1px dashed rgba(80, 199, 255, 0.16);
  background: linear-gradient(180deg, rgba(7, 23, 37, 0.72) 0%, rgba(4, 13, 24, 0.9) 100%);
  color: #96dcee;
}
.alert-empty-title {
  font-size: 16px;
  font-weight: 700;
  color: #e8fbff;
}
.alert-empty-copy {
  font-size: 12px;
  color: #6fbfd6;
}
@media (max-width: 1100px) {
  .alert-list {
    max-height: none;
  }
  .alert-body-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 640px) {
  .alert-head {
    grid-template-columns: 1fr;
  }
  .alert-identity {
    flex-direction: column;
    align-items: flex-start;
  }
  .alert-bed {
    min-width: 48px;
    height: 48px;
    font-size: 16px;
  }
  .alert-patient {
    font-size: 14px;
  }
  .alert-head-side {
    justify-items: start;
  }
  .alert-code {
    white-space: normal;
  }
  .alert-snapshot-row {
    grid-template-columns: 1fr;
    gap: 4px;
  }
  .alert-snapshot-label {
    padding-top: 0;
  }
}
</style>





